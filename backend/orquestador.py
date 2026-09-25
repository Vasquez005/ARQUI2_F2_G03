"""Convierte los eventos de la maqueta (portus/evt/#) en avances del turno.

Antes, app.py:on_message solo guardaba el evento en event_log y los turnos
avanzaban unicamente llamando a los endpoints a mano. Aqui vive el ciclo
fisico automatico (fase 1 del plan de trabajo):

    garita   evento=rfid           -> el servidor decide: AbrirTalanquera o RechazarIngreso
    garita   evento=rechazado      -> registro de intento (si lo decidio el controlador)
    pesaje   evento=meseta         -> procesar_pesaje_entrada (RT01 / RT03 / EnRuta)
    salida   evento=rfid_salida    -> el servidor decide: AbrirPuertaSalida o RechazarSalida
    salida   evento=salida_autorizada;decision=local -> reconcilia una salida sin servidor
    salida   evento=salida_completada -> cierra el turno
    alarma   (cualquier placa)     -> se guarda en alarmas (fase 2)

Fase 2: las alarmas nuevas se anuncian por MQTT (portus/srv/alarma) despues
del commit, para que la web las muestre en vivo sin consultar.

Los comandos se publican DESPUES del commit: si la transaccion se deshace
(rechazo), nunca sale un AbrirTalanquera que la base no respalda.
"""

import json
from typing import Callable, Optional

from sqlalchemy import event, select

import servicios
from catalogos import ANULADO, EN_GARITA, EN_PESAJE_ENTRADA, EN_SALIDA, RETENIDO
from models import Alarma, CommandAudit, Turno

TOPICO_ALARMAS_SERVIDOR = "portus/srv/alarma"

EnviarMqtt = Callable[[str, str], None]  # (topic, payload_json)


class PublicadorDiferido:
    """publish_cmd compatible con servicios.py que audita en la sesion y
    retiene el envio MQTT hasta que se llama enviar() tras el commit."""

    def __init__(self, db, enviar_mqtt: EnviarMqtt):
        self.db = db
        self._enviar_mqtt = enviar_mqtt
        self._pendientes: list[str] = []

    def __call__(self, name: str, target: str, params: dict) -> None:
        payload = json.dumps({"name": name, "target": target, "params": params}, ensure_ascii=False)
        self.db.add(CommandAudit(cmd_name=name, target=target, request_json=payload,
                                 result="PENDING", response_json="{}"))
        self._pendientes.append(payload)

    def descartar(self) -> None:
        self._pendientes.clear()

    def enviar(self) -> None:
        for payload in self._pendientes:
            self._enviar_mqtt("portus/cmd/solicitud", payload)
        self._pendientes.clear()


def _confirmar(db, pub: PublicadorDiferido) -> None:
    db.commit()
    pub.enviar()


# ══════════════════════════════════════════════════════════════════════════
#  Garita de entrada
# ══════════════════════════════════════════════════════════════════════════

def _garita_rfid(db, pub: PublicadorDiferido, datos: dict) -> None:
    uid = servicios.normalizar_uid(datos.get("uid", ""))
    if not uid:
        return
    try:
        servicios.ingreso_por_rfid(db, uid, publish_cmd=pub)
        _confirmar(db, pub)
    except servicios.ReglaDeNegocioError as exc:
        db.rollback()
        pub.descartar()
        causa = str(exc)
        if causa == "parqueo_lleno":
            servicios.generar_alarma(db, "AL11", origen="garita",
                                     descripcion=f"Parqueo lleno, ingreso rechazado ({uid})")
        servicios.registrar_intento_rechazado(db, uid, "garita_entrada", causa,
                                              contenedor_id=getattr(exc, "contenedor_id", None))
        pub("RechazarIngreso", "UNO_ENTRADA", {"uid": uid, "motivo": servicios.motivo_lcd(causa)})
        _confirmar(db, pub)


