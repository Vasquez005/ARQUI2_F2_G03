"""Pruebas de la perdida de la estacion (sec. 3.4) con reloj simulado.

    cd backend
    py -3 -m unittest test_vigilancia -v
"""

import unittest

from estacion import VigilanciaEstacion
from iluminacion import ControlIluminacion


class VigilanciaEstacionTests(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]
        self.eventos = []
        self.v = VigilanciaEstacion(
            alerta=lambda: self.eventos.append("fuera"),
            recuperacion=lambda: self.eventos.append("vuelve"),
            segundos_periodo=lambda: 10,
            reloj=lambda: self.t[0],
        )

    def test_no_declara_fuera_antes_de_tres_periodos(self):
        self.v.senal_de_vida()
        self.t[0] = 30          # exactamente 3 periodos: todavia no
        self.v.revisar()
        self.assertEqual(self.eventos, [])

    def test_declara_fuera_despues_de_tres_periodos_una_sola_vez(self):
        self.v.senal_de_vida()
        self.t[0] = 31
        self.v.revisar()
        self.t[0] = 40
        self.v.revisar()
        self.assertEqual(self.eventos, ["fuera"])
        self.assertTrue(self.v.fuera_de_servicio)

    def test_al_volver_avisa_y_se_puede_volver_a_caer(self):
        self.v.senal_de_vida()
        self.t[0] = 31
        self.v.revisar()
        self.v.senal_de_vida()
        self.assertEqual(self.eventos, ["fuera", "vuelve"])
        self.t[0] = 70           # 39 s desde la ultima senal de vida: pasa el limite de 30 s
        self.v.revisar()
        self.assertEqual(self.eventos, ["fuera", "vuelve", "fuera"])

    def test_sin_ninguna_senal_todavia_no_hay_alarma(self):
        self.t[0] = 1000
        self.v.revisar()
        self.assertEqual(self.eventos, [])

    def test_el_periodo_se_lee_en_cada_revision(self):
        periodo = [10]
        self.v._segundos_periodo = lambda: periodo[0]
        self.v.senal_de_vida()
        periodo[0] = 20          # la estacion cambio su latido a 20 s
        self.t[0] = 50           # 50 s: menos de 3 x 20 = 60
        self.v.revisar()
        self.assertEqual(self.eventos, [])


class EncenderSinEstacionTests(unittest.TestCase):
    def test_manda_iluminacion_encender_y_la_mantiene(self):
        cmds = []
        control = ControlIluminacion(enviar=lambda n, t, p: cmds.append(n))
        control.encender_sin_estacion()
        self.assertEqual(cmds, ["IluminacionEncender"])
        self.assertTrue(control.encendida)


if __name__ == "__main__":
    unittest.main()
