# lector_placas.py
# Detecta la placa con YOLO, la recorta, la preprocesa y lee el texto con PaddleOCR.
# Uso:  python lector_placas.py ref/test-image/placa2.jpg

import sys
import cv2
import numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR

# ── CAMBIA ESTO por el nombre real de tu archivo .pt ──
RUTA_MODELO = "models/license-plate-finetune-v1x.pt"

# QUE: carga el detector de placas (YOLO) una sola vez.
model = YOLO(RUTA_MODELO)

# QUE: OCR preentrenado. Desactivamos modulos de documentos para que sea mas rapido.
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    lang="en",
)


def preprocesar(crop_rgb):
    """Mejora el recorte de la placa para que el OCR lea mejor."""
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(gray, -1, kernel)


def ocr_sobre(img_gray):
    """Corre el OCR y devuelve (texto, confianza) del renglon mas grande."""
    img_3ch = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    res = ocr.predict(img_3ch)
    if not res or not res[0].get("rec_texts"):
        return "", 0.0

    r = res[0]
    textos = r["rec_texts"]
    scores = r["rec_scores"]
    polys = r.get("rec_polys", [])

    # QUE: elegimos el texto cuyo renglon es mas ALTO (suele ser el numero principal).
    if polys:
        alturas = [max(p[i][1] for i in range(len(p))) - min(p[i][1] for i in range(len(p))) for p in polys]
        idx = alturas.index(max(alturas))
    else:
        idx = scores.index(max(scores))

    texto = textos[idx].upper().replace(" ", "")
    texto = "".join(c for c in texto if c.isalnum() or c == "-")
    return texto, float(scores[idx])


def leer_placa(ruta_imagen):
    """Devuelve una lista de placas encontradas en la imagen."""
    bgr = cv2.imread(ruta_imagen)
    if bgr is None:
        print(f"No se pudo abrir la imagen: {ruta_imagen}")
        return []
    img_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    resultados = model(img_rgb, verbose=False)[0]
    placas = []

    for box in resultados.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf_det = float(box.conf[0])
        crop = img_rgb[y1:y2, x1:x2]
        proc = preprocesar(crop)
        texto, conf_ocr = ocr_sobre(proc)
        placas.append({
            "placa": texto,
            "confianza_deteccion": round(conf_det, 3),
            "confianza_ocr": round(conf_ocr, 3),
            "bbox": [x1, y1, x2, y2],
        })

    return placas


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python lector_placas.py <ruta_imagen>")
        sys.exit(1)

    placas = leer_placa(sys.argv[1])

    if not placas:
        print("No se detecto ninguna placa en la imagen.")
    else:
        print(f"Placas detectadas: {len(placas)}")
        for i, p in enumerate(placas, 1):
            print(f"  #{i}  PLACA: {p['placa'] or '[no leida]'}"
                  f"   det={p['confianza_deteccion']:.0%}"
                  f"   ocr={p['confianza_ocr']:.0%}"
                  f"   bbox={p['bbox']}")