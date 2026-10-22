"""Servicio de vision PORTUS.

Adaptacion de https://github.com/fercho9134/ejemplo-placas
(YOLO de placas + PaddleOCR + Mongo). Añade webcam, MQTT y el formato
de PORTUS. Python 3.12 (usar el contenedor o un venv 3.12).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient

import camara
import config
import mqtt_io
import pipeline

_client = AsyncIOMotorClient(config.MONGO_URI)
_db = _client[config.MONGO_DB]
col_autorizadas = _db["placas_autorizadas"]
col_logs = _db["logs_acceso"]
_loop = None


async def sembrar_placas() -> None:
    for texto in config.PLACAS_SEMILLA:
        if await col_autorizadas.find_one({"placa": texto}):
            continue
        await col_autorizadas.insert_one({"placa": texto, "origen": "semilla"})


async def verificar_y_loguear(plate: dict) -> bool:
    texto = plate.get("plate_text") or ""
    if not texto:
        tipo, autorizado = "no_reconocido", False
    else:
        existe = await col_autorizadas.find_one({"placa": texto})
        if existe is None:
            normal = "".join(c for c in texto.upper() if c.isalnum())
            async for doc in col_autorizadas.find({}):
                otra = "".join(c for c in str(doc.get("placa", "")).upper() if c.isalnum())
                if otra == normal:
                    existe = doc
                    break
        autorizado = existe is not None
        tipo = "autorizado" if autorizado else "no_autorizada"
    await col_logs.insert_one({
        "tipo": tipo,
        "placa": texto or None,
        "bbox": plate.get("bbox"),
        "detection_confidence": plate.get("detection_confidence"),
        "ocr_confidence": plate.get("ocr_confidence"),
        "timestamp": datetime.now(timezone.utc),
    })
    return autorizado


def _sin_steps(plate: dict) -> dict:
    return {k: v for k, v in plate.items() if k != "steps"}


async def _enriquecer(plates: list) -> list:
    resultados = []
    if not plates:
        await col_logs.insert_one({
            "tipo": "no_reconocida",
            "placa": None,
            "bbox": None,
            "detection_confidence": None,
            "ocr_confidence": None,
            "timestamp": datetime.now(timezone.utc),
        })
    for plate in plates:
        autorizado = await verificar_y_loguear(plate)
        item = _sin_steps(plate)
        item["autorizada"] = autorizado
        resultados.append(item)
    return resultados


def _mejor(plates: list) -> dict:
    if not plates:
        return {"plate_text": "", "ocr_confidence": 0.0, "detection_confidence": 0.0, "bbox": None}
    return max(plates, key=lambda p: (p.get("ocr_confidence") or 0, p.get("detection_confidence") or 0))


def _publicar_lectura(uid: str, plates: list, foto: str, intento: int) -> dict:
    mejor = _mejor(plates)
    lectura = {
        "uid": uid,
        "placa": mejor.get("plate_text") or "",
        "confianza": mejor.get("ocr_confidence") or 0.0,
        "deteccion": mejor.get("detection_confidence") or 0.0,
        "bbox": mejor.get("bbox"),
        "fuente": mejor.get("fuente", "yolo"),
        "intento": intento,
        "foto": foto,
        "count": len(plates),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    mqtt_io.publicar_placa(lectura)
    return lectura


def _capturar_y_leer(uid: str = "") -> dict:
    img = camara.capturar_rgb()
    if img is None:
        mqtt_io.publicar_estado("fuera", "no hay imagen")
        return {"ok": False, "error": "camara_fuera", "plates": []}
    ultima = {"ok": False, "plates": [], "lectura": {}}
    for intento in range(1, config.INTENTOS_OCR + 1):
        if intento > 1:
            otra = camara.capturar_rgb()
            if otra is not None:
                img = otra
        plates = pipeline.process_image(img)
        foto = camara.guardar_captura(img, f"uid_{uid or 'manual'}_{intento}")
        lectura = _publicar_lectura(uid, plates, foto, intento)
        ultima = {"ok": True, "plates": plates, "lectura": lectura, "foto": foto}
        if (lectura["placa"] and lectura["confianza"] >= config.CONFIANZA_MINIMA):
            break
    return ultima


def _on_capturar_mqtt(datos: dict) -> None:
    if _loop is None:
        return
    fut = asyncio.run_coroutine_threadsafe(_capturar_desde_mqtt(datos), _loop)
    try:
        fut.result(timeout=60)
    except Exception as exc:
        print(f"[VISION] captura MQTT fallo: {exc!r}")


async def _capturar_desde_mqtt(datos: dict) -> dict:
    resultado = await asyncio.to_thread(_capturar_y_leer, datos.get("uid", ""))
    if resultado.get("ok"):
        await _enriquecer(resultado.get("plates") or [])
    return resultado


def _latido_loop() -> None:
    import time

    while True:
        est = camara.estado_camara()
        modelos = "ok" if not pipeline.error_modelo() else "fuera"
        mqtt_io.publicar_estado(est["camara"], modelos=modelos)
        time.sleep(config.SEGUNDOS_LATIDO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    await sembrar_placas()
    mqtt_io.conectar(on_capturar=_on_capturar_mqtt)
    import threading
    threading.Thread(target=_latido_loop, daemon=True).start()
    yield


app = FastAPI(title="PORTUS Vision (placas)", lifespan=lifespan)


@app.get("/health")
async def health():
    est = camara.estado_camara()
    return {
        "ok": True,
        "camara": est["camara"],
        "modelo": config.MODELO_PLACAS,
        "modelo_listo": not bool(pipeline.error_modelo()),
        "mongo": config.MONGO_URI,
    }


@app.get("/placas")
async def listar_placas():
    return [{"placa": d["placa"]} async for d in col_autorizadas.find({}, {"_id": 0, "placa": 1})]


@app.post("/placas/{placa}")
async def alta_placa(placa: str):
    texto = placa.strip().upper()
    if not texto:
        raise HTTPException(400, "placa_vacia")
    await col_autorizadas.update_one({"placa": texto}, {"$set": {"placa": texto}}, upsert=True)
    return {"placa": texto}


@app.get("/", response_class=HTMLResponse)
async def portada():
    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>PORTUS Vision</title>
<style>
 body{font-family:sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem}
 button,input{font:inherit;margin:.3rem 0}
</style></head><body>
<h1>PORTUS Vision</h1>
<p>Camara USB + YOLO de placas + PaddleOCR (repo del catedratico, acoplado a PORTUS).</p>
<p><a href="/health">/health</a> · <a href="/docs">/docs</a></p>
<form action="/capturar-visual" method="post"><button>Capturar de la camara</button></form>
<form action="/detect-plate-visual" method="post" enctype="multipart/form-data">
 <p>O sube una foto: <input type="file" name="image" accept="image/*">
 <button>Leer placa</button></p>
</form>
</body></html>"""


