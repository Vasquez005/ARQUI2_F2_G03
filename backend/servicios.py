"""Logica de dominio de PORTUS Fase 2 (Observaciones_Backend_PersonaB.md, punto 1).

Cada funcion recibe la sesion de BD abierta y, cuando necesita comandar la
maqueta, un `publish_cmd(name, target, params)` inyectado desde app.py (para
no acoplar este modulo al cliente MQTT). Nada aqui asume una sesion HTTP real
todavia — eso sigue pendiente de Persona C.
"""

from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import select

from catalogos import (
    ANULADO, CATALOGO_ALARMAS, CERRADO, EN_GARITA,
    EN_PESAJE_ENTRADA, EN_PESAJE_SALIDA, EN_RUTA, EN_SALIDA, EN_TRANSFERENCIA,
    ESTADOS_FINALES, ROL_FACULTADO_POR_CAUSA, RESOLUCIONES, RETENIDO,
    RT01, RT02, RT03, RT04, SEVERIDADES_AUTO_RECONOCIBLES, TRANSICIONES,
)
from models import (
    Alarma, Cita, LinkDevice, Manifiesto, ParqueoPlaza, PosicionPatio,
    Retencion, Turno, EventoTurno,
)

PublishFn = Callable[[str, str, dict], None]


class ReglaDeNegocioError(Exception):
    """Un rechazo esperado del dominio (no autorizado, estado invalido, etc.)."""


def _noop_publish(name: str, target: str, params: dict) -> None:
    pass


# ══════════════════════════════════════════════════════════════════════════
#  Turnos y su linea de tiempo
# ══════════════════════════════════════════════════════════════════════════

def registrar_evento(db, turno_id: int, origen: str, descripcion: str, valores: Optional[dict] = None) -> None:
    import json
    db.add(EventoTurno(
        turno_id=turno_id, origen=origen, descripcion=descripcion,
        valores_json=json.dumps(valores or {}, ensure_ascii=False),
    ))


def transicionar_turno(db, turno: Turno, nuevo_estado: str, origen: str = "servidor",
                        descripcion: str = "", valores: Optional[dict] = None) -> None:
    permitidas = TRANSICIONES.get(turno.estado, ())
    if nuevo_estado not in permitidas and turno.estado not in ESTADOS_FINALES:
        # Los saltos que salen del flujo normal 
        # los arman las funciones de mas arriba explicitamente; esta funcion
        # solo bloquea transiciones que ni siquiera tienen sentido en el mapa.
        raise ReglaDeNegocioError(f"Transicion no permitida: {turno.estado} -> {nuevo_estado}")
    turno.estado = nuevo_estado
    if nuevo_estado in ESTADOS_FINALES:
        turno.closed_at = datetime.utcnow()
    registrar_evento(db, turno.id, origen, descripcion or f"Turno pasa a {nuevo_estado}", valores)


def notificar_transportista(db, turno: Turno, evento: str, detalle: Optional[dict] = None) -> None:
    """Persona D (bot) todavia no existe en este repo. Se deja constancia en la
    linea de tiempo del turno para que quede visible que "aqui debia salir una
    notificacion", en vez de fallar silenciosamente o inventar un canal."""
    registrar_evento(db, turno.id, "servidor",
                      f"[pendiente bot D] notificacion '{evento}' al transportista", detalle)


# ══════════════════════════════════════════════════════════════════════════
#  Patio (4 posiciones)
# ══════════════════════════════════════════════════════════════════════════

def asignar_posicion_patio(db) -> Optional[PosicionPatio]:
    """Politica secuencial (misma que Fase 1): la primera posicion libre en
    orden ascendente. Se deja como funcion aislada para que sea el "modo
    seleccionable" que el PDF exige conservar como linea base (sec. 13)."""
    posiciones = db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all()
    for p in posiciones:
        if p.estado == "LIBRE":
            p.estado = "RESERVADA"
            p.updated_at = datetime.utcnow()
            return p
    return None


