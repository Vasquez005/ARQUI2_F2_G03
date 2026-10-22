"""Verificacion de ingreso en dos pasos (Fase 3, sec. 6 y 7).

Un vehiculo solo ingresa si su etiqueta de radiofrecuencia y su placa corresponden
al mismo camion registrado. Este modulo decide el resultado a partir de la
etiqueta, la lectura de la camara y las listas. No toca la base de datos ni MQTT.
"""

from dataclasses import dataclass
from typing import Iterable, Optional

RT07 = "RT07"  # la placa leida no corresponde a la etiqueta (TERMINAL)
RT08 = "RT08"  # placa restringida por la autoridad (AUTORIDAD)

INGRESO_AUTORIZADO = "autorizado"
RETENCION = "retencion"
RECHAZO = "rechazo"
VERIFICACION_MANUAL = "verificacion_manual"
MODO_DEGRADADO = "modo_degradado"


@dataclass(frozen=True)
class Decision:
    resultado: str
    causa: Optional[str] = None     # RT07 / RT08 cuando hay retencion
    alarma: Optional[str] = None    # AL18, AL20, AL21, AL22
    linea1: str = ""                # textos literales de la pantalla de la garita (sec. 6.4)
    linea2: str = ""


def normalizar(placa: str) -> str:
    """Sec. 5.2 regla 5: se ignoran espacios y mayusculas."""
    return "".join(c for c in placa.upper() if c.isalnum())


def a_un_caracter(a: str, b: str) -> bool:
    """True si a y b son iguales o difieren en exactamente un caracter (cambio, alta o baja)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]


def buscar_coincidencia(leida: str, placas: Iterable[str]) -> Optional[str]:
    """Devuelve la placa de la lista que coincide con la leida.

    Coincidencia exacta tiene prioridad. Si no hay exacta, se acepta una sola
    placa que difiera en un caracter (sec. 5.3 regla 4). Si hay ambiguedad, no hay coincidencia.
    """
    n = normalizar(leida)
    if not n:
        return None
    placas = list(placas)
    for p in placas:
        if normalizar(p) == n:
            return p
    cercanas = [p for p in placas if a_un_caracter(n, normalizar(p))]
    return cercanas[0] if len(cercanas) == 1 else None


def evaluar_ingreso(
    etiqueta_registrada: bool,
    camara_ok: bool,
    texto_leido: str,
    confianza_ocr: float,
    umbral_ocr: float,
    placa_registrada: str,
    restringidas: Iterable[str],
    catalogo: Iterable[str],
) -> Decision:
    """Aplica las reglas de la sec. 6.2 y 7.

    confianza_ocr y umbral_ocr van en porcentaje (0 a 100).
    placa_registrada es la placa del camion asociado a la etiqueta ("" si no tiene).
    """
    # Etiqueta desconocida: rechazo en garita, pase lo que pase con la placa (sec. 6.2).
    if not etiqueta_registrada:
        return Decision(RECHAZO, linea1="ACCESO DENEGADO", linea2="TARJETA NO REGISTRADA")

    # Camara o modelo fuera de servicio: modo degradado con confirmacion manual (sec. 5.6).
    if not camara_ok:
        return Decision(MODO_DEGRADADO, alarma="AL18", linea1="MODO DEGRADADO", linea2="ESPERE AL OPERADOR")

    restringidas = list(restringidas)
    catalogo = list(catalogo)
    conocidas = catalogo + restringidas

    coincide = buscar_coincidencia(texto_leido, conocidas)
    lectura_valida = confianza_ocr >= umbral_ocr and coincide is not None

    # Sin lectura valida tras los intentos: verificacion manual del operador (sec. 6.2).
    if not lectura_valida:
        return Decision(VERIFICACION_MANUAL, alarma="AL22", linea1="VERIFICACION MANUAL", linea2="ESPERE AL OPERADOR")

    # Placa restringida tiene prioridad sobre cualquier otra regla (sec. 6.2).
    if buscar_coincidencia(texto_leido, restringidas) is not None:
        return Decision(RETENCION, causa=RT08, alarma="AL21", linea1="PLACA RESTRINGIDA", linea2=texto_leido)

    # La placa corresponde al camion de la etiqueta: ingreso autorizado (sujeto a la fase 2).
    if placa_registrada and buscar_coincidencia(texto_leido, [placa_registrada]) is not None:
        return Decision(INGRESO_AUTORIZADO, linea1="PLACA VERIFICADA", linea2=texto_leido)

    # Placa de otro camion registrado (o de la lista, ya cubierta arriba): no corresponde a la etiqueta.
    return Decision(RETENCION, causa=RT07, alarma="AL20", linea1="PLACA NO COINCIDE", linea2=texto_leido)


def texto_lectura_en_curso(etiqueta: str) -> tuple[str, str]:
    """Pantalla de la garita mientras se lee la placa (sec. 6.4)."""
    return "LEYENDO PLACA", etiqueta
