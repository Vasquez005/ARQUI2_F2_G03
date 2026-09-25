"""Logica de dominio de PORTUS Fase 2 (Observaciones_Backend_PersonaB.md, punto 1).

Cada funcion recibe la sesion de BD abierta y, cuando necesita comandar la
maqueta, un `publish_cmd(name, target, params)` inyectado desde app.py (para
no acoplar este modulo al cliente MQTT). Nada aqui asume una sesion HTTP real
todavia — eso sigue pendiente de Persona C.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select

from catalogos import (
    ANULADO, CATALOGO_ALARMAS, CERRADO, EN_GARITA,
    EN_PESAJE_ENTRADA, EN_PESAJE_SALIDA, EN_RUTA, EN_SALIDA, EN_TRANSFERENCIA,
    ESTADOS_FINALES, MINUTOS_AL12_RETENCION, MINUTOS_AL13_PATIO, MINUTOS_EXPIRA_CODIGO, ROL_FACULTADO_POR_CAUSA, RESOLUCIONES, RETENIDO,
    RT01, RT02, RT03, RT04, SEVERIDADES_AUTO_RECONOCIBLES, TOLERANCIA_VENTANA_MIN,
    TRANSICIONES, ZONA_HORARIA,
)
from models import (
    Alarma, Cita, CommandAudit, IntentoIngreso, LinkDevice, Manifiesto, Notificacion, ParqueoPlaza, PosicionPatio,
    Retencion, Transportista, Turno, EventoTurno, Vehiculo,
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
    if nuevo_estado == CERRADO:
        liberar_plazas_de_turno(db, turno.id)
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


def rango_utc(desde: Optional[str], hasta: Optional[str]) -> tuple:
    """Fechas YYYY-MM-DD en hora local -> [inicio, fin) en UTC para filtrar
    created_at. hasta es inclusivo (se toma el dia completo)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(ZONA_HORARIA)
    except Exception:
        tz = timezone(timedelta(hours=-6))

    def a_utc(fecha: str) -> datetime:
        local = datetime.strptime(fecha, "%Y-%m-%d").replace(tzinfo=tz)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    inicio = a_utc(desde) if desde else None
    fin = a_utc(hasta) + timedelta(days=1) if hasta else None
    return inicio, fin


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
        p.nivel1_desde = datetime.utcnow()
        p.estado = "OCUPADA_1"
    elif p.contenedor_nivel2 is None:
        p.contenedor_nivel2 = contenedor_id
        p.nivel2_desde = datetime.utcnow()
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
        p.nivel2_desde = None
        p.remociones += 1
        p.estado = "OCUPADA_1"
    elif p.contenedor_nivel1 is not None:
        cid = p.contenedor_nivel1
        p.contenedor_nivel1 = None
        p.nivel1_desde = None
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
    if p.contenedor_nivel2:
        p.estado = "OCUPADA_2"
    else:
        p.estado = "OCUPADA_1" if p.contenedor_nivel1 else "LIBRE"
    p.updated_at = datetime.utcnow()


# ══════════════════════════════════════════════════════════════════════════
#  Parqueo de retencion (3 plazas logicas — sec. 8.1)
# ══════════════════════════════════════════════════════════════════════════

def asignar_plaza_parqueo(db, turno_id: int) -> Optional[int]:
    plazas = db.scalars(select(ParqueoPlaza).order_by(ParqueoPlaza.id)).all()
    for p in plazas:
        if p.ocupada and p.turno_id == turno_id:
            # El vehiculo sigue fisicamente en su plaza (ej. RT04 aclarada y luego RT01)
            p.desde = datetime.utcnow()
            return p.id
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


def liberar_plazas_de_turno(db, turno_id: int) -> list:
    """El vehiculo ya no esta en el parqueo (salio, llego a otra estacion o el
    controlador confirmo AgujaLiberar). Devuelve las plazas liberadas."""
    liberadas = []
    for p in db.scalars(select(ParqueoPlaza).where(ParqueoPlaza.turno_id == turno_id)).all():
        liberar_plaza_parqueo(db, p.id)
        liberadas.append(p.id)
    if liberadas:
        registrar_evento(db, turno_id, "servidor", f"Vehiculo fuera del parqueo, plaza {liberadas[0]} libre")
    return liberadas


