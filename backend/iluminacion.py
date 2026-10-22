"""Iluminacion de la planta (fase 3, sec. 4.2 y 8.1).

El servidor decide si la tira LED debe estar encendida a partir de la luz que
mide la estacion meteorologica y manda al controlador IluminacionEncender o
IluminacionApagar solo cuando el estado cambia. El controlador solo actua
(firmware/mega_grua_pesaje, seccion FASE 3).

Reglas:
  - Automatico: enciende si la luz baja de UmbralLuzEncendido, apaga si supera
    UmbralLuzApagado. Entre ambos umbrales conserva el estado (histeresis).
  - Encendido forzado / Apagado forzado: ignoran la luz.
  - UmbralLuzApagado debe superar a UmbralLuzEncendido por al menos 5.

Este modulo no toca la base de datos ni MQTT: recibe una funcion que envia el
comando, y asi se prueba sin hardware (ver test_iluminacion.py).
"""

import threading
from typing import Callable, Optional

MODO_AUTOMATICO = "Automatico"
MODO_ENCENDIDO = "Encendido forzado"
MODO_APAGADO = "Apagado forzado"
MODOS = (MODO_AUTOMATICO, MODO_ENCENDIDO, MODO_APAGADO)

MARGEN_HISTERESIS = 5
RANGO_UMBRAL_ENCENDIDO = (0, 95)
RANGO_UMBRAL_APAGADO = (5, 100)

UMBRAL_ENCENDIDO_DEFECTO = 30
UMBRAL_APAGADO_DEFECTO = 45

TARGET_CONTROLADOR = "MEGA_GRUA"

# Envia un comando: (nombre, target, params). En app.py se conecta a MQTT y a la auditoria.
EnviarComando = Callable[[str, str, dict], None]
# Registra un cambio de modo en auditoria: (detalle).
Auditar = Callable[[dict], None]


def validar_umbrales(encendido: int, apagado: int) -> None:
    """Lanza ValueError si la pareja de umbrales no cumple los rangos ni la histeresis."""
    if not RANGO_UMBRAL_ENCENDIDO[0] <= encendido <= RANGO_UMBRAL_ENCENDIDO[1]:
        raise ValueError(f"UmbralLuzEncendido fuera de rango ({RANGO_UMBRAL_ENCENDIDO[0]} a {RANGO_UMBRAL_ENCENDIDO[1]})")
    if not RANGO_UMBRAL_APAGADO[0] <= apagado <= RANGO_UMBRAL_APAGADO[1]:
        raise ValueError(f"UmbralLuzApagado fuera de rango ({RANGO_UMBRAL_APAGADO[0]} a {RANGO_UMBRAL_APAGADO[1]})")
    if apagado - encendido < MARGEN_HISTERESIS:
        raise ValueError(
            f"UmbralLuzApagado debe ser mayor que UmbralLuzEncendido por al menos {MARGEN_HISTERESIS}"
        )


def validar_modo(modo: str) -> None:
    if modo not in MODOS:
        raise ValueError(f"modo de iluminacion invalido: {modo!r}")


def decidir_encendida(modo: str, nivel_luz: float, encendida_actual: Optional[bool],
                      umbral_encendido: int, umbral_apagado: int) -> bool:
    """Estado deseado de la tira. encendida_actual None = aun no se ha mandado nada."""
    validar_modo(modo)
    if modo == MODO_ENCENDIDO:
        return True
    if modo == MODO_APAGADO:
        return False
    if nivel_luz < umbral_encendido:
        return True
    if nivel_luz > umbral_apagado:
        return False
    # Zona de histeresis: se queda como estaba (None cuenta como apagada).
    return bool(encendida_actual)


class ControlIluminacion:
    """Guarda el modo y los umbrales vigentes y manda comandos solo al cambiar."""

    def __init__(self, enviar: EnviarComando, auditar: Optional[Auditar] = None,
                 modo: str = MODO_AUTOMATICO,
                 umbral_encendido: int = UMBRAL_ENCENDIDO_DEFECTO,
                 umbral_apagado: int = UMBRAL_APAGADO_DEFECTO):
        validar_modo(modo)
        validar_umbrales(umbral_encendido, umbral_apagado)
        self._enviar = enviar
        self._auditar = auditar or (lambda detalle: None)
        self._lock = threading.Lock()  # lecturas (hilo MQTT) y cambios de modo (FastAPI)
        self.modo = modo
        self.umbral_encendido = umbral_encendido
        self.umbral_apagado = umbral_apagado
        self.encendida: Optional[bool] = None  # ultimo estado mandado al controlador

    def procesar_lectura(self, nivel_luz: float) -> bool:
        """Aplica una lectura de luz (escala 0-100). Devuelve el estado deseado."""
        with self._lock:
            deseada = decidir_encendida(self.modo, nivel_luz, self.encendida,
                                        self.umbral_encendido, self.umbral_apagado)
            if deseada != self.encendida:
                self._mandar(deseada)
            return deseada

    def cambiar_modo(self, modo: str, origen: str = "") -> None:
        """Cambia el modo (selector de la pestaña Operacion). Se audita siempre."""
        validar_modo(modo)
        with self._lock:
            anterior = self.modo
            self.modo = modo
            self._auditar({"accion": "cambio_modo_iluminacion", "anterior": anterior,
                           "nuevo": modo, "origen": origen})
            if modo == MODO_ENCENDIDO:
                self._mandar(True)
            elif modo == MODO_APAGADO:
                self._mandar(False)
            # En Automatico no se manda nada hasta la siguiente lectura de luz.

    def cambiar_umbrales(self, encendido: int, apagado: int) -> None:
        """Rechaza la pareja si no cumple la histeresis (sec. 4.2 regla 1)."""
        validar_umbrales(encendido, apagado)
        with self._lock:
            self.umbral_encendido = encendido
            self.umbral_apagado = apagado

    def resincronizar(self) -> None:
        """El controlador volvio a tener enlace: encendio la tira sola al perderlo
        (sec. 4.2 regla 3). Se reenvia el estado que corresponde ahora."""
        with self._lock:
            if self.modo == MODO_ENCENDIDO:
                self._mandar(True)
            elif self.modo == MODO_APAGADO:
                self._mandar(False)
            else:
                # Automatico: la siguiente lectura de luz manda el estado correcto.
                self.encendida = None

    def _mandar(self, encender: bool) -> None:
        nombre = "IluminacionEncender" if encender else "IluminacionApagar"
        self._enviar(nombre, TARGET_CONTROLADOR, {"modo": self.modo})
        self.encendida = encender