def confirmar_deposito_patio(db, posicion_id: int, contenedor_id: str) -> None:
    p = db.get(PosicionPatio, posicion_id)
    if not p:
        raise ReglaDeNegocioError("posicion_invalida")
    if p.contenedor_nivel1 is None:
        p.contenedor_nivel1 = contenedor_id
        p.estado = "OCUPADA_1"
    elif p.contenedor_nivel2 is None:
        p.contenedor_nivel2 = contenedor_id
        p.estado = "OCUPADA_2"
    else:
        raise ReglaDeNegocioError("posicion_llena")
    p.updated_at = datetime.utcnow()


def confirmar_remocion_patio(db, posicion_id: int) -> Optional[str]:
    """Retira el contenedor del nivel superior presente. Devuelve su id."""
    p = db.get(PosicionPatio, posicion_id)
    if not p:
        raise ReglaDeNegocioError("posicion_invalida")
    if p.contenedor_nivel2 is not None:
        cid = p.contenedor_nivel2
        p.contenedor_nivel2 = None
        p.remociones += 1
        p.estado = "OCUPADA_1"
    elif p.contenedor_nivel1 is not None:
        cid = p.contenedor_nivel1
        p.contenedor_nivel1 = None
        p.estado = "LIBRE"
    else:
        raise ReglaDeNegocioError("posicion_vacia")
    p.updated_at = datetime.utcnow()
    return cid


def bloquear_posicion_patio(db, posicion_id: int) -> None:
    p = db.get(PosicionPatio, posicion_id)
    if not p:
        raise ReglaDeNegocioError("posicion_invalida")
    p.estado = "BLOQUEADA"
    p.updated_at = datetime.utcnow()


def liberar_posicion_patio(db, posicion_id: int) -> None:
    p = db.get(PosicionPatio, posicion_id)
    if not p:
        raise ReglaDeNegocioError("posicion_invalida")
    if p.estado != "BLOQUEADA":
        raise ReglaDeNegocioError("posicion_no_bloqueada")
    p.estado = "LIBRE" if not p.contenedor_nivel1 else "OCUPADA_1"
    p.updated_at = datetime.utcnow()


# ══════════════════════════════════════════════════════════════════════════
#  Parqueo de retencion (3 plazas logicas — sec. 8.1)
# ══════════════════════════════════════════════════════════════════════════

def asignar_plaza_parqueo(db, turno_id: int) -> Optional[int]:
    plazas = db.scalars(select(ParqueoPlaza).order_by(ParqueoPlaza.id)).all()
    for p in plazas:
        if not p.ocupada:
            p.ocupada = True
            p.turno_id = turno_id
            p.desde = datetime.utcnow()
            return p.id
    return None


def liberar_plaza_parqueo(db, plaza_id: int) -> None:
    p = db.get(ParqueoPlaza, plaza_id)
    if p:
        p.ocupada = False
        p.turno_id = None
        p.desde = None


def parqueo_lleno(db) -> bool:
    plazas = db.scalars(select(ParqueoPlaza)).all()
    return all(p.ocupada for p in plazas) and len(plazas) > 0


# ══════════════════════════════════════════════════════════════════════════
#  Alarmas (catalogo sec. 4.6)
# ══════════════════════════════════════════════════════════════════════════

def generar_alarma(db, codigo: str, origen: str = "", descripcion: Optional[str] = None) -> Alarma:
    if codigo not in CATALOGO_ALARMAS:
        raise ReglaDeNegocioError(f"codigo_alarma_desconocido:{codigo}")
    severidad, desc_default = CATALOGO_ALARMAS[codigo]
    alarma = Alarma(codigo=codigo, severidad=severidad, origen=origen,
                     descripcion=descripcion or desc_default, estado="activa")
    db.add(alarma)
    return alarma


def reconocer_alarma(db, alarma_id: int, comentario: Optional[str] = None) -> Alarma:
    alarma = db.get(Alarma, alarma_id)
    if not alarma:
        raise ReglaDeNegocioError("alarma_no_existe")
    alarma.estado = "reconocida"
    alarma.ack_at = datetime.utcnow()
    alarma.ack_comentario = comentario
    return alarma


def reconocer_todas_media_baja(db) -> int:
    activas = db.scalars(
        select(Alarma).where(Alarma.estado == "activa", Alarma.severidad.in_(SEVERIDADES_AUTO_RECONOCIBLES))
    ).all()
    for a in activas:
        a.estado = "reconocida"
        a.ack_at = datetime.utcnow()
    return len(activas)


