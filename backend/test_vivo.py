"""Pruebas de la fase 6: cambios en vivo para naviera, agente y autoridad, y
el bot que nunca queda sin responder.

- El backend anuncia en portus/srv/cambio los manifiestos, declaraciones,
  transportistas (vinculacion) y vehiculos.
- La web reenvia a cada rol solo el NOMBRE de las entidades que le tocan
  (/ws/rol), sin ids ni datos.
- El bot contesta a mensajes sin texto y a errores internos, y /cita ofrece
  botones con los contenedores y las franjas.

    cd backend
    .venv/bin/python3 -m unittest test_vivo -v
"""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import orquestador
import servicios
from models import Declaracion, Manifiesto, PosicionPatio, Transportista, Vehiculo, make_db

_fd, _DB_IMPORT = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PORTUS_DB_PATH"] = _DB_IMPORT
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bot_d", "app")))
import main as bot  # noqa: E402  (bot_d/app/main.py)

# web_c/app/main.py se carga con otro nombre para no chocar con el "main" del bot
_WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web_c", "app", "main.py"))
_spec = importlib.util.spec_from_file_location("web_main", _WEB)
web = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(web)

CHAT = "5005"


class AnunciosTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.Session = make_db(self.db_path)
        self.mqtt = []
        orquestador.anunciar_cambios(self.Session, lambda t, p: self.mqtt.append((t, json.loads(p))))
        bot.SessionLocal = self.Session
        with self.Session() as db:
            for i in range(1, 5):
                db.add(PosicionPatio(id=i, estado="LIBRE"))
            t = Transportista(nombre="Transportista Uno")
            db.add(t)
            db.commit()
            self.trans = t.id
        self.mqtt.clear()

    def tearDown(self):
        for sufijo in ("", "-wal", "-shm"):
            if os.path.exists(self.db_path + sufijo):
                os.remove(self.db_path + sufijo)

    def cambios(self, entidad):
        return [p["id"] for t, p in self.mqtt if t == "portus/srv/cambio" and p["entidad"] == entidad]

    def test_manifiesto_y_declaracion_se_anuncian(self):
        with self.Session() as db:
            m = Manifiesto(contenedor_id="MSCU0000001", tipo_operacion="DEPOSITO", peso_declarado_g=1000,
                           transportista_id=self.trans)
            db.add(m)
            db.commit()
            mid = m.id
            db.add(Declaracion(manifiesto_id=mid, numero_declaracion="DECL-1", regimen="importacion_definitiva",
                               descripcion="Mercancia de prueba", valor_declarado=10))
            m.estado_documental = "declaracion_presentada"
            db.commit()
        self.assertIn(mid, self.cambios("manifiesto"))
        self.assertTrue(self.cambios("declaracion"))

    def test_vehiculo_se_anuncia_con_su_uid(self):
        # Vehiculo no tiene id: antes el anuncio intentaba usar .inicio y reventaba
        with self.Session() as db:
            db.add(Vehiculo(uid="E1 69 73 15", transportista_id=self.trans))
            db.commit()
        self.assertEqual(self.cambios("vehiculo"), ["E1 69 73 15"])

    def test_vincular_por_el_bot_se_anuncia(self):
        with self.Session() as db:
            codigo = servicios.generar_codigo_vinculacion(db, db.get(Transportista, self.trans))
            db.commit()
        self.mqtt.clear()
        self.assertIn("Vinculacion exitosa", bot.responder(CHAT, f"/vincular {codigo}"))
        self.assertEqual(self.cambios("transportista"), [self.trans])

    def test_nada_se_anuncia_si_se_deshace(self):
        with self.Session() as db:
            db.add(Vehiculo(uid="AA BB CC DD", transportista_id=self.trans))
            db.flush()
            db.rollback()
        self.assertEqual(self.mqtt, [])


class BotRespondeSiempreTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.Session = make_db(self.db_path)
        bot.SessionLocal = self.Session
        with self.Session() as db:
            t = Transportista(nombre="Transportista Uno", chat_id=CHAT)
            db.add(t)
            db.flush()
            for cid in ("MSCU0000001", "MSCU0000002"):
                db.add(Manifiesto(contenedor_id=cid, tipo_operacion="DEPOSITO", peso_declarado_g=1000,
                                  transportista_id=t.id, estado_documental="levante_otorgado", canal="verde"))
            db.commit()

    def tearDown(self):
        for sufijo in ("", "-wal", "-shm"):
            if os.path.exists(self.db_path + sufijo):
                os.remove(self.db_path + sufijo)

    def test_mensaje_sin_texto_recibe_respuesta(self):
        self.assertEqual(bot.responder(CHAT, None), bot.MSG_SOLO_TEXTO)
        self.assertIn("/ayuda", bot.MSG_SOLO_TEXTO)

    def test_error_interno_recibe_respuesta(self):
        with mock.patch.object(bot, "process_command", side_effect=RuntimeError("base caida")):
            self.assertEqual(bot.responder(CHAT, "/miscitas"), bot.MSG_ERROR)

    def test_cita_ofrece_botones_de_contenedor_y_franja(self):
        r = bot.responder(CHAT, "/cita")
        self.assertEqual(r.opciones, ["/cita MSCU0000001", "/cita MSCU0000002"])
        r = bot.responder(CHAT, "/cita MSCU0000001")
        self.assertEqual(r.opciones[0], "/cita MSCU0000001 1")
        self.assertEqual(len(r.opciones), bot.FRANJAS_A_OFRECER)
        # La confirmacion no trae botones: Telegram quita el teclado anterior
        r = bot.responder(CHAT, "/cita MSCU0000001 1")
        self.assertIn("Cita confirmada", r)
        self.assertEqual(getattr(r, "opciones", []), [])

    def test_no_vinculado_siempre_igual(self):
        self.assertEqual(bot.responder("9999", "/cita"), bot.MSG_NO_VINCULADO)
        self.assertEqual(bot.responder("9999", "hola"), bot.MSG_NO_VINCULADO)


class _WsFalso:
    def __init__(self):
        self.enviados = []

    async def accept(self):
        pass

    async def send_json(self, datos):
        self.enviados.append(datos)


class WebRolesTests(unittest.TestCase):
    def test_cada_rol_recibe_solo_sus_entidades_y_sin_ids(self):
        bus = web.EventBus()
        naviera, agente, autoridad = _WsFalso(), _WsFalso(), _WsFalso()

        async def correr():
            await bus.register_role(naviera, "NAVIERA")
            await bus.register_role(agente, "AGENTE")
            await bus.register_role(autoridad, "AUTORIDAD")
            for entidad in ("declaracion", "turno", "cita", "intento"):
                await bus.broadcast_roles({"kind": "cambio", "entidad": entidad}, entidad)

        asyncio.run(correr())
        recibido = lambda ws: [m["entidad"] for m in ws.enviados if m["kind"] == "cambio"]
        self.assertEqual(recibido(naviera), ["turno"])
        self.assertEqual(recibido(agente), ["declaracion"])
        self.assertEqual(recibido(autoridad), ["declaracion", "turno"])
        for ws in (naviera, agente, autoridad):
            self.assertTrue(all(set(m) <= {"kind", "entidad", "connected"} for m in ws.enviados))

    def test_terminal_no_entra_por_ws_rol(self):
        self.assertNotIn("TERMINAL", web.ENTIDADES_POR_ROL)


if __name__ == "__main__":
    unittest.main()
