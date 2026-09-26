"""Pruebas de citas y franjas (fase 4): reglas de la sec. 9, agenda de la
terminal (sec. 4.7), cancelar / reprogramar con su aviso, franjas bloqueadas
y el bot del transportista con dos transportistas (aislamiento, sec. 6.3).

    cd backend
    .venv/bin/python3 -m unittest test_citas -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

import orquestador
import servicios
from models import Cita, Manifiesto, Notificacion, PosicionPatio, Transportista, Vehiculo, make_db

# El bot y app.py abren su base al importarse: se les da una temporal y cada
# prueba les pasa la suya.
_fd, _DB_IMPORT = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PORTUS_DB_PATH"] = _DB_IMPORT
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bot_d", "app")))
import app  # noqa: E402
import main as bot  # noqa: E402  (bot_d/app/main.py)

CHAT_UNO, CHAT_DOS = "1001", "2002"


def manana_local(hora: int, minuto: int = 0) -> datetime:
    """Una franja de maniana en hora local, pasada a UTC como la guarda la BD."""
    local = datetime.strptime(servicios.hora_local(datetime.utcnow() + timedelta(days=1), "%Y-%m-%d"), "%Y-%m-%d")
    return servicios.local_a_utc(local.replace(hour=hora, minute=minuto))


class CitasTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.Session = make_db(self.db_path)
        self.mqtt = []
        orquestador.anunciar_cambios(self.Session, lambda t, p: self.mqtt.append((t, json.loads(p))))
        app.SessionLocal = self.Session
        with self.Session() as db:
            for i in range(1, 5):
                db.add(PosicionPatio(id=i, estado="LIBRE"))
            uno = Transportista(nombre="Transportista Uno", chat_id=CHAT_UNO)
            dos = Transportista(nombre="Transportista Dos", chat_id=CHAT_DOS)
            db.add_all([uno, dos])
            db.flush()
            self.uno, self.dos = uno.id, dos.id
            db.add(Vehiculo(uid="E1 69 73 15", transportista_id=uno.id))
            for cid, t in (("MSCU0000001", uno.id), ("MSCU0000002", dos.id), ("MSCU0000003", uno.id),
                           ("MSCU0000004", dos.id)):
                db.add(Manifiesto(contenedor_id=cid, tipo_operacion="DEPOSITO", peso_declarado_g=1000,
                                  transportista_id=t, estado_documental="levante_otorgado", canal="verde"))
            db.commit()

    def tearDown(self):
        for sufijo in ("", "-wal", "-shm"):
            if os.path.exists(self.db_path + sufijo):
                os.remove(self.db_path + sufijo)

    # ── ayudas ──
    def manifiesto(self, db, contenedor):
        return db.scalars(select(Manifiesto).where(Manifiesto.contenedor_id == contenedor)).one()

    def cita(self, contenedor, inicio, transportista=None, estado="programada"):
        with self.Session() as db:
            c = Cita(contenedor_id=contenedor, transportista_id=transportista or self.uno, inicio=inicio,
                     fin=inicio + timedelta(minutes=15), estado=estado)
            db.add(c)
            db.commit()
            return c.id

    def avisos(self, transportista_id):
        with self.Session() as db:
            return [n.texto for n in db.scalars(select(Notificacion).where(
                Notificacion.transportista_id == transportista_id).order_by(Notificacion.id)).all()]

    def bot(self, chat, texto):
        with self.Session() as db:
            return bot.process_command(db, chat, texto)

    # ── Reglas de la sec. 9 ──
    def test_franjas_llenas_y_bloqueadas_no_se_ofrecen(self):
        f10, f1015, f1030 = manana_local(10), manana_local(10, 15), manana_local(10, 30)
        self.cita("MSCU0000001", f10)
        self.cita("MSCU0000002", f10, self.dos)
        with self.Session() as db:
            servicios.bloquear_franja(db, f1015, "mantenimiento")
            db.commit()
            ofrecidas = [i for i, _ in servicios.proximas_franjas(db, f10, cantidad=2)]
        self.assertEqual(ofrecidas, [f1030, f1030 + timedelta(minutes=15)])

    def test_asignar_cita_revalida_capacidad_y_cita_vigente(self):
        f10 = manana_local(10)
        self.cita("MSCU0000002", f10, self.dos)
        self.cita("MSCU0000004", f10, self.dos)
        with self.Session() as db:
            with self.assertRaises(servicios.ReglaDeNegocioError) as ctx:
                servicios.asignar_cita(db, self.uno, self.manifiesto(db, "MSCU0000001"), f10)
            self.assertEqual(str(ctx.exception), "franja_no_disponible")
            servicios.asignar_cita(db, self.uno, self.manifiesto(db, "MSCU0000001"), manana_local(11))
            with self.assertRaises(servicios.ReglaDeNegocioError) as ctx:
                servicios.asignar_cita(db, self.uno, self.manifiesto(db, "MSCU0000001"), manana_local(12))
            self.assertEqual(str(ctx.exception), "contenedor_con_cita_vigente")

    def test_no_se_asigna_en_una_franja_pasada_ni_desalineada(self):
        with self.Session() as db:
            m = self.manifiesto(db, "MSCU0000001")
            for inicio in (servicios.inicio_de_franja(datetime.utcnow()) - timedelta(minutes=15),
                           manana_local(10, 7)):
                with self.assertRaises(servicios.ReglaDeNegocioError):
                    servicios.asignar_cita(db, self.uno, m, inicio)

    # ── Cancelar y reprogramar (sec. 4.7 y aviso de la sec. 6.3) ──
    def test_cancelar_libera_la_franja_y_avisa_solo_al_duenio(self):
        f10 = manana_local(10)
        cid = self.cita("MSCU0000001", f10)
        self.cita("MSCU0000002", f10, self.dos)
        app.cancelar_cita(cid, app.CitaMotivoIn(motivo="cierre del muelle"))
        with self.Session() as db:
            self.assertEqual(db.get(Cita, cid).estado, "cancelada")
            self.assertTrue(servicios.franja_disponible(db, f10))
        aviso = self.avisos(self.uno)[-1]
        self.assertIn("CANCELADA", aviso)
        self.assertIn("MSCU0000001", aviso)
        self.assertIn("cierre del muelle", aviso)
        self.assertEqual(self.avisos(self.dos), [])
        with self.assertRaises(HTTPException) as ctx:
            app.cancelar_cita(cid, app.CitaMotivoIn())
        self.assertEqual(ctx.exception.detail, "cita_cancelada")

    def test_reprogramar_mueve_la_cita_y_avisa_la_ventana_nueva(self):
        cid = self.cita("MSCU0000001", manana_local(10))
        res = app.reprogramar_cita(cid, app.ReprogramarIn(inicio=manana_local(11).isoformat()))
        self.assertEqual(res["inicio"], manana_local(11).isoformat())
        with self.Session() as db:
            c = db.get(Cita, cid)
            self.assertEqual((c.inicio, c.fin), (manana_local(11), manana_local(11, 15)))
        aviso = self.avisos(self.uno)[-1]
        self.assertIn("REPROGRAMADA", aviso)
        self.assertIn(f"Ventana nueva: {servicios.texto_franja(manana_local(11), manana_local(11, 15))}", aviso)

    def test_reprogramar_a_una_franja_llena_o_bloqueada_se_rechaza(self):
        cid = self.cita("MSCU0000001", manana_local(10))
        self.cita("MSCU0000002", manana_local(11), self.dos)
        self.cita("MSCU0000004", manana_local(11), self.dos)
        app.bloquear_franja(app.FranjaIn(inicio=manana_local(12).isoformat()))
        for destino in (manana_local(11), manana_local(12), manana_local(10)):
            with self.assertRaises(HTTPException):
                app.reprogramar_cita(cid, app.ReprogramarIn(inicio=destino.isoformat()))
        opciones = [f["inicio"] for f in app.franjas_para_reprogramar(cid, cantidad=200)]
        self.assertNotIn(manana_local(11).isoformat(), opciones)
        self.assertNotIn(manana_local(12).isoformat(), opciones)

    def test_bloquear_y_desbloquear_franja(self):
        inicio = manana_local(9).isoformat()
        app.bloquear_franja(app.FranjaIn(inicio=inicio, motivo="inspeccion"))
        with self.assertRaises(HTTPException):
            app.bloquear_franja(app.FranjaIn(inicio=inicio))
        app.desbloquear_franja(app.FranjaIn(inicio=inicio))
        with self.assertRaises(HTTPException):
            app.desbloquear_franja(app.FranjaIn(inicio=inicio))
        franjas = [(d["entidad"], d["id"]) for t, d in self.mqtt if t == orquestador.TOPICO_CAMBIOS_SERVIDOR]
        self.assertIn(("franja", manana_local(9).isoformat()), franjas)

    # ── Agenda de la terminal (sec. 4.7) ──
    def test_agenda_del_dia_con_capacidad_bloqueos_y_cumplimiento(self):
        f10 = manana_local(10)
        self.cita("MSCU0000001", f10, estado="cumplida")
        self.cita("MSCU0000002", f10, self.dos, estado="vencida")
        self.cita("MSCU0000003", manana_local(10, 15))  # no se presento
        self.cita("MSCU0000004", manana_local(10, 30), self.dos, estado="cancelada")
        with self.Session() as db:
            servicios.bloquear_franja(db, manana_local(11), "grua en mantenimiento")
            db.commit()
            fecha = servicios.hora_local(f10, "%Y-%m-%d")
            agenda = servicios.agenda_del_dia(db, fecha, ahora=manana_local(12))

        porhora = {f["horaInicio"]: f for f in agenda["franjas"]}
        self.assertEqual(porhora["10:00"]["asignadas"], 2)
        self.assertEqual(porhora["10:00"]["capacidad"], 2)
        self.assertEqual(porhora["10:00"]["citas"][0]["vehiculos"], ["E1 69 73 15"])
        self.assertEqual(porhora["10:00"]["citas"][0]["transportistaNombre"], "Transportista Uno")
        self.assertEqual(porhora["10:15"]["citas"][0]["estado"], "vencida")
        self.assertEqual(porhora["10:30"]["asignadas"], 0)  # la cancelada no cuenta
        self.assertTrue(porhora["11:00"]["bloqueada"])
        self.assertIn("06:00", porhora)  # el horario de la agenda aparece aunque este vacio
        self.assertEqual((agenda["cumplidas"], agenda["evaluadas"]), (1, 3))
        self.assertEqual(agenda["cumplimientoPct"], 33.3)

    def test_franja_en_curso_no_es_pasada_y_no_se_puede_bloquear(self):
        f10 = manana_local(10)
        self.cita("MSCU0000001", f10)
        with self.Session() as db:
            fecha = servicios.hora_local(f10, "%Y-%m-%d")
            agenda = servicios.agenda_del_dia(db, fecha, ahora=f10 + timedelta(minutes=5))
            franja = next(f for f in agenda["franjas"] if f["horaInicio"] == servicios.hora_local(f10, "%H:%M"))
            self.assertTrue(franja["enCurso"])
            self.assertFalse(franja["pasada"])
            self.assertEqual(franja["citas"][0]["estado"], "programada")  # todavia se puede cancelar
            with self.assertRaises(servicios.ReglaDeNegocioError) as ctx:
                servicios.bloquear_franja(db, f10, ahora=f10 + timedelta(minutes=5))
            self.assertEqual(str(ctx.exception), "franja_ya_comenzo")

    def test_agenda_rechaza_fecha_invalida(self):
        with self.assertRaises(HTTPException):
            app.agenda_citas("25/09/2026")

    # ── Bot del transportista ──
    def test_bot_no_ofrece_franjas_bloqueadas(self):
        with self.Session() as db:
            primera = servicios.proximas_franjas(db, datetime.utcnow(), 1)[0][0]
            servicios.bloquear_franja(db, primera)
            db.commit()
        respuesta = self.bot(CHAT_UNO, "/cita MSCU0000001")
        self.assertNotIn(servicios.texto_franja(primera, primera + timedelta(minutes=15)), respuesta)

    def test_bot_confirma_la_cita_y_la_terminal_se_entera(self):
        respuesta = self.bot(CHAT_UNO, "/cita MSCU0000001 1")
        self.assertIn("Cita confirmada", respuesta)
        citas = [d for t, d in self.mqtt if t == orquestador.TOPICO_CAMBIOS_SERVIDOR and d["entidad"] == "cita"]
        self.assertEqual(len(citas), 1)

    def test_bot_si_la_franja_se_lleno_mientras_elegia(self):
        with self.Session() as db:
            oferta = servicios.proximas_franjas(db, datetime.utcnow(), 1)
        # Entre la oferta y la eleccion, el transportista Dos llena esa franja
        self.cita("MSCU0000002", oferta[0][0], self.dos)
        self.cita("MSCU0000004", oferta[0][0], self.dos)
        with mock.patch.object(bot, "proximas_franjas", return_value=oferta):
            respuesta = self.bot(CHAT_UNO, "/cita MSCU0000001 1")
        self.assertIn("ya no esta disponible", respuesta)
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Cita).where(Cita.transportista_id == self.uno)).all(), [])

    def test_dos_transportistas_no_ven_carga_ajena(self):
        self.bot(CHAT_UNO, "/cita MSCU0000001 1")
        self.bot(CHAT_DOS, "/cita MSCU0000002 1")
        self.assertIn("MSCU0000001", self.bot(CHAT_UNO, "/miscitas"))
        self.assertNotIn("MSCU0000002", self.bot(CHAT_UNO, "/miscitas"))
        self.assertEqual(self.bot(CHAT_UNO, "/estado MSCU0000002"), bot.MSG_SIN_CARGA)
        self.assertEqual(self.bot(CHAT_UNO, "/cita MSCU0000002"), bot.MSG_SIN_CARGA)
        self.assertNotIn("MSCU0000002", self.bot(CHAT_UNO, "/cita"))

    def test_estado_muestra_permanencia_desde_el_ingreso_al_patio(self):
        with self.Session() as db:
            servicios.confirmar_deposito_patio(db, 3, "MSCU0000001")
            db.get(PosicionPatio, 3).nivel1_desde = datetime.utcnow() - timedelta(minutes=135)
            db.commit()
        respuesta = self.bot(CHAT_UNO, "/estado MSCU0000001")
        self.assertIn("Patio posicion 3, nivel 1", respuesta)
        self.assertIn("Permanencia: 2 h 15 min", respuesta)

    def test_recordatorio_vuelve_a_salir_si_la_cita_se_reprograma(self):
        ahora = datetime.utcnow()
        inicio = servicios.inicio_de_franja(ahora) + timedelta(minutes=30)
        cid = self.cita("MSCU0000001", inicio)
        with self.Session() as db:
            db.get(Cita, cid).created_at = ahora - timedelta(hours=3)
            db.commit()
            self.assertEqual(bot.encolar_recordatorios(db), 1)
            self.assertEqual(bot.encolar_recordatorios(db), 0)
            c = db.get(Cita, cid)
            c.inicio, c.fin = inicio + timedelta(minutes=15), inicio + timedelta(minutes=30)
            db.commit()
            self.assertEqual(bot.encolar_recordatorios(db), 1)


if __name__ == "__main__":
    unittest.main()
