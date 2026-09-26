"""Bot del transportista (Persona D) — Fase_2_PORTUS.md sec. 6 y 9.

Integrado con el backend de B: usa la MISMA base de datos (backend/portus_core.db)
y los mismos modelos (backend/models.py). Ya no hay datos semilla propios: los
transportistas, manifiestos, turnos y citas son los reales del sistema.

- Las citas se guardan en la tabla `citas` de B, que es la que la garita usa
  para decidir RT04 (llegada fuera de ventana).
- Los avisos automaticos (sec. 6.3) los redacta el servidor en la tabla
  `notificaciones`; este bot solo los envia y marca como enviados.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import servicios  # noqa: E402
from catalogos import ESTADOS_FINALES, TOLERANCIA_VENTANA_MIN  # noqa: E402
from models import (  # noqa: E402
    Cita, Manifiesto, Notificacion, PosicionPatio, Transportista, Turno, make_db,
)
from servicios import estado_cita, proximas_franjas, texto_franja  # noqa: E402

try:
    from telegram import BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
    from telegram.ext import Application, ContextTypes, MessageHandler, filters
except Exception:
    BotCommand = ReplyKeyboardMarkup = ReplyKeyboardRemove = None  # type: ignore
    Update = object  # type: ignore
    Application = None  # type: ignore
    ContextTypes = None  # type: ignore
    MessageHandler = None  # type: ignore
    filters = None  # type: ignore


DB_PATH = os.getenv("PORTUS_DB_PATH", os.path.join(BACKEND_DIR, "portus_core.db"))
SessionLocal = make_db(DB_PATH)


def conectar_anuncios() -> None:
    """Las citas que se piden por el bot se anuncian por MQTT (portus/srv/cambio)
    igual que lo que cambia el backend: asi la agenda de la terminal se
    actualiza en vivo. Sin paho o sin broker, el bot funciona igual."""
    try:
        import paho.mqtt.client as mqtt
        import orquestador
    except Exception as exc:
        print(f"[MQTT] sin anuncios en vivo: {exc}")
        return
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cliente.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        # connect_async + loop_start: si el broker aun no esta arriba, paho reintenta solo
        cliente.connect_async(os.getenv("PORTUS_MQTT_HOST", "localhost"), int(os.getenv("PORTUS_MQTT_PORT", "1883")))
    except Exception as exc:
        print(f"[MQTT] sin anuncios en vivo: {exc}")
        return
    cliente.loop_start()
    orquestador.anunciar_cambios(SessionLocal, lambda t, p: cliente.publish(t, p))

NOMBRE_TERMINAL = "Terminal Portuaria PORTUS"
FRANJAS_A_OFRECER = 4
DIAS_BUSQUEDA_FRANJAS = 7

COMANDOS = [
    ("/inicio", "Presenta el servicio y lista los comandos"),
    ("/vincular CODIGO", "Asocia tu cuenta con el codigo que te dio la terminal"),
    ("/cita", "Solicita una cita para un contenedor con levante otorgado"),
    ("/miscitas", "Lista tus citas y su estado"),
    ("/estado CONTENEDOR", "Consulta el estado de uno de tus contenedores"),
    ("/misturnos", "Lista tus operaciones en curso"),
    ("/ayuda", "Repite esta lista de comandos"),
]

# Sec. 6.1.5: un usuario no vinculado recibe SIEMPRE la misma respuesta.
MSG_NO_VINCULADO = (
    f"Bienvenido al servicio de {NOMBRE_TERMINAL}.\n"
    "Tu cuenta no esta vinculada. Pide un codigo de vinculacion a la terminal y escribe:\n"
    "/vincular CODIGO"
)
MSG_NO_RECONOCIDO = "Comando no reconocido. Escribe /ayuda para ver los comandos disponibles."
MSG_SOLO_TEXTO = "Solo entiendo mensajes de texto. " + MSG_NO_RECONOCIDO
MSG_ERROR = "No pude procesar tu mensaje en este momento. Intenta de nuevo o escribe /ayuda."


class Respuesta(str):
    """Texto de respuesta con botones sugeridos (en Telegram, un teclado de
    respuesta rapida). Sigue siendo un str: el modo CLI y las pruebas no cambian."""

    def __new__(cls, texto: str, opciones: Optional[list] = None):
        obj = super().__new__(cls, texto)
        obj.opciones = opciones or []
        return obj
MSG_SIN_CARGA = "No tienes carga asociada a ese identificador."

ESTADO_DOCUMENTAL_TEXTO = {
    "declarado": "Manifiesto declarado (sin levante)",
    "declaracion_presentada": "Declaracion presentada (sin levante)",
    "levante_solicitado": "Levante solicitado (pendiente)",
    "levante_otorgado": "Levante otorgado",
    "levante_retenido": "Levante retenido",
}


# ══════════════════════════════════════════════════════════════════════════
#  Consultas (siempre filtradas por el transportista vinculado — sec. 6.3)
# ══════════════════════════════════════════════════════════════════════════

def get_transportista_by_chat(db: Session, chat_id: str) -> Optional[Transportista]:
    return db.scalar(select(Transportista).where(Transportista.chat_id == chat_id))


def manifiesto_del_transportista(db: Session, trans: Transportista, contenedor_id: str) -> Optional[Manifiesto]:
    return db.scalars(
        select(Manifiesto)
        .where(Manifiesto.contenedor_id == contenedor_id, Manifiesto.transportista_id == trans.id)
        .order_by(Manifiesto.id.desc())
    ).first()


def cita_vigente(db: Session, contenedor_id: str) -> Optional[Cita]:
    return db.scalars(
        select(Cita).where(Cita.contenedor_id == contenedor_id, Cita.estado == "programada")
    ).first()


def contenedores_elegibles(db: Session, trans: Transportista) -> list:
    """Levante otorgado, sin cita vigente y sin turno todavia (sec. 6.2 /cita, 9.3, 9.4)."""
    manifiestos = db.scalars(
        select(Manifiesto).where(
            Manifiesto.transportista_id == trans.id,
            Manifiesto.estado_documental == "levante_otorgado",
            Manifiesto.anulado.is_(False),
        ).order_by(Manifiesto.id)
    ).all()
    elegibles = []
    for m in manifiestos:
        tiene_turno = db.scalars(select(Turno).where(Turno.manifiesto_id == m.id)).first() is not None
        if not tiene_turno and cita_vigente(db, m.contenedor_id) is None:
            elegibles.append(m)
    return elegibles


def ubicacion_en_patio(db: Session, contenedor_id: str) -> tuple:
    """(texto de ubicacion, desde cuando esta ahi) o (None, None)."""
    for p in db.scalars(select(PosicionPatio).order_by(PosicionPatio.id)).all():
        if p.contenedor_nivel1 == contenedor_id:
            return f"Patio posicion {p.id}, nivel 1", p.nivel1_desde
        if p.contenedor_nivel2 == contenedor_id:
            return f"Patio posicion {p.id}, nivel 2", p.nivel2_desde
    return None, None


# ══════════════════════════════════════════════════════════════════════════
#  Comandos
# ══════════════════════════════════════════════════════════════════════════

def cmd_inicio() -> str:
    lineas = [f"Hola, bienvenido al servicio de {NOMBRE_TERMINAL}.", "", "Comandos disponibles:"]
    lineas += [f"{c} - {d}" for c, d in COMANDOS]
    return "\n".join(lineas)


def cmd_ayuda() -> str:
    return "Comandos disponibles:\n" + "\n".join(f"{c} - {d}" for c, d in COMANDOS)


def cmd_vincular(db: Session, chat_id: str, codigo: Optional[str]) -> str:
    if not codigo:
        return "Uso: /vincular CODIGO (6 caracteres que te dio la terminal)."
    codigo = codigo.strip().upper()
    trans = db.scalar(select(Transportista).where(Transportista.codigo_vinculacion == codigo))
    if not trans:
        return "Codigo invalido o ya utilizado. Pide uno nuevo a la terminal."
    if trans.codigo_expira_at is None or datetime.utcnow() > trans.codigo_expira_at:
        return "El codigo esta vencido (duran 60 minutos). Pide uno nuevo a la terminal."
    # Un chat solo puede representar a un transportista: si este chat estaba
    # vinculado a otro, se desvincula para que nunca reciba carga ajena.
    for otro in db.scalars(select(Transportista).where(Transportista.chat_id == chat_id)).all():
        otro.chat_id = None
    trans.chat_id = chat_id
    trans.codigo_vinculacion = None  # un solo uso
    trans.codigo_expira_at = None
    db.commit()
    return f"Vinculacion exitosa. Esta cuenta ahora representa a: {trans.nombre}.\n\n{cmd_ayuda()}"


def cmd_cita(db: Session, trans: Transportista, args: list) -> str:
    if not args:
        elegibles = contenedores_elegibles(db, trans)
        if not elegibles:
            return "No tienes contenedores con levante otorgado pendientes de cita."
        lista = "\n".join(f"- {m.contenedor_id} ({m.tipo_operacion}, canal {(m.canal or '-').upper()})" for m in elegibles)
        return Respuesta(f"Contenedores disponibles para cita:\n{lista}\n\nEscribe /cita CONTENEDOR para ver los horarios.",
                         [f"/cita {m.contenedor_id}" for m in elegibles])

    contenedor = args[0].upper()
    m = manifiesto_del_transportista(db, trans, contenedor)
    if m is None:
        return MSG_SIN_CARGA
    if m not in contenedores_elegibles(db, trans):
        if m.estado_documental != "levante_otorgado":
            return f"El contenedor {contenedor} aun no tiene levante otorgado."
        if cita_vigente(db, contenedor) is not None:
            return f"El contenedor {contenedor} ya tiene una cita vigente. Revisa /miscitas."
        return f"El contenedor {contenedor} ya tiene un turno en la terminal."

    franjas = proximas_franjas(db, datetime.utcnow(), FRANJAS_A_OFRECER, DIAS_BUSQUEDA_FRANJAS)
    if not franjas:
        return "No hay franjas con capacidad en los proximos dias."

    if len(args) < 2:
        lineas = [f"{i}. {texto_franja(s, e)}" for i, (s, e) in enumerate(franjas, start=1)]
        return Respuesta(f"Proximas franjas con capacidad para {contenedor}:\n" + "\n".join(lineas) +
                         f"\n\nEscribe /cita {contenedor} NUMERO para confirmar (ej. /cita {contenedor} 1).",
                         [f"/cita {contenedor} {i}" for i in range(1, len(franjas) + 1)])

    try:
        eleccion = int(args[1])
        if eleccion < 1:
            raise IndexError
        inicio, fin = franjas[eleccion - 1]
    except (ValueError, IndexError):
        return f"Opcion invalida. Escribe /cita {contenedor} para ver las franjas disponibles."

    try:
        servicios.asignar_cita(db, trans.id, m, inicio)
    except servicios.ReglaDeNegocioError:
        # Alguien tomo la ultima plaza de la franja (o la terminal la bloqueo) entre la oferta y la eleccion
        db.rollback()
        return f"Esa franja ya no esta disponible. Escribe /cita {contenedor} para ver los horarios actualizados."
    db.commit()
    return (f"Cita confirmada.\nContenedor: {contenedor}\n"
            f"Fecha: {servicios.hora_local(inicio, '%d/%m/%Y')}\n"
            f"Hora de inicio: {servicios.hora_local(inicio, '%H:%M')}\n"
            f"Hora de fin: {servicios.hora_local(fin, '%H:%M')}\n"
            f"Debes presentarte entre el inicio y {TOLERANCIA_VENTANA_MIN} minutos despues del fin.")


def cmd_miscitas(db: Session, trans: Transportista) -> str:
    rows = db.scalars(
        select(Cita).where(Cita.transportista_id == trans.id).order_by(Cita.inicio.desc()).limit(10)
    ).all()
    if not rows:
        return "No tienes citas registradas."
    ahora = datetime.utcnow()
    lineas = [f"- {c.contenedor_id} | {texto_franja(c.inicio, c.fin)} | {estado_cita(c, ahora)}" for c in rows]
    return "Tus citas:\n" + "\n".join(lineas)


def cmd_estado(db: Session, trans: Transportista, contenedor: Optional[str]) -> str:
    if not contenedor:
        return "Uso: /estado CONTENEDOR"
    contenedor = contenedor.upper()
    m = manifiesto_del_transportista(db, trans, contenedor)
    if m is None:
        return MSG_SIN_CARGA

    turno = db.scalars(select(Turno).where(Turno.manifiesto_id == m.id).order_by(Turno.id.desc())).first()
    ubicacion, en_patio_desde = ubicacion_en_patio(db, contenedor)
    if turno is not None and turno.estado not in ESTADOS_FINALES:
        estado = f"Turno {turno.estado} (estacion: {turno.estacion_actual or '-'})"
    elif m.anulado:
        estado = "Manifiesto anulado"
    elif turno is not None:
        estado = f"Turno {turno.estado}"
    else:
        estado = ESTADO_DOCUMENTAL_TEXTO.get(m.estado_documental, m.estado_documental)

    # Reloj de permanencia desde que el contenedor quedo en el patio (fase 2)
    permanencia = servicios.duracion_texto(en_patio_desde) if en_patio_desde else "-"

    return (f"Contenedor: {contenedor}\n"
            f"Estado: {estado}\n"
            f"Ubicacion: {ubicacion or 'No esta en patio'}\n"
            f"Permanencia: {permanencia}\n"
            f"Autorizacion: {ESTADO_DOCUMENTAL_TEXTO.get(m.estado_documental, m.estado_documental)}\n"
            f"Canal: {(m.canal or '-').upper()}")


def cmd_misturnos(db: Session, trans: Transportista) -> str:
    rows = db.scalars(
        select(Turno).where(Turno.transportista_id == trans.id, Turno.estado.not_in(ESTADOS_FINALES))
        .order_by(Turno.id)
    ).all()
    if not rows:
        return "No tienes turnos activos."
    lineas = [f"- Vehiculo {t.vehiculo_uid} | {t.contenedor_id} | {t.tipo_operacion} | {t.estado} | {t.estacion_actual or '-'}"
              for t in rows]
    return "Tus turnos activos:\n" + "\n".join(lineas)


def process_command(db: Session, chat_id: str, text: str) -> str:
    """Nunca devuelve vacio: sec. 6.2 'el servicio nunca debera quedar sin responder'."""
    parts = (text or "").strip().split()
    if not parts:
        return MSG_NO_RECONOCIDO
    cmd = parts[0].lower().split("@")[0]  # en grupos Telegram manda /cmd@NombreBot
    args = parts[1:]

    if cmd == "/vincular":
        return cmd_vincular(db, chat_id, args[0] if args else None)

    trans = get_transportista_by_chat(db, chat_id)
    if not trans:
        return MSG_NO_VINCULADO

    if cmd in ("/inicio", "/start"):
        return cmd_inicio()
    if cmd == "/ayuda":
        return cmd_ayuda()
    if cmd == "/cita":
        return cmd_cita(db, trans, args)
    if cmd == "/miscitas":
        return cmd_miscitas(db, trans)
    if cmd == "/estado":
        return cmd_estado(db, trans, args[0] if args else None)
    if cmd == "/misturnos":
        return cmd_misturnos(db, trans)
    return MSG_NO_RECONOCIDO


# ══════════════════════════════════════════════════════════════════════════
#  Notificaciones automaticas (sec. 6.3)
# ══════════════════════════════════════════════════════════════════════════

def encolar_recordatorios(db: Session) -> int:
    """Recordatorio 1 hora antes. Solo para citas pedidas con mas de 1 h de
    anticipacion (si la pidio 20 min antes, no tiene sentido 'recordarle')."""
    ahora = datetime.utcnow()
    citas = db.scalars(
        select(Cita).where(Cita.estado == "programada", Cita.inicio > ahora,
                           Cita.inicio <= ahora + timedelta(hours=1))
    ).all()
    n = 0
    for c in citas:
        if c.created_at and c.created_at > c.inicio - timedelta(hours=1):
            continue
        # La ventana va en la referencia: si la terminal reprograma la cita, la nueva ventana tiene su recordatorio
        ref = f"recordatorio:cita:{c.id}:{c.inicio:%Y%m%d%H%M}"
        if db.scalar(select(Notificacion.id).where(Notificacion.referencia == ref)):
            continue
        servicios.encolar_notificacion(
            db, c.transportista_id, "recordatorio_cita",
            f"PORTUS: recordatorio, tu cita es en menos de 1 hora.\nContenedor: {c.contenedor_id}\n"
            f"Ventana: {texto_franja(c.inicio, c.fin)}",
            referencia=ref)
        n += 1
    db.commit()
    return n


def notificaciones_pendientes(db: Session) -> list:
    """(notificacion, chat_id) de transportistas ya vinculados. Si aun no se
    vinculan, el aviso queda en cola y sale cuando se vinculen."""
    return db.execute(
        select(Notificacion, Transportista.chat_id)
        .join(Transportista, Transportista.id == Notificacion.transportista_id)
        .where(Notificacion.sent_at.is_(None), Transportista.chat_id.is_not(None))
        .order_by(Notificacion.id)
    ).all()


async def despachar_notificaciones(send) -> None:
    with SessionLocal() as db:
        encolar_recordatorios(db)
        for notif, chat_id in notificaciones_pendientes(db):
            try:
                await send(chat_id, notif.texto)
            except Exception as exc:  # un chat bloqueado no debe frenar a los demas
                print(f"[NOTIF] error enviando #{notif.id} a {chat_id}: {exc}")
                continue
            notif.sent_at = datetime.utcnow()
            db.commit()


# ══════════════════════════════════════════════════════════════════════════
#  Modos de ejecucion
# ══════════════════════════════════════════════════════════════════════════

def responder(chat_id: str, texto: Optional[str]) -> str:
    """Nunca lanza ni devuelve vacio (sec. 6.2): un mensaje sin texto (sticker,
    foto, audio) o un error interno tambien reciben respuesta."""
    if texto is None:
        return MSG_SOLO_TEXTO
    try:
        with SessionLocal() as db:
            return process_command(db, chat_id, texto)
    except Exception as exc:
        print(f"[BOT] error procesando {texto!r} de {chat_id}: {exc!r}")
        return MSG_ERROR


def teclado(respuesta: str):
    """Botones de /cita (contenedores o franjas); si no hay, se quita el teclado anterior."""
    opciones = getattr(respuesta, "opciones", [])
    if ReplyKeyboardMarkup is None:
        return None
    if not opciones:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup([[o] for o in opciones], resize_keyboard=True, one_time_keyboard=True)


async def telegram_mode(token: str) -> None:
    app = Application.builder().token(token).build()

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_chat or not update.effective_message:
            return
        reply = responder(str(update.effective_chat.id), update.effective_message.text)
        await update.effective_message.reply_text(reply, reply_markup=teclado(reply))

    # Un solo handler para TODO mensaje nuevo (comandos, texto libre, stickers, fotos...):
    # el servicio nunca queda sin responder. Las ediciones no se contestan dos veces.
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE, on_message))

    async def send(chat_id: str, text: str) -> None:
        await app.bot.send_message(chat_id=chat_id, text=text)

    await app.initialize()
    try:
        # Menu de comandos del telefono (el boton "/" de Telegram)
        await app.bot.set_my_commands([BotCommand(c.split()[0].lstrip("/"), d) for c, d in COMANDOS])
    except Exception as exc:
        print(f"[BOT] no se pudo registrar el menu de comandos: {exc}")
    await app.start()
    await app.updater.start_polling()
    print("Bot Telegram activo.")
    while True:
        try:
            await despachar_notificaciones(send)
        except Exception as exc:
            print(f"[NOTIF] error: {exc}")
        await asyncio.sleep(3)


def cli_mode() -> None:
    print("Modo simulacion CLI (sin PORTUS_BOT_TOKEN). BD:", DB_PATH)
    print("Utilitarios: transportistas | gen-code <id> | chat <chat_id> <texto> | notifs | exit")

    async def send(chat_id: str, text: str) -> None:
        print(f"[NOTIF -> chat {chat_id}]\n{text}\n")

    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if line == "exit":
            break
        if line == "transportistas":
            with SessionLocal() as db:
                for t in db.scalars(select(Transportista).order_by(Transportista.id)).all():
                    print(f"  id={t.id} {t.nombre} chat={t.chat_id} codigo={t.codigo_vinculacion}")
            continue
        if line.startswith("gen-code "):
            with SessionLocal() as db:
                t = db.get(Transportista, int(line.split()[1]))
                if not t:
                    print("Transportista no existe")
                    continue
                print("Codigo generado:", servicios.generar_codigo_vinculacion(db, t))
                db.commit()
            continue
        if line.startswith("chat "):
            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                print("Uso: chat <chat_id> <texto>")
                continue
            reply = responder(parts[1], parts[2])
            print(reply)
            if getattr(reply, "opciones", None):
                print("  [botones] " + " | ".join(reply.opciones))
            continue
        if line == "notifs":
            asyncio.run(despachar_notificaciones(send))
            continue
        print("Utilitario no reconocido.")


def main() -> None:
    conectar_anuncios()
    token = os.getenv("PORTUS_BOT_TOKEN")
    if token and Application is not None:
        asyncio.run(telegram_mode(token))
    else:
        cli_mode()


if __name__ == "__main__":
    main()
