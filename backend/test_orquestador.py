"""Pruebas del ciclo fisico automatico (fase 1) sin MQTT ni Arduinos.

    cd backend
    .venv/bin/python3 -m unittest test_orquestador -v
"""

import json
import os
import tempfile
import unittest

from sqlalchemy import select

import orquestador
from models import (
    Alarma, IntentoIngreso, Manifiesto, ParqueoPlaza, PosicionPatio, Retencion,
    Transportista, Turno, Vehiculo, make_db,
)

UID_OK = "E1 69 73 15"
UID_FUERA = "E1 8E 3C 53"
UID_DESCONOCIDO = "90 C7 3D 5F"


class MaquetaBase(unittest.TestCase):
    """Base de datos temporal con patio, parqueo, 2 tarjetas y sus manifiestos."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.Session = make_db(self.db_path)
        self.enviados = []
        with self.Session() as db:
            for i in range(1, 5):
                db.add(PosicionPatio(id=i, estado="LIBRE"))
            for i in range(1, 4):
                db.add(ParqueoPlaza(id=i, ocupada=False))
            t = Transportista(nombre="Transportista Uno")
            db.add(t)
            db.flush()
            db.add(Vehiculo(uid=UID_OK, transportista_id=t.id))
            db.add(Vehiculo(uid=UID_FUERA, transportista_id=t.id))
            db.add(Manifiesto(contenedor_id="MSCU0000001", tipo_operacion="DEPOSITO", peso_declarado_g=1000,
                              transportista_id=t.id, vehiculo_uid=UID_OK,
                              estado_documental="levante_otorgado", canal="verde"))
            db.add(Manifiesto(contenedor_id="MSCU0000003", tipo_operacion="DEPOSITO", peso_declarado_g=1500,
                              transportista_id=t.id, vehiculo_uid=UID_FUERA,
                              estado_documental="levante_otorgado", canal="verde"))
            db.commit()

    def tearDown(self):
        for sufijo in ("", "-wal", "-shm"):
            if os.path.exists(self.db_path + sufijo):
                os.remove(self.db_path + sufijo)

    # ── ayudas ──
    def evento(self, topic, **datos):
        orquestador.procesar_evento(self.Session, lambda t, p: self.enviados.append(json.loads(p)),
                                    f"portus/evt/{topic}", datos)

    def comandos(self, nombre):
        return [c for c in self.enviados if c["name"] == nombre]

    def turno(self, uid):
        with self.Session() as db:
            return db.scalars(select(Turno).where(Turno.vehiculo_uid == uid).order_by(Turno.id.desc())).first()


class CicloFisicoTests(MaquetaBase):
    def test_deposito_completo_de_punta_a_punta(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        abrir = self.comandos("AbrirTalanquera")
        self.assertEqual(len(abrir), 1)
        self.assertEqual(abrir[0]["params"]["uid"], UID_OK)
        self.assertEqual(abrir[0]["params"]["op"], "DEPOSITO")
        self.assertEqual(self.turno(UID_OK).estado, "EnGarita")

        self.evento("pesaje", evento="meseta", resultado="ok", uid=UID_OK)
        t = self.turno(UID_OK)
        self.assertEqual(t.estado, "EnRuta")
        self.assertEqual(t.peso_medido_entrada_g, 1000)

        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        self.assertEqual(self.comandos("AbrirPuertaSalida")[0]["params"]["uid"], UID_OK)
        self.assertEqual(self.turno(UID_OK).estado, "EnSalida")

        self.evento("salida", evento="salida_completada", uid=UID_OK)
        t = self.turno(UID_OK)
        self.assertEqual(t.estado, "Cerrado")
        self.assertIsNotNone(t.closed_at)

    def test_tarjeta_no_registrada_se_rechaza_y_queda_el_intento(self):
        self.evento("garita", evento="rfid", uid=UID_DESCONOCIDO)
        rechazo = self.comandos("RechazarIngreso")
        self.assertEqual(rechazo[0]["params"], {"uid": UID_DESCONOCIDO, "motivo": "RFID no registr"})
        self.assertEqual(self.comandos("AbrirTalanquera"), [])
        self.assertIsNone(self.turno(UID_DESCONOCIDO))
        with self.Session() as db:
            intento = db.scalars(select(IntentoIngreso)).one()
            self.assertEqual(intento.causa, "rfid_no_registrado")

    def test_sin_levante_no_abre(self):
        with self.Session() as db:
            m = db.scalars(select(Manifiesto).where(Manifiesto.vehiculo_uid == UID_OK)).one()
            m.estado_documental = "levante_solicitado"
            db.commit()
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.assertEqual(self.comandos("RechazarIngreso")[0]["params"]["motivo"], "Sin levante")
        self.assertIsNone(self.turno(UID_OK))
        with self.Session() as db:
            self.assertEqual(db.scalars(select(IntentoIngreso)).one().contenedor_id, "MSCU0000001")

    def test_segunda_lectura_con_turno_activo_se_rechaza(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.assertEqual(len(self.comandos("AbrirTalanquera")), 1)
        self.assertEqual(self.comandos("RechazarIngreso")[0]["params"]["motivo"], "Ya tiene turno")

    def test_pesaje_fuera_de_tolerancia_genera_rt01(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", causa="RT01", uid=UID_FUERA)
        t = self.turno(UID_FUERA)
        self.assertEqual(t.estado, "Retenido")
        self.assertEqual(t.peso_medido_entrada_g, 2250)  # 1500 x 1.5 simulado
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Retencion)).one().causa, "RT01")
        self.assertEqual(self.comandos("AgujaParqueo")[0]["params"], {"plaza": 1})

        # Retenido no puede salir
        self.evento("salida", evento="rfid_salida", uid=UID_FUERA)
        self.assertEqual(self.comandos("RechazarSalida")[0]["params"]["motivo"], "Retenido")
        self.assertEqual(self.turno(UID_FUERA).estado, "Retenido")

    def test_salida_sin_turno_se_rechaza(self):
        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        self.assertEqual(self.comandos("RechazarSalida")[0]["params"]["motivo"], "Sin turno activo")

    def test_rechazo_local_por_timeout_anula_turno_en_garita(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.evento("garita", evento="rechazado", motivo="Sin respuesta", uid=UID_OK, decision="local")
        self.assertEqual(self.turno(UID_OK).estado, "Anulado")
        with self.Session() as db:
            self.assertEqual(db.scalars(select(IntentoIngreso)).one().decidido_por, "controlador")

    def test_rechazo_decidido_por_servidor_no_se_registra_dos_veces(self):
        self.evento("garita", evento="rfid", uid=UID_DESCONOCIDO)
        self.evento("garita", evento="rechazado", motivo="RFID no registr", uid=UID_DESCONOCIDO,
                    decision="servidor")
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(IntentoIngreso)).all()), 1)

    def test_parqueo_lleno_con_canal_rojo_rechaza_y_genera_al11(self):
        with self.Session() as db:
            for p in db.scalars(select(ParqueoPlaza)).all():
                p.ocupada = True
            db.scalars(select(Manifiesto).where(Manifiesto.vehiculo_uid == UID_OK)).one().canal = "rojo"
            db.commit()
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.assertEqual(self.comandos("RechazarIngreso")[0]["params"]["motivo"], "Parqueo lleno")
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Alarma)).one().codigo, "AL11")

    def test_no_publica_nada_si_la_transaccion_se_deshace(self):
        self.evento("garita", evento="rfid", uid=UID_DESCONOCIDO)
        self.assertEqual([c["name"] for c in self.enviados], ["RechazarIngreso"])


if __name__ == "__main__":
    unittest.main()