def _garita_rechazado(db, pub: PublicadorDiferido, datos: dict) -> None:
    """Rechazos que la garita decidio sola (modo degradado o sin respuesta del
    servidor). Los que decidio el servidor ya quedaron registrados."""
    if datos.get("decision") != "local":
        return
    uid = servicios.normalizar_uid(datos.get("uid", ""))
    motivo = datos.get("motivo", "")
    servicios.registrar_intento_rechazado(db, uid, "garita_entrada", motivo, decidido_por="controlador")
    # Si el servidor alcanzo a crear el turno pero la respuesta llego tarde,
    # la barrera nunca se abrio: ese turno no debe quedar vivo.
    turno = servicios.turno_activo_por_uid(db, uid) if uid else None
    if turno is not None and turno.estado == EN_GARITA:
        servicios.transicionar_turno(db, turno, ANULADO, origen="controlador",
                                     descripcion=f"La garita rechazo localmente: {motivo}")
    _confirmar(db, pub)


def _pesaje_meseta(db, pub: PublicadorDiferido, datos: dict) -> None:
    uid = servicios.normalizar_uid(datos.get("uid", ""))
    turno = servicios.turno_activo_por_uid(db, uid) if uid else None
    if turno is None:
        return
    if turno.estado == RETENIDO:
        # Ej. RT04 en garita: el peso se guarda y se aplica al resolver la retencion.
        servicios.guardar_pesaje_durante_retencion(db, turno, servicios.peso_simulado_entrada(turno, datos), datos)
        _confirmar(db, pub)
        return
    if turno.estado not in (EN_GARITA, EN_PESAJE_ENTRADA):
        return
    peso = servicios.peso_simulado_entrada(turno, datos)
    try:
        servicios.procesar_pesaje_entrada(db, turno, peso, publish_cmd=pub)
        if "peso" not in datos:
            servicios.registrar_evento(db, turno.id, "servidor", "Peso simulado a partir del resultado de la garita",
                                       {"resultado": datos.get("resultado"), "peso_g": peso})
        _confirmar(db, pub)
    except servicios.ReglaDeNegocioError:
        db.rollback()
        pub.descartar()


# ══════════════════════════════════════════════════════════════════════════
#  Garita de salida
# ══════════════════════════════════════════════════════════════════════════

def _salida_rfid(db, pub: PublicadorDiferido, datos: dict) -> None:
    uid = servicios.normalizar_uid(datos.get("uid", ""))
    if not uid:
        return
    try:
        servicios.salida_por_rfid(db, uid, publish_cmd=pub)
        _confirmar(db, pub)
    except servicios.ReglaDeNegocioError as exc:
        db.rollback()
        pub.descartar()
        causa = str(exc)
        turno = servicios.ultimo_turno_por_uid(db, uid)
        if causa == "retenido" and turno is not None and turno.estado != RETENIDO:
            # avanzar_hasta_salida genero una retencion (RT02): se conserva.
            servicios.avanzar_hasta_salida(db, turno, publish_cmd=pub)
        servicios.registrar_intento_rechazado(db, uid, "garita_salida", causa,
                                              contenedor_id=turno.contenedor_id if turno else None)
        if causa == "sin_turno":
            # R14: la verificacion de salida no es valida. Una sola alarma
            # activa por vehiculo aunque pase la tarjeta varias veces.
            servicios.generar_alarma_unica(db, "AL10", f"vehiculo:{uid}", origen="garita_salida",
                                           descripcion=f"Vehiculo {uid} en la salida sin turno activo",
                                           solo_activas=True)
        pub("RechazarSalida", "UNO_SALIDA", {"uid": uid, "motivo": servicios.motivo_lcd(causa)})
        _confirmar(db, pub)


def _salida_autorizada(db, pub: PublicadorDiferido, datos: dict) -> None:
    """Solo interesa cuando la garita abrio por su cuenta (sec. 12.1.2: sin
    servidor, los turnos que ya estan dentro pueden salir)."""
    if datos.get("decision") != "local":
        return
    uid = servicios.normalizar_uid(datos.get("uid", ""))
    turno = servicios.turno_activo_por_uid(db, uid) if uid else None
    if turno is None or turno.estado == RETENIDO:
        return
    try:
        servicios.avanzar_hasta_salida(db, turno, publish_cmd=pub)
        servicios.registrar_evento(db, turno.id, "controlador", "Salida autorizada por la garita sin servidor")
        _confirmar(db, pub)
    except servicios.ReglaDeNegocioError:
        db.rollback()
        pub.descartar()