# ══════════════════════════════════════════════════════════════════════════
#  Retenciones (RT01-RT06) y sus 3 resoluciones (sec. 8.2 / 8.3)
# ══════════════════════════════════════════════════════════════════════════

def crear_retencion(db, turno: Turno, causa: str, estado_resume: str, estacion: str = "",
                     peso_declarado_g: Optional[int] = None, peso_medido_g: Optional[int] = None,
                     publish_cmd: PublishFn = _noop_publish) -> Retencion:
    plaza = asignar_plaza_parqueo(db, turno.id)
    if plaza is None:
        generar_alarma(db, "AL11", origen="parqueo", descripcion="Parqueo de retencion lleno")

    retencion = Retencion(
        turno_id=turno.id, causa=causa, estacion=estacion, estado_anterior=estado_resume,
        plaza=plaza, peso_declarado_g=peso_declarado_g, peso_medido_g=peso_medido_g,
    )
    db.add(retencion)
    db.flush()  # para tener retencion.id antes de seguir

    transicionar_turno(db, turno, RETENIDO, origen="servidor",
                        descripcion=f"Retenido por {causa}",
                        valores={"causa": causa, "plaza": plaza})

    if plaza is not None:
        publish_cmd("AgujaParqueo", "MEGA_GRUA", {"plaza": plaza})

    notificar_transportista(db, turno, "retencion_generada",
                             {"causa": causa, "plaza": plaza, "peso_declarado_g": peso_declarado_g,
                              "peso_medido_g": peso_medido_g})
    return retencion


def resolver_retencion(db, retencion_id: int, resolucion: str, rol_usuario: str,
                        motivo: Optional[str] = None, observacion: Optional[str] = None,
                        publish_cmd: PublishFn = _noop_publish) -> Retencion:
    retencion = db.get(Retencion, retencion_id)
    if not retencion:
        raise ReglaDeNegocioError("retencion_no_existe")
    if retencion.estado != "abierta":
        raise ReglaDeNegocioError("retencion_ya_resuelta")
    if resolucion not in RESOLUCIONES:
        raise ReglaDeNegocioError("resolucion_invalida")

    rol_facultado = ROL_FACULTADO_POR_CAUSA[retencion.causa]
    if rol_usuario != rol_facultado:
        # Esta es la validacion que el PDF exige en servidor, no solo ocultando
        # el boton en la interfaz (sec. 2.3 y penalizaciones).
        raise PermissionError(f"rol_no_facultado: {rol_usuario} != {rol_facultado} para {retencion.causa}")

    if resolucion == "rechazar" and not motivo:
        raise ReglaDeNegocioError("motivo_obligatorio_para_rechazar")
    if resolucion == "corregir" and retencion.causa not in (RT01, RT02):
        raise ReglaDeNegocioError("corregir_solo_aplica_a_causas_de_peso")
    if resolucion == "corregir" and rol_usuario != "TERMINAL":
        raise ReglaDeNegocioError("corregir_es_exclusivo_de_terminal")

    turno = db.get(Turno, retencion.turno_id)
    if not turno:
        raise ReglaDeNegocioError("turno_no_existe")

    if retencion.plaza is not None:
        liberar_plaza_parqueo(db, retencion.plaza)
        publish_cmd("AgujaLiberar", "MEGA_GRUA", {"plaza": retencion.plaza})

    if resolucion == "rechazar":
        transicionar_turno(db, turno, ANULADO, origen="usuario",
                            descripcion=f"Turno anulado ({retencion.causa}): {motivo}",
                            valores={"motivo": motivo})
    else:
        if resolucion == "corregir":
            manifiesto = db.get(Manifiesto, turno.manifiesto_id) if turno.manifiesto_id else None
            if manifiesto is not None:
                manifiesto.peso_declarado_anterior_g = manifiesto.peso_declarado_g
                manifiesto.peso_declarado_g = retencion.peso_medido_g
            turno.peso_declarado_g = retencion.peso_medido_g
        turno.estado = retencion.estado_anterior  # continua el flujo, no pasa por transicionar_turno
        # (transicionar_turno valida el mapa "hacia adelante"; volver desde
        # Retenido es un caso especial de esta funcion, no del mapa general)
        registrar_evento(db, turno.id, "usuario",
                          f"Retencion {retencion.causa} resuelta con {resolucion}",
                          {"observacion": observacion})

    retencion.estado = "resuelta"
    retencion.resolucion = resolucion
    retencion.motivo = motivo
    retencion.observacion = observacion
    retencion.resolved_at = datetime.utcnow()

    notificar_transportista(db, turno, "retencion_resuelta",
                             {"resolucion": resolucion, "motivo": motivo,
                              "peso_declarado_g": turno.peso_declarado_g if resolucion == "corregir" else None})
    return retencion


