"""Ajustes del servicio de vision (ejemplo-placas acoplado a PORTUS)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MONGO_URI = os.getenv("PORTUS_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("PORTUS_MONGO_DB", "placas")

MQTT_HOST = os.getenv("PORTUS_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("PORTUS_MQTT_PORT", "1883"))

CAMARA_INDICE = int(os.getenv("PORTUS_CAMARA", "0"))
# Region fija de la garita (x1,y1,x2,y2) si YOLO no encuentra placa. Vacio = no.
ROI_GARITA = os.getenv("PORTUS_ROI_GARITA", "")

MODELO_PLACAS = os.getenv(
    "PORTUS_MODELO_PLACAS",
    str(ROOT / "models" / "license-plate-finetune-v1n.pt"),
)
MODELO_URL = os.getenv(
    "PORTUS_MODELO_URL",
    "https://huggingface.co/morsetechlab/yolov11-license-plate-detection/resolve/main/license-plate-finetune-v1n.pt",
)

CAPTURA_DIR = Path(os.getenv("PORTUS_CAPTURA_DIR", str(ROOT / "capturas")))
SEGUNDOS_LATIDO = int(os.getenv("PORTUS_VISION_LATIDO", "10"))
INTENTOS_OCR = max(1, min(5, int(os.getenv("PORTUS_INTENTOS_OCR", "3"))))
CONFIANZA_MINIMA = float(os.getenv("PORTUS_CONFIANZA_OCR", "0.60"))

# Placas que Mongo considera autorizadas si el backend no responde.
PLACAS_SEMILLA = [
    p.strip().upper()
    for p in os.getenv("PORTUS_PLACAS_SEMILLA", "C-001,C-002,C-003").split(",")
    if p.strip()
]
