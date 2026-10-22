# ocr_test.py
import cv2, sys
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_textline_orientation=False, lang="en")

img = cv2.imread(sys.argv[1])            # ruta de la imagen
res = ocr.predict(img)

if res and res[0].get("rec_texts"):
    for texto, score in zip(res[0]["rec_texts"], res[0]["rec_scores"]):
        print(f"Texto: {texto!r}   confianza: {score:.2f}")
else:
    print("No se leyo texto")