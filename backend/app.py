import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select

import camara_garita
import estacion
import grua
import iluminacion
import orquestador
import reportes
import servicios
from catalogos import (
    CAUSAS_RETENCION, CONTENEDORES_MAQUETA, ESTADOS_FINALES, POLITICAS_PATIO, ROL_FACULTADO_POR_CAUSA, DISPOSITIVOS, MINUTOS_EXPIRA_CODIGO, ROLES, SEGUNDOS_REVISION_ALARMAS,
    UMBRAL_ENLACE_PERDIDO_S,
)
from models import (
    Alarma, Cita, CommandAudit, ContenedorCatalogo, Corrida, Declaracion, GruaCiclo, ManifiestoEvento, EventLog, EventoTurno, IntentoIngreso, LinkDevice,
    LinkStatus, Manifiesto, ParqueoPlaza, PosicionPatio, Retencion, Turno,
    Transportista, Usuario, Vehiculo, make_db,
)
import garita_verificacion
from models import LecturaPlaca, PlacaRestringida
from security import verify_password

DB_PATH = os.getenv("PORTUS_DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "portus_core.db")))
SessionLocal = make_db(DB_PATH)
MQTT_HOST = os.getenv("PORTUS_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("PORTUS_MQTT_PORT", "1883"))

app = FastAPI(title="PORTUS Backend Core (Persona B)")
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
started = False
# Cada alarma nueva (portus/srv/alarma) y cada cambio de turnos, retenciones,
# parqueo y patio (portus/srv/cambio) sale por MQTT al confirmarse: la web lo muestra en vivo.
orquestador.anunciar_cambios(SessionLocal, lambda t, p: mqttc.publish(t, p))


# Fase 3: estacion meteorologica -> iluminacion (luz) y clima (lluvia -> grua).
def _enviar_comando_mega(name: str, target: str, params: dict) -> None:
    with SessionLocal() as db:
        make_publish_and_audit(db)(name, target, params)
        db.commit()


def _auditar_iluminacion(detalle: dict) -> None:
    with SessionLocal() as db:
        db.add(CommandAudit(
            cmd_name="CambioModoIluminacion", target="SERVIDOR",
            request_json=json.dumps(detalle, ensure_ascii=False), result="OK", response_json="{}",
        ))
        db.commit()


control_iluminacion = iluminacion.ControlIluminacion(
    enviar=_enviar_comando_mega, auditar=_auditar_iluminacion,
)
# Sec. 4.2 r2: antes de fotografiar una placa, la planta debe estar encendida.
camara_garita.set_preparador_iluminacion(control_iluminacion.para_captura)
registro_estacion = estacion.RegistroEstacion()

CLAVE_CONFIG_CLIMA = "clima_actual"  # snapshot que lee el bot para /clima (sec. 9.1)


def _afectados_por_lluvia(db) -> list[int]:
    """Transportistas con turno activo en la terminal (sec. 3.3). La cita en franja
    se cubre con la notificacion de cita; aqui avisamos a los que estan operando."""
    ids = db.scalars(
        select(Turno.transportista_id)
        .where(Turno.estado.not_in(ESTADOS_FINALES), Turno.transportista_id.is_not(None))
        .distinct()
    ).all()
    return [i for i in ids if i is not None]


def _guardar_snapshot_clima(disponible: bool) -> None:
    """Deja el ultimo clima y el estado de la grua en la tabla configuracion para /clima."""
    ultima = registro_estacion.ultima()
    datos = {
        "ok": disponible and ultima is not None,
        "t": getattr(ultima, "temperatura", None) if ultima else None,
        "h": getattr(ultima, "humedad", None) if ultima else None,
        "ll": getattr(ultima, "lluvia", None) if ultima else None,
        "luz": getattr(ultima, "luz", None) if ultima else None,
        "ts": getattr(ultima, "ts", None) if ultima else None,
        "susp": control_clima_lluvia.suspendido_por_lluvia,
        "susp_desde": _suspension_desde[0],
    }
    with SessionLocal() as db:
        servicios.set_config_json(db, CLAVE_CONFIG_CLIMA, datos)
        db.commit()


_suspension_desde = [None]  # hora ISO del inicio de la suspension por lluvia vigente


def _al_cambiar_clima(suspendido: bool) -> None:
    """Sec. 2.2 / 3.3: inicio y fin de la suspension por lluvia -> portus/evt/clima,
    alarma AL17 y avisos a los transportistas afectados."""
    ahora = datetime.now(timezone.utc)
    if suspendido:
        _suspension_desde[0] = ahora.isoformat()
        with SessionLocal() as db:
            servicios.generar_alarma(db, "AL17", origen="estacion",
                                     descripcion="Lluvia detectada, grua suspendida")
            texto = (f"PORTUS: operacion de grua suspendida por lluvia desde "
                     f"{servicios.hora_local(ahora, '%H:%M')}. Tu operacion podria demorarse.")
            for tid in _afectados_por_lluvia(db):
                servicios.encolar_notificacion(db, tid, "grua_suspendida_lluvia", texto)
            db.commit()
        mqttc.publish("portus/evt/clima",
                      json.dumps({"estado": "suspension", "motivo": "Clima", "ts": ahora.isoformat()}))
    else:
        inicio = _suspension_desde[0]
        _suspension_desde[0] = None
        with SessionLocal() as db:
            texto = f"PORTUS: operacion de grua reanudada a las {servicios.hora_local(ahora, '%H:%M')}."
            for tid in _afectados_por_lluvia(db):
                servicios.encolar_notificacion(db, tid, "grua_reanudada_lluvia", texto)
            db.commit()
        mqttc.publish("portus/evt/clima",
                      json.dumps({"estado": "reanudacion", "desde": inicio, "ts": ahora.isoformat()}))
    _guardar_snapshot_clima(disponible=True)


control_clima_lluvia = estacion.ControlClimaLluvia(
    enviar=_enviar_comando_mega, al_cambiar=_al_cambiar_clima,
)


def _publicar_config_estacion_mqtt() -> None:
    seg_l = int(os.getenv("PORTUS_ESTACION_LECTURA_S", estacion.CONFIG_LECTURA_DEFECTO_S))
    seg_t = int(os.getenv("PORTUS_ESTACION_LATIDO_S", estacion.CONFIG_LATIDO_DEFECTO_S))
    try:
        msg = estacion.mensaje_config_estacion(seg_l, seg_t)
        mqttc.publish(estacion.TOPIC_CONFIG, msg)
        print(f"[ESTACION] config publicada: {msg}")
    except ValueError as exc:
        print(f"[ESTACION] config no publicada: {exc!r}")


def _procesar_lectura_estacion(payload: dict) -> None:
    vigilancia_estacion.senal_de_vida()
    try:
        estacion.procesar_lectura_estacion(
            payload, registro_estacion, control_iluminacion, control_clima_lluvia,
        )
        _guardar_snapshot_clima(disponible=True)
    except Exception as exc:
        print(f"[ESTACION] error procesando lectura: {exc!r}")


# Sec. 3.4: sin latido de la estacion durante 3 periodos, AL16 y la planta encendida.
segundos_latido_vigente = [estacion.CONFIG_LATIDO_DEFECTO_S]


def _alerta_estacion_fuera() -> None:
    print("[ESTACION] fuera de servicio: AL16 y iluminacion encendida")
    with SessionLocal() as db:
        servicios.generar_alarma(db, "AL16", origen="estacion",
                                 descripcion="Estacion meteorologica sin comunicacion")
        db.commit()
    control_iluminacion.encender_sin_estacion()
    _guardar_snapshot_clima(disponible=False)  # /clima respondera que el clima no esta disponible


def _recuperacion_estacion() -> None:
    print("[ESTACION] vuelve a comunicarse; se reaplican las reglas con la lectura nueva")


vigilancia_estacion = estacion.VigilanciaEstacion(
    alerta=_alerta_estacion_fuera,
    recuperacion=_recuperacion_estacion,
    segundos_periodo=lambda: segundos_latido_vigente[0],
)


def vigilancia_estacion_loop() -> None:
    while True:
        time.sleep(1)
        try:
            vigilancia_estacion.revisar()
        except Exception as exc:
            print(f"[ESTACION] error revisando latido: {exc!r}")


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
    for c in CONTENEDORES_MAQUETA:
        if not db.get(ContenedorCatalogo, c):
            db.add(ContenedorCatalogo(contenedor_id=c, descripcion="Contenedor de la maqueta"))
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


def alarmas_por_tiempo_loop() -> None:
    """AL12 (retencion > 30 min) y AL13 (contenedor > 2 h en patio): nadie
    manda un evento cuando pasa el tiempo, asi que se revisa periodicamente."""
    while True:
        time.sleep(SEGUNDOS_REVISION_ALARMAS)
        try:
            with SessionLocal() as db:
                servicios.revisar_alarmas_por_tiempo(db)
                db.commit()
        except Exception as exc:  # que un error no mate el hilo
            print(f"[ALARMAS] error revisando alarmas por tiempo: {exc!r}")


def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe("portus/evt/#")
    client.subscribe("portus/cmd/respuesta")
    client.subscribe("portus/estacion/#")
    upsert_link_status(connected=True)
    if rc == 0:
        _publicar_config_estacion_mqtt()


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

    if topic == "portus/estacion/lectura":
        _procesar_lectura_estacion(payload)
    if topic == "portus/estacion/estado":
        vigilancia_estacion.senal_de_vida()

    if topic == "portus/evt/iluminacion" and payload.get("data", {}).get("evento") == "enlace_restablecido":
        control_iluminacion.resincronizar()

    if topic.startswith("portus/estacion/"):
        return

    # Fase 1: los eventos de garitas y pesaje avanzan el turno solos.
    try:
        orquestador.procesar_evento(SessionLocal, lambda t, p: mqttc.publish(t, p), topic,
                                    payload.get("data", {}), origen=origin)
    except Exception as exc:  # un evento malo no debe tumbar el hilo MQTT
        print(f"[ORQUESTADOR] error procesando {topic}: {exc!r}")

    if topic == "portus/evt/estado":
        upsert_link_status(True, last_ts=int(time.time()), origin=origin)
        if origin in DISPOSITIVOS:
            upsert_link_device(origin, int(time.time()))

    if topic == "portus/cmd/respuesta":
        # Auditoria del comando y, si fue REJ, AL14 con la causa (sec. 11.2)
        with SessionLocal() as db:
            datos = payload.get("data", {})
            servicios.registrar_respuesta_comando(db, origin, evt_type, datos,
                                                  json.dumps(payload, ensure_ascii=False))
            if evt_type == "ACK" and datos.get("name") in ("GruaReanudar", "ModoMantenimiento"):
                # La grua vuelve a admitir trabajos: sigue la cola (E13)
                grua.despachar_trabajo(db, make_publish_and_audit(db))
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
    threading.Thread(target=alarmas_por_tiempo_loop, daemon=True).start()
    threading.Thread(target=vigilancia_estacion_loop, daemon=True).start()


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


class ModoIluminacionIn(BaseModel):
    modo: str  # Automatico | Encendido forzado | Apagado forzado
    origen: str = "API"


class UmbralesIluminacionIn(BaseModel):
    umbral_encendido: int
    umbral_apagado: int


class ConfigEstacionIn(BaseModel):
    segundos_lectura: int = estacion.CONFIG_LECTURA_DEFECTO_S
    segundos_latido: int = estacion.CONFIG_LATIDO_DEFECTO_S


@app.post("/iluminacion/modo")
def cambiar_modo_iluminacion(body: ModoIluminacionIn):
    try:
        control_iluminacion.cambiar_modo(body.modo, origen=body.origen)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "modo": control_iluminacion.modo}


@app.post("/iluminacion/umbrales")
def cambiar_umbrales_iluminacion(body: UmbralesIluminacionIn):
    try:
        control_iluminacion.cambiar_umbrales(body.umbral_encendido, body.umbral_apagado)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    ultima = registro_estacion.ultima()
    if ultima and ultima.luz is not None and control_iluminacion.modo == iluminacion.MODO_AUTOMATICO:
        control_iluminacion.procesar_lectura(ultima.luz)
    return {
        "ok": True,
        "umbral_encendido": control_iluminacion.umbral_encendido,
        "umbral_apagado": control_iluminacion.umbral_apagado,
    }


@app.get("/iluminacion/estado")
def estado_iluminacion():
    return {
        "modo": control_iluminacion.modo,
        "encendida": control_iluminacion.encendida,
        "umbral_encendido": control_iluminacion.umbral_encendido,
        "umbral_apagado": control_iluminacion.umbral_apagado,
        "clima_suspendido_por_lluvia": control_clima_lluvia.suspendido_por_lluvia,
    }


@app.get("/estacion/lectura")
def ultima_lectura_estacion():
    ultima = registro_estacion.ultima()
    if not ultima:
        return {"ok": True, "lectura": None}
    return {"ok": True, "lectura": ultima.to_dict()}


@app.post("/estacion/config")
def publicar_config_estacion(body: ConfigEstacionIn):
    try:
        msg = estacion.mensaje_config_estacion(body.segundos_lectura, body.segundos_latido)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    mqttc.publish(estacion.TOPIC_CONFIG, msg)
    segundos_latido_vigente[0] = body.segundos_latido
    return {"ok": True, "mensaje": msg}


class MotivoVerificacionIn(BaseModel):
    motivo: str
    usuario: str = "terminal"


class RestringirPlacaIn(BaseModel):
    placa: str
    motivo: str
    usuario: str = "autoridad"


class LiberarPlacaIn(BaseModel):
    motivo: str
    usuario: str = "autoridad"


def _auditar_db(db, nombre: str, datos: dict) -> None:
    """Auditoria de acciones de la fase 3 que no son comandos al controlador (sec. 8.8)."""
    db.add(CommandAudit(
        cmd_name=nombre, target="SERVIDOR",
        request_json=json.dumps(datos, ensure_ascii=False), result="OK", response_json="{}",
    ))


def _lectura_dict(f: LecturaPlaca) -> dict:
    return {
        "id": f.id, "uid": f.vehiculo_uid, "placaLeida": f.placa_leida, "confianza": f.confianza,
        "resultado": f.resultado, "causa": f.causa, "foto": f.foto, "turnoId": f.turno_id,
        "pendiente": f.pendiente, "decididoPor": f.decidido_por, "motivo": f.motivo_decision,
        "ts": f.ts.isoformat(),
    }


@app.get("/garita/verificaciones-pendientes")
def listar_verificaciones_pendientes():
    with SessionLocal() as db:
        return [_lectura_dict(f) for f in garita_verificacion.verificaciones_pendientes(db)]


@app.get("/garita/lecturas")
def listar_lecturas_placa(resultado: Optional[str] = None, limit: int = 100):
    with SessionLocal() as db:
        q = db.query(LecturaPlaca).order_by(LecturaPlaca.ts.desc())
        if resultado:
            q = q.filter(LecturaPlaca.resultado == resultado)
        return [_lectura_dict(f) for f in q.limit(limit).all()]


@app.get("/garita/lecturas/{lectura_id}/foto")
def foto_lectura(lectura_id: int):
    with SessionLocal() as db:
        f = db.get(LecturaPlaca, lectura_id)
        if f is None or not f.foto or not os.path.exists(f.foto):
            raise HTTPException(404, "foto_no_disponible")
        return FileResponse(f.foto, media_type="image/jpeg")


@app.post("/garita/verificaciones/{lectura_id}/confirmar")
def confirmar_verificacion(lectura_id: int, body: MotivoVerificacionIn):
    """Sec. 6.2 y 8.2: el operador confirma el ingreso con motivo de al menos 10 caracteres."""
    try:
        motivo = garita_verificacion.validar_motivo(body.motivo)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    with SessionLocal() as db:
        f = db.get(LecturaPlaca, lectura_id)
        if f is None or not f.pendiente:
            raise HTTPException(404, "verificacion_no_pendiente")
        try:
            turno = servicios.ingreso_por_rfid(db, f.vehiculo_uid, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        f.pendiente = False
        f.resultado = "confirmada_manual"
        f.decidido_por = body.usuario
        f.motivo_decision = motivo
        f.turno_id = turno.id
        _auditar_db(db, "ConfirmarVerificacionIngreso", {"lectura": lectura_id, "motivo": motivo, "usuario": body.usuario})
        db.commit()
        return {"ok": True, "turno": turno.id}


@app.post("/garita/verificaciones/{lectura_id}/rechazar")
def rechazar_verificacion(lectura_id: int, body: MotivoVerificacionIn):
    """Sec. 6.2 y 8.2: el operador rechaza; la talanquera no abre y no se crea turno."""
    try:
        motivo = garita_verificacion.validar_motivo(body.motivo)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    with SessionLocal() as db:
        f = db.get(LecturaPlaca, lectura_id)
        if f is None or not f.pendiente:
            raise HTTPException(404, "verificacion_no_pendiente")
        f.pendiente = False
        f.resultado = "rechazada_manual"
        f.decidido_por = body.usuario
        f.motivo_decision = motivo
        servicios.registrar_intento_rechazado(db, f.vehiculo_uid, "garita_entrada",
                                              "verificacion_manual_rechazada", decidido_por=body.usuario)
        make_publish_and_audit(db)("RechazarIngreso", "UNO_ENTRADA",
                                   {"uid": f.vehiculo_uid, "motivo": "Rechazado"})
        _auditar_db(db, "RechazarVerificacionIngreso", {"lectura": lectura_id, "motivo": motivo, "usuario": body.usuario})
        db.commit()
        return {"ok": True}


@app.get("/autoridad/placas-restringidas")
def listar_placas_restringidas():
    """Tabla y historial: las activas y las ya liberadas con quien las libero (sec. 8.3)."""
    with SessionLocal() as db:
        filas = db.query(PlacaRestringida).order_by(PlacaRestringida.restringida_at.desc()).all()
        return [{
            "id": p.id, "placa": p.placa, "motivo": p.motivo, "usuario": p.usuario,
            "restringidaAt": p.restringida_at.isoformat(), "activa": p.activa,
            "liberadaPor": p.liberada_por,
            "liberadaAt": p.liberada_at.isoformat() if p.liberada_at else None,
            "motivoLiberacion": p.motivo_liberacion,
        } for p in filas]


@app.post("/autoridad/placas-restringidas")
def restringir_placa(body: RestringirPlacaIn):
    with SessionLocal() as db:
        try:
            fila = garita_verificacion.restringir(db, body.placa, body.motivo, body.usuario)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        _auditar_db(db, "RestringirPlaca", {"placa": fila.placa, "motivo": fila.motivo, "usuario": body.usuario})
        db.commit()
        return {"ok": True, "id": fila.id, "placa": fila.placa}


@app.post("/autoridad/placas-restringidas/{restriccion_id}/liberar")
def liberar_placa(restriccion_id: int, body: LiberarPlacaIn):
    with SessionLocal() as db:
        try:
            fila = garita_verificacion.liberar(db, restriccion_id, body.motivo, body.usuario)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        _auditar_db(db, "LiberarPlaca", {"placa": fila.placa, "motivo": body.motivo, "usuario": body.usuario})
        db.commit()
        return {"ok": True}


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
    vehiculo_uid: Optional[str] = None
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


# ══════════════════════════════════════════════════════════════════════════
#  Citas (sec. 4.7 y 9). El transportista las pide por el bot; la terminal
#  ve la agenda, cancela, reprograma y bloquea franjas.
# ══════════════════════════════════════════════════════════════════════════

def _fecha_hora(valor: str) -> datetime:
    """Inicio de franja en UTC tal como lo devuelve la agenda (ISO sin zona)."""
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "inicio_invalido")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@app.get("/citas/agenda")
def agenda_citas(fecha: Optional[str] = None):
    fecha = fecha or servicios.hora_local(datetime.utcnow(), "%Y-%m-%d")
    with SessionLocal() as db:
        try:
            return servicios.agenda_del_dia(db, fecha)
        except ValueError:
            raise HTTPException(400, "fecha_invalida_usar_YYYY-MM-DD")


@app.get("/citas/{cita_id}/franjas-disponibles")
def franjas_para_reprogramar(cita_id: int, cantidad: int = 12):
    with SessionLocal() as db:
        if not db.get(Cita, cita_id):
            raise HTTPException(404, "cita_no_existe")
        franjas = servicios.proximas_franjas(db, datetime.utcnow(), cantidad, excluir_cita_id=cita_id)
        return [{"inicio": i.isoformat(), "texto": servicios.texto_franja(i, f)} for i, f in franjas]


class CitaMotivoIn(BaseModel):
    motivo: Optional[str] = None


class ReprogramarIn(BaseModel):
    inicio: str
    motivo: Optional[str] = None


class FranjaIn(BaseModel):
    inicio: str
    motivo: Optional[str] = None


def _ejecutar(accion):
    with SessionLocal() as db:
        try:
            resultado = accion(db)
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return resultado


@app.post("/citas/{cita_id}/cancelar")
def cancelar_cita(cita_id: int, body: CitaMotivoIn):
    return _ejecutar(lambda db: {"ok": True, "estado": servicios.cancelar_cita(db, cita_id, body.motivo).estado})


@app.post("/citas/{cita_id}/reprogramar")
def reprogramar_cita(cita_id: int, body: ReprogramarIn):
    inicio = _fecha_hora(body.inicio)
    return _ejecutar(lambda db: {"ok": True,
                                 "inicio": servicios.reprogramar_cita(db, cita_id, inicio, body.motivo).inicio.isoformat()})


@app.post("/franjas/bloquear")
def bloquear_franja(body: FranjaIn):
    inicio = _fecha_hora(body.inicio)
    return _ejecutar(lambda db: {"ok": True, "inicio": servicios.bloquear_franja(db, inicio, body.motivo).inicio.isoformat()})


@app.post("/franjas/desbloquear")
def desbloquear_franja(body: FranjaIn):
    inicio = _fecha_hora(body.inicio)
    return _ejecutar(lambda db: servicios.desbloquear_franja(db, inicio) or {"ok": True})


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


class VehiculoIn(BaseModel):
    uid: str
    transportista_id: Optional[int] = None
    placa: str = ""
    activo: bool = True


@app.get("/vehiculos")
def listar_vehiculos():
    with SessionLocal() as db:
        rows = db.scalars(select(Vehiculo).order_by(Vehiculo.uid)).all()
        return [{"uid": v.uid, "transportistaId": v.transportista_id, "placa": v.placa, "activo": v.activo}
                for v in rows]


@app.post("/vehiculos")
def registrar_vehiculo(body: VehiculoIn):
    """Alta o cambio de la tarjeta RFID de un vehiculo (tarjeta -> transportista)."""
    uid = servicios.normalizar_uid(body.uid)
    if not uid:
        raise HTTPException(400, "uid_obligatorio")
    with SessionLocal() as db:
        if body.transportista_id is not None and not db.get(Transportista, body.transportista_id):
            raise HTTPException(404, "transportista_no_existe")
        v = db.get(Vehiculo, uid) or Vehiculo(uid=uid)
        v.transportista_id = body.transportista_id
        v.placa = body.placa
        v.activo = body.activo
        db.add(v)
        db.commit()
        return {"uid": uid}


class PruebaIngresoIn(BaseModel):
    uid: str
    placa: str = ""
    transportista_id: Optional[int] = None


@app.post("/pruebas/preparar-ingreso")
def preparar_ingreso_prueba(body: PruebaIngresoIn):
    """ATAJO SOLO PARA PRUEBAS (escenarios sec. 11): deja un vehiculo listo para
    entrar sin recorrer naviera -> agente -> autoridad. Registra la tarjeta con su
    placa y conductor, anula el turno activo que hubiera y crea un manifiesto con
    levante verde para esa tarjeta. Se desactiva con PORTUS_PRUEBAS=0."""
    if os.getenv("PORTUS_PRUEBAS", "1") != "1":
        raise HTTPException(403, "modo_pruebas_desactivado")
    uid = servicios.normalizar_uid(body.uid)
    if not uid:
        raise HTTPException(400, "uid_obligatorio")
    placa = (body.placa or "").strip().upper()
    with SessionLocal() as db:
        if body.transportista_id is not None and not db.get(Transportista, body.transportista_id):
            raise HTTPException(404, "transportista_no_existe")
        # 1) tarjeta -> placa + conductor
        v = db.get(Vehiculo, uid) or Vehiculo(uid=uid)
        v.transportista_id = body.transportista_id
        v.placa = placa
        v.activo = True
        db.add(v)
        # 2) libera el turno activo anterior (para poder repetir el ingreso en pruebas)
        turno = servicios.turno_activo_por_uid(db, uid)
        if turno is not None:
            servicios.liberar_plazas_de_turno(db, turno.id)
            turno.estado = "Anulado"
            turno.closed_at = datetime.utcnow()
            servicios.registrar_evento(db, turno.id, "pruebas", "Turno reiniciado por el boton de pruebas")
        # 3) contenedor de pruebas en el catalogo
        cont = ("PRUEBA" + uid.replace(" ", ""))[:32]
        if not db.get(ContenedorCatalogo, cont):
            db.add(ContenedorCatalogo(contenedor_id=cont, descripcion="Contenedor de pruebas", activo=True))
        # 4) manifiesto con levante verde para esta tarjeta (si no hay uno usable)
        man = db.scalars(
            select(Manifiesto).where(Manifiesto.vehiculo_uid == uid, Manifiesto.anulado.is_(False))
            .order_by(Manifiesto.id.desc())
        ).first()
        if man is None or man.estado_documental != "levante_otorgado" or not servicios._manifiesto_sin_turno(db, man):
            man = Manifiesto(contenedor_id=cont, tipo_operacion="DEPOSITO", peso_declarado_g=1000,
                             transportista_id=body.transportista_id, vehiculo_uid=uid,
                             estado_documental="levante_otorgado", canal="verde")
            db.add(man)
            db.flush()
        db.commit()
        return {"ok": True, "uid": uid, "placa": placa,
                "contenedor": man.contenedor_id, "manifiesto": man.id}


@app.post("/manifiestos")
def crear_manifiesto(body: ManifiestoIn):
    if body.tipo_operacion not in ("DEPOSITO", "RETIRO"):
        raise HTTPException(400, "tipo_operacion_invalida")
    if body.peso_declarado_g <= 0:
        raise HTTPException(400, "peso_declarado_debe_ser_mayor_a_cero")
    contenedor = body.contenedor_id.strip().upper()
    with SessionLocal() as db:
        catalogo = db.get(ContenedorCatalogo, contenedor)
        if catalogo is None or not catalogo.activo:
            # Sec. 5.1: debe existir en el catalogo de contenedores de la maqueta
            raise HTTPException(400, "contenedor_no_existe_en_el_catalogo_de_la_maqueta")
        if _tiene_manifiesto_pendiente(db, contenedor):
            raise HTTPException(409, "el_contenedor_ya_tiene_un_manifiesto_pendiente")
        if body.transportista_id is not None and not db.get(Transportista, body.transportista_id):
            raise HTTPException(404, "transportista_no_existe")
        datos = body.model_dump()
        datos["contenedor_id"] = contenedor
        datos["vehiculo_uid"] = servicios.normalizar_uid(datos["vehiculo_uid"]) or None
        m = Manifiesto(**datos)
        db.add(m)
        db.flush()
        servicios.registrar_evento_manifiesto(db, m.id, "naviera", "Manifiesto declarado",
                                              {"peso_g": m.peso_declarado_g, "tolerancia_pct": m.tolerancia_pct,
                                               "operacion": m.tipo_operacion})
        db.commit()
        db.refresh(m)
        return {"id": m.id}


def _manifiesto_dict(db, m: Manifiesto, usuarios: dict, transportistas: dict) -> dict:
    decl = db.scalars(select(Declaracion).where(Declaracion.manifiesto_id == m.id)
                      .order_by(Declaracion.id.desc())).first()
    return {
        "id": m.id, "contenedorId": m.contenedor_id, "tipoOperacion": m.tipo_operacion,
        "pesoDeclaradoG": m.peso_declarado_g, "toleranciaPct": m.tolerancia_pct,
        "estadoDocumental": m.estado_documental, "canal": m.canal, "anulado": m.anulado,
        "navieraUsuarioId": m.naviera_usuario_id, "navieraNombre": usuarios.get(m.naviera_usuario_id),
        "transportistaId": m.transportista_id, "transportistaNombre": transportistas.get(m.transportista_id),
        "vehiculoUid": m.vehiculo_uid, "motivoLevante": m.motivo_levante,
        "pesoDeclaradoAnteriorG": m.peso_declarado_anterior_g, "observaciones": m.observaciones,
        "declaracionId": decl.id if decl else None, "numeroDeclaracion": decl.numero_declaracion if decl else None,
        "agenteNombre": usuarios.get(decl.agente_usuario_id) if decl else None,
        "estadoOperativo": reportes.estado_operativo(db, m)["estadoOperativo"],
        "createdAt": m.created_at.isoformat(),
    }


def _nombres(db) -> tuple:
    usuarios = {u.id: (u.nombre or u.username) for u in db.scalars(select(Usuario)).all()}
    return usuarios, _nombres_transportistas(db)


@app.get("/manifiestos")
def listar_manifiestos(naviera_usuario_id: Optional[int] = None, contenedor_id: Optional[str] = None,
                       estado_documental: Optional[str] = None):
    with SessionLocal() as db:
        q = select(Manifiesto)
        if naviera_usuario_id is not None:
            q = q.where(Manifiesto.naviera_usuario_id == naviera_usuario_id)
        if contenedor_id is not None:
            q = q.where(Manifiesto.contenedor_id == contenedor_id)
        if estado_documental:
            q = q.where(Manifiesto.estado_documental == estado_documental)
        rows = db.scalars(q.order_by(Manifiesto.id.desc())).all()
        usuarios, transportistas = _nombres(db)
        return [_manifiesto_dict(db, m, usuarios, transportistas) for m in rows]


@app.get("/manifiestos/{manifiesto_id}")
def detalle_manifiesto(manifiesto_id: int):
    """Sec. 5.1 Ver detalle y 5.5 Ver declaracion: el manifiesto completo, su
    declaracion, su historial, sus turnos y las observaciones del agente."""
    with SessionLocal() as db:
        m = db.get(Manifiesto, manifiesto_id)
        if not m:
            raise HTTPException(404, "manifiesto_no_existe")
        usuarios, transportistas = _nombres(db)
        datos = _manifiesto_dict(db, m, usuarios, transportistas)
        datos.update(reportes.estado_operativo(db, m))
        decl = db.get(Declaracion, datos["declaracionId"]) if datos["declaracionId"] else None
        datos["declaracion"] = None if decl is None else {
            "id": decl.id, "numero": decl.numero_declaracion, "regimen": decl.regimen,
            "descripcion": decl.descripcion, "valorDeclarado": decl.valor_declarado,
            "agente": usuarios.get(decl.agente_usuario_id), "createdAt": decl.created_at.isoformat(),
        }
        eventos = db.scalars(select(ManifiestoEvento).where(ManifiestoEvento.manifiesto_id == m.id)
                             .order_by(ManifiestoEvento.ts, ManifiestoEvento.id)).all()
        datos["historial"] = [{"ts": e.ts.isoformat(), "origen": e.origen, "tipo": e.tipo,
                               "descripcion": e.descripcion, "valores": json.loads(e.valores_json)} for e in eventos]
        datos["observacionesAgente"] = [h for h in datos["historial"] if h["tipo"] == "observacion"]
        datos["turnos"] = [_turno_dict(t, transportistas) for t in db.scalars(
            select(Turno).where(Turno.manifiesto_id == m.id).order_by(Turno.id)).all()]
        return datos


class ObservacionManifiestoIn(BaseModel):
    texto: str
    agente_usuario_id: Optional[int] = None


@app.post("/manifiestos/{manifiesto_id}/observaciones")
def adjuntar_observacion(manifiesto_id: int, body: ObservacionManifiestoIn):
    """Sec. 5.3 Adjuntar observacion: nota documental visible para la autoridad."""
    texto = body.texto.strip()
    if not texto:
        raise HTTPException(400, "observacion_vacia")
    with SessionLocal() as db:
        m = db.get(Manifiesto, manifiesto_id)
        if not m:
            raise HTTPException(404, "manifiesto_no_existe")
        autor = db.get(Usuario, body.agente_usuario_id) if body.agente_usuario_id else None
        servicios.registrar_evento_manifiesto(db, m.id, "agente", texto,
                                              {"agente": autor.nombre or autor.username if autor else None},
                                              tipo="observacion")
        db.commit()
        return {"ok": True}


@app.get("/contenedores")
def catalogo_contenedores():
    with SessionLocal() as db:
        return [{"contenedorId": c.contenedor_id, "descripcion": c.descripcion, "activo": c.activo}
                for c in db.scalars(select(ContenedorCatalogo).order_by(ContenedorCatalogo.contenedor_id)).all()]


@app.get("/carga")
def consulta_carga(naviera_usuario_id: Optional[int] = None, q: Optional[str] = None,
                   naviera: Optional[str] = None, estado_documental: Optional[str] = None):
    """Sec. 5.2 (naviera, solo lo propio) y 5.7 (autoridad, todo): ubicacion,
    estado, autorizacion y reloj de permanencia de cada contenedor."""
    with SessionLocal() as db:
        return reportes.estado_de_carga(db, naviera_usuario_id, q, naviera, estado_documental)


@app.get("/declaraciones")
def seguimiento_declaraciones(agente_usuario_id: Optional[int] = None, q: Optional[str] = None,
                              estado: Optional[str] = None):
    """Sec. 5.4 Seguimiento: pendiente, autorizada o retenida, con canal y motivo."""
    with SessionLocal() as db:
        query = select(Declaracion).order_by(Declaracion.id.desc())
        if agente_usuario_id is not None:
            query = query.where(Declaracion.agente_usuario_id == agente_usuario_id)
        usuarios, _ = _nombres(db)
        filas = []
        for d in db.scalars(query).all():
            m = db.get(Manifiesto, d.manifiesto_id)
            situacion = {"levante_otorgado": "autorizada", "levante_retenido": "retenida"}.get(
                m.estado_documental if m else "", "pendiente")
            if q and q.strip().upper() not in d.numero_declaracion.upper():
                continue
            if estado and situacion != estado:
                continue
            filas.append({"id": d.id, "numeroDeclaracion": d.numero_declaracion, "manifiestoId": d.manifiesto_id,
                          "contenedorId": m.contenedor_id if m else None, "regimen": d.regimen,
                          "estadoDocumental": m.estado_documental if m else None, "situacion": situacion,
                          "canal": m.canal if m else None, "motivoRetencion": m.motivo_levante if m else None,
                          "naviera": usuarios.get(m.naviera_usuario_id) if m else None,
                          "createdAt": d.created_at.isoformat()})
        return filas


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
        servicios.registrar_evento_manifiesto(db, m.id, "naviera", "Manifiesto anulado")
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
        numero = body.numero_declaracion.strip()
        if db.scalars(select(Declaracion.id).where(Declaracion.numero_declaracion == numero)).first():
            # Sec. 5.3: unico en el sistema (antes explotaba con un error 500 de la base)
            raise HTTPException(409, "numero_de_declaracion_ya_existe")
        d = Declaracion(**{**body.model_dump(), "numero_declaracion": numero})
        db.add(d)
        m.estado_documental = "declaracion_presentada"
        servicios.registrar_evento_manifiesto(db, m.id, "agente", f"Declaracion {numero} presentada",
                                              {"regimen": body.regimen, "valor": body.valor_declarado})
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
        servicios.registrar_evento_manifiesto(db, m.id, "agente", "Levante solicitado a la autoridad")
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
            m.motivo_levante = None
            servicios.registrar_evento_manifiesto(db, m.id, "autoridad",
                                                  f"Levante otorgado, canal {body.canal}", {"canal": body.canal})
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
            m.motivo_levante = body.motivo_retencion
            servicios.registrar_evento_manifiesto(db, m.id, "autoridad", "Levante retenido",
                                                  {"motivo": body.motivo_retencion})
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
    """Ingreso manual por contenedor (pruebas sin maqueta). En operacion
    normal la garita manda el UID y lo resuelve orquestador.py."""
    with SessionLocal() as db:
        try:
            turno = servicios.procesar_ingreso_garita(
                db, body.contenedor_id, servicios.normalizar_uid(body.vehiculo_uid), body.transportista_id,
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


@app.get("/garita/intentos")
def listar_intentos(estacion: Optional[str] = None, limit: int = 100):
    """Intentos rechazados en garita (sec. 7 regla 1): no crean turno."""
    with SessionLocal() as db:
        q = select(IntentoIngreso)
        if estacion:
            q = q.where(IntentoIngreso.estacion == estacion)
        rows = db.scalars(q.order_by(IntentoIngreso.id.desc()).limit(limit)).all()
        return [
            {"id": i.id, "vehiculoUid": i.vehiculo_uid, "contenedorId": i.contenedor_id,
             "estacion": i.estacion, "causa": i.causa, "decididoPor": i.decidido_por,
             "ts": i.ts.isoformat()}
            for i in rows
        ]


# ══════════════════════════════════════════════════════════════════════════
#  Turnos
# ══════════════════════════════════════════════════════════════════════════

def _turno_dict(t: Turno, nombres: Optional[dict] = None) -> dict:
    fin = t.closed_at or datetime.utcnow()
    return {
        "id": t.id, "manifiestoId": t.manifiesto_id, "vehiculoUid": t.vehiculo_uid,
        "transportistaId": t.transportista_id,
        "transportistaNombre": (nombres or {}).get(t.transportista_id),
        "contenedorId": t.contenedor_id, "tipoOperacion": t.tipo_operacion, "estado": t.estado,
        "estacionActual": t.estacion_actual, "pesoDeclaradoG": t.peso_declarado_g,
        "pesoMedidoEntradaG": t.peso_medido_entrada_g, "pesoMedidoSalidaG": t.peso_medido_salida_g,
        "posicionPatio": t.posicion_patio, "createdAt": t.created_at.isoformat(),
        "closedAt": t.closed_at.isoformat() if t.closed_at else None,
        "tiempoEnTerminalS": int((fin - t.created_at).total_seconds()),
    }


def _nombres_transportistas(db) -> dict:
    return {t.id: t.nombre for t in db.scalars(select(Transportista)).all()}


@app.get("/turnos")
def listar_turnos(estado: Optional[str] = None, tipo_operacion: Optional[str] = None,
                  activos: Optional[bool] = None, desde: Optional[str] = None, hasta: Optional[str] = None,
                  q: Optional[str] = None, limit: int = 500):
    """Sec. 4.2: activos / historicos, filtros por estado, tipo, rango de fechas
    (YYYY-MM-DD en hora local) y busqueda por contenedor o vehiculo."""
    with SessionLocal() as db:
        query = select(Turno)
        if estado:
            query = query.where(Turno.estado == estado)
        if tipo_operacion:
            query = query.where(Turno.tipo_operacion == tipo_operacion)
        if activos is True:
            query = query.where(Turno.estado.not_in(ESTADOS_FINALES))
        elif activos is False:
            query = query.where(Turno.estado.in_(ESTADOS_FINALES))
        try:
            inicio, fin = servicios.rango_utc(desde, hasta)
        except ValueError:
            raise HTTPException(400, "fecha_invalida_usar_YYYY-MM-DD")
        if inicio:
            query = query.where(Turno.created_at >= inicio)
        if fin:
            query = query.where(Turno.created_at < fin)
        if q:
            patron = f"%{q.strip().upper()}%"
            query = query.where(Turno.contenedor_id.ilike(patron) | Turno.vehiculo_uid.ilike(patron))
        rows = db.scalars(query.order_by(Turno.id.desc()).limit(limit)).all()
        nombres = _nombres_transportistas(db)
        return [_turno_dict(t, nombres) for t in rows]


@app.get("/turnos/{turno_id}")
def detalle_turno(turno_id: int):
    with SessionLocal() as db:
        t = db.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "turno_no_existe")
        eventos = db.scalars(
            select(EventoTurno).where(EventoTurno.turno_id == turno_id).order_by(EventoTurno.ts)
        ).all()
        data = _turno_dict(t, _nombres_transportistas(db))
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
        turnos = {t.id: t for t in db.scalars(select(Turno).where(Turno.id.in_({r.turno_id for r in rows}))).all()}
        return [_retencion_dict(r, turnos.get(r.turno_id)) for r in rows]


def _retencion_dict(r: Retencion, t: Optional[Turno]) -> dict:
    """Sec. 4.3: la evidencia de peso solo aplica a las causas de peso."""
    fin = r.resolved_at or datetime.utcnow()
    datos = {
        "id": r.id, "turnoId": r.turno_id, "causa": r.causa, "estacion": r.estacion,
        "plaza": r.plaza, "estado": r.estado, "resolucion": r.resolucion,
        "motivo": r.motivo, "observacion": r.observacion,
        "vehiculoUid": t.vehiculo_uid if t else None, "contenedorId": t.contenedor_id if t else None,
        "rolFacultado": ROL_FACULTADO_POR_CAUSA.get(r.causa),
        "pesoDeclaradoG": r.peso_declarado_g, "pesoMedidoG": r.peso_medido_g,
        "diferenciaG": None, "diferenciaPct": None,
        "createdAt": r.created_at.isoformat(),
        "resolvedAt": r.resolved_at.isoformat() if r.resolved_at else None,
        "tiempoRetencionS": int((fin - r.created_at).total_seconds()),
    }
    if r.causa in ("RT01", "RT02") and r.peso_declarado_g and r.peso_medido_g is not None:
        diferencia = r.peso_medido_g - r.peso_declarado_g
        datos["diferenciaG"] = abs(diferencia)
        datos["diferenciaPct"] = round(abs(diferencia) / r.peso_declarado_g * 100, 1)
    return datos


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
             "contenedorNivel2": p.contenedor_nivel2, "remociones": p.remociones,
             "nivel1Desde": p.nivel1_desde.isoformat() if p.nivel1_desde else None,
             "nivel2Desde": p.nivel2_desde.isoformat() if p.nivel2_desde else None}
            for p in rows
        ]


