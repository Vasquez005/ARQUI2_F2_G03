"""Pruebas de la fase 5 sin MQTT ni Arduinos: ciclos de grua, inventario con
remocion, cola de trabajos, las 8 metricas del reporte y las rutas de
naviera / agente / autoridad.

    cd backend
    .venv/bin/python3 -m unittest test_grua -v
"""

import json
import os
import tempfile
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

import grua
import reportes
import servicios
from models import (
    Cita, ContenedorCatalogo, GruaCiclo, Manifiesto, PosicionPatio, Retencion, Turno, TurnoEstado, Usuario,
    Vehiculo,
)
from test_orquestador import UID_FUERA, UID_OK, MaquetaBase

_fd, _DB_IMPORT = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PORTUS_DB_PATH"] = _DB_IMPORT
import app  # noqa: E402

UID_RETIRO = "E1 67 7F 15"


class GruaTests(MaquetaBase):
    def setUp(self):
        super().setUp()
        app.SessionLocal = self.Session
        app.mqttc.publish = lambda t, p: self.enviados.append(json.loads(p))
        with self.Session() as db:
            for i in range(1, 9):
                db.add(ContenedorCatalogo(contenedor_id=f"MSCU{i:07d}"))
            db.add(Usuario(username="naviera1", password_hash="x", rol="NAVIERA", nombre="Naviera Uno"))
            db.add(Usuario(username="naviera2", password_hash="x", rol="NAVIERA", nombre="Naviera Dos"))
            db.commit()

    # ── ayudas ──
    def patio(self, pos):
        with self.Session() as db:
            return db.get(PosicionPatio, pos)

    def ciclos(self):
        with self.Session() as db:
            return db.scalars(select(GruaCiclo).order_by(GruaCiclo.id)).all()

    def linea_de_tiempo(self, uid):
        return [e["descripcion"] for e in app.detalle_turno(self.turno(uid).id)["lineaDeTiempo"]]

    def hasta_en_ruta(self, uid=UID_OK):
        self.evento("garita", evento="rfid", uid=uid)
        self.evento("pesaje", evento="meseta", resultado="ok", uid=uid)

    def ciclo_completo(self, op, pos, ms=15000, tramos=2):
        self.evento("transferencia", evento="alineado")
        self.evento("grua", evt="trabajo_inicio", op=op, pos=str(pos))
        self.evento("patio", evento="deposito" if op == "DEPOSITO" else "retiro", pos=str(pos))
        self.evento("grua", evt="trabajo_fin", op=op, pos=str(pos), ms=str(ms), tramos=str(tramos))

    def preparar_retiro(self, apilar_encima=True):
        """MSCU0000002 en P1 nivel 1 (y otro encima) con manifiesto de RETIRO para UID_RETIRO."""
        with self.Session() as db:
            t = db.scalars(select(Manifiesto)).first().transportista_id
            db.add(Vehiculo(uid=UID_RETIRO, transportista_id=t))
            db.add(Manifiesto(contenedor_id="MSCU0000002", tipo_operacion="RETIRO", peso_declarado_g=1200,
                              transportista_id=t, vehiculo_uid=UID_RETIRO,
                              estado_documental="levante_otorgado", canal="verde"))
            servicios.confirmar_deposito_patio(db, 1, "MSCU0000002")
            if apilar_encima:
                servicios.confirmar_deposito_patio(db, 1, "MSCU0000009")
            db.commit()

    # ── Ciclo de deposito ──
    def test_deposito_con_grua_de_punta_a_punta(self):
        self.hasta_en_ruta()
        trabajo = self.comandos("TrabajoGrua")
        self.assertEqual(trabajo[0]["params"], {"op": "DEPOSITO", "pos": 1})  # politica secuencial: P1
        self.assertEqual(self.patio(1).estado, "RESERVADA")

        self.ciclo_completo("DEPOSITO", 1, ms=15300, tramos=2)
        p1 = self.patio(1)
        self.assertEqual((p1.estado, p1.contenedor_nivel1), ("OCUPADA_1", "MSCU0000001"))
        ciclo = self.ciclos()[0]
        self.assertEqual((ciclo.resultado, ciclo.duracion_ms, ciclo.tramos), ("completado", 15300, 2))
        self.assertEqual(self.turno(UID_OK).estado, "EnTransferencia")
        self.assertEqual(self.turno(UID_OK).posicion_patio, 1)

        self.evento("salida", evento="rfid_salida", uid=UID_OK)
        self.evento("salida", evento="salida_completada", uid=UID_OK)
        self.assertEqual(self.turno(UID_OK).estado, "Cerrado")
        linea = self.linea_de_tiempo(UID_OK)
        for texto in ("Trabajo enviado a la grua: DEPOSITO P1", "Vehiculo alineado en la transferencia",
                      "Transferencia iniciada: DEPOSITO en P1", "Contenedor MSCU0000001 depositado en P1 nivel 1",
                      "Transferencia completada (15.3 s, 2 tramos)"):
            self.assertIn(texto, linea)

    def test_la_cola_manda_un_trabajo_a_la_vez(self):
        with self.Session() as db:
            m = db.scalars(select(Manifiesto).where(Manifiesto.vehiculo_uid == UID_FUERA)).one()
            m.peso_declarado_g = 1500
            db.commit()
        self.hasta_en_ruta(UID_OK)
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="ok", uid=UID_FUERA)
        self.assertEqual(len(self.comandos("TrabajoGrua")), 1)
        self.ciclo_completo("DEPOSITO", 1)
        trabajos = self.comandos("TrabajoGrua")
        self.assertEqual(len(trabajos), 2)
        self.assertEqual(trabajos[1]["params"], {"op": "DEPOSITO", "pos": 2})

    def test_aborto_no_toca_el_inventario_y_la_grua_reintenta(self):
        self.hasta_en_ruta()
        self.evento("grua", evt="trabajo_inicio", op="DEPOSITO", pos="1")
        self.evento("transferencia", evento="aborto", causa="camion_movido")
        ciclo = self.ciclos()[0]
        self.assertEqual((ciclo.resultado, ciclo.causa), ("abortado", "camion_movido"))
        self.assertEqual(self.patio(1).estado, "LIBRE")
        self.assertIsNone(self.patio(1).contenedor_nivel1)
        self.assertIn("Transferencia abortada: camion_movido", self.linea_de_tiempo(UID_OK))

        self.ciclo_completo("DEPOSITO", 1)  # reintento con el mismo turno
        ciclos = self.ciclos()
        self.assertEqual([c.resultado for c in ciclos], ["abortado", "completado"])
        self.assertEqual({c.turno_id for c in ciclos}, {self.turno(UID_OK).id})
        self.assertEqual(self.patio(1).contenedor_nivel1, "MSCU0000001")

    def test_rechazo_de_trabajo_en_mantenimiento_vuelve_a_la_cola(self):
        self.hasta_en_ruta()
        with self.Session() as db:
            servicios.registrar_respuesta_comando(db, "MEGA_GRUA", "REJ",
                                                  {"name": "TrabajoGrua", "causa": "modo_mantenimiento"}, "{}")
            db.commit()
            self.assertIsNone(db.get(Turno, self.turno(UID_OK).id).trabajo_grua_at)
            self.assertEqual(db.get(PosicionPatio, 1).estado, "LIBRE")
            enviados = []
            grua.despachar_trabajo(db, lambda n, t, p: enviados.append((n, p)))
            self.assertEqual(enviados, [("TrabajoGrua", {"op": "DEPOSITO", "pos": 1})])

    # ── Retiro con remocion (E15) ──
    def test_retiro_con_remocion_mueve_el_de_arriba_y_lo_registra(self):
        self.preparar_retiro()
        self.hasta_en_ruta(UID_RETIRO)
        self.assertEqual(self.comandos("TrabajoGrua")[0]["params"], {"op": "RETIRO", "pos": 1})
        self.ciclo_completo("RETIRO", 1)

        p1, p2 = self.patio(1), self.patio(2)
        self.assertEqual((p1.contenedor_nivel1, p1.contenedor_nivel2, p1.estado), (None, None, "LIBRE"))
        self.assertEqual(p1.remociones, 1)
        self.assertEqual(p2.contenedor_nivel1, "MSCU0000009")
        tipos = [(c.tipo, c.contenedor_id, c.posicion_destino) for c in self.ciclos()]
        self.assertIn(("REMOCION", "MSCU0000009", 2), tipos)
        linea = self.linea_de_tiempo(UID_RETIRO)
        self.assertIn("Remocion: MSCU0000009 de P1 nivel 2 a P2", linea)
        self.assertIn("Contenedor MSCU0000002 retirado de P1 nivel 1", linea)

    def test_retiro_del_de_arriba_no_es_remocion(self):
        self.preparar_retiro(apilar_encima=False)
        with self.Session() as db:
            servicios.confirmar_deposito_patio(db, 1, "MSCU0000009")  # ahora MSCU0000002 queda abajo...
            p = db.get(PosicionPatio, 1)
            p.contenedor_nivel1, p.contenedor_nivel2 = "MSCU0000009", "MSCU0000002"  # ...y se invierte
            db.commit()
        self.hasta_en_ruta(UID_RETIRO)
        self.ciclo_completo("RETIRO", 1)
        self.assertEqual(self.patio(1).remociones, 0)
        self.assertEqual(self.patio(1).contenedor_nivel1, "MSCU0000009")
        self.assertNotIn("REMOCION", [c.tipo for c in self.ciclos()])

    def test_retiro_de_otra_posicion_genera_al07(self):
        self.preparar_retiro(apilar_encima=False)
        self.hasta_en_ruta(UID_RETIRO)
        self.evento("grua", evt="trabajo_inicio", op="RETIRO", pos="3")
        self.evento("patio", evento="retiro", pos="3")
        self.assertIn("AL07", [a["codigo"] for a in app.listar_alarmas()])

    # ── Rutas de la grua ──
    def test_historial_de_ciclos_y_csv(self):
        self.hasta_en_ruta()
        self.ciclo_completo("DEPOSITO", 1, ms=10000)
        datos = app.ciclos_grua(limit=50)
        self.assertEqual((datos["completados"], datos["promedioS"]), (1, 10.0))
        with self.assertRaises(HTTPException):
            app.ciclos_grua(limit=30)
        csv = app.ciclos_grua_csv(limit=50).body.decode()
        self.assertIn("DEPOSITO", csv)
        self.assertIn("10.0", csv)
        estado = app.estado_grua()
        self.assertIsNone(estado["trabajoEnCurso"])
        self.assertEqual(estado["politicaPatio"], "secuencial")

    def test_politica_de_patio_seleccionable(self):
        self.assertEqual(app.ver_politica_patio()["politica"], "secuencial")
        with self.assertRaises(HTTPException):
            app.cambiar_politica_patio(app.PoliticaIn(politica="inventada"))

    # ── Reporte de corrida (sec. 13) ──
    def test_reporte_con_las_ocho_metricas(self):
        ahora = datetime.utcnow()
        self.preparar_retiro()
        self.hasta_en_ruta(UID_RETIRO)
        self.hasta_en_ruta(UID_OK)  # dos en espera a la vez -> fila maxima 2
        self.ciclo_completo("RETIRO", 1, ms=20000, tramos=2)
        self.evento("salida", evento="rfid_salida", uid=UID_RETIRO)
        self.evento("salida", evento="salida_completada", uid=UID_RETIRO)
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        with self.Session() as db:
            r = db.scalars(select(Retencion)).one()
            servicios.resolver_retencion(db, r.id, "corregir", "TERMINAL")
            db.add(Cita(contenedor_id="MSCU0000001", inicio=ahora, fin=ahora, estado="cumplida"))
            db.add(Cita(contenedor_id="MSCU0000003", inicio=ahora, fin=ahora, estado="vencida"))
            db.add(Cita(contenedor_id="MSCU0000002", inicio=ahora, fin=ahora, estado="cancelada"))
            db.commit()

        desde = servicios.hora_local(ahora - timedelta(minutes=5), "%Y-%m-%dT%H:%M")
        hasta = servicios.hora_local(ahora + timedelta(minutes=5), "%Y-%m-%dT%H:%M")
        corrida = app.generar_reporte(app.ReporteIn(desde=desde, hasta=hasta, etiqueta="corrida de evaluacion"))
        m = corrida["metricas"]
        self.assertEqual(m["remocionesPorRetiro"], {"valor": 1.0, "remociones": 1, "retirosCompletados": 1})
        self.assertEqual(m["ciclosPorOperacion"]["ciclos"], 2)  # el retiro y su remocion
        self.assertEqual(m["ciclosPorOperacion"]["valor"], 2.0)
        self.assertEqual(m["distanciaGrua"]["tramos"], 3)  # 2 del retiro + 1 de la remocion P1->P2
        self.assertEqual(m["tiempoPromedioCamionS"]["turnosCerrados"], 1)
        self.assertEqual(m["tiempoPromedioRetencionS"]["retencionesResueltas"], 1)
        self.assertEqual(m["filaMaxima"]["valor"], 2)
        self.assertEqual(m["citasCumplidasPct"], {"valor": 50.0, "cumplidas": 1, "total": 2})
        self.assertEqual(m["retencionesPorCausa"], {"RT01": {"corregir": 1}})

        self.assertEqual(app.listar_reportes()[0]["etiqueta"], "corrida de evaluacion")
        csv = app.reporte_csv(corrida["id"]).body.decode()
        self.assertIn("Longitud maxima de la fila de espera,2", csv)
        self.assertIn("Retenciones RT01,1,corregir=1", csv)
        self.assertIn("Detalle de turnos", csv)
        self.assertIn(UID_RETIRO, csv)

    def test_reporte_rechaza_rango_invertido(self):
        with self.assertRaises(HTTPException):
            app.generar_reporte(app.ReporteIn(desde="2026-09-25T10:00", hasta="2026-09-25T09:00", etiqueta="x"))

    def test_historial_de_estados_del_turno(self):
        self.hasta_en_ruta()
        with self.Session() as db:
            estados = [e.estado for e in db.scalars(select(TurnoEstado).order_by(TurnoEstado.id)).all()]
        self.assertEqual(estados, ["EnGarita", "EnPesajeEntrada", "EnRuta"])

    # ── Naviera, agente y autoridad (5.5 y 5.6) ──
    def test_manifiesto_solo_con_contenedores_del_catalogo(self):
        base = dict(tipo_operacion="DEPOSITO", peso_declarado_g=900, transportista_id=1)
        with self.assertRaises(HTTPException) as ctx:
            app.crear_manifiesto(app.ManifiestoIn(contenedor_id="CONT-XYZ", **base))
        self.assertEqual(ctx.exception.detail, "contenedor_no_existe_en_el_catalogo_de_la_maqueta")
        res = app.crear_manifiesto(app.ManifiestoIn(contenedor_id="mscu0000005", **base))
        self.assertEqual(app.detalle_manifiesto(res["id"])["contenedorId"], "MSCU0000005")

    def test_declaracion_con_numero_repetido_se_rechaza(self):
        ids = []
        for c in ("MSCU0000005", "MSCU0000006"):
            ids.append(app.crear_manifiesto(app.ManifiestoIn(contenedor_id=c, tipo_operacion="DEPOSITO",
                                                             peso_declarado_g=900, transportista_id=1))["id"])
        decl = dict(numero_declaracion="DECL-1", regimen="deposito_temporal",
                    descripcion="Mercancia de prueba", valor_declarado=10)
        app.presentar_declaracion(app.DeclaracionIn(manifiesto_id=ids[0], **decl))
        with self.assertRaises(HTTPException) as ctx:
            app.presentar_declaracion(app.DeclaracionIn(manifiesto_id=ids[1], **decl))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_historial_del_manifiesto_conserva_el_peso_anterior(self):
        self.evento("garita", evento="rfid", uid=UID_FUERA)
        self.evento("pesaje", evento="meseta", resultado="fuera_tolerancia", uid=UID_FUERA)
        with self.Session() as db:
            r = db.scalars(select(Retencion)).one()
            servicios.resolver_retencion(db, r.id, "corregir", "TERMINAL")
            db.commit()
        manifiesto_id = self.turno(UID_FUERA).manifiesto_id
        app.adjuntar_observacion(manifiesto_id, app.ObservacionManifiestoIn(texto="Revisar sellos"))
        detalle = app.detalle_manifiesto(manifiesto_id)
        self.assertEqual((detalle["pesoDeclaradoG"], detalle["pesoDeclaradoAnteriorG"]), (2250, 1500))
        textos = [h["descripcion"] for h in detalle["historial"]]
        self.assertTrue(any("de 1500 g a 2250 g" in t for t in textos))
        self.assertEqual([o["descripcion"] for o in detalle["observacionesAgente"]], ["Revisar sellos"])
        self.assertEqual(len(detalle["turnos"]), 1)

    def test_seguimiento_y_carga_con_motivo_de_retencion(self):
        with self.Session() as db:
            n1, n2 = (u.id for u in db.scalars(select(Usuario).order_by(Usuario.id)).all())
        mid = app.crear_manifiesto(app.ManifiestoIn(contenedor_id="MSCU0000005", tipo_operacion="DEPOSITO",
                                                    peso_declarado_g=900, transportista_id=1,
                                                    naviera_usuario_id=n1))["id"]
        app.crear_manifiesto(app.ManifiestoIn(contenedor_id="MSCU0000006", tipo_operacion="DEPOSITO",
                                              peso_declarado_g=900, transportista_id=1, naviera_usuario_id=n2))
        app.presentar_declaracion(app.DeclaracionIn(manifiesto_id=mid, numero_declaracion="DECL-9",
                                                    regimen="deposito_temporal", descripcion="Mercancia general",
                                                    valor_declarado=10, agente_usuario_id=7))
        app.solicitar_levante(mid)
        app.resolver_levante(mid, app.LevanteIn(otorgar=False, motivo_retencion="Falta factura"))

        seguimiento = app.seguimiento_declaraciones(agente_usuario_id=7)
        self.assertEqual((seguimiento[0]["situacion"], seguimiento[0]["motivoRetencion"]), ("retenida", "Falta factura"))
        self.assertEqual(app.seguimiento_declaraciones(agente_usuario_id=7, q="decl-9")[0]["numeroDeclaracion"], "DECL-9")
        self.assertEqual(app.seguimiento_declaraciones(agente_usuario_id=8), [])

        propios = app.consulta_carga(naviera_usuario_id=n1)
        self.assertEqual([c["contenedorId"] for c in propios], ["MSCU0000005"])  # sec. 5.2: no ve la otra naviera
        self.assertEqual(propios[0]["ubicacion"], "Fuera de la terminal")
        todos = app.consulta_carga(naviera="dos")
        self.assertEqual([c["contenedorId"] for c in todos], ["MSCU0000006"])
        self.assertEqual(len(app.consulta_carga(estado_documental="levante_retenido")), 1)

    def test_carga_en_patio_con_permanencia(self):
        self.hasta_en_ruta()
        self.ciclo_completo("DEPOSITO", 1)
        fila = next(c for c in app.consulta_carga() if c["contenedorId"] == "MSCU0000001")
        self.assertEqual(fila["ubicacion"], "Patio P1 nivel 1")
        self.assertEqual(fila["estadoOperativo"], "Turno EnTransferencia")  # el camion aun no sale
        self.assertIsNotNone(fila["enPatioDesde"])
        self.assertGreaterEqual(fila["permanenciaS"], 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
