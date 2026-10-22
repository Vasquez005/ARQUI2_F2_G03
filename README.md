# PORTUS – Lector de Placas (Visión) 🚗

Módulo de visión del proyecto PORTUS: detecta la placa de un vehículo con **YOLO**
y lee el texto con **PaddleOCR**. Corre en Mac/PC para pruebas y en la Raspberry Pi
para la integración final.

---

## 📦 Qué contiene

| Archivo               | Para qué sirve                                      |
|-----------------------|-----------------------------------------------------|
| `lector_placas.py`    | Lee la placa de una imagen (YOLO + OCR)             |
| `camara_test.py`      | Prueba que la cámara USB funcione                   |
| `captura_y_lee.py`    | Toma foto con la cámara y lee la placa al instante  |
| `models/*.pt`         | Modelo YOLO entrenado (NECESARIO, no se instala)    |
| `requirements.txt`    | Dependencias para Mac / PC                          |
| `requirements_pi.txt` | Dependencias para la Raspberry Pi                   |

> ⚠️ El modelo `.pt` NO viene en `requirements`. Asegúrate de tenerlo en `models/`.

---

## 🖥️ Instalación en Mac / PC

```bash
# 1. Entrar a la carpeta del proyecto
cd PROYECTO2

# 2. (Opcional pero recomendado) crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate      # en Windows:  .venv\Scripts\activate

# 3. Instalar dependencias
pip3 install -r requirements.txt
```

---

## 🍓 Instalación en Raspberry Pi

```bash
cd PROYECTO2
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements_pi.txt
```

> Si `paddlepaddle` falla al instalar en la Pi (es ARM), usar `easyocr` como alternativa.

---

## ▶️ Cómo usarlo

**Probar la cámara:**
```bash
python3 camara_test.py
```

**Leer una placa de una foto:**
```bash
python3 lector_placas.py ruta/de/la/foto.jpg
```

**Capturar y leer en vivo:**
```bash
python3 captura_y_lee.py
```
ESPACIO = capturar y leer la placa · Q = salir

> Si la cámara no abre, cambia `INDICE_CAMARA` (0 = cámara del equipo, 1 o 2 = USB).

---

## 💡 Tips para buena lectura
- Buena luz, sin reflejos.
- Placa de frente (no inclinada).
- Que la placa ocupe buena parte del cuadro.

---

**Proyecto:** Arquitectura de Computadoras y Ensambladores 2 – USAC
**Grupo:** G03
