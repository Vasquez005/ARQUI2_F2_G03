"""Pruebas de la camara de la garita con camara y lector simulados (sin hardware).

    cd backend
    py -3 -m unittest test_camara_garita -v
"""

import unittest

import camara_garita as cg
import verificacion as v

PROPIA = "C407BTJ"
CATALOGO = [PROPIA, "C123BCD"]


def lector_que_devuelve(placas):
    return lambda ruta: placas


class LecturaTests(unittest.TestCase):
    def test_camara_sin_imagen_devuelve_none(self):
        self.assertIsNone(cg.leer_placa_garita(capturar=lambda: False, leer=lambda r: []))

    def test_sin_placas_devuelve_texto_vacio(self):
        r = cg.leer_placa_garita(capturar=lambda: True, leer=lector_que_devuelve([]))
        self.assertEqual(r["texto"], "")
        self.assertEqual(r["confianza"], 0.0)

    def test_elige_la_placa_de_mayor_confianza_y_pasa_a_porcentaje(self):
        placas = [
            {"placa": "C2082261", "confianza_ocr": 0.24},
            {"placa": PROPIA, "confianza_ocr": 0.73},
        ]
        r = cg.leer_placa_garita(capturar=lambda: True, leer=lector_que_devuelve(placas))
        self.assertEqual(r["texto"], PROPIA)
        self.assertAlmostEqual(r["confianza"], 73.0)


class ReintentosTests(unittest.TestCase):
    def test_repite_la_foto_hasta_obtener_lectura_valida(self):
        lecturas = [[], [{"placa": "X", "confianza_ocr": 0.1}], [{"placa": PROPIA, "confianza_ocr": 0.9}]]
        capturas = []
        r = cg.leer_placa_garita(
            capturar=lambda: capturas.append(1) or True,
            leer=lambda ruta: lecturas.pop(0),
            intentos=3,
            es_valida=lambda l: l["confianza"] >= 60 and bool(l["texto"]),
        )
        self.assertEqual(len(capturas), 3)
        self.assertEqual(r["texto"], PROPIA)

    def test_se_detiene_en_IntentosOCR(self):
        capturas = []
        cg.leer_placa_garita(
            capturar=lambda: capturas.append(1) or True,
            leer=lambda ruta: [],
            intentos=2,
            es_valida=lambda l: False,
        )
        self.assertEqual(len(capturas), 2)

    def test_intentos_fuera_de_rango_se_rechazan(self):
        with self.assertRaises(ValueError):
            cg.validar_intentos(0)
        with self.assertRaises(ValueError):
            cg.validar_intentos(6)
        cg.validar_intentos(3)


class EvaluarGaritaTests(unittest.TestCase):
    def evaluar(self, lectura, umbral=60):
        return cg.evaluar_garita(
            etiqueta_registrada=True, placa_registrada=PROPIA, restringidas=[],
            catalogo=CATALOGO, umbral_ocr=umbral, lectura=lectura,
        )

    def test_camara_fuera_de_servicio_es_modo_degradado(self):
        d = self.evaluar(None)
        self.assertEqual((d.resultado, d.alarma), (v.MODO_DEGRADADO, "AL18"))

    def test_lectura_correcta_con_confianza_suficiente_autoriza(self):
        d = self.evaluar({"texto": PROPIA, "confianza": 73.0, "foto": "x.jpg"})
        self.assertEqual(d.resultado, v.INGRESO_AUTORIZADO)

    def test_confianza_debajo_del_umbral_va_a_verificacion_manual(self):
        d = self.evaluar({"texto": PROPIA, "confianza": 40.0, "foto": "x.jpg"}, umbral=60)
        self.assertEqual(d.resultado, v.VERIFICACION_MANUAL)

    def test_umbral_configurable_hace_valida_la_misma_lectura(self):
        d = self.evaluar({"texto": PROPIA, "confianza": 40.0, "foto": "x.jpg"}, umbral=30)
        self.assertEqual(d.resultado, v.INGRESO_AUTORIZADO)


if __name__ == "__main__":
    unittest.main()
