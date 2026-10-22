"""Pruebas estacion meteorologica + clima por lluvia (sin MQTT ni DB).

    cd backend
    py -3 -m unittest test_estacion -v
"""

import unittest

from estacion import (
    ControlClimaLluvia,
    RegistroEstacion,
    mensaje_config_estacion,
    parsear_lectura,
    procesar_lectura_estacion,
    validar_config_estacion,
)
from iluminacion import ControlIluminacion


class ParsearLecturaTests(unittest.TestCase):
    def test_json_tipico_esp32(self):
        l = parsear_lectura(
            {"temperatura": 24.1, "humedad": 61.3, "lluvia": False, "luz": 42, "ts": 100, "uptime_s": 50}
        )
        self.assertAlmostEqual(l.temperatura, 24.1)
        self.assertAlmostEqual(l.humedad, 61.3)
        self.assertFalse(l.lluvia)
        self.assertAlmostEqual(l.luz, 42.0)


class ConfigEstacionTests(unittest.TestCase):
    def test_mensaje_por_defecto(self):
        self.assertEqual(
            mensaje_config_estacion(5, 10),
            "SegundosLecturaEstacion=5;SegundosLatidoEstacion=10",
        )

    def test_rango_invalido(self):
        with self.assertRaises(ValueError):
            validar_config_estacion(1, 10)


class ControlClimaLluviaTests(unittest.TestCase):
    def setUp(self):
        self.enviados = []
        self.t = [0.0]
        self.c = ControlClimaLluvia(
            enviar=lambda name, target, params: self.enviados.append((name, target, params)),
            minutos_sin_lluvia=2,
            reloj=lambda: self.t[0],
        )

    def test_suspende_con_motivo_clima_una_sola_vez(self):
        self.c.procesar_lluvia(True)
        self.c.procesar_lluvia(True)
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.enviados[0][0], "GruaSuspender")
        self.assertEqual(self.enviados[0][2]["motivo"], "Clima")

    def test_no_reanuda_antes_de_los_minutos_configurados(self):
        self.c.procesar_lluvia(True)
        self.c.procesar_lluvia(False)
        self.t[0] = 119
        self.c.procesar_lluvia(False)
        self.assertEqual([n for n, _, _ in self.enviados], ["GruaSuspender"])

    def test_reanuda_con_origen_auto_al_cumplirse_el_tiempo(self):
        self.c.procesar_lluvia(True)
        self.c.procesar_lluvia(False)
        self.t[0] = 120
        self.c.procesar_lluvia(False)
        self.assertEqual(self.enviados[-1][0], "GruaReanudar")
        self.assertEqual(self.enviados[-1][2]["origen"], "auto")
        self.assertFalse(self.c.suspendido_por_lluvia)

    def test_volver_a_llover_reinicia_el_conteo(self):
        self.c.procesar_lluvia(True)
        self.c.procesar_lluvia(False)
        self.t[0] = 100
        self.c.procesar_lluvia(True)   # vuelve a llover antes de cumplirse el tiempo
        self.t[0] = 150
        self.c.procesar_lluvia(False)  # empieza de cero
        self.t[0] = 200                # solo 50 s desde el nuevo inicio
        self.c.procesar_lluvia(False)
        self.assertEqual([n for n, _, _ in self.enviados], ["GruaSuspender"])

    def test_minutos_fuera_de_rango_se_rechazan(self):
        with self.assertRaises(ValueError):
            ControlClimaLluvia(enviar=lambda *a: None, minutos_sin_lluvia=0)
        with self.assertRaises(ValueError):
            ControlClimaLluvia(enviar=lambda *a: None, minutos_sin_lluvia=31)


class ProcesarLecturaIntegracionTests(unittest.TestCase):
    def test_luz_dispara_iluminacion(self):
        cmds = []

        def enviar(name, target, params):
            cmds.append(name)

        reg = RegistroEstacion()
        ilum = ControlIluminacion(enviar=enviar)
        clima = ControlClimaLluvia(enviar=enviar)
        procesar_lectura_estacion({"luz": 10, "lluvia": False}, reg, ilum, clima)
        self.assertIn("IluminacionEncender", cmds)


if __name__ == "__main__":
    unittest.main()
