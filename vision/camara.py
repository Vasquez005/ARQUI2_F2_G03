"""Captura de la webcam USB (/dev/video0 en Linux)."""

from __future__ import annotations

from datetime import datetime, timezone

import cv2
import numpy as np
from PIL import Image

import config


def estado_camara() -> dict:
    cap = cv2.VideoCapture(config.CAMARA_INDICE)
    ok = bool(cap.isOpened())
    if ok:
        ok, _ = cap.read()
    cap.release()
    return {
        "camara": "ok" if ok else "fuera",
        "indice": config.CAMARA_INDICE,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def capturar_rgb():
    cap = cv2.VideoCapture(config.CAMARA_INDICE)
    if not cap.isOpened():
        return None
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def imagen_desde_bytes(contents: bytes) -> np.ndarray:
    return np.array(Image.open(__import__("io").BytesIO(contents)).convert("RGB"))


def guardar_captura(img_rgb, prefijo: str = "captura") -> str:
    config.CAPTURA_DIR.mkdir(parents=True, exist_ok=True)
    nombre = f"{prefijo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    ruta = config.CAPTURA_DIR / nombre
    cv2.imwrite(str(ruta), cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))
    return str(ruta)
