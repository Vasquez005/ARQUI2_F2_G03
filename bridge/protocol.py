from dataclasses import dataclass


@dataclass
class Frame:
    src: str
    seq: int
    kind: str
    topic: str
    payload: str
    chk: str


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