def retencion_abierta_de_turno(db, turno_id: int) -> Optional[Retencion]:
    return db.scalars(
        select(Retencion).where(Retencion.turno_id == turno_id, Retencion.estado == "abierta")
        .order_by(Retencion.id.desc())
    ).first()


def solicitar_liberar_parqueo(db, plaza_id: int, publish_cmd: PublishFn = _noop_publish) -> ParqueoPlaza:
    """Boton Liberar parqueo (sec. 4.1): solo si la plaza esta ocupada y su
    retencion ya fue resuelta. La plaza se libera cuando el controlador
    confirma AgujaLiberar (ACK) o cuando el vehiculo aparece en la salida."""
    p = db.get(ParqueoPlaza, plaza_id)
    if p is None:
        raise ReglaDeNegocioError("plaza_invalida")
    if not p.ocupada or p.turno_id is None:
        raise ReglaDeNegocioError("plaza_libre")
    if retencion_abierta_de_turno(db, p.turno_id) is not None:
        raise ReglaDeNegocioError("retencion_sin_resolver")
    publish_cmd("AgujaLiberar", "MEGA_GRUA", {"plaza": plaza_id})
    registrar_evento(db, p.turno_id, "usuario", f"Liberar parqueo: AgujaLiberar para la plaza {plaza_id}")
    return p


def parqueo_lleno(db) -> bool:
    plazas = db.scalars(select(ParqueoPlaza)).all()
    return all(p.ocupada for p in plazas) and len(plazas) > 0


# ══════════════════════════════════════════════════════════════════════════
#  Alarmas (catalogo sec. 4.6)
# ══════════════════════════════════════════════════════════════════════════

def generar_alarma(db, codigo: str, origen: str = "", descripcion: Optional[str] = None,
                   referencia: Optional[str] = None) -> Alarma:
    if codigo not in CATALOGO_ALARMAS:
        raise ReglaDeNegocioError(f"codigo_alarma_desconocido:{codigo}")
    severidad, desc_default = CATALOGO_ALARMAS[codigo]
    alarma = Alarma(codigo=codigo, severidad=severidad, origen=origen,
                     descripcion=(descripcion or desc_default)[:200], referencia=referencia, estado="activa")
    db.add(alarma)
    return alarma


def generar_alarma_unica(db, codigo: str, referencia: str, origen: str = "",
                         descripcion: Optional[str] = None, solo_activas: bool = False,
                         desde: Optional[datetime] = None) -> Optional[Alarma]:
    """Como generar_alarma, pero no la repite si ya hay una con el mismo codigo
    y referencia. solo_activas=True permite volver a generarla una vez
    reconocida la anterior; desde ignora las alarmas anteriores a esa fecha."""
    q = select(Alarma.id).where(Alarma.codigo == codigo, Alarma.referencia == referencia)
    if solo_activas:
        q = q.where(Alarma.estado == "activa")
    if desde is not None:
        q = q.where(Alarma.created_at >= desde)
    if db.scalars(q).first() is not None:
        return None
    return generar_alarma(db, codigo, origen=origen, descripcion=descripcion, referencia=referencia)


def alarma_pesaje(db, turno: Turno, estacion: str, declarado: int, medido: int, diferencia_pct: float) -> Alarma:
    """AL09: acompania a RT01 / RT02 con la evidencia del pesaje."""
    return generar_alarma(
        db, "AL09", origen=estacion, referencia=f"turno:{turno.id}",
        descripcion=(f"Pesaje fuera de tolerancia en {estacion} (turno {turno.id}): "
                     f"declarado {declarado} g, medido {medido} g, diferencia {diferencia_pct:.1f} %"),
    )


