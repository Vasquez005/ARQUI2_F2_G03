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
    grua     evt=trabajo_inicio / trabajo_fin / sin_posicion -> ciclo de grua y turno (fase 5)
    patio    evento=deposito / retiro -> inventario, solo con confirmacion fisica (R09)
    transferencia evento=alineado / aborto -> linea de tiempo del turno y ciclo abortado

Fase 2: las alarmas nuevas se anuncian por MQTT (portus/srv/alarma) despues
del commit, para que la web las muestre en vivo sin consultar.
Fase 3: los cambios de turnos, retenciones, parqueo, patio e intentos se
anuncian en portus/srv/cambio ({entidad, id}); la web recarga solo eso.
Fase 4: tambien las citas y las franjas bloqueadas (el bot usa el mismo anuncio).
Fase 6: tambien manifiestos, declaraciones, transportistas y vehiculos, para
que naviera, agente y autoridad vean los cambios de estado sin recargar.

Los comandos se publican DESPUES del commit: si la transaccion se deshace
(rechazo), nunca sale un AbrirTalanquera que la base no respalda.
"""

import json
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import event, select

import camara_garita
import garita_verificacion
import grua
import servicios
import verificacion
from catalogos import ANULADO, EN_GARITA, EN_PESAJE_ENTRADA, EN_SALIDA, RETENIDO
from models import (
    Alarma, Cita, CommandAudit, Declaracion, FranjaBloqueada, GruaCiclo, IntentoIngreso, Manifiesto,
    ParqueoPlaza, PosicionPatio, Retencion, Transportista, Turno, Vehiculo,
)

TOPICO_ALARMAS_SERVIDOR = "portus/srv/alarma"
TOPICO_CAMBIOS_SERVIDOR = "portus/srv/cambio"

ENTIDADES_ANUNCIADAS = {
    Turno: "turno", Retencion: "retencion", ParqueoPlaza: "parqueo",
    PosicionPatio: "patio", IntentoIngreso: "intento", Cita: "cita", FranjaBloqueada: "franja",
    GruaCiclo: "ciclo", Manifiesto: "manifiesto", Declaracion: "declaracion",
    Transportista: "transportista", Vehiculo: "vehiculo",
}

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

    def publicar_ahora(self, topic: str, datos: dict) -> None:
        """Publica de inmediato en un topico informativo (no es un comando con ACK ni
        depende del commit). Sirve para portus/vision/* (sec. 2.2)."""
        try:
            self._enviar_mqtt(topic, json.dumps(datos, ensure_ascii=False))
        except Exception as exc:
            print(f"[VISION] no se pudo publicar en {topic}: {exc!r}")


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
    if garita_verificacion.activa():
        _garita_rfid_verificada(db, pub, uid)
        return
    try:
        servicios.ingreso_por_rfid(db, uid, publish_cmd=pub)
        _confirmar(db, pub)
    except servicios.ReglaDeNegocioError as exc:
        _rechazar_entrada(db, pub, uid, exc)


def _rechazar_entrada(db, pub: PublicadorDiferido, uid: str, exc: Exception) -> None:
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


def _alarma_verificacion(db, decision: verificacion.Decision, uid: str) -> None:
    if decision.alarma:
        servicios.generar_alarma(db, decision.alarma, origen="garita",
                                 descripcion=f"{decision.linea1} ({uid})", referencia=f"uid:{uid}")


def _pantalla_garita(pub: PublicadorDiferido, uid: str, decision: verificacion.Decision) -> None:
    """Textos literales de la sec. 6.4 para la LCD y el semaforo de la garita."""
    pub("GaritaResultado", "UNO_ENTRADA",
        {"uid": uid, "linea1": decision.linea1, "linea2": decision.linea2})


def _publicar_vision(pub: PublicadorDiferido, uid: str, lectura: Optional[dict],
                     decision: verificacion.Decision) -> None:
    """Sec. 2.2: resultado de cada lectura (portus/vision/placa) y estado de la camara
    y los modelos (portus/vision/estado). lectura None = camara fuera de servicio."""
    camara_ok = lectura is not None
    pub.publicar_ahora("portus/vision/placa", {
        "uid": uid,
        "placa": (lectura or {}).get("texto", ""),
        "confianza": (lectura or {}).get("confianza", 0.0),
        "resultado": decision.resultado,
        "causa": decision.causa,
        "foto": (lectura or {}).get("foto"),
    })
    pub.publicar_ahora("portus/vision/estado", {
        "camara": "operativa" if camara_ok else "fuera_de_servicio",
        "modelos": "operativos" if camara_ok else "fuera_de_servicio",
    })


def _notificar_ingreso(db, turno, lectura: Optional[dict], fila) -> None:
    """Sec. 9.2: al autorizar el ingreso, se avisa al transportista con la fotografia,
    la placa leida, la hora, el contenedor y el tipo de operacion. La foto se resuelve
    por la lectura de placa (referencia ingreso:<id>), que el bot adjunta."""
    placa = (lectura or {}).get("texto", "") or "-"
    texto = (
        "PORTUS: ingreso verificado en garita.\n"
        f"Placa leida: {placa}\n"
        f"Contenedor: {turno.contenedor_id or '-'}\n"
        f"Operacion: {turno.tipo_operacion or '-'}\n"
        f"Hora de ingreso: {servicios.hora_local(datetime.utcnow(), '%d/%m/%Y %H:%M')}"
    )
    servicios.encolar_notificacion(db, turno.transportista_id, "ingreso_verificado", texto,
                                   referencia=f"ingreso:{fila.id}")


def _garita_rfid_verificada(db, pub: PublicadorDiferido, uid: str) -> None:
    """Fase 3 (sec. 6.1): la camara lee la placa y se verifica contra la etiqueta."""
    lectura = camara_garita.leer_placa_garita(
        intentos=garita_verificacion.intentos_ocr(),
        es_valida=lambda l: l["confianza"] >= garita_verificacion.umbral_ocr() and bool(l["texto"]),
    )
    decision = garita_verificacion.decidir_entrada(db, uid, lectura)
    _publicar_vision(pub, uid, lectura, decision)

    if decision.resultado == verificacion.RECHAZO:
        servicios.registrar_intento_rechazado(db, uid, "garita_entrada", "tarjeta_no_registrada")
        garita_verificacion.registrar_lectura(db, uid, lectura, "rechazo")
        pub("RechazarIngreso", "UNO_ENTRADA", {"uid": uid, "motivo": "Tarjeta no registrada"})
        _pantalla_garita(pub, uid, decision)
        _confirmar(db, pub)
        return

    if decision.resultado in (verificacion.MODO_DEGRADADO, verificacion.VERIFICACION_MANUAL):
        # La talanquera no abre; el operador confirma desde la pestana Accesos (sec. 8.2).
        _alarma_verificacion(db, decision, uid)
        garita_verificacion.registrar_lectura(db, uid, lectura, decision.resultado, pendiente=True)
        pub("RechazarIngreso", "UNO_ENTRADA", {"uid": uid, "motivo": decision.linea1[:16]})
        _pantalla_garita(pub, uid, decision)
        _confirmar(db, pub)
        return

    # Autorizado o retencion: primero la validacion documental de la fase 2.
    try:
        turno = servicios.ingreso_por_rfid(db, uid, publish_cmd=pub)
    except servicios.ReglaDeNegocioError as exc:
        _rechazar_entrada(db, pub, uid, exc)
        # _rechazar_entrada confirma; ahora queda registrada la lectura de la placa.
        garita_verificacion.registrar_lectura(db, uid, lectura, "rechazo_documental")
        db.commit()
        return

    if decision.resultado == verificacion.RETENCION:
        # sec. 6.2: la retencion RT07/RT08 se crea despues del pesaje de entrada.
        _alarma_verificacion(db, decision, uid)
        garita_verificacion.registrar_lectura(db, uid, lectura, "retencion_pendiente",
                                              causa=decision.causa, turno_id=turno.id)
    else:
        fila = garita_verificacion.registrar_lectura(db, uid, lectura, "autorizado", turno_id=turno.id)
        _notificar_ingreso(db, turno, lectura, fila)
    _pantalla_garita(pub, uid, decision)
    _confirmar(db, pub)


def _aplicar_retencion_verificacion(db, pub: PublicadorDiferido, turno) -> None:
    """Despues del pesaje de entrada, aplica la retencion RT07/RT08 que quedo pendiente."""
    pendiente = garita_verificacion.retencion_pendiente_de(db, turno.id)
    if pendiente is None or turno.estado == RETENIDO:
        return
    servicios.crear_retencion(db, turno, pendiente.causa, estado_resume=turno.estado,
                              estacion="parqueo", publish_cmd=pub)
    pendiente.resultado = "retencion_aplicada"


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
        _aplicar_retencion_verificacion(db, pub, turno)
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


# ══════════════════════════════════════════════════════════════════════════
#  Grua, patio y transferencia (fase 5)
# ══════════════════════════════════════════════════════════════════════════

def _entero(valor) -> Optional[int]:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _grua_trabajo_inicio(db, pub: PublicadorDiferido, datos: dict) -> None:
    grua.iniciar_ciclo(db, datos.get("op", ""), _entero(datos.get("pos")))
    _confirmar(db, pub)


def _grua_trabajo_fin(db, pub: PublicadorDiferido, datos: dict) -> None:
    grua.terminar_ciclo(db, _entero(datos.get("ms")), _entero(datos.get("tramos")), publish_cmd=pub)
    _confirmar(db, pub)


def _grua_sin_posicion(db, pub: PublicadorDiferido, datos: dict) -> None:
    turno = grua.turno_en_transferencia(db)
    if turno is not None:
        texto = ("La grua no encontro posicion libre en el patio" if datos.get("op") == "DEPOSITO"
                 else "La grua no encontro contenedor para retirar en el patio")
        servicios.registrar_evento(db, turno.id, "controlador", texto, datos)
        _confirmar(db, pub)


def _patio_deposito(db, pub: PublicadorDiferido, datos: dict) -> None:
    grua.confirmar_deposito(db, _entero(datos.get("pos")))
    _confirmar(db, pub)


def _patio_retiro(db, pub: PublicadorDiferido, datos: dict) -> None:
    grua.confirmar_retiro(db, _entero(datos.get("pos")))
    _confirmar(db, pub)


def _transferencia_alineado(db, pub: PublicadorDiferido, datos: dict) -> None:
    turno = grua.turno_en_transferencia(db)
    if turno is not None:
        servicios.registrar_evento(db, turno.id, "controlador", "Vehiculo alineado en la transferencia")
        _confirmar(db, pub)


def _transferencia_aborto(db, pub: PublicadorDiferido, datos: dict) -> None:
    grua.abortar_ciclo(db, datos.get("causa", "desconocida"))
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
    ("portus/evt/grua", "trabajo_inicio"): _grua_trabajo_inicio,
    ("portus/evt/grua", "trabajo_fin"): _grua_trabajo_fin,
    ("portus/evt/grua", "sin_posicion"): _grua_sin_posicion,
    ("portus/evt/patio", "deposito"): _patio_deposito,
    ("portus/evt/patio", "retiro"): _patio_retiro,
    ("portus/evt/transferencia", "alineado"): _transferencia_alineado,
    ("portus/evt/transferencia", "aborto"): _transferencia_aborto,
}


def procesar_evento(session_factory, enviar_mqtt: EnviarMqtt, topic: str, datos: dict,
                    origen: str = "") -> bool:
    """Punto de entrada desde app.py:on_message. Devuelve True si el evento
    tenia un manejador."""
    if topic == "portus/evt/alarma":
        with session_factory() as db:
            _alarma_controlador(db, PublicadorDiferido(db, enviar_mqtt), datos, origen)
        return True
    # El Mega nombra el evento con "evt" (evt=estado, evt=trabajo_inicio...)
    manejador = MANEJADORES.get((topic, datos.get("evento") or datos.get("evt")))
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


def anunciar_cambios(session_factory, enviar_mqtt: EnviarMqtt) -> None:
    """Lo que se confirme en la base (desde cualquier hilo o endpoint) se
    anuncia por MQTT: cada alarma nueva completa en portus/srv/alarma, y cada
    cambio de las entidades del sinoptico en portus/srv/cambio. Si la
    transaccion se deshace, no sale nada."""

    @event.listens_for(session_factory, "after_flush")
    def _anotar(session, _ctx):
        alarmas = session.info.setdefault("alarmas_nuevas", [])
        cambios = session.info.setdefault("cambios", set())
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            if isinstance(obj, Alarma):
                if obj in session.new:
                    alarmas.append(alarma_dict(obj))
                continue
            entidad = ENTIDADES_ANUNCIADAS.get(type(obj))
            if entidad is not None:
                # FranjaBloqueada no tiene id (su clave es la hora de inicio) y Vehiculo usa el uid
                if hasattr(obj, "id"):
                    clave = obj.id
                elif isinstance(obj, Vehiculo):
                    clave = obj.uid
                else:
                    clave = obj.inicio.isoformat()
                cambios.add((entidad, clave))

    @event.listens_for(session_factory, "after_commit")
    def _enviar(session):
        mensajes = [(TOPICO_ALARMAS_SERVIDOR, d) for d in session.info.pop("alarmas_nuevas", [])]
        mensajes += [(TOPICO_CAMBIOS_SERVIDOR, {"entidad": e, "id": i})
                     for e, i in sorted(session.info.pop("cambios", set()), key=str)]
        for topico, datos in mensajes:
            try:
                enviar_mqtt(topico, json.dumps(datos, ensure_ascii=False))
            except Exception as exc:  # ya quedo guardado; solo falla el aviso en vivo
                print(f"[ANUNCIO] no se pudo publicar en {topico}: {exc!r}")

    @event.listens_for(session_factory, "after_soft_rollback")
    def _descartar(session, _previous_transaction):
        session.info.pop("alarmas_nuevas", None)
        session.info.pop("cambios", None)

