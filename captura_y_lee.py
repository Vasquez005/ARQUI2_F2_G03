# captura_y_lee.py  →  python3 captura_y_lee.py
# ESPACIO = capturar y leer la placa   |   Q = salir
import cv2
from lector_placas import leer_placa   # reusa tu lector ya hecho

INDICE_CAMARA = 1   # cambia a 0 (Mac) o 2 si no abre la USB

cap = cv2.VideoCapture(INDICE_CAMARA)
if not cap.isOpened():
    print(f"No se abrio la camara {INDICE_CAMARA}. Prueba con 0 o 2.")
    exit()

print("ESPACIO = capturar y leer   |   Q = salir")
while True:
    ok, frame = cap.read()
    if not ok:
        break
    cv2.imshow("PORTUS - placa (ESPACIO=leer, Q=salir)", frame)

    k = cv2.waitKey(1) & 0xFF
    if k == ord(" "):
        cv2.imwrite("captura_actual.jpg", frame)
        print("\n--- Leyendo ---")
        placas = leer_placa("captura_actual.jpg")
        if not placas:
            print("  No se detecto placa. Acerca mas / mejor luz.")
        for i, p in enumerate(placas, 1):
            print(f"  PLACA: {p['placa'] or '[no leida]'}"
                  f"   det={p['confianza_deteccion']:.0%}"
                  f"   ocr={p['confianza_ocr']:.0%}")
    elif k == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()