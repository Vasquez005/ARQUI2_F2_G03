import json
import os
import threading
import time
from datetime import datetime
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import servicios
from catalogos import (
    CAUSAS_RETENCION, DISPOSITIVOS, MINUTOS_EXPIRA_CODIGO, ROLES, UMBRAL_ENLACE_PERDIDO_S,
)
from models import (
    Alarma, CommandAudit, Declaracion, EventLog, EventoTurno, LinkDevice,
    LinkStatus, Manifiesto, ParqueoPlaza, PosicionPatio, Retencion, Turno,
    Transportista, Usuario, make_db,
)
from security import verify_password

DB_PATH = os.getenv("PORTUS_DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "portus_core.db")))
SessionLocal = make_db(DB_PATH)
MQTT_HOST = os.getenv("PORTUS_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("PORTUS_MQTT_PORT", "1883"))

app = FastAPI(title="PORTUS Backend Core (Persona B)")
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
started = False


# ══════════════════════════════════════════════════════════════════════════
#  Arranque: siembra minima de patio/parqueo (sin esto, asignar_plaza y
#  asignar_posicion no tienen filas sobre las que trabajar).
# ══════════════════════════════════════════════════════════════════════════

def seed_minimo(db) -> None:
    if not db.get(PosicionPatio, 1):
        for i in range(1, 5):
            db.add(PosicionPatio(id=i, estado="LIBRE"))
    if not db.get(ParqueoPlaza, 1):
        for i in range(1, 4):
            db.add(ParqueoPlaza(id=i, ocupada=False))
    for d in DISPOSITIVOS:
        if not db.get(LinkDevice, d):
            db.add(LinkDevice(device=d, connected=False, last_heartbeat_ts=0))
    db.commit()


# ══════════════════════════════════════════════════════════════════════════
#  Enlace / MQTT (existia; se agrega tracking por dispositivo)
# ══════════════════════════════════════════════════════════════════════════

def upsert_link_status(connected: bool, last_ts: int = 0, origin: str = "") -> None:
    with SessionLocal() as db:
        row = db.get(LinkStatus, 1)
        if not row:
            row = LinkStatus(id=1, connected="false", last_heartbeat_ts=0, last_origin="", updated_at=datetime.utcnow())
            db.add(row)
        row.connected = "true" if connected else "false"
        if last_ts:
            row.last_heartbeat_ts = last_ts
        if origin:
            row.last_origin = origin
        row.updated_at = datetime.utcnow()
        db.commit()


def upsert_link_device(device: str, last_ts: int) -> None:
    with SessionLocal() as db:
        row = db.get(LinkDevice, device)
        if not row:
            row = LinkDevice(device=device, connected=True, last_heartbeat_ts=last_ts)
            db.add(row)
        else:
            row.connected = True
            row.last_heartbeat_ts = last_ts
            row.updated_at = datetime.utcnow()
        db.commit()


def link_watchdog_loop() -> None:
    """Observaciones_Backend_PersonaB.md punto 2.2: sin esto, el backend solo
    se enteraba de que Mosquitto se habia caido, nunca de que UN dispositivo
    especifico dejo de mandar su latido mientras el broker seguia arriba."""
    while True:
        time.sleep(5)
        now_ts = int(time.time())
        with SessionLocal() as db:
            for name in DISPOSITIVOS:
                device = db.get(LinkDevice, name)
                if not device:
                    continue
                if servicios.evaluar_enlace_perdido(db, device, UMBRAL_ENLACE_PERDIDO_S, now_ts):
                    servicios.generar_alarma(db, "AL01", origen=name,
                                              descripcion=f"Enlace perdido con {name}")
            db.commit()


def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe("portus/evt/#")
    client.subscribe("portus/cmd/respuesta")
    upsert_link_status(connected=True)


def on_disconnect(client, userdata, flags, rc, properties=None):
    upsert_link_status(connected=False)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return
    topic = msg.topic
    evt_id = payload.get("id", "")
    origin = payload.get("origin", "")
    evt_type = payload.get("type", "")
    seq = int(payload.get("seq", 0))

    with SessionLocal() as db:
        db.add(
            EventLog(
                event_id=evt_id, topic=topic, origin=origin, evt_type=evt_type,
                seq=seq, payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.commit()

    if topic == "portus/evt/estado":
        upsert_link_status(True, last_ts=int(time.time()), origin=origin)
        if origin in DISPOSITIVOS:
            upsert_link_device(origin, int(time.time()))

    if topic == "portus/cmd/respuesta":
        cmd_name = payload.get("data", {}).get("name", "UNKNOWN")
        result = "ACK" if evt_type == "ACK" else "REJ"
        with SessionLocal() as db:
            # Correlacion (Observaciones_Backend_PersonaB.md punto 2.4): se
            # actualiza el PENDING mas reciente para ese target+comando en vez
            # de insertar una fila nueva sin relacion. El protocolo serial no
            # trae un id de correlacion propio (ver limitacion en el .md), asi
            # que esto es "mejor esfuerzo", no una garantia bajo concurrencia.
            pendiente = db.scalars(
                select(CommandAudit)
                .where(CommandAudit.target == origin, CommandAudit.cmd_name == cmd_name,
                       CommandAudit.result == "PENDING")
                .order_by(CommandAudit.id.desc())
            ).first()
            if pendiente:
                pendiente.result = result
                pendiente.response_json = json.dumps(payload, ensure_ascii=False)
            else:
                db.add(CommandAudit(
                    cmd_name=cmd_name, target=origin, request_json="{}",
                    result=result, response_json=json.dumps(payload, ensure_ascii=False),
                ))
            db.commit()


def mqtt_loop():
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_message = on_message
    while True:
        try:
            mqttc.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            mqttc.loop_forever()
        except Exception:
            upsert_link_status(connected=False)
            time.sleep(3)


def ensure_started():
    global started
    if started:
        return
    started = True
    threading.Thread(target=mqtt_loop, daemon=True).start()
    threading.Thread(target=link_watchdog_loop, daemon=True).start()


def make_publish_and_audit(db):
    """Fabrica un publish_cmd atado a LA MISMA sesion de la peticion en curso.

    Bug real encontrado al probar (no se veia leyendo el codigo): la version
    anterior abria su propia `with SessionLocal() as db: ... db.commit()`
    independiente de la sesion del endpoint que la llamaba. Cuando un endpoint
    como /garita/ingreso todavia tenia cambios sin commitear (el INSERT del
    turno) y, dentro de esa misma llamada, servicios.py invocaba publish_cmd,
    la sesion nueva intentaba escribir en el mismo archivo SQLite mientras la
    primera seguia con una transaccion abierta -> "database is locked".
    Con una sola sesion por peticion, todo se confirma junto al final.
    """
    def _publish(name: str, target: str, params: dict) -> None:
        payload = {"name": name, "target": target, "params": params}
        mqttc.publish("portus/cmd/solicitud", json.dumps(payload))
        db.add(CommandAudit(
            cmd_name=name, target=target, request_json=json.dumps(payload, ensure_ascii=False),
            result="PENDING", response_json="{}",
        ))
    return _publish


@app.on_event("startup")
def startup():
    with SessionLocal() as db:
        seed_minimo(db)
    ensure_started()
    upsert_link_status(False)


# ══════════════════════════════════════════════════════════════════════════
#  Diagnostico (existia)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    with SessionLocal() as db:
        ls = db.get(LinkStatus, 1)
        devices = db.scalars(select(LinkDevice)).all()
        return {
            "ok": True,
            "mqttHost": MQTT_HOST,
            "mqttPort": MQTT_PORT,
            "connected": (ls.connected == "true") if ls else False,
            "lastHeartbeatTs": ls.last_heartbeat_ts if ls else 0,
            "lastOrigin": ls.last_origin if ls else "",
            "devices": [
                {"device": d.device, "connected": d.connected, "lastHeartbeatTs": d.last_heartbeat_ts}
                for d in devices
            ],
        }


@app.get("/events/recent")
def recent_events(limit: int = 50):
    with SessionLocal() as db:
        rows = db.scalars(select(EventLog).order_by(EventLog.id.desc()).limit(limit)).all()
        return [
            {
                "id": r.id, "eventId": r.event_id, "topic": r.topic, "origin": r.origin,
                "type": r.evt_type, "seq": r.seq, "payload": json.loads(r.payload_json),
                "createdAt": r.created_at.isoformat(),
            }
            for r in rows
        ]


class CmdRequest(BaseModel):
    name: str
    target: str
    params: dict = {}


@app.post("/commands/send")
def send_command(cmd: CmdRequest):
    with SessionLocal() as db:
        make_publish_and_audit(db)(cmd.name, cmd.target, cmd.params)
        db.commit()
    return {"ok": True, "published": {"name": cmd.name, "target": cmd.target, "params": cmd.params}}


# ══════════════════════════════════════════════════════════════════════════
#  Manifiestos / declaraciones / levante (cadena documental)
# ══════════════════════════════════════════════════════════════════════════

class ManifiestoIn(BaseModel):
    contenedor_id: str
    tipo_operacion: str  # DEPOSITO | RETIRO
    peso_declarado_g: int
    tolerancia_pct: float = 5.0
    naviera_usuario_id: Optional[int] = None
    transportista_id: Optional[int] = None
    observaciones: Optional[str] = None


def _tiene_manifiesto_pendiente(db, contenedor_id: str) -> bool:
    abiertos = db.scalars(
        select(Manifiesto).where(Manifiesto.contenedor_id == contenedor_id, Manifiesto.anulado.is_(False))
    ).all()
    for m in abiertos:
        turno = db.scalars(select(Turno).where(Turno.manifiesto_id == m.id).order_by(Turno.id.desc())).first()
        if turno is None or turno.estado not in ("Cerrado", "Anulado"):
            return True
    return False


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def login(body: LoginIn):
    """Lo usa la web (web_c) para validar credenciales contra la tabla usuarios
    (contrasenas hasheadas, sec. 2.2). La sesion/cookie la maneja web_c."""
    with SessionLocal() as db:
        u = db.scalars(select(Usuario).where(Usuario.username == body.username)).first()
        if not u or not u.activo or not verify_password(body.password, u.password_hash):
            raise HTTPException(401, "credenciales_invalidas")
        return {"id": u.id, "username": u.username, "rol": u.rol, "nombre": u.nombre}


@app.get("/usuarios")
def listar_usuarios(rol: Optional[str] = None):
    with SessionLocal() as db:
        q = select(Usuario)
        if rol:
            q = q.where(Usuario.rol == rol)
        rows = db.scalars(q.order_by(Usuario.id)).all()
        return [{"id": u.id, "username": u.username, "rol": u.rol, "nombre": u.nombre} for u in rows]


class TransportistaIn(BaseModel):
    nombre: str


@app.post("/transportistas")
def crear_transportista(body: TransportistaIn):
    with SessionLocal() as db:
        t = Transportista(nombre=body.nombre)
        db.add(t)
        db.commit()
        db.refresh(t)
        return {"id": t.id}


@app.get("/transportistas")
def listar_transportistas():
    with SessionLocal() as db:
        rows = db.scalars(select(Transportista).order_by(Transportista.id)).all()
        return [{"id": t.id, "nombre": t.nombre, "vinculado": t.chat_id is not None} for t in rows]


@app.post("/transportistas/{transportista_id}/codigo-vinculacion")
def generar_codigo_vinculacion(transportista_id: int):
    with SessionLocal() as db:
        t = db.get(Transportista, transportista_id)
        if not t:
            raise HTTPException(404, "transportista_no_existe")
        codigo = servicios.generar_codigo_vinculacion(db, t)
        db.commit()
        return {"transportistaId": t.id, "nombre": t.nombre, "codigo": codigo,
                "expiraEnMinutos": MINUTOS_EXPIRA_CODIGO, "expiraLocal": servicios.hora_local(t.codigo_expira_at)}


@app.post("/manifiestos")
def crear_manifiesto(body: ManifiestoIn):
    if body.tipo_operacion not in ("DEPOSITO", "RETIRO"):
        raise HTTPException(400, "tipo_operacion_invalida")
    if body.peso_declarado_g <= 0:
        raise HTTPException(400, "peso_declarado_debe_ser_mayor_a_cero")
    with SessionLocal() as db:
        if _tiene_manifiesto_pendiente(db, body.contenedor_id):
            raise HTTPException(409, "el_contenedor_ya_tiene_un_manifiesto_pendiente")
        m = Manifiesto(**body.model_dump())
        db.add(m)
        db.commit()
        db.refresh(m)
        return {"id": m.id}


@app.get("/manifiestos")
def listar_manifiestos(naviera_usuario_id: Optional[int] = None, contenedor_id: Optional[str] = None):
    with SessionLocal() as db:
        q = select(Manifiesto)
        if naviera_usuario_id is not None:
            q = q.where(Manifiesto.naviera_usuario_id == naviera_usuario_id)
        if contenedor_id is not None:
            q = q.where(Manifiesto.contenedor_id == contenedor_id)
        rows = db.scalars(q.order_by(Manifiesto.id.desc())).all()
        return [
            {"id": m.id, "contenedorId": m.contenedor_id, "tipoOperacion": m.tipo_operacion,
             "pesoDeclaradoG": m.peso_declarado_g, "toleranciaPct": m.tolerancia_pct,
             "estadoDocumental": m.estado_documental, "canal": m.canal, "anulado": m.anulado,
             "navieraUsuarioId": m.naviera_usuario_id, "transportistaId": m.transportista_id,
             "pesoDeclaradoAnteriorG": m.peso_declarado_anterior_g, "observaciones": m.observaciones,
             "createdAt": m.created_at.isoformat()}
            for m in rows
        ]


@app.post("/manifiestos/{manifiesto_id}/anular")
def anular_manifiesto(manifiesto_id: int):
    with SessionLocal() as db:
        m = db.get(Manifiesto, manifiesto_id)
        if not m:
            raise HTTPException(404, "manifiesto_no_existe")
        turno = db.scalars(select(Turno).where(Turno.manifiesto_id == m.id)).first()
        if turno is not None:
            raise HTTPException(409, "el_manifiesto_ya_tiene_turno_asociado")
        m.anulado = True
        db.commit()
        return {"ok": True}


class DeclaracionIn(BaseModel):
    manifiesto_id: int
    numero_declaracion: str
    regimen: str
    descripcion: str
    valor_declarado: float
    agente_usuario_id: Optional[int] = None


@app.post("/declaraciones")
def presentar_declaracion(body: DeclaracionIn):
    if body.regimen not in ("importacion_definitiva", "deposito_temporal"):
        raise HTTPException(400, "regimen_invalido")
    if len(body.descripcion) < 10:
        raise HTTPException(400, "descripcion_muy_corta")
    if body.valor_declarado <= 0:
        raise HTTPException(400, "valor_declarado_debe_ser_mayor_a_cero")
    with SessionLocal() as db:
        m = db.get(Manifiesto, body.manifiesto_id)
        if not m:
            raise HTTPException(404, "manifiesto_no_existe")
        if m.estado_documental != "declarado":
            raise HTTPException(409, "el_manifiesto_no_esta_en_estado_declarado")
        d = Declaracion(**body.model_dump())
        db.add(d)
        m.estado_documental = "declaracion_presentada"
        db.commit()
        db.refresh(d)
        return {"id": d.id}


@app.post("/manifiestos/{manifiesto_id}/solicitar-levante")
def solicitar_levante(manifiesto_id: int):
    with SessionLocal() as db:
        m = db.get(Manifiesto, manifiesto_id)
        if not m:
            raise HTTPException(404, "manifiesto_no_existe")
        if m.estado_documental != "declaracion_presentada":
            raise HTTPException(409, "falta_presentar_la_declaracion")
        m.estado_documental = "levante_solicitado"
        db.commit()
        return {"ok": True}


class LevanteIn(BaseModel):
    otorgar: bool
    canal: Optional[str] = None  # obligatorio si otorgar=True
    motivo_retencion: Optional[str] = None  # obligatorio si otorgar=False


@app.post("/manifiestos/{manifiesto_id}/levante")
def resolver_levante(manifiesto_id: int, body: LevanteIn):
    with SessionLocal() as db:
        m = db.get(Manifiesto, manifiesto_id)
        if not m:
            raise HTTPException(404, "manifiesto_no_existe")
        if m.estado_documental != "levante_solicitado":
            raise HTTPException(409, "no_hay_solicitud_de_levante_pendiente")
        if body.otorgar:
            if body.canal not in ("verde", "rojo"):
                raise HTTPException(400, "canal_obligatorio_al_otorgar")
            m.estado_documental = "levante_otorgado"
            m.canal = body.canal
            texto = (f"PORTUS: levante OTORGADO para el contenedor {m.contenedor_id}.\n"
                     f"Canal asignado: {body.canal.upper()}")
            if body.canal == "rojo":
                texto += "\nEl vehiculo sera enviado a verificacion (parqueo) despues del pesaje de entrada."
            texto += "\nYa puedes pedir tu cita con /cita."
            servicios.encolar_notificacion(db, m.transportista_id, "levante_otorgado", texto,
                                            referencia=f"manifiesto:{m.id}")
        else:
            if not body.motivo_retencion:
                raise HTTPException(400, "motivo_obligatorio_al_retener")
            m.estado_documental = "levante_retenido"
            m.observaciones = (m.observaciones or "") + f"\n[levante retenido] {body.motivo_retencion}"
            servicios.encolar_notificacion(
                db, m.transportista_id, "levante_retenido",
                f"PORTUS: levante RETENIDO para el contenedor {m.contenedor_id}.\n"
                f"Motivo: {body.motivo_retencion}",
                referencia=f"manifiesto:{m.id}")
        db.commit()
        return {"ok": True, "estadoDocumental": m.estado_documental, "canal": m.canal}


# ══════════════════════════════════════════════════════════════════════════
#  Garita (validacion de acceso del lado servidor)
# ══════════════════════════════════════════════════════════════════════════

class IngresoIn(BaseModel):
    contenedor_id: str
    vehiculo_uid: str
    transportista_id: Optional[int] = None


@app.post("/garita/ingreso")
def garita_ingreso(body: IngresoIn):
    """Pieza de servidor de la validacion de acceso (sec. 12). Falta que el
    firmware de la garita llame esto en vez de decidir con su tabla local
    (ver Observaciones_Firmware_PersonaA.md, punto 2 — dependencia conocida,
    no resuelta en esta pasada de B)."""
    with SessionLocal() as db:
        try:
            turno = servicios.procesar_ingreso_garita(
                db, body.contenedor_id, body.vehiculo_uid, body.transportista_id,
                publish_cmd=make_publish_and_audit(db),
            )
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            if str(exc) == "parqueo_lleno":
                servicios.generar_alarma(db, "AL11", origen="garita",
                                          descripcion=f"Parqueo lleno, ingreso rechazado ({body.contenedor_id})")
                db.commit()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"turnoId": turno.id, "estado": turno.estado}


# ══════════════════════════════════════════════════════════════════════════
#  Turnos
# ══════════════════════════════════════════════════════════════════════════

def _turno_dict(t: Turno) -> dict:
    return {
        "id": t.id, "manifiestoId": t.manifiesto_id, "vehiculoUid": t.vehiculo_uid,
        "contenedorId": t.contenedor_id, "tipoOperacion": t.tipo_operacion, "estado": t.estado,
        "estacionActual": t.estacion_actual, "pesoDeclaradoG": t.peso_declarado_g,
        "pesoMedidoEntradaG": t.peso_medido_entrada_g, "pesoMedidoSalidaG": t.peso_medido_salida_g,
        "posicionPatio": t.posicion_patio, "createdAt": t.created_at.isoformat(),
        "closedAt": t.closed_at.isoformat() if t.closed_at else None,
    }


@app.get("/turnos")
def listar_turnos(estado: Optional[str] = None, tipo_operacion: Optional[str] = None):
    with SessionLocal() as db:
        q = select(Turno)
        if estado:
            q = q.where(Turno.estado == estado)
        if tipo_operacion:
            q = q.where(Turno.tipo_operacion == tipo_operacion)
        rows = db.scalars(q.order_by(Turno.id.desc())).all()
        return [_turno_dict(t) for t in rows]


@app.get("/turnos/{turno_id}")
def detalle_turno(turno_id: int):
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        eventos = db.scalars(
            select(EventoTurno).where(EventoTurno.turno_id == turno_id).order_by(EventoTurno.ts)
        ).all()
        data = _turno_dict(t)
        data["lineaDeTiempo"] = [
            {"ts": e.ts.isoformat(), "origen": e.origen, "descripcion": e.descripcion,
             "valores": json.loads(e.valores_json)}
            for e in eventos
        ]
        return data


class PesajeIn(BaseModel):
    peso_medido_g: int


@app.post("/turnos/{turno_id}/pesaje-entrada")
def pesaje_entrada(turno_id: int, body: PesajeIn):
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        try:
            servicios.procesar_pesaje_entrada(db, t, body.peso_medido_g, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True, "estado": t.estado}


@app.post("/turnos/{turno_id}/pesaje-salida")
def pesaje_salida(turno_id: int, body: PesajeIn):
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        try:
            servicios.procesar_pesaje_salida(db, t, body.peso_medido_g, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True, "estado": t.estado}


class AvanzarIn(BaseModel):
    nuevo_estado: str
    descripcion: Optional[str] = None


@app.post("/turnos/{turno_id}/avanzar")
def avanzar_turno(turno_id: int, body: AvanzarIn):
    """Ayuda generica para progresar el turno por los estados que no dependen
    de una regla de negocio propia (EnRuta->EnTransferencia->EnPesajeSalida,
    EnSalida). Los pasos con regla propia (pesaje, retencion) tienen su
    endpoint dedicado arriba."""
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        try:
            servicios.transicionar_turno(db, t, body.nuevo_estado, origen="servidor",
                                          descripcion=body.descripcion or "")
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True, "estado": t.estado}


@app.post("/turnos/{turno_id}/cerrar")
def cerrar_turno_endpoint(turno_id: int):
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        try:
            servicios.cerrar_turno(db, t, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True}


class AnularIn(BaseModel):
    causa: Optional[str] = None


@app.post("/turnos/{turno_id}/anular")
def anular_turno_endpoint(turno_id: int, body: AnularIn):
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        try:
            servicios.anular_turno(db, t, body.causa, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True, "estado": t.estado}


class RetenerManualIn(BaseModel):
    causa: str  # RT05 o RT06
    rol_usuario: str
    observacion: Optional[str] = None


@app.post("/turnos/{turno_id}/retener")
def retener_manual(turno_id: int, body: RetenerManualIn):
    if body.causa not in ("RT05", "RT06"):
        raise HTTPException(400, "esta_via_es_solo_para_retencion_manual_RT05_RT06")
    rol_esperado = "AUTORIDAD" if body.causa == "RT05" else "TERMINAL"
    if body.rol_usuario != rol_esperado:
        raise HTTPException(403, f"rol_no_facultado_para_{body.causa}")
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        try:
            r = servicios.retener_manualmente(db, t, body.causa, body.observacion, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"retencionId": r.id, "estado": t.estado}


# ══════════════════════════════════════════════════════════════════════════
#  Retenciones
# ══════════════════════════════════════════════════════════════════════════

@app.get("/retenciones")
def listar_retenciones(estado: Optional[str] = None, causa: Optional[str] = None):
    with SessionLocal() as db:
        q = select(Retencion)
        if estado:
            q = q.where(Retencion.estado == estado)
        if causa:
            if causa not in CAUSAS_RETENCION:
                raise HTTPException(400, "causa_invalida")
            q = q.where(Retencion.causa == causa)
        rows = db.scalars(q.order_by(Retencion.id.desc())).all()
        return [
            {"id": r.id, "turnoId": r.turno_id, "causa": r.causa, "estacion": r.estacion,
             "plaza": r.plaza, "estado": r.estado, "resolucion": r.resolucion,
             "pesoDeclaradoG": r.peso_declarado_g, "pesoMedidoG": r.peso_medido_g,
             "createdAt": r.created_at.isoformat()}
            for r in rows
        ]


class ResolverRetencionIn(BaseModel):
    resolucion: str  # aclarar | corregir | rechazar
    rol_usuario: str
    motivo: Optional[str] = None
    observacion: Optional[str] = None


@app.post("/retenciones/{retencion_id}/resolver")
def resolver_retencion_endpoint(retencion_id: int, body: ResolverRetencionIn):
    if body.rol_usuario not in ROLES:
        raise HTTPException(400, "rol_invalido")
    with SessionLocal() as db:
        try:
            r = servicios.resolver_retencion(
                db, retencion_id, body.resolucion, body.rol_usuario,
                body.motivo, body.observacion, publish_cmd=make_publish_and_audit(db),
            )
        except PermissionError as exc:
            db.rollback()
            raise HTTPException(403, str(exc))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True, "retencionId": r.id, "resolucion": r.resolucion}


# ══════════════════════════════════════════════════════════════════════════
#  Patio y parqueo
# ══════════════════════════════════════════════════════════════════════════

@app.get("/patio")
def listar_patio():
    with SessionLocal() as db:
        rows = db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all()
        return [
            {"id": p.id, "estado": p.estado, "contenedorNivel1": p.contenedor_nivel1,
             "contenedorNivel2": p.contenedor_nivel2, "remociones": p.remociones}
            for p in rows
        ]


@app.post("/patio/{posicion_id}/bloquear")
def bloquear_patio(posicion_id: int):
    with SessionLocal() as db:
        try:
            servicios.bloquear_posicion_patio(db, posicion_id)
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        make_publish_and_audit(db)("PosicionBloquear", "MEGA_GRUA", {"pos": posicion_id})
        db.commit()
        return {"ok": True}


@app.post("/patio/{posicion_id}/liberar")
def liberar_patio(posicion_id: int):
    with SessionLocal() as db:
        try:
            servicios.liberar_posicion_patio(db, posicion_id)
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        make_publish_and_audit(db)("PosicionLiberar", "MEGA_GRUA", {"pos": posicion_id})
        db.commit()
        return {"ok": True}


@app.get("/parqueo")
def listar_parqueo():
    with SessionLocal() as db:
        rows = db.scalars(select(ParqueoPlaza).order_by(ParqueoPlaza.id)).all()
        return [{"id": p.id, "ocupada": p.ocupada, "turnoId": p.turno_id} for p in rows]


# ══════════════════════════════════════════════════════════════════════════
#  Alarmas
# ══════════════════════════════════════════════════════════════════════════

@app.get("/alarmas")
def listar_alarmas(estado: Optional[str] = None, severidad: Optional[str] = None):
    with SessionLocal() as db:
        q = select(Alarma)
        if estado:
            q = q.where(Alarma.estado == estado)
        if severidad:
            q = q.where(Alarma.severidad == severidad)
        rows = db.scalars(q.order_by(Alarma.id.desc())).all()
        return [
            {"id": a.id, "codigo": a.codigo, "severidad": a.severidad, "origen": a.origen,
             "descripcion": a.descripcion, "estado": a.estado, "createdAt": a.created_at.isoformat()}
            for a in rows
        ]


class AckIn(BaseModel):
    comentario: Optional[str] = None


@app.post("/alarmas/{alarma_id}/reconocer")
def reconocer_alarma_endpoint(alarma_id: int, body: AckIn):
    with SessionLocal() as db:
        try:
            servicios.reconocer_alarma(db, alarma_id, body.comentario)
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(404, str(exc))
        db.commit()
        return {"ok": True}


@app.post("/alarmas/reconocer-todas")
def reconocer_todas_endpoint():
    with SessionLocal() as db:
        n = servicios.reconocer_todas_media_baja(db)
        db.commit()
        return {"ok": True, "reconocidas": n}
