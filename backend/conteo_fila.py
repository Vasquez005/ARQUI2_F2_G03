"""Conteo de la fila de espera (Fase 3, sec. 5.4 y 5.5).

Cuenta vehiculos en la zona de espera con un detector COCO preentrenado.
La logica (contar, comparar con UmbralCola, alarma AL19 y pausa cuando se lee una
placa) es pura y se prueba sin hardware. El modelo solo se carga cuando se usa.
"""

import os
import threading
from typing import Iterable, Optional

# Clases COCO que puede dar un camion de maqueta (sec. 5.4 punto 2).
CLASES_VEHICULO_COCO = {2: "automovil", 5: "autobus", 7: "camion"}

UMBRAL_COLA_DEFECTO = 3       # sec. 8.7
UMBRAL_COLA_MIN = 1
UMBRAL_COLA_MAX = 10
SEGUNDOS_CONTEO_DEFECTO = 5   # sec. 8.7
SEGUNDOS_CONTEO_MIN = 2
SEGUNDOS_CONTEO_MAX = 30

RUTA_MODELO_COCO = os.getenv("PORTUS_MODELO_COCO", "yolov8n.pt")


def validar_umbral(umbral: int) -> None:
    if not UMBRAL_COLA_MIN <= umbral <= UMBRAL_COLA_MAX:
        raise ValueError(f"UmbralCola fuera de rango ({UMBRAL_COLA_MIN} a {UMBRAL_COLA_MAX})")


def validar_segundos(segundos: int) -> None:
    if not SEGUNDOS_CONTEO_MIN <= segundos <= SEGUNDOS_CONTEO_MAX:
        raise ValueError(f"SegundosConteoCola fuera de rango ({SEGUNDOS_CONTEO_MIN} a {SEGUNDOS_CONTEO_MAX})")


def contar_vehiculos(clases_detectadas: Iterable[int]) -> int:
    """Cuenta solo las clases de vehiculo; ignora personas, perros, etc."""
    return sum(1 for c in clases_detectadas if int(c) in CLASES_VEHICULO_COCO)


class ConteoFila:
    """Mantiene el ultimo conteo y la alarma AL19 (sec. 5.4 punto 5)."""

    def __init__(self, umbral: int = UMBRAL_COLA_DEFECTO,
                 alarma: Optional[callable] = None, superada: Optional[callable] = None) -> None:
        validar_umbral(umbral)
        self.umbral = umbral
        self._alarma = alarma or (lambda conteo: None)
        self._superada = superada or (lambda conteo: None)
        self._lock = threading.Lock()
        self.ultimo_conteo: Optional[int] = None
        self.congestionada = False
        self.pausado_por_placa = False

    def pausar_por_lectura_de_placa(self, pausado: bool) -> None:
        """Sec. 5.5 punto 2: la lectura de placas tiene prioridad sobre el conteo."""
        with self._lock:
            self.pausado_por_placa = pausado

    def registrar(self, conteo: int) -> None:
        """Aplica un conteo nuevo. Alarma al llegar al umbral; superada al bajar."""
        with self._lock:
            self.ultimo_conteo = conteo
            if conteo >= self.umbral and not self.congestionada:
                self.congestionada = True
                self._alarma(conteo)
            elif conteo < self.umbral and self.congestionada:
                self.congestionada = False
                self._superada(conteo)

    def puede_contar(self) -> bool:
        with self._lock:
            return not self.pausado_por_placa


def contar_con_modelo(frame_bgr, roi: Optional[tuple] = None) -> int:
    """Corre el detector COCO sobre la region de interes de la zona de espera.

    roi = (x1, y1, x2, y2). Si es None se usa la imagen completa.
    Requiere ultralytics y el modelo (se descarga la primera vez si hay internet).
    """
    global _modelo_coco
    if _modelo_coco is None:
        from ultralytics import YOLO
        _modelo_coco = YOLO(RUTA_MODELO_COCO)
    if roi is not None:
        x1, y1, x2, y2 = roi
        frame_bgr = frame_bgr[y1:y2, x1:x2]
    resultados = _modelo_coco(frame_bgr, verbose=False)[0]
    return contar_vehiculos(int(c) for c in resultados.boxes.cls.tolist())


_modelo_coco = None
