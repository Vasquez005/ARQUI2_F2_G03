# check_modelo.py
from ultralytics import YOLO
m = YOLO("models/license-plate-finetune-v1x.pt")   # pon el nombre real de tu archivo
print("Clases que detecta:", m.names)