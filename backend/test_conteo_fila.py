"""Pruebas del conteo de la fila (sec. 5.4 y 5.5). Sin modelo ni camara.

    cd backend
    py -3 -m unittest test_conteo_fila -v
"""

import unittest

import conteo_fila as cf


class ContarVehiculosTests(unittest.TestCase):
    def test_cuenta_automovil_camion_y_autobus(self):
        self.assertEqual(cf.contar_vehiculos([2, 7, 5]), 3)

    def test_ignora_otras_clases(self):
        self.assertEqual(cf.contar_vehiculos([0, 16, 2]), 1)  # persona, perro, automovil

    def test_sin_detecciones_es_cero(self):
        self.assertEqual(cf.contar_vehiculos([]), 0)


class ValidacionTests(unittest.TestCase):
    def test_umbral_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            cf.validar_umbral(0)
        with self.assertRaises(ValueError):
            cf.validar_umbral(11)
        cf.validar_umbral(3)

    def test_segundos_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            cf.validar_segundos(1)
        cf.validar_segundos(5)


class ConteoFilaTests(unittest.TestCase):
    def setUp(self):
        self.eventos = []
        self.c = cf.ConteoFila(
            umbral=3,
            alarma=lambda n: self.eventos.append(("AL19", n)),
            superada=lambda n: self.eventos.append(("superada", n)),
        )

    def test_alarma_al_llegar_al_umbral_y_no_se_repite(self):
        self.c.registrar(2)
        self.c.registrar(3)
        self.c.registrar(4)
        self.assertEqual(self.eventos, [("AL19", 3)])
        self.assertTrue(self.c.congestionada)

    def test_superada_cuando_baja_del_umbral(self):
        self.c.registrar(3)
        self.c.registrar(2)
        self.assertEqual(self.eventos, [("AL19", 3), ("superada", 2)])
        self.assertFalse(self.c.congestionada)

    def test_guarda_el_ultimo_conteo(self):
        self.c.registrar(1)
        self.c.registrar(2)
        self.assertEqual(self.c.ultimo_conteo, 2)

    def test_la_lectura_de_placa_pausa_el_conteo(self):
        self.assertTrue(self.c.puede_contar())
        self.c.pausar_por_lectura_de_placa(True)
        self.assertFalse(self.c.puede_contar())
        self.c.pausar_por_lectura_de_placa(False)
        self.assertTrue(self.c.puede_contar())


if __name__ == "__main__":
    unittest.main()
