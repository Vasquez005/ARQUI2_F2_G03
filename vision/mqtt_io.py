"""Publica lecturas y latidos en MQTT para que el backend de PORTUS los use."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

import config

_client = None
_on_capturar = None


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def conectar(on_capturar=None) -> None:
    global _client, _on_capturar
    _on_capturar = on_capturar
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="PORTUS_VISION")

    def on_connect(c, userdata, flags, rc, properties=None):
        c.subscribe("portus/vision/capturar")
        publicar_estado("ok", "conectado")

    def on_message(c, userdata, msg):
        if msg.topic != "portus/vision/capturar" or _on_capturar is None:
            return
        try:
            datos = json.loads(msg.payload.decode("utf-8") or "{}")
        except Exception:
            datos = {}
        threading.Thread(target=_on_capturar, args=(datos,), daemon=True).start()

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, 30)
    except Exception as exc:
        print(f"[VISION] MQTT no disponible ({config.MQTT_HOST}:{config.MQTT_PORT}): {exc!r}")
        return
    client.loop_start()
    _client = client


def _pub(topic: str, payload: dict) -> None:
    if _client is None:
        return
    try:
        _client.publish(topic, json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        print(f"[VISION] no se pudo publicar {topic}: {exc!r}")


def publicar_estado(camara: str, detalle: str = "", modelos: str = "ok") -> None:
    _pub("portus/vision/estado", {
        "camara": camara,
        "modelos": modelos,
        "detalle": detalle,
        "ts": _ahora(),
    })


def publicar_placa(lectura: dict) -> None:
    _pub("portus/vision/placa", lectura)
