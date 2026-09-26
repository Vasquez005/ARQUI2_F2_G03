"""Reportes de corrida (sec. 4.8 y 13) y consulta del estado de la carga
(sec. 5.2 Mis contenedores, 5.7 Consulta de carga).

Las 8 metricas se calculan sobre un rango [desde, hasta) en UTC:
  1. Remociones por contenedor retirado   5. Tiempo promedio de retencion
  2. Ciclos de grua por operacion          6. Longitud maxima de la fila de espera
  3. Distancia total de la grua            7. % de citas cumplidas en ventana
  4. Tiempo promedio de camion             8. Retenciones por causa y resolucion
"""

import csv
import io
from datetime import datetime
from typing import Optional

from sqlalchemy import select

import servicios
from catalogos import CERRADO, CM_POR_TRAMO, ESTADOS_EN_ESPERA, ESTADOS_FINALES
from models import (
    Cita, GruaCiclo, Manifiesto, PosicionPatio, Retencion, Transportista, Turno, TurnoEstado, Usuario,
)


def _promedio(valores: list) -> Optional[float]:
    return round(sum(valores) / len(valores), 1) if valores else None


def _cociente(a: int, b: int) -> Optional[float]:
    return round(a / b, 2) if b else None


def fila_maxima(db, desde: datetime, hasta: datetime) -> int:
    """Maximo de vehiculos en espera (ESTADOS_EN_ESPERA) al mismo tiempo en el
    rango, recorriendo el historial de estados de todos los turnos."""
    cambios = db.scalars(select(TurnoEstado).where(TurnoEstado.ts < hasta)
                         .order_by(TurnoEstado.ts, TurnoEstado.id)).all()
    estado_actual: dict = {}
    maximo = 0
    contado_inicio = False
    for cambio in cambios:
        if cambio.ts >= desde and not contado_inicio:
            maximo = sum(1 for e in estado_actual.values() if e in ESTADOS_EN_ESPERA)
            contado_inicio = True
        estado_actual[cambio.turno_id] = cambio.estado
        if cambio.ts >= desde:
            maximo = max(maximo, sum(1 for e in estado_actual.values() if e in ESTADOS_EN_ESPERA))
    if not contado_inicio:
        maximo = sum(1 for e in estado_actual.values() if e in ESTADOS_EN_ESPERA)
    return maximo


def calcular_metricas(db, desde: datetime, hasta: datetime, ahora: Optional[datetime] = None) -> dict:
    cerrados = db.scalars(select(Turno).where(Turno.estado == CERRADO, Turno.closed_at >= desde,
                                              Turno.closed_at < hasta)).all()
    retiros = [t for t in cerrados if t.tipo_operacion == "RETIRO"]
    ciclos = db.scalars(select(GruaCiclo).where(GruaCiclo.inicio >= desde, GruaCiclo.inicio < hasta)).all()
    completados = [c for c in ciclos if c.resultado == "completado"]
    remociones = [c for c in completados if c.tipo == "REMOCION"]
    tramos = sum(c.tramos or 0 for c in ciclos)

    retenciones = db.scalars(select(Retencion).where(Retencion.created_at >= desde,
                                                     Retencion.created_at < hasta)).all()
    resueltas = [r for r in retenciones if r.resolved_at is not None]
    por_causa: dict = {}
    for r in retenciones:
        grupo = por_causa.setdefault(r.causa, {})
        clave = r.resolucion or "abierta"
        grupo[clave] = grupo.get(clave, 0) + 1

    citas = [c for c in db.scalars(select(Cita).where(Cita.inicio >= desde, Cita.inicio < hasta)).all()
             if c.estado != "cancelada"]
    cumplidas = [c for c in citas if servicios.estado_cita(c, ahora) == "cumplida"]

    return {
        "remocionesPorRetiro": {"valor": _cociente(len(remociones), len(retiros)),
                                "remociones": len(remociones), "retirosCompletados": len(retiros)},
        "ciclosPorOperacion": {"valor": _cociente(len(completados), len(cerrados)),
                               "ciclos": len(completados), "turnosCerrados": len(cerrados)},
        "distanciaGrua": {"tramos": tramos, "cm": round(tramos * CM_POR_TRAMO, 1) if CM_POR_TRAMO else None},
        "tiempoPromedioCamionS": {"valor": _promedio([(t.closed_at - t.created_at).total_seconds() for t in cerrados]),
                                  "turnosCerrados": len(cerrados)},
        "tiempoPromedioRetencionS": {"valor": _promedio([(r.resolved_at - r.created_at).total_seconds()
                                                         for r in resueltas]),
                                     "retencionesResueltas": len(resueltas)},
        "filaMaxima": {"valor": fila_maxima(db, desde, hasta)},
        "citasCumplidasPct": {"valor": round(len(cumplidas) / len(citas) * 100, 1) if citas else None,
                              "cumplidas": len(cumplidas), "total": len(citas)},
        "retencionesPorCausa": por_causa,
    }


