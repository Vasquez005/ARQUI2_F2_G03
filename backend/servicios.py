"""Logica de dominio de PORTUS Fase 2 (Observaciones_Backend_PersonaB.md, punto 1).

Cada funcion recibe la sesion de BD abierta y, cuando necesita comandar la
maqueta, un `publish_cmd(name, target, params)` inyectado desde app.py (para
no acoplar este modulo al cliente MQTT). Nada aqui asume una sesion HTTP real
todavia — eso sigue pendiente de Persona C.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select

from catalogos import (
    ANULADO, CATALOGO_ALARMAS, CERRADO, EN_GARITA,
    EN_PESAJE_ENTRADA, EN_PESAJE_SALIDA, EN_RUTA, EN_SALIDA, EN_TRANSFERENCIA,
    ESTADOS_FINALES, MINUTOS_EXPIRA_CODIGO, ROL_FACULTADO_POR_CAUSA, RESOLUCIONES, RETENIDO,
    RT01, RT02, RT03, RT04, SEVERIDADES_AUTO_RECONOCIBLES, TOLERANCIA_VENTANA_MIN,
    TRANSICIONES, ZONA_HORARIA,
)
from models import (
    Alarma, Cita, LinkDevice, Manifiesto, Notificacion, ParqueoPlaza, PosicionPatio,
    Retencion, Transportista, Turno, EventoTurno,
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


def hora_local(dt_utc: Optional[datetime], formato: str = "%d/%m/%Y %H:%M") -> str:
    """La BD guarda UTC (datetime.utcnow); a las personas se les muestra la hora de Guatemala."""
    if dt_utc is None:
        return "-"
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(ZONA_HORARIA)
    except Exception:
        tz = timezone(timedelta(hours=-6))
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(tz).strftime(formato)


def duracion_texto(desde: Optional[datetime], hasta: Optional[datetime] = None) -> str:
    if desde is None:
        return "-"
    minutos = int(((hasta or datetime.utcnow()) - desde).total_seconds() // 60)
    return f"{minutos // 60} h {minutos % 60} min"


def encolar_notificacion(db, transportista_id: Optional[int], evento: str, texto: str,
                          referencia: Optional[str] = None) -> Optional[Notificacion]:
    """Deja el aviso en la bandeja de salida; el bot (bot_d) lo envia."""
    if transportista_id is None:
        return None
    n = Notificacion(transportista_id=transportista_id, evento=evento, texto=texto, referencia=referencia)
    db.add(n)
    return n


_ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para que no se confundan al teclear


def generar_codigo_vinculacion(db, transportista: Transportista) -> str:
    """Sec. 6.1: 6 caracteres, un solo uso, expira a los 60 minutos. Generar
    uno nuevo invalida el anterior. El bot lo consume con /vincular."""
    while True:
        codigo = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(6))
        if not db.scalars(select(Transportista).where(Transportista.codigo_vinculacion == codigo)).first():
            break
    transportista.codigo_vinculacion = codigo
    transportista.codigo_expira_at = datetime.utcnow() + timedelta(minutes=MINUTOS_EXPIRA_CODIGO)
    return codigo


def _gramos(valor: Optional[int]) -> str:
    return "-" if valor is None else f"{valor} g"


def _texto_notificacion_turno(turno: Turno, evento: str, detalle: dict) -> str:
    base = f"Vehiculo {turno.vehiculo_uid} | Contenedor {turno.contenedor_id}"
    if evento == "retencion_generada":
        texto = f"PORTUS: tu vehiculo fue RETENIDO.\n{base}\nCausa: {detalle.get('causa')}"
        if detalle.get("plaza"):
            texto += f"\nPlaza de parqueo: {detalle['plaza']}"
        declarado, medido = detalle.get("peso_declarado_g"), detalle.get("peso_medido_g")
        if detalle.get("causa") in (RT01, RT02) and declarado is not None and medido is not None:
            texto += (f"\nPeso declarado: {_gramos(declarado)}\nPeso medido: {_gramos(medido)}"
                      f"\nDiferencia: {abs(medido - declarado)} g")
        return texto
    if evento == "retencion_resuelta":
        resolucion = detalle.get("resolucion")
        texto = f"PORTUS: tu retencion fue resuelta ({resolucion}).\n{base}"
        if resolucion == "corregir":
            texto += f"\nNuevo peso declarado: {_gramos(detalle.get('peso_declarado_g'))}"
        if resolucion == "rechazar":
            texto += f"\nMotivo: {detalle.get('motivo')}\nEl turno fue ANULADO; el vehiculo sale sin completar la operacion."
        return texto
    if evento == "turno_cerrado":
        return (f"PORTUS: turno CERRADO.\n{base}\nOperacion: {turno.tipo_operacion}"
                f"\nTiempo total en la terminal: {duracion_texto(turno.created_at, turno.closed_at)}")
    if evento == "turno_anulado":
        return f"PORTUS: turno ANULADO.\n{base}\nCausa: {detalle.get('causa') or 'no indicada'}"
    return f"PORTUS: {evento}\n{base}"


def notificar_transportista(db, turno: Turno, evento: str, detalle: Optional[dict] = None) -> None:
    """Sec. 6.3: cada aviso va solo al transportista duenio del turno. Tambien
    queda en la linea de tiempo para poder demostrar que se envio."""
    detalle = detalle or {}
    encolar_notificacion(db, turno.transportista_id, evento, _texto_notificacion_turno(turno, evento, detalle),
                          referencia=f"turno:{turno.id}")
    registrar_evento(db, turno.id, "servidor", f"Notificacion '{evento}' al transportista", detalle)


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
    turno.estacion_actual = f"parqueo_plaza_{plaza}" if plaza is not None else (estacion or turno.estacion_actual)

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
        turno.estacion_actual = retencion.estacion or turno.estacion_actual
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
    return not (cita.inicio <= ahora <= cita.fin + timedelta(minutes=TOLERANCIA_VENTANA_MIN))


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
        # La AL11 la registra app.py despues del rollback (si se agregara aqui,
        # el rollback del rechazo la borraria junto con todo lo demas).
        raise ReglaDeNegocioError("parqueo_lleno")

    if transportista_id is None:
        # Sin esto el turno queda sin duenio y el bot no puede avisarle a nadie (sec. 6.3)
        transportista_id = manifiesto.transportista_id

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

    if cita is not None:
        # Sec. 9.8: el cumplimiento de ventana se registra por cita (metrica de Reportes)
        cita.estado = "vencida" if _fuera_de_ventana(cita, ahora) else "cumplida"

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
    turno.estacion_actual = "pesaje_entrada"

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
    turno.estacion_actual = "ruta_transferencia"


def procesar_pesaje_salida(db, turno: Turno, peso_medido_g: int,
                            publish_cmd: PublishFn = _noop_publish) -> None:
    if turno.estado == EN_TRANSFERENCIA:
        transicionar_turno(db, turno, EN_PESAJE_SALIDA, origen="controlador",
                            descripcion="Cruza plataforma de pesaje de salida")
    elif turno.estado != EN_PESAJE_SALIDA:
        raise ReglaDeNegocioError(f"turno_no_listo_para_pesaje_salida:{turno.estado}")
    turno.estacion_actual = "pesaje_salida"

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
    turno.estacion_actual = "salida"


def cerrar_turno(db, turno: Turno, publish_cmd: PublishFn = _noop_publish) -> None:
    transicionar_turno(db, turno, CERRADO, origen="servidor", descripcion="Turno cerrado")
    notificar_transportista(db, turno, "turno_cerrado", {"contenedor_id": turno.contenedor_id})


def anular_turno(db, turno: Turno, causa: Optional[str] = None,
                 publish_cmd: PublishFn = _noop_publish) -> None:
    """Boton Anular de la pestania Turnos (sec. 4.2): anula y autoriza la salida
    sin completar la operacion. Un turno Retenido se anula con Rechazar desde su
    retencion (asi se libera la plaza y lo resuelve el rol facultado)."""
    if turno.estado == RETENIDO:
        raise ReglaDeNegocioError("turno_retenido_usar_rechazar_en_la_retencion")
    if ANULADO not in TRANSICIONES.get(turno.estado, ()):
        raise ReglaDeNegocioError(f"no_se_puede_anular_desde:{turno.estado}")
    transicionar_turno(db, turno, ANULADO, origen="usuario",
                        descripcion=f"Turno anulado por la terminal: {causa or 'sin causa indicada'}",
                        valores={"causa": causa})
    publish_cmd("AbrirPuertaSalida", "UNO_SALIDA", {"turno": turno.id})
    notificar_transportista(db, turno, "turno_anulado", {"causa": causa})


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
