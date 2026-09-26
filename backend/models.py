from datetime import datetime
from typing import Optional
from sqlalchemy import event

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════════════════════════════════
#  Infraestructura de mensajeria (ya existia)
# ══════════════════════════════════════════════════════════════════════════

class EventLog(Base):
    __tablename__ = "event_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), index=True)
    topic: Mapped[str] = mapped_column(String(80), index=True)
    origin: Mapped[str] = mapped_column(String(32), index=True)
    evt_type: Mapped[str] = mapped_column(String(16), index=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class LinkStatus(Base):
    """Estado global (compatibilidad hacia atras). Ver LinkDevice para el estado por dispositivo."""
    __tablename__ = "link_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connected: Mapped[str] = mapped_column(String(8), default="false")
    last_heartbeat_ts: Mapped[int] = mapped_column(Integer, default=0)
    last_origin: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LinkDevice(Base):
    """Estado de enlace por dispositivo (UNO_ENTRADA / UNO_SALIDA / MEGA_GRUA).

    Ver Observaciones_Backend_PersonaB.md punto 2.2: el link_status global no
    alcanzaba a detectar que UN dispositivo especifico dejara de mandar su
    latido mientras los otros seguian activos.
    """
    __tablename__ = "link_devices"
    device: Mapped[str] = mapped_column(String(32), primary_key=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_heartbeat_ts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CommandAudit(Base):
    __tablename__ = "command_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cmd_name: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(32), index=True)
    request_json: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(16), default="PENDING")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════
#  Dominio PORTUS (nuevo — ver Observaciones_Backend_PersonaB.md punto 1)
# ══════════════════════════════════════════════════════════════════════════

class Usuario(Base):
    """Nota: aqui solo vive el dato (rol + password hasheado). El login/sesion
    real (cookies, tokens) es tarea de Persona C, que todavia no existe en este
    repo. Mientras tanto los endpoints reciben el rol como parametro explicito
    (ver app.py) — la regla de permisos SI se valida en el servidor, que es lo
    que el PDF exige; falta conectarla a una sesion real."""
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    rol: Mapped[str] = mapped_column(String(16), index=True)  # TERMINAL, NAVIERA, AGENTE, AUTORIDAD
    nombre: Mapped[str] = mapped_column(String(120), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transportista(Base):
    __tablename__ = "transportistas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120))
    codigo_vinculacion: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    codigo_expira_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # lo llena el bot de D
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Vehiculo(Base):
    """Tarjeta RFID de un vehiculo y el transportista al que pertenece.

    La garita solo conoce el UID de la tarjeta; con esta tabla el servidor
    sabe de quien es el vehiculo y, por sus manifiestos, que contenedor trae
    (fase 1 del plan: tarjeta -> contenedor).
    """
    __tablename__ = "vehiculos"
    uid: Mapped[str] = mapped_column(String(32), primary_key=True)  # "E1 69 73 15"
    transportista_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transportistas.id"), nullable=True)
    placa: Mapped[str] = mapped_column(String(16), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Manifiesto(Base):
    __tablename__ = "manifiestos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contenedor_id: Mapped[str] = mapped_column(String(32), index=True)
    tipo_operacion: Mapped[str] = mapped_column(String(16))  # DEPOSITO | RETIRO
    peso_declarado_g: Mapped[int] = mapped_column(Integer)
    peso_declarado_anterior_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tolerancia_pct: Mapped[float] = mapped_column(Float, default=5.0)
    naviera_usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    transportista_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transportistas.id"), nullable=True)
    # Opcional: fija que vehiculo trae este contenedor. Si queda vacio, la
    # garita lo deduce por el transportista duenio de la tarjeta (ver Vehiculo).
    vehiculo_uid: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    motivo_levante: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # si la autoridad lo retuvo
    estado_documental: Mapped[str] = mapped_column(String(24), default="declarado")
    # declarado -> declaracion_presentada -> levante_solicitado -> levante_otorgado | levante_retenido
    canal: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # verde | rojo
    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Declaracion(Base):
    __tablename__ = "declaraciones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manifiesto_id: Mapped[int] = mapped_column(ForeignKey("manifiestos.id"), index=True)
    numero_declaracion: Mapped[str] = mapped_column(String(40), unique=True)
    regimen: Mapped[str] = mapped_column(String(24))  # importacion_definitiva | deposito_temporal
    descripcion: Mapped[str] = mapped_column(Text)
    valor_declarado: Mapped[float] = mapped_column(Float)
    agente_usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    observacion_autoridad: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cita(Base):
    """Cita de un contenedor en una franja de 15 min (sec. 9). La garita la usa
    para RT04 y la marca cumplida / vencida al llegar el vehiculo."""
    __tablename__ = "citas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contenedor_id: Mapped[str] = mapped_column(String(32), index=True)
    transportista_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transportistas.id"), nullable=True)
    inicio: Mapped[datetime] = mapped_column(DateTime, index=True)
    fin: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(String(16), default="programada")  # programada|cumplida|vencida|cancelada
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # de la cancelacion o reprogramacion
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FranjaBloqueada(Base):
    """Boton Bloquear franja (sec. 4.7): no se asignan citas nuevas en ella.
    Las citas que ya tenia se conservan."""
    __tablename__ = "franjas_bloqueadas"
    inicio: Mapped[datetime] = mapped_column(DateTime, primary_key=True)  # UTC, alineada a 15 min
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Turno(Base):
    __tablename__ = "turnos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manifiesto_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manifiestos.id"), nullable=True)
    vehiculo_uid: Mapped[str] = mapped_column(String(32), index=True)
    transportista_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transportistas.id"), nullable=True)
    contenedor_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tipo_operacion: Mapped[str] = mapped_column(String(16))
    estado: Mapped[str] = mapped_column(String(24), index=True)  # ver catalogos.ESTADOS_TURNO
    estacion_actual: Mapped[str] = mapped_column(String(32), default="")
    peso_declarado_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    peso_medido_entrada_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    peso_medido_salida_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    posicion_patio: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trabajo_grua_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # TrabajoGrua enviado
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    historial_estados: Mapped[list["TurnoEstado"]] = relationship(cascade="all, delete-orphan")


class TurnoEstado(Base):
    """Cada estado por el que paso un turno y cuando (lo llena el listener de
    Turno.estado). Con esto se calcula la fila de espera maxima (sec. 13)."""
    __tablename__ = "turno_estados"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    estado: Mapped[str] = mapped_column(String(24))
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


@event.listens_for(Turno.estado, "set")
def _historial_de_estado(turno, valor, anterior, _iniciador):
    if valor != anterior:
        turno.historial_estados.append(TurnoEstado(estado=valor, ts=datetime.utcnow()))


class GruaCiclo(Base):
    """Un trabajo de la grua (sec. 4.5 y 13): lo abre trabajo_inicio y lo cierra
    trabajo_fin o un aborto. Las remociones del retiro quedan como ciclos REMOCION."""
    __tablename__ = "grua_ciclos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[Optional[int]] = mapped_column(ForeignKey("turnos.id"), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(12))  # DEPOSITO | RETIRO | REMOCION
    contenedor_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    posicion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    posicion_destino: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # remocion: a donde se movio
    resultado: Mapped[str] = mapped_column(String(12), default="en_curso", index=True)  # en_curso|completado|abortado
    causa: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    duracion_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tramos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # posiciones recorridas
    inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    fin: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class EventoTurno(Base):
    """Linea de tiempo del turno (Fase_2_PORTUS.md sec. 4.2.1)."""
    __tablename__ = "eventos_turno"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    origen: Mapped[str] = mapped_column(String(16))  # controlador | servidor | usuario
    descripcion: Mapped[str] = mapped_column(String(200))
    valores_json: Mapped[str] = mapped_column(Text, default="{}")


class IntentoIngreso(Base):
    """Sec. 7 regla 1: un ingreso rechazado no crea turno, pero queda
    registrado con su causa. Tambien guarda los rechazos de la garita de salida."""
    __tablename__ = "intentos_ingreso"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehiculo_uid: Mapped[str] = mapped_column(String(32), index=True)
    contenedor_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    estacion: Mapped[str] = mapped_column(String(16))  # garita_entrada | garita_salida
    causa: Mapped[str] = mapped_column(String(40))
    decidido_por: Mapped[str] = mapped_column(String(16), default="servidor")  # servidor | controlador
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PosicionPatio(Base):
    """4 posiciones fisicas (sensor binario ocupado/libre por posicion, ver
    PORTUS_Fase2_Plan.md: 'el nivel se maneja de forma logica en el servidor').
    """
    __tablename__ = "patio"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1..4
    estado: Mapped[str] = mapped_column(String(16), default="LIBRE")
    # LIBRE | RESERVADA | OCUPADA_1 | OCUPADA_2 | BLOQUEADA
    contenedor_nivel1: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    contenedor_nivel2: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    remociones: Mapped[int] = mapped_column(Integer, default=0)
    # Desde cuando esta cada contenedor en el patio (AL13: mas de 2 h).
    nivel1_desde: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    nivel2_desde: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParqueoPlaza(Base):
    __tablename__ = "parqueo_plazas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1..3
    ocupada: Mapped[bool] = mapped_column(Boolean, default=False)
    turno_id: Mapped[Optional[int]] = mapped_column(ForeignKey("turnos.id"), nullable=True)
    desde: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Retencion(Base):
    __tablename__ = "retenciones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    causa: Mapped[str] = mapped_column(String(8), index=True)  # RT01..RT06
    estacion: Mapped[str] = mapped_column(String(32), default="")
    estado_anterior: Mapped[str] = mapped_column(String(24), default="")  # a donde regresa el turno (Aclarar/Corregir)
    plaza: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(16), default="abierta", index=True)  # abierta|resuelta
    resolucion: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # aclarar|corregir|rechazar
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    observacion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    peso_declarado_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    peso_medido_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Alarma(Base):
    __tablename__ = "alarmas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(8), index=True)  # AL01..AL14
    severidad: Mapped[str] = mapped_column(String(12))  # critica|alta|media|baja
    origen: Mapped[str] = mapped_column(String(32), default="")
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    # A que se refiere ("turno:5", "retencion:3", "contenedor:MSCU1", "comando:12"):
    # sirve para no repetir una alarma por la misma causa.
    referencia: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    estado: Mapped[str] = mapped_column(String(16), default="activa", index=True)  # activa|reconocida
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ack_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ack_comentario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ManifiestoEvento(Base):
    """Historial del manifiesto (sec. 5.1 Ver detalle): declaracion, levante,
    turnos, correccion de peso (con el valor anterior) y las observaciones que
    adjunta el agente para la autoridad (tipo=observacion)."""
    __tablename__ = "manifiesto_eventos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manifiesto_id: Mapped[int] = mapped_column(ForeignKey("manifiestos.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    origen: Mapped[str] = mapped_column(String(16))  # naviera|agente|autoridad|terminal|servidor
    tipo: Mapped[str] = mapped_column(String(16), default="historial")  # historial | observacion
    descripcion: Mapped[str] = mapped_column(Text)
    valores_json: Mapped[str] = mapped_column(Text, default="{}")


