"""Comparacion de placas (Fase 3) sin camara ni Mongo.

    cd backend
    .venv/bin/python3 -m unittest test_vision -v
"""

import unittest

from sqlalchemy import select

import servicios
from models import Alarma, PlacaRestringida, Vehiculo
from test_orquestador import UID_OK, MaquetaBase


class PlacaTextoTests(unittest.TestCase):
    def test_normaliza_espacios_guion_y_minusculas(self):
        self.assertEqual(servicios.normalizar_placa("c 001"), "C001")
        self.assertEqual(servicios.normalizar_placa("C-001"), "C001")
        self.assertEqual(servicios.normalizar_placa("C123BCD"), "C123BCD")

    def test_un_caracter_de_diferencia(self):
        self.assertTrue(servicios._un_caracter("C001", "C001"))
        self.assertTrue(servicios._un_caracter("C001", "C002"))
        self.assertTrue(servicios._un_caracter("C001", "C01"))
        self.assertFalse(servicios._un_caracter("C001", "X999"))

    def test_coincidencia_exacta_o_unica_cercana(self):
        cat = ["C001", "C123BCD"]
        self.assertEqual(servicios.coincidencia_placa("C-001", cat), "C001")
        self.assertEqual(servicios.coincidencia_placa("C123BCE", cat), "C123BCD")
        self.assertIsNone(servicios.coincidencia_placa("Z999", cat))


class EvaluarIngresoTests(MaquetaBase):
    def setUp(self):
        super().setUp()
        with self.Session() as db:
            db.get(Vehiculo, UID_OK).placa = "C-001"
            db.commit()

    def test_placa_que_coincide_pasa(self):
        with self.Session() as db:
            self.assertIsNone(servicios.evaluar_placa_ingreso(db, UID_OK, "C-001", 0.9))

    def test_placa_ajena_no_corresponde(self):
        with self.Session() as db:
            self.assertEqual(servicios.evaluar_placa_ingreso(db, UID_OK, "Z999", 0.9), "placa_no_corresponde")
            self.assertTrue(any(a.codigo == "AL20" for a in db.scalars(select(Alarma)).all()))

    def test_restringida(self):
        with self.Session() as db:
            db.add(PlacaRestringida(placa="C-001", motivo="prueba"))
            db.commit()
            self.assertEqual(servicios.evaluar_placa_ingreso(db, UID_OK, "C001", 0.95), "placa_restringida")

    def test_ocr_bajo_pide_manual(self):
        with self.Session() as db:
            self.assertEqual(servicios.evaluar_placa_ingreso(db, UID_OK, "C-001", 0.2), "placa_no_leida")
