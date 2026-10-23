"""Pruebas de la iluminacion de la planta (fase 3, sec. 4.2). Sin MQTT ni base de datos.

    cd backend
    py -3 -m unittest test_iluminacion -v
"""

import unittest

from iluminacion import (
    MODO_APAGADO, MODO_AUTOMATICO, MODO_ENCENDIDO, ControlIluminacion, decidir_encendida, validar_umbrales,
)


class ValidarUmbralesTests(unittest.TestCase):
    def test_valores_por_defecto_son_validos(self):
        validar_umbrales(30, 45)

    def test_diferencia_de_exactamente_cinco_es_valida(self):
        validar_umbrales(30, 35)

    def test_diferencia_menor_que_cinco_se_rechaza(self):
        with self.assertRaises(ValueError):
            validar_umbrales(30, 34)

    def test_apagado_menor_que_encendido_se_rechaza(self):
        with self.assertRaises(ValueError):
            validar_umbrales(50, 40)

    def test_fuera_de_rango_se_rechaza(self):
        with self.assertRaises(ValueError):
            validar_umbrales(96, 100)  # encendido maximo es 95
        with self.assertRaises(ValueError):
            validar_umbrales(0, 4)     # apagado minimo es 5


class DecidirEncendidaTests(unittest.TestCase):
    def test_automatico_enciende_bajo_umbral_encendido(self):
        self.assertTrue(decidir_encendida(MODO_AUTOMATICO, 10, False, 30, 45))

    def test_automatico_apaga_sobre_umbral_apagado(self):
        self.assertFalse(decidir_encendida(MODO_AUTOMATICO, 80, True, 30, 45))

    def test_automatico_en_zona_de_histeresis_conserva_estado(self):
        # Entre 30 y 45 no cambia nada: evita el parpadeo cerca del umbral.
        self.assertTrue(decidir_encendida(MODO_AUTOMATICO, 38, True, 30, 45))
        self.assertFalse(decidir_encendida(MODO_AUTOMATICO, 38, False, 30, 45))

    def test_automatico_sin_estado_previo_en_histeresis_queda_apagada(self):
        self.assertFalse(decidir_encendida(MODO_AUTOMATICO, 38, None, 30, 45))

    def test_forzados_ignoran_la_luz(self):
        self.assertTrue(decidir_encendida(MODO_ENCENDIDO, 100, False, 30, 45))
        self.assertFalse(decidir_encendida(MODO_APAGADO, 0, True, 30, 45))

    def test_modo_invalido_se_rechaza(self):
        with self.assertRaises(ValueError):
            decidir_encendida("Turbo", 10, False, 30, 45)


