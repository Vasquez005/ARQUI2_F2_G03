"""Pipeline del repo del catedratico (fercho9134/ejemplo-placas).

YOLO recorta la placa, se preprocesa y PaddleOCR lee los caracteres.
No se entrena nada: los pesos son preentrenados.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

import config

_model = None
_ocr = None
_error_modelo = ""


STEP_DESCRIPTIONS = {
    "0_original": "Recorte detectado por YOLO. Este es el punto de partida del OCR.",
    "1_grayscale": "Conversion a escala de grises. El OCR no necesita color.",
    "2_upscaled": "Upscale 3x. PaddleOCR rinde mejor con caracteres grandes.",
    "3_denoised": "Filtro bilateral. Reduce ruido preservando bordes.",
    "4_clahe": "CLAHE. Levanta contraste local sin saturar.",
    "5_sharpened": "Sharpening. Ayuda a distinguir 0/O, 1/I, 5/S.",
}


def error_modelo() -> str:
    return _error_modelo


def _cargar():
    global _model, _ocr, _error_modelo
    if _model is not None or _ocr is not None:
        return
    from paddleocr import PaddleOCR
    from ultralytics import YOLO

    ruta = Path(config.MODELO_PLACAS)
    if not ruta.is_file():
        _error_modelo = f"Falta el modelo YOLO en {ruta}. Corre vision/descargar_modelo.sh"
        raise FileNotFoundError(_error_modelo)
    _model = YOLO(str(ruta))
    _ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        lang="en",
    )
    _error_modelo = ""


def to_base64(img) -> str:
    import base64

    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode()


def preprocess_pipeline(crop_rgb):
    steps = {}
    steps["0_original"] = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    steps["1_grayscale"] = gray
    upscaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    steps["2_upscaled"] = upscaled
    denoised = cv2.bilateralFilter(upscaled, d=9, sigmaColor=75, sigmaSpace=75)
    steps["3_denoised"] = denoised
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    contrast = clahe.apply(denoised)
    steps["4_clahe"] = contrast
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(contrast, -1, kernel)
    steps["5_sharpened"] = sharpened
    return steps, sharpened


def run_ocr(img_gray):
    _cargar()
    img_3ch = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    result = _ocr.predict(img_3ch)
    if not result:
        return "", 0.0
    res = result[0]
    texts = res.get("rec_texts", [])
    scores = res.get("rec_scores", [])
    polys = res.get("rec_polys", [])
    if not texts:
        return "", 0.0

    def poly_height(poly):
        ys = [p[1] for p in poly]
        return max(ys) - min(ys)

    heights = [poly_height(p) for p in polys] if polys else [1] * len(texts)
    best_idx = heights.index(max(heights))
    text = texts[best_idx].upper().replace(" ", "")
    text = "".join(c for c in text if c.isalnum() or c == "-")
    return text, float(scores[best_idx]) if scores else 0.0


def _roi_fija(img_rgb):
    raw = config.ROI_GARITA.strip()
    if not raw:
        return None
    try:
        x1, y1, x2, y2 = [int(v) for v in raw.split(",")]
    except ValueError:
        return None
    h, w = img_rgb.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def process_image(img_rgb):
    _cargar()
    results = _model(img_rgb, verbose=False)[0]
    plates = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        det_conf = float(box.conf[0])
        crop = img_rgb[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        steps, final_img = preprocess_pipeline(crop)
        plate_text, ocr_conf = run_ocr(final_img)
        plates.append({
            "bbox": [x1, y1, x2, y2],
            "detection_confidence": round(det_conf, 3),
            "plate_text": plate_text,
            "ocr_confidence": round(ocr_conf, 3),
            "fuente": "yolo",
            "steps": steps,
        })
    if not plates:
        roi = _roi_fija(img_rgb)
        if roi:
            x1, y1, x2, y2 = roi
            crop = img_rgb[y1:y2, x1:x2]
            steps, final_img = preprocess_pipeline(crop)
            plate_text, ocr_conf = run_ocr(final_img)
            plates.append({
                "bbox": roi,
                "detection_confidence": 0.0,
                "plate_text": plate_text,
                "ocr_confidence": round(ocr_conf, 3),
                "fuente": "roi",
                "steps": steps,
            })
    return plates