def retener_manualmente(db, turno: Turno, causa: str, observacion: Optional[str] = None,
                         publish_cmd: PublishFn = _noop_publish) -> Retencion:
    """RT05 (AUTORIDAD) / RT06 (TERMINAL): se ordena en cualquier momento, el
    turno vuelve a su MISMO estado al resolverse (no representa una estacion)."""
    return crear_retencion(db, turno, causa, estado_resume=turno.estado,
                            estacion=turno.estacion_actual, publish_cmd=publish_cmd)


# ══════════════════════════════════════════════════════════════════════════
#  Garita: validacion de acceso del lado servidor (sec. 12: "Servidor")
# ══════════════════════════════════════════════════════════════════════════

def _cita_vigente(db, contenedor_id: str) -> Optional[Cita]:
    return db.scalars(
        select(Cita).where(Cita.contenedor_id == contenedor_id, Cita.estado == "programada")
        .order_by(Cita.inicio.desc())
    ).first()


def _fuera_de_ventana(cita: Cita, ahora: datetime) -> bool:
    return not (cita.inicio <= ahora <= cita.fin + timedelta(minutes=5))


def procesar_ingreso_garita(db, contenedor_id: str, vehiculo_uid: str,
                             transportista_id: Optional[int] = None,
                             publish_cmd: PublishFn = _noop_publish,
                             ahora: Optional[datetime] = None) -> Turno:
    """Reemplaza la decision que hoy toma el Arduino solo (ver
    Observaciones_Firmware_PersonaA.md, punto 2). Esta funcion es la pieza de
    servidor; falta que el firmware la llame en vez de decidir con su tabla
    local — eso sigue pendiente, ver limitaciones al final de este archivo."""
    ahora = ahora or datetime.utcnow()

    manifiesto = db.scalars(
        select(Manifiesto).where(
            Manifiesto.contenedor_id == contenedor_id, Manifiesto.anulado.is_(False),
        ).order_by(Manifiesto.id.desc())
    ).first()
    if manifiesto is None:
        raise ReglaDeNegocioError("sin_manifiesto")
    if manifiesto.estado_documental != "levante_otorgado":
        raise ReglaDeNegocioError("sin_levante")

    cita = _cita_vigente(db, contenedor_id)
    riesgo_conocido = (manifiesto.canal == "rojo") or (cita is not None and _fuera_de_ventana(cita, ahora))
    if riesgo_conocido and parqueo_lleno(db):
        generar_alarma(db, "AL11", origen="garita", descripcion="Parqueo lleno, ingreso rechazado")
        raise ReglaDeNegocioError("parqueo_lleno")

    turno = Turno(
        manifiesto_id=manifiesto.id, vehiculo_uid=vehiculo_uid, transportista_id=transportista_id,
        contenedor_id=contenedor_id, tipo_operacion=manifiesto.tipo_operacion,
        estado=EN_GARITA, estacion_actual="garita", peso_declarado_g=manifiesto.peso_declarado_g,
    )
    db.add(turno)
    db.flush()
    registrar_evento(db, turno.id, "servidor", "Ingreso autorizado por servidor",
                      {"contenedor_id": contenedor_id, "canal": manifiesto.canal})
    publish_cmd("AbrirTalanquera", "UNO_ENTRADA", {})

    if cita is not None and _fuera_de_ventana(cita, ahora):
        crear_retencion(db, turno, RT04, estado_resume=EN_PESAJE_ENTRADA, estacion="garita",
                         publish_cmd=publish_cmd)

    return turno


