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
    def test_flanco_subida_y_bajada(self):
        enviados = []

        def enviar(name, target, params):
            enviados.append((name, target, params))

        c = ControlClimaLluvia(enviar=enviar)
        c.procesar_lluvia(True)
        c.procesar_lluvia(True)
        self.assertEqual(len(enviados), 1)
        self.assertEqual(enviados[0][0], "GruaSuspender")
        self.assertEqual(enviados[0][2]["motivo"], "Clima")

        c.procesar_lluvia(False)
        self.assertEqual(len(enviados), 2)
        self.assertEqual(enviados[1][0], "GruaReanudar")
        self.assertEqual(enviados[1][2]["origen"], "auto")


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