@app.get("/patio/inventario")
def inventario_patio():
    """Sec. 4.4: un renglon por contenedor en el patio."""
    with SessionLocal() as db:
        navieras = {u.id: (u.nombre or u.username) for u in db.scalars(select(Usuario)).all()}
        filas = []
        for p in db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all():
            for nivel, contenedor, desde in ((1, p.contenedor_nivel1, p.nivel1_desde),
                                             (2, p.contenedor_nivel2, p.nivel2_desde)):
                if not contenedor:
                    continue
                m = db.scalars(select(Manifiesto).where(Manifiesto.contenedor_id == contenedor)
                               .order_by(Manifiesto.id.desc())).first()
                t = db.scalars(select(Turno).where(Turno.contenedor_id == contenedor)
                               .order_by(Turno.id.desc())).first()
                filas.append({
                    "contenedorId": contenedor, "posicion": p.id, "nivel": nivel,
                    "naviera": navieras.get(m.naviera_usuario_id) if m else None,
                    "pesoDeclaradoG": m.peso_declarado_g if m else None,
                    "estadoAutorizacion": m.estado_documental if m else None,
                    "ingresoTerminal": t.created_at.isoformat() if t else None,
                    "enPatioDesde": desde.isoformat() if desde else None,
                    "permanenciaS": int((datetime.utcnow() - desde).total_seconds()) if desde else None,
                    # El patio lleva las remociones por posicion; el Mega todavia
                    # no informa movimientos por contenedor (fase 5).
                    "remociones": p.remociones,
                })
        return filas


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
    """Plazas con el vehiculo que la ocupa, su tiempo y si la retencion ya
    fue resuelta (condicion del boton Liberar parqueo, sec. 4.1)."""
    with SessionLocal() as db:
        rows = db.scalars(select(ParqueoPlaza).order_by(ParqueoPlaza.id)).all()
        salida = []
        for p in rows:
            t = db.get(Turno, p.turno_id) if p.turno_id else None
            abierta = servicios.retencion_abierta_de_turno(db, p.turno_id) if p.turno_id else None
            salida.append({
                "id": p.id, "ocupada": p.ocupada, "turnoId": p.turno_id,
                "vehiculoUid": t.vehiculo_uid if t else None, "contenedorId": t.contenedor_id if t else None,
                "desde": p.desde.isoformat() if p.desde else None,
                "retencionAbiertaId": abierta.id if abierta else None,
                "causa": abierta.causa if abierta else None,
                "retencionResuelta": bool(p.ocupada and t is not None and abierta is None),
            })
        return salida


