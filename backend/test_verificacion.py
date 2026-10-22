"""Pruebas de la verificacion en dos pasos (sec. 6 y 7). Sin base de datos ni MQTT.

    cd backend
    py -3 -m unittest test_verificacion -v
"""

import unittest

import verificacion as v

PROPIA = "C407BTJ"
OTRA = "C123BCD"
RESTRINGIDA = "C999XYZ"
CATALOGO = [PROPIA, OTRA]


def evaluar(**kw):
    base = dict(
        etiqueta_registrada=True, camara_ok=True, texto_leido=PROPIA, confianza_ocr=80, umbral_ocr=60,
        placa_registrada=PROPIA, restringidas=[], catalogo=CATALOGO,
    )
    base.update(kw)
    return v.evaluar_ingreso(**base)


class TablaCasosTests(unittest.TestCase):
    def test_etiqueta_registrada_y_placa_correcta_autoriza(self):
        d = evaluar()
        self.assertEqual(d.resultado, v.INGRESO_AUTORIZADO)
        self.assertEqual((d.linea1, d.linea2), ("PLACA VERIFICADA", PROPIA))

    def test_placa_de_otro_camion_genera_rt07_y_al20(self):
        d = evaluar(texto_leido=OTRA)
        self.assertEqual((d.resultado, d.causa, d.alarma), (v.RETENCION, v.RT07, "AL20"))
        self.assertEqual(d.linea1, "PLACA NO COINCIDE")

    def test_placa_restringida_genera_rt08_y_al21(self):
        d = evaluar(texto_leido=RESTRINGIDA, restringidas=[RESTRINGIDA], catalogo=CATALOGO + [RESTRINGIDA])
        self.assertEqual((d.resultado, d.causa, d.alarma), (v.RETENCION, v.RT08, "AL21"))
        self.assertEqual(d.linea1, "PLACA RESTRINGIDA")

    def test_etiqueta_desconocida_rechaza_sin_alarma(self):
        d = evaluar(etiqueta_registrada=False)
        self.assertEqual(d.resultado, v.RECHAZO)
        self.assertIsNone(d.alarma)
        self.assertEqual((d.linea1, d.linea2), ("ACCESO DENEGADO", "TARJETA NO REGISTRADA"))

    def test_etiqueta_desconocida_rechaza_aunque_la_placa_sea_valida(self):
        d = evaluar(etiqueta_registrada=False, texto_leido=PROPIA)
        self.assertEqual(d.resultado, v.RECHAZO)

    def test_sin_lectura_valida_pasa_a_verificacion_manual_con_al22(self):
        d = evaluar(texto_leido="ZZZZZZZ")
        self.assertEqual((d.resultado, d.alarma), (v.VERIFICACION_MANUAL, "AL22"))
        self.assertEqual((d.linea1, d.linea2), ("VERIFICACION MANUAL", "ESPERE AL OPERADOR"))

    def test_camara_fuera_de_servicio_entra_en_modo_degradado_con_al18(self):
        d = evaluar(camara_ok=False)
        self.assertEqual((d.resultado, d.alarma), (v.MODO_DEGRADADO, "AL18"))
        self.assertEqual((d.linea1, d.linea2), ("MODO DEGRADADO", "ESPERE AL OPERADOR"))


class RestriccionesTests(unittest.TestCase):
    def test_restringida_tiene_prioridad_sobre_placa_propia(self):
        d = evaluar(texto_leido=PROPIA, restringidas=[PROPIA])
        self.assertEqual(d.causa, v.RT08)

    def test_restringida_con_tarjeta_valida_se_retiene(self):
        d = evaluar(texto_leido=RESTRINGIDA, restringidas=[RESTRINGIDA], catalogo=CATALOGO)
        self.assertEqual(d.resultado, v.RETENCION)

    def test_quitar_restriccion_hace_que_la_placa_no_se_retenga(self):
        d = evaluar(texto_leido=RESTRINGIDA, restringidas=[], catalogo=CATALOGO)
        # Ya no esta en la lista: no coincide con nada conocido, asi que es verificacion manual.
        self.assertEqual(d.resultado, v.VERIFICACION_MANUAL)


class ToleranciaUnCaracterTests(unittest.TestCase):
    def test_un_caracter_de_diferencia_con_la_propia_autoriza(self):
        d = evaluar(texto_leido="C407BTK")
        self.assertEqual(d.resultado, v.INGRESO_AUTORIZADO)

    def test_ambiguedad_entre_dos_placas_no_coincide(self):
        # "C123BCE" difiere en un caracter de C123BCD y de C123BCF: no se acepta.
        d = evaluar(texto_leido="C123BCE", placa_registrada="C123BCD", catalogo=["C123BCD", "C123BCF"])
        self.assertEqual(d.resultado, v.VERIFICACION_MANUAL)

    def test_confianza_baja_no_es_valida(self):
        d = evaluar(confianza_ocr=40, umbral_ocr=60)
        self.assertEqual(d.resultado, v.VERIFICACION_MANUAL)

    def test_umbral_configurado_se_respeta(self):
        self.assertEqual(evaluar(confianza_ocr=40, umbral_ocr=30).resultado, v.INGRESO_AUTORIZADO)


class NormalizacionTests(unittest.TestCase):
    def test_ignora_espacios_y_mayusculas(self):
        self.assertEqual(v.normalizar("c 407 btj"), "C407BTJ")

    def test_a_un_caracter(self):
        self.assertTrue(v.a_un_caracter("ABC", "ABC"))
        self.assertTrue(v.a_un_caracter("ABC", "ABD"))
        self.assertTrue(v.a_un_caracter("ABC", "AB"))
        self.assertTrue(v.a_un_caracter("AB", "ABC"))
        self.assertFalse(v.a_un_caracter("ABC", "AXY"))
        self.assertFalse(v.a_un_caracter("ABC", "A"))

    def test_buscar_coincidencia_exacta_tiene_prioridad(self):
        self.assertEqual(v.buscar_coincidencia("c407btj", ["C407BTJ", "C407BTK"]), "C407BTJ")

    def test_texto_leyendo_placa(self):
        self.assertEqual(v.texto_lectura_en_curso("TAG-1"), ("LEYENDO PLACA", "TAG-1"))


if __name__ == "__main__":
    unittest.main()
