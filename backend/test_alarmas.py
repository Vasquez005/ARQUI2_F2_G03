"""Pruebas de las alarmas del backend (fase 2) sin MQTT ni Arduinos.

    cd backend
    .venv/bin/python3 -m unittest test_alarmas -v
"""

import json
import unittest
from datetime import datetime, timedelta

from sqlalchemy import select

import orquestador
import servicios
from models import Alarma, Cita, CommandAudit, Manifiesto, PosicionPatio, Retencion
from test_orquestador import UID_FUERA, UID_OK, MaquetaBase


class AlarmasTests(MaquetaBase):
    def alarmas(self, codigo=None):
        with self.Session() as db:
            q = select(Alarma).order_by(Alarma.id)
            if codigo:
                q = q.where(Alarma.codigo == codigo)
            return db.scalars(q).all()

    def anunciadas(self):
        return [json.loads(p) for t, p in self.mqtt if t == orquestador.TOPICO_ALARMAS_SERVIDOR]

    def setUp(self):
        super().setUp()
        self.mqtt = []
        orquestador.anunciar_cambios(self.Session, lambda t, p: self.mqtt.append((t, p)))

    # ── 2.1 AL09 ──
    def test_pesaje_fuera_de_tolerancia_genera_al09_con_la_evidencia(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        al09 = self.alarmas("AL09")
        self.assertEqual(len(al09), 1)
        self.assertEqual(al09[0].severidad, "media")
        self.assertIn("declarado 1500 g, medido 2250 g, diferencia 50.0 %", al09[0].descripcion)
        self.assertEqual(al09[0].referencia, f"turno:{self.turno(UID_FUERA).id}")

    def test_pesaje_ok_no_genera_alarma(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.evento("pesaje", evento="meseta", resultado="ok", uid=UID_OK)
        self.assertEqual(self.alarmas(), [])

    # ── 2.2 AL10 ──
    def test_vehiculo_sin_turno_en_la_salida_genera_al10_una_vez(self):
        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        al10 = self.alarmas("AL10")
        self.assertEqual(len(al10), 1)
        self.assertEqual(len(self.comandos("RechazarSalida")), 2)

        with self.Session() as db:
            servicios.reconocer_alarma(db, al10[0].id)
            db.commit()
        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        self.assertEqual(len(self.alarmas("AL10")), 2)

    def test_retenido_en_la_salida_no_es_al10(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        self.evento("salida", evento="rfid_salida", uid=UID_FUERA)
        self.assertEqual(self.alarmas("AL10"), [])

    # ── 2.3 AL14 ──
    def test_comando_rechazado_genera_al14_con_la_causa(self):
        with self.Session() as db:
            db.add(CommandAudit(cmd_name="GruaReferenciar", target="MEGA_GRUA", request_json="{}"))
            db.commit()
            servicios.registrar_respuesta_comando(db, "MEGA_GRUA", "REJ",
                                                  {"name": "GruaReferenciar", "causa": "grua_en_movimiento"}, "{}")
            db.commit()
            audit = db.scalars(select(CommandAudit)).one()
            self.assertEqual(audit.result, "REJ")
        al14 = self.alarmas("AL14")
        self.assertEqual(len(al14), 1)
        self.assertEqual(al14[0].descripcion, "MEGA_GRUA rechazo GruaReferenciar: grua_en_movimiento")
        self.assertEqual(al14[0].referencia, f"comando:{audit.id}")

    def test_comando_aceptado_no_genera_alarma(self):
        with self.Session() as db:
            servicios.registrar_respuesta_comando(db, "MEGA_GRUA", "ACK", {"name": "GruaSuspender"}, "{}")
            db.commit()
            self.assertEqual(db.scalars(select(CommandAudit)).one().result, "ACK")
        self.assertEqual(self.alarmas(), [])

    # ── 2.4 AL12 ──
    def test_retencion_de_mas_de_30_min_genera_al12_una_sola_vez(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        with self.Session() as db:
            self.assertEqual(servicios.revisar_alarmas_por_tiempo(db), [])
            db.scalars(select(Retencion)).one().created_at = datetime.utcnow() - timedelta(minutes=31)
            db.commit()
            self.assertEqual(len(servicios.revisar_alarmas_por_tiempo(db)), 1)
            db.commit()
            self.assertEqual(servicios.revisar_alarmas_por_tiempo(db), [])
            db.commit()
        al12 = self.alarmas("AL12")
        self.assertEqual(len(al12), 1)
        self.assertIn("RT01", al12[0].descripcion)

    def test_retencion_resuelta_no_genera_al12(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        with self.Session() as db:
            r = db.scalars(select(Retencion)).one()
            r.created_at = datetime.utcnow() - timedelta(minutes=45)
            servicios.resolver_retencion(db, r.id, "aclarar", "TERMINAL")
            db.commit()
            self.assertEqual(servicios.revisar_alarmas_por_tiempo(db), [])

    # ── 2.5 AL13 ──
    def test_contenedor_de_mas_de_2_h_en_patio_genera_al13(self):
        with self.Session() as db:
            servicios.confirmar_deposito_patio(db, 2, "MSCU0000001")
            servicios.confirmar_deposito_patio(db, 2, "MSCU0000009")
            db.commit()
            p = db.get(PosicionPatio, 2)
            self.assertIsNotNone(p.nivel1_desde)
            self.assertIsNotNone(p.nivel2_desde)
            self.assertEqual(servicios.revisar_alarmas_por_tiempo(db), [])

            p.nivel1_desde = datetime.utcnow() - timedelta(minutes=121)
            db.commit()
            nuevas = servicios.revisar_alarmas_por_tiempo(db)
            db.commit()
            self.assertEqual([a.referencia for a in nuevas], ["contenedor:MSCU0000001"])
            self.assertEqual(servicios.revisar_alarmas_por_tiempo(db), [])

            # Sale el de arriba: el de abajo conserva su fecha de ingreso
            servicios.confirmar_remocion_patio(db, 2)
            db.commit()
            self.assertIsNone(p.nivel2_desde)
            self.assertIsNotNone(p.nivel1_desde)

    def test_contenedor_que_vuelve_al_patio_cuenta_una_estancia_nueva(self):
        ahora = datetime.utcnow()
        with self.Session() as db:
            # Primera estancia: entro hace 5 h y su AL13 salio hace 3 h
            servicios.confirmar_deposito_patio(db, 1, "MSCU0000001")
            db.get(PosicionPatio, 1).nivel1_desde = ahora - timedelta(hours=5)
            servicios.revisar_alarmas_por_tiempo(db, ahora=ahora - timedelta(hours=3))
            servicios.confirmar_remocion_patio(db, 1)
            # Segunda estancia: volvio hace 130 min
            servicios.confirmar_deposito_patio(db, 1, "MSCU0000001")
            db.get(PosicionPatio, 1).nivel1_desde = ahora - timedelta(minutes=130)
            db.commit()
            db.scalars(select(Alarma)).one().created_at = ahora - timedelta(hours=3)
            db.commit()
            self.assertEqual(len(servicios.revisar_alarmas_por_tiempo(db, ahora=ahora)), 1)

    def test_liberar_posicion_con_dos_niveles_queda_ocupada_2(self):
        with self.Session() as db:
            servicios.confirmar_deposito_patio(db, 3, "A")
            servicios.confirmar_deposito_patio(db, 3, "B")
            servicios.bloquear_posicion_patio(db, 3)
            servicios.liberar_posicion_patio(db, 3)
            self.assertEqual(db.get(PosicionPatio, 3).estado, "OCUPADA_2")

    # ── 2.6 Alarmas de las placas ──
    def test_alarma_de_una_placa_se_guarda_con_la_severidad_del_catalogo(self):
        orquestador.procesar_evento(self.Session, lambda t, p: None, "portus/evt/alarma",
                                    {"codigo": "AL02", "severidad": "baja", "detalle": "boton"},
                                    origen="MEGA_GRUA")
        orquestador.procesar_evento(self.Session, lambda t, p: None, "portus/evt/alarma",
                                    {"codigo": "AL02"}, origen="MEGA_GRUA")
        al02 = self.alarmas("AL02")
        self.assertEqual(len(al02), 1)  # la repeticion mientras sigue activa no duplica
        self.assertEqual(al02[0].severidad, "critica")
        self.assertEqual(al02[0].origen, "MEGA_GRUA")
        self.assertIn("detalle=boton", al02[0].descripcion)

    def test_codigo_desconocido_de_una_placa_se_ignora(self):
        orquestador.procesar_evento(self.Session, lambda t, p: None, "portus/evt/alarma",
                                    {"codigo": "AL99"}, origen="UNO_ENTRADA")
        self.assertEqual(self.alarmas(), [])

    # ── Aviso en vivo ──
    def test_las_alarmas_se_anuncian_despues_del_commit(self):
        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        anunciadas = self.anunciadas()
        self.assertEqual([a["codigo"] for a in anunciadas], ["AL10"])
        self.assertEqual(anunciadas[0]["estado"], "activa")
        self.assertIsNotNone(anunciadas[0]["id"])

    def test_una_alarma_deshecha_no_se_anuncia(self):
        with self.Session() as db:
            servicios.generar_alarma(db, "AL09")
            db.flush()
            db.rollback()
            servicios.generar_alarma(db, "AL14")
            db.commit()
        self.assertEqual([a["codigo"] for a in self.anunciadas()], ["AL14"])
        self.assertEqual([a.codigo for a in self.alarmas()], ["AL14"])

    # ── Pendiente de la fase 1: pesaje que llega con RT04 ──
    def _cita_vencida(self, contenedor):
        with self.Session() as db:
            ahora = datetime.utcnow()
            db.add(Cita(contenedor_id=contenedor, inicio=ahora - timedelta(hours=2), fin=ahora - timedelta(hours=1)))
            db.commit()

    def _resolver_unica_abierta(self, rol="TERMINAL"):
        with self.Session() as db:
            r = db.scalars(select(Retencion).where(Retencion.estado == "abierta")).one()
            servicios.resolver_retencion(db, r.id, "aclarar", rol)
            db.commit()

    def test_pesaje_durante_rt04_se_aplica_al_aclarar(self):
        self._cita_vencida("MSCU0000001")
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.assertEqual(self.turno(UID_OK).estado, "Retenido")
        self.evento("pesaje", evento="meseta", resultado="ok", uid=UID_OK)
        self.assertEqual(self.turno(UID_OK).peso_medido_entrada_g, 1000)

        self._resolver_unica_abierta()
        self.assertEqual(self.turno(UID_OK).estado, "EnRuta")

    def test_pesaje_fuera_durante_rt04_termina_en_rt01_al_aclarar(self):
        self._cita_vencida("MSCU0000003")
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        self._resolver_unica_abierta()
        t = self.turno(UID_FUERA)
        self.assertEqual(t.estado, "Retenido")
        with self.Session() as db:
            causas = [r.causa for r in db.scalars(select(Retencion).order_by(Retencion.id)).all()]
        self.assertEqual(causas, ["RT04", "RT01"])
        self.assertEqual(len(self.alarmas("AL09")), 1)

    def test_rechazar_rt04_no_aplica_el_pesaje_guardado(self):
        self._cita_vencida("MSCU0000001")
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.evento("pesaje", evento="meseta", resultado="ok", uid=UID_OK)
        with self.Session() as db:
            r = db.scalars(select(Retencion)).one()
            servicios.resolver_retencion(db, r.id, "rechazar", "TERMINAL", motivo="llego tarde")
            db.commit()
        self.assertEqual(self.turno(UID_OK).estado, "Anulado")



if __name__ == "__main__":
    unittest.main()