NOMBRES_METRICAS = (
    ("remocionesPorRetiro", "Remociones por contenedor retirado"),
    ("ciclosPorOperacion", "Ciclos de grua por operacion completada"),
    ("distanciaGrua", "Distancia total recorrida por la grua (tramos)"),
    ("tiempoPromedioCamionS", "Tiempo promedio de camion en la terminal (s)"),
    ("tiempoPromedioRetencionS", "Tiempo promedio de retencion (s)"),
    ("filaMaxima", "Longitud maxima de la fila de espera"),
    ("citasCumplidasPct", "Porcentaje de citas cumplidas en ventana"),
)


def detalle_turnos(db, desde: datetime, hasta: datetime) -> list:
    """Turnos creados en el rango, para el CSV (sec. 4.8: detalle de cada turno)."""
    nombres = {t.id: t.nombre for t in db.scalars(select(Transportista)).all()}
    turnos = db.scalars(select(Turno).where(Turno.created_at >= desde, Turno.created_at < hasta)
                        .order_by(Turno.id)).all()
    return [{
        "turno": t.id, "vehiculo": t.vehiculo_uid, "transportista": nombres.get(t.transportista_id),
        "contenedor": t.contenedor_id, "operacion": t.tipo_operacion, "estado": t.estado,
        "creado": servicios.hora_local(t.created_at, "%Y-%m-%d %H:%M:%S"),
        "cerrado": servicios.hora_local(t.closed_at, "%Y-%m-%d %H:%M:%S") if t.closed_at else "",
        "tiempo_s": int(((t.closed_at or datetime.utcnow()) - t.created_at).total_seconds()),
        "peso_declarado_g": t.peso_declarado_g, "peso_entrada_g": t.peso_medido_entrada_g,
        "peso_salida_g": t.peso_medido_salida_g, "posicion_patio": t.posicion_patio,
    } for t in turnos]


def csv_reporte(etiqueta: str, desde: datetime, hasta: datetime, politica: str,
                metricas: dict, turnos: list) -> str:
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["Reporte de corrida", etiqueta])
    w.writerow(["Desde", servicios.hora_local(desde, "%Y-%m-%d %H:%M")])
    w.writerow(["Hasta", servicios.hora_local(hasta, "%Y-%m-%d %H:%M")])
    w.writerow(["Politica de patio", politica])
    w.writerow([])
    w.writerow(["Metrica", "Valor", "Detalle"])
    for clave, nombre in NOMBRES_METRICAS:
        m = dict(metricas[clave])
        valor = m.pop("valor", m.pop("tramos", ""))
        w.writerow([nombre, "" if valor is None else valor,
                    "; ".join(f"{k}={v}" for k, v in m.items() if v is not None)])
    for causa, resoluciones in sorted(metricas["retencionesPorCausa"].items()):
        w.writerow([f"Retenciones {causa}", sum(resoluciones.values()),
                    "; ".join(f"{k}={v}" for k, v in sorted(resoluciones.items()))])
    w.writerow([])
    w.writerow(["Detalle de turnos"])
    columnas = ["turno", "vehiculo", "transportista", "contenedor", "operacion", "estado", "creado", "cerrado",
                "tiempo_s", "peso_declarado_g", "peso_entrada_g", "peso_salida_g", "posicion_patio"]
    w.writerow(columnas)
    for t in turnos:
        w.writerow(["" if t[c] is None else t[c] for c in columnas])
    return salida.getvalue()