class ContenedorCatalogo(Base):
    """Catalogo de contenedores de la maqueta (sec. 5.1: el manifiesto solo
    acepta contenedores que existen aqui)."""
    __tablename__ = "contenedores"
    contenedor_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(120), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Corrida(Base):
    """Reporte guardado (sec. 4.8): rango, etiqueta y las 8 metricas. Es la
    linea base que se compara en la Fase 3."""
    __tablename__ = "corridas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etiqueta: Mapped[str] = mapped_column(String(120))
    desde: Mapped[datetime] = mapped_column(DateTime)
    hasta: Mapped[datetime] = mapped_column(DateTime)
    politica_patio: Mapped[str] = mapped_column(String(24), default="secuencial")
    metricas_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Configuracion(Base):
    """Ajustes del sistema que cambia la terminal (ej. la politica de patio)."""
    __tablename__ = "configuracion"
    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))


class Notificacion(Base):
    """Bandeja de salida hacia el bot (Persona D, Fase_2_PORTUS.md sec. 6.3).

    El servidor inserta aqui el aviso ya redactado y el bot lo envia al chat
    del transportista y marca sent_at. Si el bot esta apagado, los avisos se
    quedan pendientes y salen al volver (no se pierden).
    """
    __tablename__ = "notificaciones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transportista_id: Mapped[int] = mapped_column(ForeignKey("transportistas.id"), index=True)
    evento: Mapped[str] = mapped_column(String(32), index=True)
    texto: Mapped[str] = mapped_column(Text)
    referencia: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)  # ej. "cita:12"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)


def make_db(db_path: str):
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    # Activa WAL: permite lecturas y escrituras concurrentes sin bloquear tanto
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    Base.metadata.create_all(engine)
    _agregar_columnas_nuevas(engine)
    return sessionmaker(bind=engine)


# create_all no agrega columnas a tablas que ya existen: una base creada antes
# de la fase 1 o 2 (por ejemplo la de la Raspberry) necesita este ALTER TABLE.
_COLUMNAS_NUEVAS = {
    "alarmas": {"referencia": "VARCHAR(60)"},
    "citas": {"motivo": "TEXT"},
    "manifiestos": {"vehiculo_uid": "VARCHAR(32)", "motivo_levante": "TEXT"},
    "turnos": {"trabajo_grua_at": "DATETIME"},
    "patio": {"nivel1_desde": "DATETIME", "nivel2_desde": "DATETIME"},
}


def _agregar_columnas_nuevas(engine) -> None:
    with engine.begin() as conn:
        for tabla, columnas in _COLUMNAS_NUEVAS.items():
            existentes = {fila[1] for fila in conn.exec_driver_sql(f"PRAGMA table_info({tabla})")}
            for nombre, tipo in columnas.items():
                if nombre not in existentes:
                    conn.exec_driver_sql(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")