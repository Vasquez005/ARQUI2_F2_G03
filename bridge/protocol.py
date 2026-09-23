from dataclasses import dataclass


FRAME_PREFIX = b"<PORTUS|"
MAX_SERIAL_BUFFER = 2048


@dataclass
class Frame:
    src: str
    seq: int
    kind: str
    topic: str
    payload: str
    chk: str


class FrameStreamDecoder:
    """Extrae frames PORTUS completos de un flujo serial arbitrariamente cortado.

    Los Arduino tambien imprimen mensajes de diagnostico. Esos bytes se descartan
    hasta encontrar ``<PORTUS|``. El frame puede llegar repartido entre varias
    lecturas sin perderse.
    """

    def __init__(self, max_buffer: int = MAX_SERIAL_BUFFER):
        self._buffer = bytearray()
        self._max_buffer = max_buffer

    def feed(self, chunk: bytes) -> list[str]:
        if chunk:
            self._buffer.extend(chunk)

        frames: list[str] = []
        while True:
            start = self._buffer.find(FRAME_PREFIX)
            if start < 0:
                # Conserva solo los bytes que aun podrian ser el inicio parcial
                # del prefijo; evita crecimiento por los logs libres del firmware.
                keep = min(len(self._buffer), len(FRAME_PREFIX) - 1)
                if keep:
                    del self._buffer[:-keep]
                else:
                    self._buffer.clear()
                break

            if start:
                del self._buffer[:start]

            end = self._buffer.find(b">", len(FRAME_PREFIX))
            if end < 0:
                if len(self._buffer) > self._max_buffer:
                    del self._buffer[:-len(FRAME_PREFIX)]
                break

            raw = bytes(self._buffer[:end + 1])
            del self._buffer[:end + 1]
            frames.append(raw.decode("utf-8", errors="replace"))

        return frames


def checksum(content: str) -> str:
    total = sum(ord(c) for c in content) % 256
    return f"{total:02X}"


def encode_frame(src: str, seq: int, kind: str, topic: str, payload: str) -> str:
    body = f"PORTUS|{src}|{seq}|{kind}|{topic}|{payload}"
    chk = checksum(body)
    return f"<{body}|{chk}>"


def parse_frame(raw: str) -> Frame:
    text = raw.strip()
    if not text.startswith("<") or not text.endswith(">"):
        raise ValueError("delimitador invalido")
    body = text[1:-1]
    parts = body.split("|")
    if len(parts) != 7:
        raise ValueError("cantidad de campos invalida")
    if parts[0] != "PORTUS":
        raise ValueError("cabecera invalida")
    src, seq_s, kind, topic, payload, chk = parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
    base = f"PORTUS|{src}|{seq_s}|{kind}|{topic}|{payload}"
    expected = checksum(base)
    if chk.upper() != expected:
        raise ValueError(f"checksum invalido ({chk} != {expected})")
    return Frame(src=src, seq=int(seq_s), kind=kind, topic=topic, payload=payload, chk=chk.upper())


def payload_to_dict(payload: str) -> dict:
    if not payload:
        return {}
    out = {}
    for token in payload.split(";"):
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out