def procesar_pesaje_entrada(db, turno: Turno, peso_medido_g: int,
                             publish_cmd: PublishFn = _noop_publish) -> None:
    if turno.estado == EN_GARITA:
        transicionar_turno(db, turno, EN_PESAJE_ENTRADA, origen="controlador",
                            descripcion="Cruza plataforma de pesaje de entrada")
    elif turno.estado != EN_PESAJE_ENTRADA:
        raise ReglaDeNegocioError(f"turno_no_listo_para_pesaje_entrada:{turno.estado}")

    manifiesto = db.get(Manifiesto, turno.manifiesto_id) if turno.manifiesto_id else None
    declarado = turno.peso_declarado_g or 0
    tolerancia_pct = manifiesto.tolerancia_pct if manifiesto else 5.0
    turno.peso_medido_entrada_g = peso_medido_g
    registrar_evento(db, turno.id, "controlador", "Pesaje de entrada",
                      {"medido": peso_medido_g, "declarado": declarado})

    diferencia_pct = abs(peso_medido_g - declarado) / declarado * 100 if declarado else 100
    if diferencia_pct > tolerancia_pct:
        crear_retencion(db, turno, RT01, estado_resume=EN_RUTA, estacion="pesaje_entrada",
                         peso_declarado_g=declarado, peso_medido_g=peso_medido_g, publish_cmd=publish_cmd)
        return

    if manifiesto is not None and manifiesto.canal == "rojo":
        crear_retencion(db, turno, RT03, estado_resume=EN_RUTA, estacion="pesaje_entrada",
                         peso_declarado_g=declarado, peso_medido_g=peso_medido_g, publish_cmd=publish_cmd)
        return

    transicionar_turno(db, turno, EN_RUTA, origen="controlador", descripcion="Pesaje de entrada dentro de tolerancia")


def procesar_pesaje_salida(db, turno: Turno, peso_medido_g: int,
                            publish_cmd: PublishFn = _noop_publish) -> None:
    if turno.estado == EN_TRANSFERENCIA:
        transicionar_turno(db, turno, EN_PESAJE_SALIDA, origen="controlador",
                            descripcion="Cruza plataforma de pesaje de salida")
    elif turno.estado != EN_PESAJE_SALIDA:
        raise ReglaDeNegocioError(f"turno_no_listo_para_pesaje_salida:{turno.estado}")

    manifiesto = db.get(Manifiesto, turno.manifiesto_id) if turno.manifiesto_id else None
    declarado = turno.peso_declarado_g or 0
    tolerancia_pct = manifiesto.tolerancia_pct if manifiesto else 5.0
    turno.peso_medido_salida_g = peso_medido_g
    registrar_evento(db, turno.id, "controlador", "Pesaje de salida",
                      {"medido": peso_medido_g, "declarado": declarado})

    diferencia_pct = abs(peso_medido_g - declarado) / declarado * 100 if declarado else 100
    if diferencia_pct > tolerancia_pct:
        crear_retencion(db, turno, RT02, estado_resume=EN_SALIDA, estacion="pesaje_salida",
                         peso_declarado_g=declarado, peso_medido_g=peso_medido_g, publish_cmd=publish_cmd)
        return

    transicionar_turno(db, turno, EN_SALIDA, origen="controlador", descripcion="Pesaje de salida dentro de tolerancia")


def cerrar_turno(db, turno: Turno, publish_cmd: PublishFn = _noop_publish) -> None:
    transicionar_turno(db, turno, CERRADO, origen="servidor", descripcion="Turno cerrado")
    notificar_transportista(db, turno, "turno_cerrado", {"contenedor_id": turno.contenedor_id})


# ══════════════════════════════════════════════════════════════════════════
#  Watchdog de enlace (Observaciones_Backend_PersonaB.md punto 2.2 -> AL01)
# ══════════════════════════════════════════════════════════════════════════

def evaluar_enlace_perdido(db, device: LinkDevice, umbral_s: int, ahora_ts: int) -> bool:
    """Devuelve True si corresponde declarar el enlace perdido para este
    dispositivo (y generar AL01). No genera la alarma dos veces seguidas."""
    if device.last_heartbeat_ts == 0:
        return False  # nunca ha reportado; no hay "perdida" que declarar todavia
    vencido = (ahora_ts - device.last_heartbeat_ts) > umbral_s
    if vencido and device.connected:
        device.connected = False
        return True
    if not vencido and not device.connected:
        device.connected = True
    return False