@app.post("/parqueo/{plaza_id}/liberar")
def liberar_parqueo(plaza_id: int):
    with SessionLocal() as db:
        try:
            servicios.solicitar_liberar_parqueo(db, plaza_id, publish_cmd=make_publish_and_audit(db))
        except servicios.ReglaDeNegocioError as exc:
            db.rollback()
            raise HTTPException(409, str(exc))
        db.commit()
        return {"ok": True, "enviado": "AgujaLiberar", "plaza": plaza_id}


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
        return [orquestador.alarma_dict(a) for a in rows]


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


# ══════════════════════════════════════════════════════════════════════════
#  Grua (sec. 4.5): historial de ciclos, tiempos, fallas y CSV
# ══════════════════════════════════════════════════════════════════════════

def _ultimos_ciclos(db, limit: int) -> list:
    if limit not in (50, 100, 200):
        raise HTTPException(400, "rango_valido_50_100_200")
    return db.scalars(select(GruaCiclo).order_by(GruaCiclo.id.desc()).limit(limit)).all()


@app.get("/grua/ciclos")
def ciclos_grua(limit: int = 50):
    """Ultimas N operaciones (50, 100 o 200) con su tiempo de ciclo."""
    with SessionLocal() as db:
        ciclos = _ultimos_ciclos(db, limit)
        completados = [c for c in ciclos if c.resultado == "completado" and c.tipo != "REMOCION"]
        tiempos = [c.duracion_ms for c in completados if c.duracion_ms is not None]
        return {
            "ciclos": [grua.ciclo_dict(c) for c in reversed(ciclos)],
            "completados": len(completados),
            "promedioS": round(sum(tiempos) / len(tiempos) / 1000, 1) if tiempos else None,
        }