def revisar_alarmas_por_tiempo(db, ahora: Optional[datetime] = None) -> list:
    """AL12 (retencion abierta > 30 min) y AL13 (contenedor > 2 h en patio).
    La llama un hilo de app.py. Cada caso genera su alarma una sola vez."""
    ahora = ahora or datetime.utcnow()
    nuevas = []

    limite_retencion = ahora - timedelta(minutes=MINUTOS_AL12_RETENCION)
    abiertas = db.scalars(
        select(Retencion).where(Retencion.estado == "abierta", Retencion.created_at <= limite_retencion)
    ).all()
    for r in abiertas:
        a = generar_alarma_unica(
            db, "AL12", f"retencion:{r.id}", origen="parqueo",
            descripcion=(f"Retencion {r.causa} del turno {r.turno_id} abierta hace "
                         f"{duracion_texto(r.created_at, ahora)}"),
        )
        if a is not None:
            nuevas.append(a)

    limite_patio = ahora - timedelta(minutes=MINUTOS_AL13_PATIO)
    for p in db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all():
        for nivel, contenedor, desde in ((1, p.contenedor_nivel1, p.nivel1_desde),
                                         (2, p.contenedor_nivel2, p.nivel2_desde)):
            if not contenedor or desde is None or desde > limite_patio:
                continue
            # desde: si el contenedor sale y vuelve a entrar, cuenta como estancia nueva
            a = generar_alarma_unica(
                db, "AL13", f"contenedor:{contenedor}", origen=f"patio_{p.id}", desde=desde,
                descripcion=(f"Contenedor {contenedor} en posicion {p.id} nivel {nivel} desde hace "
                             f"{duracion_texto(desde, ahora)}"),
            )
            if a is not None:
                nuevas.append(a)
    return nuevas


def registrar_respuesta_comando(db, origen: str, tipo: str, datos: dict, payload_json: str) -> Optional[Alarma]:
    """ACK/REJ de un controlador (portus/cmd/respuesta). Actualiza la auditoria
    del comando y, si fue rechazado, genera AL14 con la causa (sec. 11.1 y 11.2).

    Correlacion: se actualiza el PENDING mas reciente para ese target+comando.
    El protocolo serial no trae un id de correlacion propio (ver limitacion en
    docs/protocolo_serial.md), asi que es "mejor esfuerzo" bajo concurrencia."""
    nombre = datos.get("name", "UNKNOWN")
    resultado = "ACK" if tipo == "ACK" else "REJ"
    pendiente = db.scalars(
        select(CommandAudit)
        .where(CommandAudit.target == origen, CommandAudit.cmd_name == nombre, CommandAudit.result == "PENDING")
        .order_by(CommandAudit.id.desc())
    ).first()
    if pendiente is None:
        pendiente = CommandAudit(cmd_name=nombre, target=origen, request_json="{}")
        db.add(pendiente)
    pendiente.result = resultado
    pendiente.response_json = payload_json
    if resultado == "ACK":
        if nombre == "AgujaLiberar":
            _liberar_plaza_por_ack(db, pendiente)
        return None
    db.flush()
    causa = datos.get("causa") or "sin causa"
    return generar_alarma(db, "AL14", origen=origen, referencia=f"comando:{pendiente.id}",
                          descripcion=f"{origen} rechazo {nombre}: {causa}")


def _liberar_plaza_por_ack(db, audit: CommandAudit) -> None:
    """El controlador confirmo AgujaLiberar: el vehiculo salio de su plaza."""
    import json
    try:
        plaza_id = int(json.loads(audit.request_json or "{}").get("params", {}).get("plaza"))
    except (TypeError, ValueError):
        return
    p = db.get(ParqueoPlaza, plaza_id)
    if p is not None and p.ocupada and p.turno_id is not None:
        if retencion_abierta_de_turno(db, p.turno_id) is None:
            liberar_plazas_de_turno(db, p.turno_id)


def registrar_alarma_controlador(db, origen: str, datos: dict) -> Optional[Alarma]:
    """Alarma que manda una placa por portus/evt/alarma (codigo=ALxx;...).
    La severidad sale del catalogo, no de la placa. Mientras siga activa, la
    misma alarma de la misma placa no se duplica."""
    codigo = str(datos.get("codigo", "")).upper()
    if codigo not in CATALOGO_ALARMAS:
        return None
    detalle = ", ".join(f"{k}={v}" for k, v in datos.items() if k not in ("codigo", "severidad", "evento"))
    descripcion = CATALOGO_ALARMAS[codigo][1] + (f" ({detalle})" if detalle else "")
    return generar_alarma_unica(db, codigo, f"{origen}:{codigo}", origen=origen,
                                descripcion=descripcion, solo_activas=True)


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
                     publish_cmd: PublishFn = _noop_publish, al_parqueo: bool = True) -> Retencion:
    plaza = None
    if al_parqueo:
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
        # La plaza sigue ocupada hasta que el vehiculo salga del parqueo: el
        # ACK de AgujaLiberar o su llegada a la salida la liberan.
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
    if observacion:
        retencion.observacion = observacion
    retencion.resolved_at = datetime.utcnow()

    notificar_transportista(db, turno, "retencion_resuelta",
                             {"resolucion": resolucion, "motivo": motivo,
                              "peso_declarado_g": turno.peso_declarado_g if resolucion == "corregir" else None})

    if turno.estado in (EN_GARITA, EN_PESAJE_ENTRADA) and turno.peso_medido_entrada_g is not None:
        # El vehiculo ya cruzo la bascula mientras estaba retenido (ej. RT04 en
        # garita): ese pesaje quedo guardado y se aplica ahora. Puede generar
        # otra retencion (RT01 / RT03) con su propia plaza.
        registrar_evento(db, turno.id, "servidor", "Se aplica el pesaje de entrada recibido durante la retencion",
                          {"peso_g": turno.peso_medido_entrada_g})
        procesar_pesaje_entrada(db, turno, turno.peso_medido_entrada_g, publish_cmd=publish_cmd)
    return retencion