def _salida_completada(db, pub: PublicadorDiferido, datos: dict) -> None:
    uid = servicios.normalizar_uid(datos.get("uid", ""))
    turno: Optional[Turno] = None
    if uid:
        turno = servicios.ultimo_turno_por_uid(db, uid)
    else:
        # Apertura manual (sin tarjeta): solo si no hay ambiguedad.
        en_salida = db.scalars(select(Turno).where(Turno.estado == EN_SALIDA)).all()
        turno = en_salida[0] if len(en_salida) == 1 else None
    if turno is None:
        return
    servicios.registrar_salida_fisica(db, turno, publish_cmd=pub)
    _confirmar(db, pub)


def _alarma_controlador(db, pub: PublicadorDiferido, datos: dict, origen: str = "") -> None:
    servicios.registrar_alarma_controlador(db, origen or "controlador", datos)
    _confirmar(db, pub)


MANEJADORES = {
    ("portus/evt/garita", "rfid"): _garita_rfid,
    ("portus/evt/garita", "rechazado"): _garita_rechazado,
    ("portus/evt/pesaje", "meseta"): _pesaje_meseta,
    ("portus/evt/salida", "rfid_salida"): _salida_rfid,
    ("portus/evt/salida", "salida_autorizada"): _salida_autorizada,
    ("portus/evt/salida", "salida_completada"): _salida_completada,
}


def procesar_evento(session_factory, enviar_mqtt: EnviarMqtt, topic: str, datos: dict,
                    origen: str = "") -> bool:
    """Punto de entrada desde app.py:on_message. Devuelve True si el evento
    tenia un manejador."""
    if topic == "portus/evt/alarma":
        with session_factory() as db:
            _alarma_controlador(db, PublicadorDiferido(db, enviar_mqtt), datos, origen)
        return True
    manejador = MANEJADORES.get((topic, datos.get("evento")))
    if manejador is None:
        return False
    with session_factory() as db:
        manejador(db, PublicadorDiferido(db, enviar_mqtt), datos)
    return True


def alarma_dict(a: Alarma) -> dict:
    return {"id": a.id, "codigo": a.codigo, "severidad": a.severidad, "origen": a.origen,
            "descripcion": a.descripcion, "referencia": a.referencia, "estado": a.estado,
            "createdAt": a.created_at.isoformat() if a.created_at else None,
            "ackAt": a.ack_at.isoformat() if a.ack_at else None, "ackComentario": a.ack_comentario}


def anunciar_alarmas_nuevas(session_factory, enviar_mqtt: EnviarMqtt) -> None:
    """Toda alarma que se confirme en la base (desde cualquier hilo o endpoint)
    sale por portus/srv/alarma. Si la transaccion se deshace, no sale nada."""

    @event.listens_for(session_factory, "after_flush")
    def _anotar(session, _ctx):
        for obj in session.new:
            if isinstance(obj, Alarma):
                session.info.setdefault("alarmas_nuevas", []).append(alarma_dict(obj))

    @event.listens_for(session_factory, "after_commit")
    def _enviar(session):
        for datos in session.info.pop("alarmas_nuevas", []):
            try:
                enviar_mqtt(TOPICO_ALARMAS_SERVIDOR, json.dumps(datos, ensure_ascii=False))
            except Exception as exc:  # la alarma ya quedo guardada; solo falla el aviso en vivo
                print(f"[ALARMAS] no se pudo anunciar {datos.get('codigo')}: {exc!r}")

    @event.listens_for(session_factory, "after_soft_rollback")
    def _descartar(session, _previous_transaction):
        session.info.pop("alarmas_nuevas", None)