class ControlIluminacionTests(unittest.TestCase):
    def setUp(self):
        self.enviados = []
        self.auditoria = []
        self.control = ControlIluminacion(
            enviar=lambda nombre, target, params: self.enviados.append((nombre, target, params)),
            auditar=self.auditoria.append,
        )

    def test_primera_lectura_siempre_manda_un_comando(self):
        self.control.procesar_lectura(80)  # luz alta: apagada
        self.assertEqual(self.enviados, [("IluminacionApagar", "MEGA_GRUA", {"modo": "Automatico"})])

    def test_no_repite_el_comando_si_el_estado_no_cambia(self):
        self.control.procesar_lectura(80)
        self.control.procesar_lectura(90)
        self.control.procesar_lectura(70)
        self.assertEqual(len(self.enviados), 1)

    def test_enciende_al_oscurecer_y_apaga_al_aclarar(self):
        self.control.procesar_lectura(80)   # apagada
        self.control.procesar_lectura(10)   # oscurece
        self.control.procesar_lectura(40)   # histeresis: sigue encendida
        self.control.procesar_lectura(60)   # aclara
        nombres = [n for n, _, _ in self.enviados]
        self.assertEqual(nombres, ["IluminacionApagar", "IluminacionEncender", "IluminacionApagar"])

    def test_cubrir_y_descubrir_el_sensor_no_parpadea(self):
        # Escenario E05: una lectura en la zona intermedia no debe provocar comandos extra.
        self.control.procesar_lectura(10)
        for nivel in (38, 40, 42, 38, 41):
            self.control.procesar_lectura(nivel)
        self.assertEqual(len(self.enviados), 1)

    def test_cambio_a_encendido_forzado_manda_encender_y_se_audita(self):
        self.control.procesar_lectura(80)
        self.control.cambiar_modo(MODO_ENCENDIDO, origen="TERMINAL")
        self.assertEqual(self.enviados[-1], ("IluminacionEncender", "MEGA_GRUA", {"modo": MODO_ENCENDIDO}))
        self.assertEqual(self.auditoria[-1]["nuevo"], MODO_ENCENDIDO)
        self.assertEqual(self.auditoria[-1]["anterior"], MODO_AUTOMATICO)

    def test_forzado_ignora_lecturas_de_luz(self):
        self.control.cambiar_modo(MODO_APAGADO)
        self.control.procesar_lectura(0)
        self.assertEqual([n for n, _, _ in self.enviados], ["IluminacionApagar"])

    def test_volver_a_automatico_no_manda_nada_hasta_la_siguiente_lectura(self):
        self.control.cambiar_modo(MODO_ENCENDIDO)
        cantidad = len(self.enviados)
        self.control.cambiar_modo(MODO_AUTOMATICO)
        self.assertEqual(len(self.enviados), cantidad)
        self.control.procesar_lectura(90)
        self.assertEqual(self.enviados[-1][0], "IluminacionApagar")

    def test_umbrales_invalidos_no_se_aplican(self):
        with self.assertRaises(ValueError):
            self.control.cambiar_umbrales(30, 32)
        self.assertEqual((self.control.umbral_encendido, self.control.umbral_apagado), (30, 45))

    def test_resincronizar_en_automatico_espera_la_siguiente_lectura(self):
        self.control.procesar_lectura(80)   # apagada
        self.control.resincronizar()        # el Mega encendio sola al perder enlace
        self.assertEqual(len(self.enviados), 1)
        self.control.procesar_lectura(80)   # ahora si se reenvia el estado real
        self.assertEqual(self.enviados[-1][0], "IluminacionApagar")
        self.assertEqual(len(self.enviados), 2)

    def test_resincronizar_en_forzado_reenvia_el_estado_del_modo(self):
        self.control.cambiar_modo(MODO_APAGADO)
        self.control.resincronizar()
        self.assertEqual([n for n, _, _ in self.enviados], ["IluminacionApagar", "IluminacionApagar"])

    def test_construir_con_umbrales_invalidos_falla(self):
        with self.assertRaises(ValueError):
            ControlIluminacion(enviar=lambda *a: None, umbral_encendido=50, umbral_apagado=50)

    # Sec. 4.2 regla 2: iluminacion previa a la captura de placa.
    def test_para_captura_enciende_si_estaba_apagada_y_restaura_en_automatico(self):
        self.control.procesar_lectura(80)   # luz alta -> apagada
        self.enviados.clear()
        esperas = []
        with self.control.para_captura(espera_s=1.0, dormir=esperas.append):
            # dentro de la captura la tira esta encendida y ya se espero 1 s
            self.assertEqual(esperas, [1.0])
            self.assertEqual(self.enviados[-1][0], "IluminacionEncender")
        # al salir, en Automatico se devuelve a apagada (la siguiente lectura la ajusta)
        self.assertEqual(self.enviados[-1][0], "IluminacionApagar")

    def test_para_captura_no_apaga_si_el_modo_es_encendido_forzado(self):
        self.control.cambiar_modo(MODO_ENCENDIDO)  # queda encendida
        self.enviados.clear()
        with self.control.para_captura(espera_s=1.0, dormir=lambda s: None):
            pass
        # no estaba apagada, el modo es Encendido forzado: nunca manda IluminacionApagar
        self.assertNotIn("IluminacionApagar", [n for n, _, _ in self.enviados])


if __name__ == "__main__":
    unittest.main()