def guardar_pesaje_durante_retencion(db, turno: Turno, peso_g: int, datos: dict) -> bool:
    """El pesaje de entrada llego con el turno Retenido. Si la retencion es de
    antes de la bascula (RT04 en garita, o RT05/RT06 ordenadas ahi), se guarda
    el peso para aplicarlo al resolverla. Devuelve True si lo guardo."""
    retencion = db.scalars(
        select(Retencion).where(Retencion.turno_id == turno.id, Retencion.estado == "abierta")
        .order_by(Retencion.id.desc())
    ).first()
    if (retencion is None or retencion.estado_anterior not in (EN_GARITA, EN_PESAJE_ENTRADA)
            or turno.peso_medido_entrada_g is not None):
        registrar_evento(db, turno.id, "controlador",
                          "Pesaje de entrada durante una retencion (no se procesa)", datos)
        return False
    turno.peso_medido_entrada_g = peso_g
    registrar_evento(db, turno.id, "controlador",
                      f"Pesaje de entrada durante la retencion {retencion.causa}; se aplica al resolverla",
                      {**datos, "peso_g": peso_g})
    return True


def retener_manualmente(db, turno: Turno, causa: str, observacion: Optional[str] = None,
                         publish_cmd: PublishFn = _noop_publish) -> Retencion:
    """RT05 (AUTORIDAD) / RT06 (TERMINAL): se ordena en cualquier momento, el
    turno vuelve a su MISMO estado al resolverse (no representa una estacion).
    Sec. 4.2: el vehiculo va al parqueo solo si todavia no llego a la transferencia."""
    if turno.estado in ESTADOS_FINALES or turno.estado == RETENIDO:
        raise ReglaDeNegocioError(f"no_se_puede_retener_desde:{turno.estado}")
    antes_de_transferencia = turno.estado in (EN_GARITA, EN_PESAJE_ENTRADA, EN_RUTA)
    retencion = crear_retencion(db, turno, causa, estado_resume=turno.estado,
                                estacion=turno.estacion_actual, publish_cmd=publish_cmd,
                                al_parqueo=antes_de_transferencia)
    retencion.observacion = observacion
    return retencion


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
                             ahora: Optional[datetime] = None,
                             manifiesto: Optional[Manifiesto] = None) -> Turno:
    """Validacion de acceso del lado servidor (sec. 12). La llama
    ingreso_por_rfid cuando la garita manda el UID de la tarjeta, o el
    endpoint /garita/ingreso para pruebas manuales."""
    ahora = ahora or datetime.utcnow()

    if manifiesto is None:
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
    # uid y op le dicen a la garita que esta es la respuesta a SU tarjeta
    # pendiente (sin uid, el firmware lo trata como apertura manual). Nada mas:
    # el UNO recibe con un bufer de 64 bytes y un frame largo se puede cortar.
    publish_cmd("AbrirTalanquera", "UNO_ENTRADA", {"uid": vehiculo_uid, "op": manifiesto.tipo_operacion})

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
        alarma_pesaje(db, turno, "pesaje_entrada", declarado, peso_medido_g, diferencia_pct)
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
        alarma_pesaje(db, turno, "pesaje_salida", declarado, peso_medido_g, diferencia_pct)
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
#  Garitas automaticas por RFID (fase 1: los eventos de la maqueta mueven el turno)
# ══════════════════════════════════════════════════════════════════════════

