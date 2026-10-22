"""Estacion meteorologica (Fase 3, sec. 3) — lecturas MQTT y reglas derivadas.

- Guarda la ultima lectura recibida en ``portus/estacion/lectura``.
- Delega el campo ``luz`` al modulo ``iluminacion`` (sec. 4.2).
- Ante ``lluvia`` activa suspende la grua por clima; al cesar lluvia reanuda con origen auto (sec. 4.3).
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

TARGET_GRUA = "MEGA_GRUA"

TOPIC_CONFIG = "portus/estacion/config"
CONFIG_LECTURA_DEFECTO_S = 5
CONFIG_LATIDO_DEFECTO_S = 10
CONFIG_LECTURA_MIN_S = 2
CONFIG_LECTURA_MAX_S = 60
CONFIG_LATIDO_MIN_S = 5
CONFIG_LATIDO_MAX_S = 60


EnviarComando = Callable[[str, str, dict], None]


@dataclass
class LecturaEstacion:
    temperatura: Optional[float] = None
    humedad: Optional[float] = None
    lluvia: Optional[bool] = None
    luz: Optional[float] = None
    ts: Optional[int] = None
    uptime_s: Optional[int] = None
    recibido_en: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parsear_lectura(payload: dict) -> LecturaEstacion:
    """Convierte el JSON plano del ESP32 en LecturaEstacion (campos opcionales)."""
    lectura = LecturaEstacion(recibido_en=time.time())
    temp = payload.get("temperatura")
    hum = payload.get("humedad")
    if temp is not None and temp != "null":
        try:
            lectura.temperatura = float(temp)
        except (TypeError, ValueError):
            pass
    if hum is not None and hum != "null":
        try:
            lectura.humedad = float(hum)
        except (TypeError, ValueError):
            pass
    if "lluvia" in payload:
        lectura.lluvia = bool(payload["lluvia"])
    if "luz" in payload and payload["luz"] is not None:
        try:
            lectura.luz = float(payload["luz"])
        except (TypeError, ValueError):
            lectura.luz = None
    if "ts" in payload:
        try:
            lectura.ts = int(payload["ts"])
        except (TypeError, ValueError):
            pass
    if "uptime_s" in payload:
        try:
            lectura.uptime_s = int(payload["uptime_s"])
        except (TypeError, ValueError):
            pass
    return lectura


class RegistroEstacion:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ultima: Optional[LecturaEstacion] = None

    def actualizar(self, lectura: LecturaEstacion) -> None:
        with self._lock:
            self._ultima = lectura

    def ultima(self) -> Optional[LecturaEstacion]:
        with self._lock:
            return self._ultima


class ControlClimaLluvia:
    """Suspende / reanuda la grua segun el sensor de lluvia de la estacion."""

    def __init__(self, enviar: EnviarComando) -> None:
        self._enviar = enviar
        self._lock = threading.Lock()
        self.suspendido_por_lluvia = False

    def procesar_lluvia(self, lloviendo: bool) -> None:
        with self._lock:
            if lloviendo and not self.suspendido_por_lluvia:
                self._enviar("GruaSuspender", TARGET_GRUA, {"motivo": "Clima"})
                self.suspendido_por_lluvia = True
            elif not lloviendo and self.suspendido_por_lluvia:
                self._enviar("GruaReanudar", TARGET_GRUA, {"origen": "auto"})
                self.suspendido_por_lluvia = False


def validar_config_estacion(seg_lectura: int, seg_latido: int) -> None:
    if not CONFIG_LECTURA_MIN_S <= seg_lectura <= CONFIG_LECTURA_MAX_S:
        raise ValueError(
            f"SegundosLecturaEstacion fuera de rango ({CONFIG_LECTURA_MIN_S} a {CONFIG_LECTURA_MAX_S})"
        )
    if not CONFIG_LATIDO_MIN_S <= seg_latido <= CONFIG_LATIDO_MAX_S:
        raise ValueError(
            f"SegundosLatidoEstacion fuera de rango ({CONFIG_LATIDO_MIN_S} a {CONFIG_LATIDO_MAX_S})"
        )


def mensaje_config_estacion(seg_lectura: int, seg_latido: int) -> str:
    validar_config_estacion(seg_lectura, seg_latido)
    return f"SegundosLecturaEstacion={seg_lectura};SegundosLatidoEstacion={seg_latido}"


def procesar_lectura_estacion(
    payload: dict,
    registro: RegistroEstacion,
    control_iluminacion,
    control_clima: ControlClimaLluvia,
) -> LecturaEstacion:
    """Punto unico: persistir lectura, iluminacion (luz) y clima (lluvia)."""
    lectura = parsear_lectura(payload)
    registro.actualizar(lectura)

    if lectura.luz is not None:
        control_iluminacion.procesar_lectura(lectura.luz)

    if lectura.lluvia is not None:
        control_clima.procesar_lluvia(lectura.lluvia)

    return lectura