@app.get("/grua/ciclos.csv", response_class=PlainTextResponse)
def ciclos_grua_csv(limit: int = 50):
    with SessionLocal() as db:
        texto = reportes.csv_ciclos(list(reversed(_ultimos_ciclos(db, limit))))
    return PlainTextResponse(texto, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="grua_ultimos_{limit}.csv"'})


CODIGOS_FALLA_GRUA = ("AL02", "AL03", "AL04", "AL05", "AL06", "AL07", "AL08")


@app.get("/grua/estado")
def estado_grua():
    """Trabajo en curso, cola de trabajos (orden de atencion) y fallas recientes."""
    with SessionLocal() as db:
        en_curso = grua.ciclo_en_curso(db)
        cola = db.scalars(select(Turno).where(Turno.estado == "EnRuta").order_by(Turno.id)).all()
        fallas = db.scalars(select(Alarma).where(Alarma.codigo.in_(CODIGOS_FALLA_GRUA))
                            .order_by(Alarma.id.desc()).limit(50)).all()
        abortados = db.scalars(select(GruaCiclo).where(GruaCiclo.resultado == "abortado")
                               .order_by(GruaCiclo.id.desc()).limit(50)).all()
        return {
            "trabajoEnCurso": grua.ciclo_dict(en_curso) if en_curso else None,
            "cola": [{"orden": i + 1, "turnoId": t.id, "tipo": t.tipo_operacion, "contenedorId": t.contenedor_id,
                      "vehiculoUid": t.vehiculo_uid, "enviadoALaGrua": t.trabajo_grua_at is not None}
                     for i, t in enumerate(cola)],
            "fallas": [orquestador.alarma_dict(a) for a in fallas],
            "abortados": [grua.ciclo_dict(c) for c in abortados],
            "politicaPatio": grua.politica_patio(db),
        }


# ══════════════════════════════════════════════════════════════════════════
#  Politica de asignacion de posiciones (sec. 13, modo seleccionable)
# ══════════════════════════════════════════════════════════════════════════

class PoliticaIn(BaseModel):
    politica: str


@app.get("/config/politica-patio")
def ver_politica_patio():
    with SessionLocal() as db:
        return {"politica": grua.politica_patio(db), "disponibles": POLITICAS_PATIO}


@app.post("/config/politica-patio")
def cambiar_politica_patio(body: PoliticaIn):
    return _ejecutar(lambda db: grua.cambiar_politica_patio(db, body.politica) or {"ok": True, "politica": body.politica})


# ══════════════════════════════════════════════════════════════════════════
#  Reportes de corrida (sec. 4.8 y 13)
# ══════════════════════════════════════════════════════════════════════════

class ReporteIn(BaseModel):
    desde: str  # hora local, "YYYY-MM-DDTHH:MM" (input datetime-local)
    hasta: str
    etiqueta: str


def _local(valor: str) -> datetime:
    try:
        return servicios.local_a_utc(datetime.fromisoformat(valor))
    except ValueError:
        raise HTTPException(400, "fecha_invalida_usar_YYYY-MM-DDTHH:MM")


def _corrida_dict(c: Corrida) -> dict:
    return {"id": c.id, "etiqueta": c.etiqueta, "desde": c.desde.isoformat(), "hasta": c.hasta.isoformat(),
            "politicaPatio": c.politica_patio, "createdAt": c.created_at.isoformat(),
            "metricas": json.loads(c.metricas_json)}


@app.post("/reportes")
def generar_reporte(body: ReporteIn):
    """Calcula las 8 metricas del rango y guarda la corrida con su etiqueta."""
    desde, hasta = _local(body.desde), _local(body.hasta)
    if hasta <= desde:
        raise HTTPException(400, "el_rango_debe_terminar_despues_de_empezar")
    etiqueta = body.etiqueta.strip() or "corrida sin nombre"
    with SessionLocal() as db:
        corrida = Corrida(etiqueta=etiqueta, desde=desde, hasta=hasta, politica_patio=grua.politica_patio(db),
                          metricas_json=json.dumps(reportes.calcular_metricas(db, desde, hasta)))
        db.add(corrida)
        db.commit()
        return _corrida_dict(corrida)


@app.get("/reportes")
def listar_reportes():
    with SessionLocal() as db:
        return [_corrida_dict(c) for c in db.scalars(select(Corrida).order_by(Corrida.id.desc())).all()]


@app.get("/reportes/{corrida_id}.csv", response_class=PlainTextResponse)
def reporte_csv(corrida_id: int):
    with SessionLocal() as db:
        c = db.get(Corrida, corrida_id)
        if not c:
            raise HTTPException(404, "reporte_no_existe")
        texto = reportes.csv_reporte(c.etiqueta, c.desde, c.hasta, c.politica_patio, json.loads(c.metricas_json),
                                     reportes.detalle_turnos(db, c.desde, c.hasta))
    nombre = "".join(ch if ch.isalnum() else "_" for ch in c.etiqueta)[:40]
    return PlainTextResponse(texto, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="reporte_{c.id}_{nombre}.csv"'})
