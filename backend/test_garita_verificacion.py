"""Flujo de la garita con verificacion de placa (fase 3, sec. 6) contra una base temporal.

La camara se simula: no hace falta hardware.

    cd backend
    py -3 -m unittest test_garita_verificacion -v
"""

import json
import os
import tempfile

import camara_garita
import garita_verificacion as gv
import orquestador
import servicios
from models import Alarma, LecturaPlaca, PlacaRestringida, Turno, Vehiculo
from test_orquestador import UID_FUERA, UID_OK, MaquetaBase

PLACA_OK = "C407BTJ"
PLACA_OTRA = "C123BCD"


class GaritaVerificacionTests(MaquetaBase):
    def setUp(self):
        super().setUp()
        self._camara_original = camara_garita.leer_placa_garita
        self._activa_original = os.environ.get("PORTUS_VERIFICACION_PLACA")
        os.environ["PORTUS_VERIFICACION_PLACA"] = "1"
        with self.Session() as db:
            db.query(Vehiculo).filter(Vehiculo.uid == UID_OK).one().placa = PLACA_OK
            db.query(Vehiculo).filter(Vehiculo.uid == UID_FUERA).one().placa = PLACA_OTRA
            db.commit()

    def tearDown(self):
        camara_garita.leer_placa_garita = self._camara_original
        if self._activa_original is None:
            os.environ.pop("PORTUS_VERIFICACION_PLACA", None)
        else:
            os.environ["PORTUS_VERIFICACION_PLACA"] = self._activa_original
        # En Windows SQLite puede seguir abierto; no fallar por limpiar el archivo temporal.

    def ejecutar(self, uid, lectura):
        camara_garita.leer_placa_garita = lambda **kwargs: lectura
        comandos = []
        self.vision = []  # (topic, datos) de portus/vision/* publicados en el flujo

        def capturar(topic, payload):
            datos = json.loads(payload)
            if topic == "portus/cmd/solicitud":
                comandos.append(datos)
            elif topic.startswith("portus/vision/"):
                self.vision.append((topic, datos))

        with self.Session() as db:
            pub = orquestador.PublicadorDiferido(db, capturar)
            orquestador._garita_rfid_verificada(db, pub, uid)
        return [c["name"] for c in comandos], comandos

    def lectura(self, placa, confianza=73.0):
        return {"texto": placa, "confianza": confianza, "foto": "debug/prueba.jpg"}

    def test_placa_correcta_autoriza_y_registra_la_lectura(self):
        nombres, _ = self.ejecutar(UID_OK, self.lectura(PLACA_OK))
        self.assertIn("AbrirTalanquera", nombres)
        with self.Session() as db:
            lect = db.query(LecturaPlaca).one()
            self.assertEqual((lect.resultado, lect.placa_leida), ("autorizado", PLACA_OK))
            self.assertIsNotNone(lect.turno_id)
            self.assertEqual(db.query(Turno).count(), 1)

    def test_ingreso_autorizado_publica_vision_y_notifica_con_foto(self):
        from models import Notificacion
        self.ejecutar(UID_OK, self.lectura(PLACA_OK))
        # sec. 2.2: se publico el resultado de la lectura y el estado de la camara
        topicos = {t for t, _ in self.vision}
        self.assertIn("portus/vision/placa", topicos)
        self.assertIn("portus/vision/estado", topicos)
        placa_msg = next(d for t, d in self.vision if t == "portus/vision/placa")
        self.assertEqual(placa_msg["placa"], PLACA_OK)
        estado_msg = next(d for t, d in self.vision if t == "portus/vision/estado")
        self.assertEqual(estado_msg["camara"], "operativa")
        # sec. 9.2: aviso de ingreso con referencia a la foto (ingreso:<id>)
        with self.Session() as db:
            notif = db.query(Notificacion).filter(Notificacion.evento == "ingreso_verificado").one()
            lect = db.query(LecturaPlaca).one()
            self.assertEqual(notif.referencia, f"ingreso:{lect.id}")

    def test_camara_fuera_de_servicio_publica_estado_fuera(self):
        self.ejecutar(UID_OK, None)  # None = camara fuera de servicio
        estado_msg = next(d for t, d in self.vision if t == "portus/vision/estado")
        self.assertEqual(estado_msg["camara"], "fuera_de_servicio")

    def test_placa_de_otro_camion_crea_retencion_pendiente_rt07_y_al20(self):
        self.ejecutar(UID_OK, self.lectura(PLACA_OTRA))
        with self.Session() as db:
            lect = db.query(LecturaPlaca).one()
            self.assertEqual((lect.resultado, lect.causa), ("retencion_pendiente", "RT07"))
            codigos = [a.codigo for a in db.query(Alarma).all()]
            self.assertIn("AL20", codigos)

    def test_placa_restringida_gana_aunque_la_tarjeta_sea_valida(self):
        with self.Session() as db:
            gv.restringir(db, PLACA_OK, "Alerta de la autoridad aduanera", "autoridad")
            db.commit()
        self.ejecutar(UID_OK, self.lectura(PLACA_OK))
        with self.Session() as db:
            lect = db.query(LecturaPlaca).one()
            self.assertEqual((lect.resultado, lect.causa), ("retencion_pendiente", "RT08"))
            self.assertIn("AL21", [a.codigo for a in db.query(Alarma).all()])

    def test_etiqueta_desconocida_rechaza_sin_turno(self):
        nombres, comandos = self.ejecutar("AA BB CC DD", self.lectura(PLACA_OK))
        self.assertEqual(nombres, ["RechazarIngreso", "GaritaResultado"])
        self.assertEqual(comandos[0]["params"]["motivo"], "Tarjeta no registrada")
        with self.Session() as db:
            self.assertEqual(db.query(Turno).count(), 0)
            self.assertEqual(db.query(LecturaPlaca).one().resultado, "rechazo")

    def test_camara_fuera_de_servicio_queda_pendiente_para_el_operador(self):
        nombres, comandos = self.ejecutar(UID_OK, None)
        self.assertIn("RechazarIngreso", nombres)
        self.assertEqual(comandos[0]["params"]["motivo"], "MODO DEGRADADO")
        with self.Session() as db:
            lect = db.query(LecturaPlaca).one()
            self.assertTrue(lect.pendiente)
            self.assertEqual(lect.resultado, "modo_degradado")
            self.assertEqual(db.query(Turno).count(), 0)
            self.assertIn("AL18", [a.codigo for a in db.query(Alarma).all()])

    def test_sin_lectura_valida_pasa_a_verificacion_manual(self):
        nombres, _ = self.ejecutar(UID_OK, self.lectura("ZZZZZZZ", confianza=80))
        self.assertIn("RechazarIngreso", nombres)
        with self.Session() as db:
            lect = db.query(LecturaPlaca).one()
            self.assertTrue(lect.pendiente)
            self.assertEqual(lect.resultado, "verificacion_manual")

    def test_verificaciones_pendientes_listan_solo_las_pendientes(self):
        self.ejecutar(UID_OK, None)
        self.ejecutar(UID_OK, self.lectura(PLACA_OK))
        with self.Session() as db:
            pendientes = gv.verificaciones_pendientes(db)
            self.assertEqual(len(pendientes), 1)
            self.assertEqual(pendientes[0].resultado, "modo_degradado")