# Texto corto (LCD de 16 columnas) para cada causa de rechazo en garita (E03).
MOTIVO_LCD = {
    "rfid_no_registrado": "RFID no registr",
    "vehiculo_inactivo": "Vehiculo inactiv",
    "sin_manifiesto": "Sin manifiesto",
    "sin_levante": "Sin levante",
    "parqueo_lleno": "Parqueo lleno",
    "turno_activo": "Ya tiene turno",
    "sin_turno": "Sin turno activo",
    "retenido": "Retenido",
    "pesaje_pendiente": "Falta pesaje",
}

# No hay bascula real: la garita de entrada solo informa resultado=ok o
# fuera_tolerancia. El servidor necesita un peso para aplicar su propia regla
# (RT01), asi que usa el declarado si fue ok y declarado x este factor si no.
FACTOR_PESO_FUERA = float(os.getenv("PORTUS_FACTOR_PESO_FUERA", "1.5"))

DESC_SALIO = "Vehiculo salio de la terminal"


def normalizar_uid(uid: str) -> str:
    return " ".join((uid or "").upper().split())


def motivo_lcd(causa: str) -> str:
    return MOTIVO_LCD.get(causa, "No autorizado")


def registrar_intento_rechazado(db, vehiculo_uid: str, estacion: str, causa: str,
                                 contenedor_id: Optional[str] = None,
                                 decidido_por: str = "servidor") -> IntentoIngreso:
    intento = IntentoIngreso(vehiculo_uid=vehiculo_uid, contenedor_id=contenedor_id,
                             estacion=estacion, causa=causa, decidido_por=decidido_por)
    db.add(intento)
    return intento


def turno_activo_por_uid(db, vehiculo_uid: str) -> Optional[Turno]:
    return db.scalars(
        select(Turno).where(Turno.vehiculo_uid == vehiculo_uid, Turno.estado.not_in(ESTADOS_FINALES))
        .order_by(Turno.id.desc())
    ).first()


def ultimo_turno_por_uid(db, vehiculo_uid: str) -> Optional[Turno]:
    return db.scalars(
        select(Turno).where(Turno.vehiculo_uid == vehiculo_uid).order_by(Turno.id.desc())
    ).first()


def _manifiesto_sin_turno(db, m: Manifiesto) -> bool:
    return db.scalars(select(Turno.id).where(Turno.manifiesto_id == m.id)).first() is None


def resolver_manifiesto_por_uid(db, vehiculo_uid: str, ahora: Optional[datetime] = None) -> Manifiesto:
    """Tarjeta -> contenedor. Primero busca manifiestos que nombren este
    vehiculo; si no hay, los del transportista duenio de la tarjeta. Entre
    varios candidatos prefiere el que tiene levante y cita en ventana."""
    ahora = ahora or datetime.utcnow()
    candidatos = db.scalars(
        select(Manifiesto).where(Manifiesto.vehiculo_uid == vehiculo_uid, Manifiesto.anulado.is_(False))
        .order_by(Manifiesto.id)
    ).all()
    candidatos = [m for m in candidatos if _manifiesto_sin_turno(db, m)]

    if not candidatos:
        vehiculo = db.get(Vehiculo, vehiculo_uid)
        if vehiculo is None:
            raise ReglaDeNegocioError("rfid_no_registrado")
        if not vehiculo.activo:
            raise ReglaDeNegocioError("vehiculo_inactivo")
        if vehiculo.transportista_id is not None:
            candidatos = db.scalars(
                select(Manifiesto).where(
                    Manifiesto.transportista_id == vehiculo.transportista_id,
                    Manifiesto.vehiculo_uid.is_(None), Manifiesto.anulado.is_(False),
                ).order_by(Manifiesto.id)
            ).all()
            candidatos = [m for m in candidatos if _manifiesto_sin_turno(db, m)]
    if not candidatos:
        raise ReglaDeNegocioError("sin_manifiesto")

    def prioridad(m: Manifiesto):
        cita = _cita_vigente(db, m.contenedor_id)
        en_ventana = cita is not None and not _fuera_de_ventana(cita, ahora)
        return (m.estado_documental != "levante_otorgado", not en_ventana, m.id)

    return min(candidatos, key=prioridad)


