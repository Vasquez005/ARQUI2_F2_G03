"""Grua y patio (fase 5 del plan): trabajos, ciclos, inventario y remociones.

El Mega detecta el camion en la transferencia y mueve la grua; el servidor:
  - le asigna el trabajo (TrabajoGrua: DEPOSITO o RETIRO y la posicion que
    elige la politica de patio seleccionada, sec. 13),
  - abre y cierra el ciclo con trabajo_inicio / trabajo_fin / aborto,
  - actualiza el inventario solo cuando el Mega confirma el movimiento fisico
    (patio evento=deposito / evento=retiro, regla R09),
  - resuelve las remociones del retiro: en la maqueta hay un bloque por celda
    y el nivel 2 es logico (PORTUS_Fase2_Plan.md), asi que la remocion se
    registra en el servidor como un ciclo REMOCION.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select

import servicios
from catalogos import (
    EN_RUTA, EN_TRANSFERENCIA, POLITICA_PATIO_DEFAULT, POLITICAS_PATIO,
)
from models import Configuracion, GruaCiclo, PosicionPatio, Turno

PublishFn = servicios.PublishFn
_noop_publish = servicios._noop_publish


# ══════════════════════════════════════════════════════════════════════════
#  Politica de asignacion de posiciones (sec. 13, modo seleccionable)
# ══════════════════════════════════════════════════════════════════════════

def politica_patio(db) -> str:
    fila = db.get(Configuracion, "politica_patio")
    return fila.valor if fila and fila.valor in POLITICAS_PATIO else POLITICA_PATIO_DEFAULT


def cambiar_politica_patio(db, politica: str) -> None:
    if politica not in POLITICAS_PATIO:
        raise servicios.ReglaDeNegocioError("politica_desconocida")
    fila = db.get(Configuracion, "politica_patio") or Configuracion(clave="politica_patio")
    fila.valor = politica
    db.add(fila)


def _secuencial(posiciones: list, excluir: Optional[int]) -> Optional[PosicionPatio]:
    """Politica de la fase 1: la primera posicion libre en orden ascendente. Si
    todas tienen nivel 1, apila en la primera con el nivel 2 libre."""
    candidatas = [p for p in posiciones if p.id != excluir and p.estado != "BLOQUEADA"]
    for p in candidatas:
        if p.contenedor_nivel1 is None and p.estado == "LIBRE":
            return p
    for p in candidatas:
        if p.contenedor_nivel1 is not None and p.contenedor_nivel2 is None:
            return p
    return None


POLITICAS = {"secuencial": _secuencial}


def elegir_posicion(db, excluir: Optional[int] = None) -> Optional[PosicionPatio]:
    posiciones = db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all()
    return POLITICAS[politica_patio(db)](posiciones, excluir)


def ubicar_contenedor(db, contenedor_id: str) -> tuple:
    """(posicion, nivel) donde esta el contenedor en el inventario, o (None, None)."""
    for p in db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all():
        if p.contenedor_nivel1 == contenedor_id:
            return p, 1
        if p.contenedor_nivel2 == contenedor_id:
            return p, 2
    return None, None


# ══════════════════════════════════════════════════════════════════════════
#  Asignacion de trabajos a la grua
# ══════════════════════════════════════════════════════════════════════════

def ciclo_en_curso(db) -> Optional[GruaCiclo]:
    return db.scalars(select(GruaCiclo).where(GruaCiclo.resultado == "en_curso",
                                              GruaCiclo.tipo != "REMOCION")).first()


def despachar_trabajo(db, publish_cmd: PublishFn = _noop_publish) -> Optional[Turno]:
    """Manda TrabajoGrua para el turno mas antiguo que espera la grua, si la
    grua no tiene otro trabajo pendiente. El Mega guarda un solo trabajo."""
    if ciclo_en_curso(db) is not None:
        return None
    enviado = db.scalars(select(Turno).where(Turno.estado.in_((EN_RUTA, EN_TRANSFERENCIA)),
                                             Turno.trabajo_grua_at.is_not(None))).first()
    if enviado is not None:
        return None
    turno = db.scalars(select(Turno).where(Turno.estado == EN_RUTA).order_by(Turno.id)).first()
    if turno is None:
        return None

    params = {"op": turno.tipo_operacion}
    if turno.tipo_operacion == "DEPOSITO":
        destino = elegir_posicion(db)
        if destino is not None:
            params["pos"] = destino.id
            if destino.estado == "LIBRE":
                destino.estado = "RESERVADA"
                destino.updated_at = datetime.utcnow()
    else:
        posicion, _nivel = ubicar_contenedor(db, turno.contenedor_id)
        if posicion is not None:
            params["pos"] = posicion.id
    turno.trabajo_grua_at = datetime.utcnow()
    publish_cmd("TrabajoGrua", "MEGA_GRUA", params)
    destino_txt = f" P{params['pos']}" if "pos" in params else " (posicion la decide la grua)"
    servicios.registrar_evento(db, turno.id, "servidor",
                               f"Trabajo enviado a la grua: {turno.tipo_operacion}{destino_txt}",
                               {**params, "politica": politica_patio(db)})
    return turno


def trabajo_rechazado(db) -> None:
    """El Mega respondio REJ a TrabajoGrua (ej. modo mantenimiento): se vuelve a
    mandar cuando la grua lo admita (GruaReanudar / fin de mantenimiento)."""
    for turno in db.scalars(select(Turno).where(Turno.estado == EN_RUTA, Turno.trabajo_grua_at.is_not(None))).all():
        turno.trabajo_grua_at = None
        servicios.registrar_evento(db, turno.id, "controlador", "La grua no acepto el trabajo; queda en cola")
    for p in db.scalars(select(PosicionPatio).where(PosicionPatio.estado == "RESERVADA")).all():
        p.estado = "LIBRE"


# ══════════════════════════════════════════════════════════════════════════
#  Eventos del Mega
# ══════════════════════════════════════════════════════════════════════════

def _turno_para_trabajo(db, op: Optional[str]) -> Optional[Turno]:
    """El turno que esta en la transferencia: primero el que recibio el
    TrabajoGrua, si no el mas antiguo esperando la grua (grua en modo local)."""
    candidatos = db.scalars(select(Turno).where(Turno.estado.in_((EN_RUTA, EN_TRANSFERENCIA)))
                            .order_by(Turno.id)).all()
    abiertos = {c.turno_id for c in db.scalars(select(GruaCiclo).where(GruaCiclo.resultado == "en_curso")).all()}
    candidatos = [t for t in candidatos if t.id not in abiertos]
    for filtro in (lambda t: t.trabajo_grua_at is not None and t.tipo_operacion == op,
                   lambda t: t.tipo_operacion == op,
                   lambda t: True):
        elegidos = [t for t in candidatos if filtro(t)]
        if elegidos:
            return elegidos[0]
    return None


def turno_en_transferencia(db) -> Optional[Turno]:
    ciclo = ciclo_en_curso(db)
    if ciclo is not None and ciclo.turno_id is not None:
        return db.get(Turno, ciclo.turno_id)
    return _turno_para_trabajo(db, None)


def iniciar_ciclo(db, op: str, posicion: Optional[int]) -> GruaCiclo:
    turno = _turno_para_trabajo(db, op)
    ciclo = GruaCiclo(turno_id=turno.id if turno else None, tipo=op, posicion=posicion,
                      contenedor_id=turno.contenedor_id if turno else None)
    db.add(ciclo)
    if turno is not None:
        if turno.estado == EN_RUTA:
            servicios.transicionar_turno(db, turno, EN_TRANSFERENCIA, origen="controlador",
                                         descripcion=f"Transferencia iniciada: {op} en P{posicion}",
                                         valores={"posicion": posicion})
        else:
            servicios.registrar_evento(db, turno.id, "controlador",
                                       f"La grua reintenta la transferencia: {op} en P{posicion}")
        turno.estacion_actual = "transferencia"
        turno.posicion_patio = posicion
    db.flush()
    return ciclo


def confirmar_deposito(db, posicion: int) -> Optional[GruaCiclo]:
    """patio evento=deposito: el sensor de la celda confirmo el contenedor (R09)."""
    ciclo = ciclo_en_curso(db)
    if ciclo is None or ciclo.tipo != "DEPOSITO" or not ciclo.contenedor_id:
        return None
    p = db.get(PosicionPatio, posicion)
    if p is not None and p.estado == "RESERVADA":
        p.estado = "LIBRE"
    servicios.confirmar_deposito_patio(db, posicion, ciclo.contenedor_id)
    ciclo.posicion = posicion
    _, nivel = ubicar_contenedor(db, ciclo.contenedor_id)
    if ciclo.turno_id:
        servicios.registrar_evento(db, ciclo.turno_id, "controlador",
                                   f"Contenedor {ciclo.contenedor_id} depositado en P{posicion} nivel {nivel}",
                                   {"posicion": posicion, "nivel": nivel})
    return ciclo


def confirmar_retiro(db, posicion: int) -> Optional[GruaCiclo]:
    """patio evento=retiro: la grua tomo el contenedor de la celda. Si en el
    inventario habia otro encima, primero se registra su remocion."""
    ciclo = ciclo_en_curso(db)
    if ciclo is None or ciclo.tipo != "RETIRO" or not ciclo.contenedor_id:
        return None
    contenedor = ciclo.contenedor_id
    p, nivel = ubicar_contenedor(db, contenedor)
    if p is None:
        servicios.generar_alarma_unica(db, "AL07", f"contenedor:{contenedor}", origen="patio",
                                       descripcion=f"Retiro de {contenedor} en P{posicion}, pero no esta en el inventario",
                                       solo_activas=True)
        return ciclo
    if p.id != posicion:
        servicios.generar_alarma_unica(db, "AL07", f"contenedor:{contenedor}", origen="patio",
                                       descripcion=f"La grua retiro de P{posicion}; el inventario tenia {contenedor} en P{p.id}",
                                       solo_activas=True)
    if nivel == 1 and p.contenedor_nivel2:
        _remocion(db, ciclo, p)
    servicios.confirmar_remocion_patio(db, p.id)
    if ciclo.turno_id:
        servicios.registrar_evento(db, ciclo.turno_id, "controlador",
                                   f"Contenedor {contenedor} retirado de P{p.id} nivel {nivel}",
                                   {"posicion": p.id, "nivel": nivel})
    return ciclo


def _remocion(db, ciclo: GruaCiclo, origen: PosicionPatio) -> GruaCiclo:
    """Mueve el contenedor de arriba a otra posicion para liberar el de abajo."""
    encima = origen.contenedor_nivel2
    destino = elegir_posicion(db, excluir=origen.id)
    servicios.confirmar_remocion_patio(db, origen.id)  # quita el nivel 2
    origen.remociones += 1
    remocion = GruaCiclo(turno_id=ciclo.turno_id, tipo="REMOCION", contenedor_id=encima, posicion=origen.id,
                         resultado="completado", fin=datetime.utcnow(), duracion_ms=0)
    if destino is not None:
        servicios.confirmar_deposito_patio(db, destino.id, encima)
        remocion.posicion_destino = destino.id
        remocion.tramos = abs(destino.id - origen.id)
        texto = f"Remocion: {encima} de P{origen.id} nivel 2 a P{destino.id}"
    else:
        remocion.causa = "sin_posicion_libre"
        texto = f"Remocion: {encima} de P{origen.id} nivel 2 fuera del patio (no hay posicion libre)"
    db.add(remocion)
    if ciclo.turno_id:
        servicios.registrar_evento(db, ciclo.turno_id, "servidor", texto,
                                   {"contenedor": encima, "desde": origen.id,
                                    "hacia": remocion.posicion_destino})
    return remocion


def terminar_ciclo(db, duracion_ms: Optional[int], tramos: Optional[int],
                   publish_cmd: PublishFn = _noop_publish) -> Optional[GruaCiclo]:
    ciclo = ciclo_en_curso(db)
    if ciclo is None:
        return None
    ciclo.resultado = "completado"
    ciclo.fin = datetime.utcnow()
    ciclo.duracion_ms = duracion_ms
    ciclo.tramos = tramos
    turno = db.get(Turno, ciclo.turno_id) if ciclo.turno_id else None
    if turno is not None:
        turno.trabajo_grua_at = None
        segundos = f"{duracion_ms / 1000:.1f} s" if duracion_ms is not None else "-"
        servicios.registrar_evento(db, turno.id, "controlador",
                                   f"Transferencia completada ({segundos}, {tramos if tramos is not None else '-'} tramos)",
                                   {"duracion_ms": duracion_ms, "tramos": tramos})
        turno.estacion_actual = "ruta_salida"
    db.flush()
    despachar_trabajo(db, publish_cmd)
    return ciclo


def abortar_ciclo(db, causa: str) -> Optional[GruaCiclo]:
    """El Mega aborto: el inventario no cambia (R09) y el turno queda en la
    transferencia hasta que la grua reintente."""
    ciclo = ciclo_en_curso(db)
    if ciclo is None:
        return None
    ciclo.resultado = "abortado"
    ciclo.causa = causa
    ciclo.fin = datetime.utcnow()
    ciclo.duracion_ms = int((ciclo.fin - ciclo.inicio).total_seconds() * 1000)
    for p in db.scalars(select(PosicionPatio).where(PosicionPatio.estado == "RESERVADA")).all():
        p.estado = "LIBRE"
    if ciclo.turno_id:
        servicios.registrar_evento(db, ciclo.turno_id, "controlador", f"Transferencia abortada: {causa}",
                                   {"causa": causa})
    return ciclo


def ciclo_dict(c: GruaCiclo) -> dict:
    return {
        "id": c.id, "turnoId": c.turno_id, "tipo": c.tipo, "contenedorId": c.contenedor_id,
        "posicion": c.posicion, "posicionDestino": c.posicion_destino, "resultado": c.resultado,
        "causa": c.causa, "duracionMs": c.duracion_ms, "tramos": c.tramos,
        "inicio": c.inicio.isoformat(), "fin": c.fin.isoformat() if c.fin else None,
    }