class RestringirPlacaTests(MaquetaBase):
    def tearDown(self):
        # En Windows SQLite mantiene el archivo abierto; no fallar por limpiarlo.
        pass

    def test_restringir_exige_motivo_de_diez_caracteres(self):
        with self.Session() as db:
            with self.assertRaises(ValueError):
                gv.restringir(db, "C999XYZ", "corto", "autoridad")

    def test_no_se_restringe_dos_veces_la_misma_placa(self):
        with self.Session() as db:
            gv.restringir(db, "c 999 xyz", "Alerta de la autoridad", "autoridad")
            db.commit()
        with self.Session() as db:
            with self.assertRaises(ValueError):
                gv.restringir(db, "C999XYZ", "Otra alerta de la autoridad", "autoridad")

    def test_liberar_registra_quien_y_por_que(self):
        with self.Session() as db:
            fila = gv.restringir(db, "C999XYZ", "Alerta de la autoridad", "autoridad")
            db.commit()
            rid = fila.id
        with self.Session() as db:
            gv.liberar(db, rid, "La autoridad retiro la alerta", "autoridad")
            db.commit()
        with self.Session() as db:
            fila = db.get(PlacaRestringida, rid)
            self.assertFalse(fila.activa)
            self.assertEqual(fila.liberada_por, "autoridad")
            self.assertEqual(gv.placas_restringidas(db), [])


if __name__ == "__main__":
    import unittest
    unittest.main()