def ingreso_por_rfid(db, vehiculo_uid: str, publish_cmd: PublishFn = _noop_publish,
                     ahora: Optional[datetime] = None) -> Turno:
    """La garita de entrada leyo una tarjeta: el servidor decide (sec. 12).
    Si autoriza, crea el turno y manda AbrirTalanquera; si no, lanza
    ReglaDeNegocioError con la causa y quien llama responde RechazarIngreso."""
    if turno_activo_por_uid(db, vehiculo_uid) is not None:
        raise ReglaDeNegocioError("turno_activo")
    manifiesto = resolver_manifiesto_por_uid(db, vehiculo_uid, ahora)
    try:
        return procesar_ingreso_garita(db, manifiesto.contenedor_id, vehiculo_uid,
                                       manifiesto.transportista_id, publish_cmd=publish_cmd,
                                       ahora=ahora, manifiesto=manifiesto)
    except ReglaDeNegocioError as exc:
        exc.contenedor_id = manifiesto.contenedor_id  # para el registro de intento
        raise


def peso_simulado_entrada(turno: Turno, datos: dict) -> int:
    """Peso para procesar_pesaje_entrada a partir del evento de la garita.
    Si algun dia el controlador manda peso=<gramos>, se usa ese valor."""
    if str(datos.get("peso", "")).isdigit():
        return int(datos["peso"])
    declarado = turno.peso_declarado_g or 0
    if datos.get("resultado") == "ok":
        return declarado
    return max(1, round(declarado * FACTOR_PESO_FUERA))


def ya_salio(db, turno: Turno) -> bool:
    return db.scalars(
        select(EventoTurno.id).where(EventoTurno.turno_id == turno.id, EventoTurno.descripcion == DESC_SALIO)
    ).first() is not None


def avanzar_hasta_salida(db, turno: Turno, publish_cmd: PublishFn = _noop_publish) -> None:
    """El vehiculo se presento en la garita de salida. La grua todavia no
    reporta el fin de la transferencia y la salida no tiene bascula, asi que el
    servidor completa esos pasos aqui y lo deja en la linea de tiempo."""
    if turno.estado == EN_RUTA:
        transicionar_turno(db, turno, EN_TRANSFERENCIA, origen="servidor",
                           descripcion="Transferencia no reportada por la grua; se asume completada")
    if turno.estado in (EN_TRANSFERENCIA, EN_PESAJE_SALIDA):
        # Sin bascula de salida: se toma el peso declarado (pesaje simulado).
        procesar_pesaje_salida(db, turno, turno.peso_declarado_g or 0, publish_cmd=publish_cmd)


def salida_por_rfid(db, vehiculo_uid: str, publish_cmd: PublishFn = _noop_publish) -> Turno:
    """La garita de salida leyo una tarjeta: el servidor decide si abre."""
    turno = ultimo_turno_por_uid(db, vehiculo_uid)
    if turno is None or turno.estado == CERRADO:
        raise ReglaDeNegocioError("sin_turno")
    if turno.estado == ANULADO:
        # Sec. 8.3: un turno anulado sale sin completar la operacion (una sola vez).
        if ya_salio(db, turno):
            raise ReglaDeNegocioError("sin_turno")
    elif turno.estado == RETENIDO:
        raise ReglaDeNegocioError("retenido")
    elif turno.estado in (EN_GARITA, EN_PESAJE_ENTRADA):
        raise ReglaDeNegocioError("pesaje_pendiente")
    else:
        avanzar_hasta_salida(db, turno, publish_cmd=publish_cmd)
        if turno.estado != EN_SALIDA:
            raise ReglaDeNegocioError("retenido")

    registrar_evento(db, turno.id, "servidor", "Salida autorizada por servidor", {"uid": vehiculo_uid})
    liberar_plazas_de_turno(db, turno.id)  # si llego a la salida, ya no esta en el parqueo
    turno.estacion_actual = "salida"
    publish_cmd("AbrirPuertaSalida", "UNO_SALIDA", {"uid": vehiculo_uid})
    return turno


def registrar_salida_fisica(db, turno: Turno, publish_cmd: PublishFn = _noop_publish) -> None:
    """La garita de salida confirma que el vehiculo cruzo (sec. 7 regla 5:
    ningun turno queda abierto con el vehiculo ya afuera)."""
    if ya_salio(db, turno):
        return
    registrar_evento(db, turno.id, "controlador", DESC_SALIO)
    liberar_plazas_de_turno(db, turno.id)
    if turno.estado == EN_SALIDA:
        cerrar_turno(db, turno, publish_cmd=publish_cmd)


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
