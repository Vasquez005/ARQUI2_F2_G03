"""Camara de la garita en el servidor (Fase 3, sec. 5.3 y 6.1).

Al llegar un vehiculo, el servidor toma una foto, lee la placa con el lector de
lector_placas.py y aplica la verificacion en dos pasos (verificacion.py).

Las dependencias de vision (OpenCV, YOLO, EasyOCR) solo se cargan cuando se usan,
para que el backend siga arrancando en equipos sin esas librerias.
"""

import os
import sys
import threading
from typing import Callable, Iterable, Optional

import verificacion

RAIZ_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INDICE_CAMARA = int(os.getenv("PORTUS_INDICE_CAMARA", "0"))
RUTA_FOTO = os.getenv("PORTUS_RUTA_FOTO_GARITA", os.path.join(RAIZ_REPO, "captura_garita.jpg"))

_lock = threading.Lock()
_lector = None


def _modulo_lector():
    """Importa lector_placas solo la primera vez (carga YOLO y EasyOCR)."""
    global _lector
    if _lector is None:
        if RAIZ_REPO not in sys.path:
            sys.path.insert(0, RAIZ_REPO)
        import lector_placas
        _lector = lector_placas
    return _lector


def capturar_foto(ruta: str = RUTA_FOTO, indice: int = INDICE_CAMARA) -> bool:
    """Toma una foto de la garita. False si la camara no abre o no entrega imagen (sec. 5.6)."""
    import cv2

    cap = cv2.VideoCapture(indice)
    try:
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        if not ok:
            return False
        cv2.imwrite(ruta, frame)
        return True
    finally:
        cap.release()


INTENTOS_OCR_DEFECTO = 3       # sec. 8.7
INTENTOS_OCR_MIN = 1
INTENTOS_OCR_MAX = 5


def validar_intentos(intentos: int) -> None:
    if not INTENTOS_OCR_MIN <= intentos <= INTENTOS_OCR_MAX:
        raise ValueError(f"IntentosOCR fuera de rango ({INTENTOS_OCR_MIN} a {INTENTOS_OCR_MAX})")


def _mejor_placa(placas: list, ruta: str) -> dict:
    if not placas:
        return {"texto": "", "confianza": 0.0, "foto": ruta}
    mejor = max(placas, key=lambda p: p["confianza_ocr"])
    return {"texto": mejor["placa"], "confianza": mejor["confianza_ocr"] * 100, "foto": ruta}


def leer_placa_garita(
    capturar: Callable[[], bool] = capturar_foto,
    leer: Optional[Callable[[str], list]] = None,
    intentos: int = INTENTOS_OCR_DEFECTO,
    es_valida: Optional[Callable[[dict], bool]] = None,
) -> Optional[dict]:
    """Foto + lectura. None si la camara esta fuera de servicio.

    Si la lectura no es valida (es_valida), toma otra foto, hasta `intentos` veces (sec. 5.3 punto 5).
    Devuelve {"texto", "confianza" (0-100), "foto"} con la ultima lectura realizada.
    """
    validar_intentos(intentos)
    ultima = None
    with _lock:
        if leer is None:
            leer = _modulo_lector().leer_placa
        for _ in range(intentos):
            if not capturar():
                return None
            ultima = _mejor_placa(leer(RUTA_FOTO), RUTA_FOTO)
            if es_valida is None or es_valida(ultima):
                break
    return ultima


def evaluar_garita(
    etiqueta_registrada: bool,
    placa_registrada: str,
    restringidas: Iterable[str],
    catalogo: Iterable[str],
    umbral_ocr: float,
    lectura: Optional[dict],
) -> verificacion.Decision:
    """Combina la lectura de la camara (o su ausencia) con la verificacion en dos pasos."""
    camara_ok = lectura is not None
    texto = lectura["texto"] if camara_ok else ""
    confianza = lectura["confianza"] if camara_ok else 0.0
    return verificacion.evaluar_ingreso(
        etiqueta_registrada=etiqueta_registrada,
        camara_ok=camara_ok,
        texto_leido=texto,
        confianza_ocr=confianza,
        umbral_ocr=umbral_ocr,
        placa_registrada=placa_registrada,
        restringidas=restringidas,
        catalogo=catalogo,
    )
