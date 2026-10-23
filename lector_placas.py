# lector_placas.py
# Lectura de placa con EasyOCR sobre una REGION FIJA de la imagen (sin YOLO).
# El enunciado (sec. 5.3 punto 3) permite usar una region fija cuando el detector
# no es confiable por la escala de la maqueta. Ademas, no cargar YOLO ni sus
# dependencias reduce la memoria a la mitad: entra en una Raspberry Pi de 2 GB.
#
# Uso:  python lector_placas.py captura_1.jpg
#
# Region de interes (opcional): PORTUS_ROI="x,y,w,h" en fracciones de 0 a 1.
#   Ej. PORTUS_ROI="0.2,0.35,0.6,0.3"  -> recorta el centro donde cae la placa.
#   Sin PORTUS_ROI se usa la imagen completa (EasyOCR ubica el texto solo).

import os
import sys

import cv2
import numpy as np
import easyocr

# QUE: confianza minima (sec. 5.3, rango 30 a 95). Configurable para igualar al backend.
CONFIANZA_MINIMA_OCR = float(os.getenv("PORTUS_CONFIANZA_MINIMA_OCR", "30"))

# QUE: OCR preentrenado de EasyOCR, en CPU (la Raspberry no tiene GPU).
reader = easyocr.Reader(["en"], gpu=False, verbose=False)


def _roi_config():
    """Lee PORTUS_ROI='x,y,w,h' (fracciones 0-1). Devuelve None si no esta definida."""
    crudo = os.getenv("PORTUS_ROI", "").strip()
    if not crudo:
        return None
    try:
        x, y, w, h = (float(v) for v in crudo.split(","))
        return x, y, w, h
    except (ValueError, TypeError):
        print(f"PORTUS_ROI invalida ({crudo!r}); se usa la imagen completa.")
        return None


def recortar_region(img_rgb):
    """Recorta la region fija donde aparece la placa (si PORTUS_ROI esta definida)."""
    roi = _roi_config()
    if roi is None:
        return img_rgb, [0, 0, img_rgb.shape[1], img_rgb.shape[0]]
    alto, ancho = img_rgb.shape[:2]
    fx, fy, fw, fh = roi
    x1 = max(0, int(fx * ancho))
    y1 = max(0, int(fy * alto))
    x2 = min(ancho, int((fx + fw) * ancho))
    y2 = min(alto, int((fy + fh) * alto))
    if x2 <= x1 or y2 <= y1:
        return img_rgb, [0, 0, ancho, alto]
    return img_rgb[y1:y2, x1:x2], [x1, y1, x2, y2]


def enderezar(crop_rgb):
    """Gira el recorte para que la placa quede recta, midiendo con el cuerpo blanco."""
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


# QUE: confusiones tipicas del OCR. En posiciones de digitos se cambian letras por numeros y viceversa.
MAPA_DIGITO = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "T": "1", "S": "5", "Z": "2", "B": "8", "G": "6"}
MAPA_LETRA = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}


def corregir_formato(texto):
    """Formato placa comercial: 1 letra, 3 digitos, 3 letras (ej. C123BCD). Solo si hay 7 caracteres."""
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
    """Devuelve una lista con la lectura de la placa (una region). Interfaz compatible
    con camara_garita: cada dict trae 'placa' y 'confianza_ocr' (0-1)."""
    bgr = cv2.imread(ruta_imagen)
    if bgr is None:
        print(f"No se pudo abrir la imagen: {ruta_imagen}")
        return []
    img_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    region, bbox = recortar_region(img_rgb)
    recto = enderezar(region)
    ampliado = cv2.resize(recto, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    texto, conf_ocr = ocr_sobre(ampliado)

    # DEBUG: guarda lo que recibe el OCR para revisarlo a simple vista.
    os.makedirs("debug", exist_ok=True)
    cv2.imwrite("debug/region.jpg", cv2.cvtColor(region, cv2.COLOR_RGB2BGR))
    cv2.imwrite("debug/ampliado.png", cv2.cvtColor(ampliado, cv2.COLOR_RGB2BGR))

    return [{
        "placa": texto,
        "confianza_deteccion": 1.0,          # region fija: no hay detector que puntuar
        "confianza_ocr": conf_ocr,
        "valida": bool(texto) and conf_ocr * 100 >= CONFIANZA_MINIMA_OCR,
        "bbox": bbox,
    }]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python lector_placas.py <ruta_imagen>")
        sys.exit(1)

    placas = leer_placa(sys.argv[1])
    if not placas:
        print("No se detecto ninguna placa en la imagen.")
    else:
        for p in placas:
            print(f"  PLACA: {p['placa'] or '[no leida]'}"
                  f"   ocr={p['confianza_ocr']:.0%}"
                  f"   valida={'si' if p['valida'] else 'no'}"
                  f"   bbox={p['bbox']}")