@app.post("/capturar")
async def capturar(uid: str = ""):
    try:
        resultado = await asyncio.to_thread(_capturar_y_leer, uid)
    except FileNotFoundError as exc:
        mqtt_io.publicar_estado("ok", str(exc), modelos="fuera")
        raise HTTPException(503, str(exc))
    if not resultado.get("ok"):
        raise HTTPException(503, resultado.get("error", "camara_fuera"))
    plates = await _enriquecer(resultado["plates"])
    return {"count": len(plates), "plates": plates, "lectura": resultado.get("lectura")}


@app.post("/capturar-visual", response_class=HTMLResponse)
async def capturar_visual():
    try:
        resultado = await asyncio.to_thread(_capturar_y_leer, "")
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))
    if not resultado.get("ok"):
        return HTMLResponse("<p>No hay imagen de la camara. Revisa el USB y /dev/video0.</p>", 503)
    await _enriquecer(resultado["plates"])
    return render_html(resultado["plates"])


@app.post("/detect-plate")
async def detect_plate(image: UploadFile = File(...)):
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(400, "El archivo debe ser una imagen")
    contents = await image.read()
    img = camara.imagen_desde_bytes(contents)
    try:
        plates = await asyncio.to_thread(pipeline.process_image, img)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))
    foto = camara.guardar_captura(img, "upload")
    _publicar_lectura("", plates, foto, 1)
    resultados = await _enriquecer(plates)
    return {"count": len(plates), "plates": resultados}


@app.post("/detect-plate-visual", response_class=HTMLResponse)
async def detect_plate_visual(image: UploadFile = File(...)):
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(400, "El archivo debe ser una imagen")
    contents = await image.read()
    img = camara.imagen_desde_bytes(contents)
    try:
        plates = await asyncio.to_thread(pipeline.process_image, img)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))
    foto = camara.guardar_captura(img, "upload")
    _publicar_lectura("", plates, foto, 1)
    await _enriquecer(plates)
    return render_html(plates)


def render_html(plates) -> str:
    if not plates:
        body = "<p>No se detectaron placas en la imagen.</p>"
    else:
        body = "".join(render_plate_card(i, p) for i, p in enumerate(plates, 1))
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Pipeline placas</title>
<style>
 body{{font-family:sans-serif;background:#111;color:#eee;margin:0;padding:1.5rem}}
 .card{{background:#1c1c1c;border-radius:12px;padding:1rem;margin:1rem 0}}
 .meta{{display:flex;gap:1rem;flex-wrap:wrap}}
 .steps{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.8rem}}
 .steps img{{width:100%;border-radius:8px}}
 .conf-good{{color:#6f6}}.conf-mid{{color:#fc6}}.conf-low{{color:#f66}}
 a{{color:#9cf}}
</style></head><body>
<p><a href="/">Volver</a></p>
{body}
</body></html>"""


def render_plate_card(idx, plate) -> str:
    text = plate.get("plate_text") or "[no reconocida]"
    det = plate.get("detection_confidence") or 0
    ocr = plate.get("ocr_confidence") or 0

    def conf_class(v):
        if v >= 0.85:
            return "conf-good"
        if v >= 0.6:
            return "conf-mid"
        return "conf-low"

    steps_html = "".join(
        f"""<div><img src="data:image/jpeg;base64,{pipeline.to_base64(img)}" alt="{name}">
        <p>{name.split('_', 1)[-1]}</p>
        <small>{pipeline.STEP_DESCRIPTIONS.get(name, '')}</small></div>"""
        for name, img in (plate.get("steps") or {}).items()
    )
    return f"""<div class="card">
 <h2>Placa #{idx} · bbox {plate.get("bbox")}</h2>
 <p class="{conf_class(ocr)}" style="font-size:1.6rem">{text}</p>
 <div class="meta">
  <span>YOLO <b class="{conf_class(det)}">{det:.1%}</b></span>
  <span>OCR <b class="{conf_class(ocr)}">{ocr:.1%}</b></span>
  <span>fuente {plate.get("fuente", "yolo")}</span>
 </div>
 <div class="steps">{steps_html}</div>
</div>"""
