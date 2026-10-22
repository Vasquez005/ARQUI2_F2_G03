# lector_placas.py
# Detecta la placa con YOLO, la recorta, la preprocesa y lee el texto con EasyOCR.
# Uso:  python lector_placas.py ref/test-image/placa2.jpg

import os
import sys
import cv2
import numpy as np
import easyocr
from ultralytics import YOLO

# ── CAMBIA ESTO por el nombre real de tu archivo .pt ──
RUTA_MODELO = "models/license-plate-finetune-v1x.pt"

# QUE: carga el detector de placas (YOLO) una sola vez.
model = YOLO(RUTA_MODELO)

# QUE: fraccion de la caja de YOLO que se agrega a cada lado antes del OCR (8 %).
MARGEN_CAJA = 0.08

# QUE: OCR preentrenado de EasyOCR, en CPU (la Raspberry no tiene GPU).
reader = easyocr.Reader(["en"], gpu=False, verbose=False)


def enderezar(crop_rgb):
    """Gira el recorte para que la placa quede recta. Mide la inclinacion con el cuerpo blanco de la placa."""
    gris = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    _, blanco = cv2.threshold(gris, 180, 255, cv2.THRESH_BINARY)
    contornos, _ = cv2.findContours(blanco, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return crop_rgb
    mayor = max(contornos, key=cv2.contourArea)
    _, _, angulo = cv2.minAreaRect(mayor)
    if angulo > 45:
        angulo -= 90
    alto, ancho = crop_rgb.shape[:2]
    M = cv2.getRotationMatrix2D((ancho / 2, alto / 2), angulo, 1.0)
    return cv2.warpAffine(crop_rgb, M, (ancho, alto), borderMode=cv2.BORDER_REPLICATE)


def preprocesar(crop_rgb):
    """Mejora el recorte de la placa para que el OCR lea mejor."""
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(gray, -1, kernel)


# QUE: confusiones tipicas del OCR. En las posiciones de digitos se cambian letras por numeros y viceversa.
MAPA_DIGITO = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "T": "1", "S": "5", "Z": "2", "B": "8", "G": "6"}
MAPA_LETRA = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}


def corregir_formato(texto):
    """Formato de placa: 1 letra, 3 digitos, 3 letras (ej. C123BCD). Solo corrige si tiene 7 caracteres."""
    if len(texto) != 7:
        return texto
    digitos = "".join(MAPA_DIGITO.get(c, c) for c in texto[1:4])
    letras = "".join(MAPA_LETRA.get(c, c) for c in texto[4:])
    return texto[0] + digitos + letras


def altura_caja(resultado):
    """resultado = (caja, texto, confianza). Altura de la caja en pixeles."""
    ys = [p[1] for p in resultado[0]]
    return max(ys) - min(ys)


def ocr_sobre(img):
    """Corre EasyOCR y devuelve (texto, confianza 0-1) del renglon mas alto. Acepta RGB o gris."""
    img_rgb = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    resultados = reader.readtext(img_rgb, detail=1, paragraph=False)
    if not resultados:
        return "", 0.0

    _, texto, conf = max(resultados, key=altura_caja)
    texto = texto.upper().replace(" ", "")
    texto = "".join(c for c in texto if c.isalnum() or c == "-")
    texto = corregir_formato(texto)
    return texto, float(conf)


def leer_placa(ruta_imagen):
    """Devuelve una lista de placas encontradas en la imagen."""
    bgr = cv2.imread(ruta_imagen)
    if bgr is None:
        print(f"No se pudo abrir la imagen: {ruta_imagen}")
        return []
    img_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    resultados = model(img_rgb, verbose=False)[0]
    placas = []

    for i, box in enumerate(resultados.boxes, 1):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf_det = float(box.conf[0])
        # QUE: margen alrededor de la caja de YOLO para no cortar letras de la orilla.
        margen_x = int((x2 - x1) * MARGEN_CAJA)
        margen_y = int((y2 - y1) * MARGEN_CAJA)
        alto_img, ancho_img = img_rgb.shape[:2]
        x1, x2 = max(0, x1 - margen_x), min(ancho_img, x2 + margen_x)
        y1, y2 = max(0, y1 - margen_y), min(alto_img, y2 + margen_y)
        crop = img_rgb[y1:y2, x1:x2]
        # QUE: primero se endereza la placa y luego se amplía a color; EasyOCR lee mejor asi.
        recto = enderezar(crop)
        ampliado = cv2.resize(recto, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        texto, conf_ocr = ocr_sobre(ampliado)

        # DEBUG: guarda lo que recibe el OCR para revisarlo a simple vista.
        os.makedirs("debug", exist_ok=True)
        cv2.imwrite(f"debug/crop_{i}.jpg", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        cv2.imwrite(f"debug/ampliado_{i}.png", cv2.cvtColor(ampliado, cv2.COLOR_RGB2BGR))

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
