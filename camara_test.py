# camara_test.py  →  python camara_test.py
import cv2

cap = cv2.VideoCapture(0)          # 0 = primera camara. Si no, prueba 1 o 2.
if not cap.isOpened():
    print("No se abrio la camara (prueba VideoCapture(1))")
    exit()

print("ESPACIO = tomar foto y guardarla   |   Q = salir")
n = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    cv2.imshow("Camara (ESPACIO=foto, Q=salir)", frame)
    k = cv2.waitKey(1) & 0xFF
    if k == ord(" "):
        n += 1
        cv2.imwrite(f"captura_{n}.jpg", frame)
        print(f"Guardada captura_{n}.jpg")
    elif k == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()