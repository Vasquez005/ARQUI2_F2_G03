from __future__ import annotations

import argparse
import json
import os
import threading
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt
import serial

from protocol import FrameStreamDecoder, encode_frame, parse_frame, payload_to_dict


@dataclass
class SerialNode:
    name: str
    port: str
    baud: int
    ser: serial.Serial | None = None
    last_seq: int = -1
    tx_seq: int = 1


class PortusBridge:
    def __init__(self, mqtt_host: str, mqtt_port: int, nodes: list[SerialNode]):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.nodes = {n.name: n for n in nodes}
        self.running = True
        self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqttc.on_connect = self.on_connect
        self.mqttc.on_message = self.on_message

    def open_serial(self) -> None:
        for node in self.nodes.values():
            # En Linux, exclusive=True impide que miniterm, otro bridge o un
            # diagnostico consuman simultaneamente partes del mismo frame.
            serial_options = {"timeout": 0.2}
            if os.name == "posix":
                serial_options["exclusive"] = True
            node.ser = serial.Serial(node.port, node.baud, **serial_options)
            print(f"[SERIAL] {node.name} -> {node.port} @ {node.baud}")

    def start(self) -> None:
        self.open_serial()
        self.mqttc.connect(self.mqtt_host, self.mqtt_port, keepalive=30)
        threading.Thread(target=self.mqttc.loop_forever, daemon=True).start()

        for node in self.nodes.values():
            threading.Thread(target=self.read_loop, args=(node,), daemon=True).start()

        threading.Thread(target=self.ping_loop, daemon=True).start()

        print("[BRIDGE] Running...")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
        finally:
            for node in self.nodes.values():
                if node.ser:
                    node.ser.close()

    def ping_loop(self) -> None:
        # Extension del protocolo
        while self.running:
            for node in self.nodes.values():
                if not node.ser:
                    continue
                try:
                    frame = encode_frame("RPI", node.tx_seq, "PIN", "estado", "")
                    node.tx_seq += 1
                    node.ser.write((frame + "\n").encode("utf-8"))
                except Exception as exc:
                    print(f"[PING] {node.name} error: {exc}")
            time.sleep(3)

    def on_connect(self, client, userdata, flags, rc, properties=None):
        print(f"[MQTT] Connected rc={rc}")
        client.subscribe("portus/cmd/solicitud")

    def on_message(self, client, userdata, msg):
        if msg.topic != "portus/cmd/solicitud":
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            target = payload.get("target")
            cmd_name = payload.get("name", "UNKNOWN")
            params = payload.get("params", {})
            if target not in self.nodes:
                print(f"[CMD] target invalido: {target}")
                return
            node = self.nodes[target]
            payload_s = f"name={cmd_name};target={target}"
            for k, v in params.items():
                payload_s += f";{k}={v}"
            frame = encode_frame("RPI", node.tx_seq, "CMD", "cmd", payload_s)
            node.tx_seq += 1
            if node.ser:
                node.ser.write((frame + "\n").encode("utf-8"))
                print(f"[CMD->SERIAL] {target} {frame}")
        except Exception as exc:
            print(f"[CMD] error: {exc}")

    def read_loop(self, node: SerialNode):
        assert node.ser is not None
        decoder = FrameStreamDecoder()
        while self.running:
            try:
                chunk = node.ser.read(node.ser.in_waiting or 1)
                if not chunk:
                    continue
                for raw_frame in decoder.feed(chunk):
                    self.process_frame(node, raw_frame)
            except Exception as exc:
                print(f"[SERIAL] {node.name} error: {exc}")
                time.sleep(0.2)

    def process_frame(self, node: SerialNode, raw_frame: str) -> None:
        frame = parse_frame(raw_frame)
        if frame.seq <= node.last_seq:
            print(f"[WARN] {node.name} seq repetido/atrasado: {frame.seq}")
        node.last_seq = frame.seq
        data = payload_to_dict(frame.payload)
        message = {
            "id": f"{frame.src}-{frame.seq}",
            "ts": int(time.time()),
            "origin": frame.src,
            "type": frame.kind,
            "seq": frame.seq,
            "data": data,
        }

        if frame.kind in ("EVT", "HBT"):
            topic = f"portus/evt/{frame.topic}"
            self.mqttc.publish(topic, json.dumps(message))
            if frame.kind == "HBT":
                self.mqttc.publish("portus/evt/estado", json.dumps(message))
            print(f"[SERIAL->MQTT] {topic} {message}")
        elif frame.kind in ("ACK", "REJ"):
            self.mqttc.publish("portus/cmd/respuesta", json.dumps(message))
            print(f"[SERIAL->MQTT] portus/cmd/respuesta {message}")
        else:
            print(f"[WARN] kind no reconocido: {frame.kind}")


def main():
    parser = argparse.ArgumentParser(description="PORTUS serial bridge")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--uno-entrada", required=True)
    parser.add_argument("--uno-salida", required=True)
    parser.add_argument("--mega-grua", required=True)
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    nodes = [
        SerialNode(name="UNO_ENTRADA", port=args.uno_entrada, baud=args.baud),
        SerialNode(name="UNO_SALIDA", port=args.uno_salida, baud=args.baud),
        SerialNode(name="MEGA_GRUA", port=args.mega_grua, baud=args.baud),
    ]
    PortusBridge(args.mqtt_host, args.mqtt_port, nodes).start()


if __name__ == "__main__":
    main()
