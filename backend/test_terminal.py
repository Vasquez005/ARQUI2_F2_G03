"""Pruebas del backend para la pestania TERMINAL (fase 3) sin MQTT ni Arduinos:
parqueo que se libera cuando el vehiculo sale, retencion manual, anuncios en
vivo y las rutas que usa la web.

    cd backend
    .venv/bin/python3 -m unittest test_terminal -v
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

import orquestador
import servicios
from models import CommandAudit, ParqueoPlaza, Retencion, Turno
from test_orquestador import UID_FUERA, UID_OK, MaquetaBase

# app.py abre su base al importarse: se le da una temporal y cada prueba la
# reemplaza por la suya (app.SessionLocal).
_fd, _DB_IMPORT = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PORTUS_DB_PATH"] = _DB_IMPORT
import app  # noqa: E402


class TerminalTests(MaquetaBase):
    def setUp(self):
        super().setUp()
        self.mqtt = []
        orquestador.anunciar_cambios(self.Session, lambda t, p: self.mqtt.append((t, json.loads(p))))
        app.SessionLocal = self.Session
        app.mqttc.publish = lambda t, p: self.enviados.append(json.loads(p))

    # ── ayudas ──
    def retener_rt01(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)

    def plaza(self, plaza_id=1):
        with self.Session() as db:
            return db.get(ParqueoPlaza, plaza_id)

    def resolver(self, resolucion="aclarar", **kw):
        with self.Session() as db:
            r = db.scalars(select(Retencion).where(Retencion.estado == "abierta")).one()
            servicios.resolver_retencion(db, r.id, resolucion, "TERMINAL", publish_cmd=lambda *a: None, **kw)
            db.commit()

    # ── Parqueo: la plaza sigue ocupada hasta que el vehiculo sale ──
    def test_aclarar_no_libera_la_plaza_hasta_que_el_vehiculo_sale(self):
        self.retener_rt01()
        self.resolver()
        p = self.plaza()
        self.assertTrue(p.ocupada)
        self.assertEqual(p.turno_id, self.turno(UID_FUERA).id)

        parqueo = app.listar_parqueo()
        self.assertTrue(parqueo[0]["retencionResuelta"])
        self.assertEqual(parqueo[0]["vehiculoUid"], UID_FUERA)

        self.evento("salida", evento="rfid_salida", uid=UID_FUERA)
        self.assertEqual(self.comandos("AbrirPuertaSalida")[0]["params"]["uid"], UID_FUERA)
        self.assertFalse(self.plaza().ocupada)

    def test_liberar_parqueo_exige_retencion_resuelta(self):
        self.retener_rt01()
        with self.assertRaises(HTTPException) as ctx:
            app.liberar_parqueo(1)
        self.assertEqual(ctx.exception.detail, "retencion_sin_resolver")
        with self.assertRaises(HTTPException) as ctx:
            app.liberar_parqueo(2)
        self.assertEqual(ctx.exception.detail, "plaza_libre")

        self.resolver()
        app.liberar_parqueo(1)
        self.assertEqual(self.comandos("AgujaLiberar")[-1]["params"], {"plaza": 1})

    def test_ack_de_aguja_liberar_libera_la_plaza(self):
        self.retener_rt01()
        self.resolver()
        with self.Session() as db:
            db.add(CommandAudit(cmd_name="AgujaLiberar", target="MEGA_GRUA", request_json=json.dumps(
                {"name": "AgujaLiberar", "target": "MEGA_GRUA", "params": {"plaza": 1}})))
            db.commit()
            servicios.registrar_respuesta_comando(db, "MEGA_GRUA", "ACK", {"name": "AgujaLiberar"}, "{}")
            db.commit()
        self.assertFalse(self.plaza().ocupada)

    def test_rechazo_de_aguja_liberar_deja_la_plaza_ocupada(self):
        self.retener_rt01()
        self.resolver()
        with self.Session() as db:
            servicios.registrar_respuesta_comando(db, "MEGA_GRUA", "REJ",
                                                  {"name": "AgujaLiberar", "causa": "pesaje_externo"}, "{}")
            db.commit()
        self.assertTrue(self.plaza().ocupada)

    def test_parqueo_ocupado_por_resueltas_cuenta_como_lleno(self):
        with self.Session() as db:
            for p in db.scalars(select(ParqueoPlaza)).all():
                p.ocupada, p.turno_id = True, 999
            db.commit()
            self.assertTrue(servicios.parqueo_lleno(db))

    # ── Retencion manual (sec. 4.2) ──
    def test_retener_despues_de_la_transferencia_no_manda_al_parqueo(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.evento("pesaje", evento="meseta", resultado="ok", uid=UID_OK)
        with self.Session() as db:
            t = db.get(Turno, self.turno(UID_OK).id)
            servicios.transicionar_turno(db, t, "EnTransferencia")
            r = servicios.retener_manualmente(db, t, "RT06", "revision")
            db.commit()
            self.assertIsNone(r.plaza)
            self.assertEqual(r.observacion, "revision")
        self.assertEqual(self.comandos("AgujaParqueo"), [])

    def test_retener_antes_de_la_transferencia_si_manda_al_parqueo(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        res = app.retener_manual(self.turno(UID_OK).id,
                                 app.RetenerManualIn(causa="RT06", rol_usuario="TERMINAL"))
        self.assertEqual(res["estado"], "Retenido")
        self.assertEqual(self.comandos("AgujaParqueo")[0]["params"], {"plaza": 1})

    def test_no_se_retiene_un_turno_ya_retenido(self):
        self.retener_rt01()
        with self.assertRaises(HTTPException) as ctx:
            app.retener_manual(self.turno(UID_FUERA).id,
                               app.RetenerManualIn(causa="RT06", rol_usuario="TERMINAL"))
        self.assertEqual(ctx.exception.status_code, 409)

    # ── Anuncios en vivo ──
    def test_los_cambios_se_anuncian_por_entidad(self):
        self.retener_rt01()
        cambios = {(d["entidad"], d["id"]) for t, d in self.mqtt if t == orquestador.TOPICO_CAMBIOS_SERVIDOR}
        turno_id = self.turno(UID_FUERA).id
        self.assertIn(("turno", turno_id), cambios)
        self.assertIn(("parqueo", 1), cambios)
        self.assertIn(("retencion", 1), cambios)

    # ── Rutas de la web ──
    def test_turnos_activos_historicos_y_busqueda(self):
        self.evento("garita", evento="rfid", uid=UID_OK)
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("garita", evento="rechazado", motivo="x", uid=UID_FUERA, decision="local")  # lo anula

        activos = app.listar_turnos(activos=True)
        self.assertEqual([t["vehiculoUid"] for t in activos], [UID_OK])
        self.assertEqual(activos[0]["transportistaNombre"], "Transportista Uno")
        self.assertGreaterEqual(activos[0]["tiempoEnTerminalS"], 0)
        self.assertEqual([t["estado"] for t in app.listar_turnos(activos=False)], ["Anulado"])
        self.assertEqual(len(app.listar_turnos(q="mscu0000003")), 1)

        hoy = servicios.hora_local(datetime.utcnow(), "%Y-%m-%d")
        self.assertEqual(len(app.listar_turnos(desde=hoy, hasta=hoy)), 2)
        manana = servicios.hora_local(datetime.utcnow() + timedelta(days=1), "%Y-%m-%d")
        self.assertEqual(app.listar_turnos(desde=manana), [])
        with self.assertRaises(HTTPException):
            app.listar_turnos(desde="25/09/2026")

    def test_retencion_trae_evidencia_de_peso_y_rol_facultado(self):
        self.retener_rt01()
        r = app.listar_retenciones()[0]
        self.assertEqual((r["diferenciaG"], r["diferenciaPct"]), (750, 50.0))
        self.assertEqual(r["rolFacultado"], "TERMINAL")
        self.assertEqual(r["vehiculoUid"], UID_FUERA)
        self.assertEqual(r["contenedorId"], "MSCU0000003")

    def test_inventario_del_patio(self):
        with self.Session() as db:
            servicios.confirmar_deposito_patio(db, 2, "MSCU0000001")
            db.commit()
        fila = app.inventario_patio()[0]
        self.assertEqual((fila["contenedorId"], fila["posicion"], fila["nivel"]), ("MSCU0000001", 2, 1))
        self.assertEqual(fila["pesoDeclaradoG"], 1000)
        self.assertEqual(fila["estadoAutorizacion"], "levante_otorgado")
        self.assertIsNotNone(fila["enPatioDesde"])


if __name__ == "__main__":
    unittest.main()