def csv_ciclos(ciclos: list) -> str:
    salida = io.StringIO()
    w = csv.writer(salida)
    columnas = ["id", "tipo", "turno", "contenedor", "posicion", "posicion_destino", "resultado", "causa",
                "duracion_s", "tramos", "inicio", "fin"]
    w.writerow(columnas)
    for c in ciclos:
        w.writerow([c.id, c.tipo, c.turno_id or "", c.contenedor_id or "", c.posicion or "",
                    c.posicion_destino or "", c.resultado, c.causa or "",
                    "" if c.duracion_ms is None else round(c.duracion_ms / 1000, 1), c.tramos if c.tramos is not None else "",
                    servicios.hora_local(c.inicio, "%Y-%m-%d %H:%M:%S"),
                    servicios.hora_local(c.fin, "%Y-%m-%d %H:%M:%S") if c.fin else ""])
    return salida.getvalue()


# ══════════════════════════════════════════════════════════════════════════
#  Estado de la carga (naviera: solo lo propio; autoridad: todo)
# ══════════════════════════════════════════════════════════════════════════

def estado_operativo(db, m: Manifiesto) -> dict:
    """Donde esta y en que va el contenedor de un manifiesto."""
    turno = db.scalars(select(Turno).where(Turno.manifiesto_id == m.id).order_by(Turno.id.desc())).first()
    posicion = nivel = desde = None
    for p in db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all():
        if p.contenedor_nivel1 == m.contenedor_id:
            posicion, nivel, desde = p.id, 1, p.nivel1_desde
        elif p.contenedor_nivel2 == m.contenedor_id:
            posicion, nivel, desde = p.id, 2, p.nivel2_desde
    if m.anulado:
        estado = "Manifiesto anulado"
    elif turno is not None and turno.estado not in ESTADOS_FINALES:
        estado = f"Turno {turno.estado}"
    elif posicion is not None:
        estado = "En patio"
    elif turno is not None:
        estado = f"Turno {turno.estado}"
    else:
        estado = "Sin turno"
    if posicion is not None:
        ubicacion = f"Patio P{posicion} nivel {nivel}"
    elif turno is not None and turno.estado not in ESTADOS_FINALES:
        ubicacion = turno.estacion_actual or "-"
    else:
        ubicacion = "Fuera de la terminal"
    return {
        "estadoOperativo": estado, "ubicacion": ubicacion, "turnoId": turno.id if turno else None,
        "enPatioDesde": desde.isoformat() if desde else None,
        "permanenciaS": int((datetime.utcnow() - desde).total_seconds()) if desde else None,
    }


def estado_de_carga(db, naviera_usuario_id: Optional[int] = None, q: Optional[str] = None,
                    naviera: Optional[str] = None, estado_documental: Optional[str] = None) -> list:
    """Un renglon por contenedor (su manifiesto mas reciente)."""
    usuarios = {u.id: (u.nombre or u.username) for u in db.scalars(select(Usuario)).all()}
    query = select(Manifiesto).order_by(Manifiesto.id.desc())
    if naviera_usuario_id is not None:
        query = query.where(Manifiesto.naviera_usuario_id == naviera_usuario_id)
    vistos, filas = set(), []
    for m in db.scalars(query).all():
        if m.contenedor_id in vistos:
            continue
        vistos.add(m.contenedor_id)
        nombre_naviera = usuarios.get(m.naviera_usuario_id)
        if q and q.strip().upper() not in m.contenedor_id.upper():
            continue
        if naviera and naviera.strip().lower() not in (nombre_naviera or "").lower():
            continue
        if estado_documental and m.estado_documental != estado_documental:
            continue
        filas.append({"contenedorId": m.contenedor_id, "manifiestoId": m.id, "naviera": nombre_naviera,
                      "tipoOperacion": m.tipo_operacion, "estadoDocumental": m.estado_documental,
                      "canal": m.canal, "motivoLevante": m.motivo_levante, "anulado": m.anulado,
                      **estado_operativo(db, m)})
    return filas
