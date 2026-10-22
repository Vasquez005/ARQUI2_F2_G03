"""Verificacion de placa en la garita (Fase 3, sec. 6 y 7) conectada a la base de datos.

Activacion: PORTUS_VERIFICACION_PLACA=1. Sin esa variable, la garita sigue con el
flujo de la fase 2 (tarjeta + documentos), para no romper la maqueta.
"""

import os
from datetime import datetime
from typing import Optional

import camara_garita
import verificacion
from models import LecturaPlaca, PlacaRestringida, Vehiculo

MOTIVO_MINIMO = 10  # sec. 6.2 y 7: motivo de al menos diez caracteres


def activa() -> bool:
    return os.getenv("PORTUS_VERIFICACION_PLACA", "0") == "1"


def umbral_ocr() -> float:
    """ConfianzaMinimaOCR, en porcentaje. Por defecto 60 (sec. 8.7)."""
    return float(os.getenv("PORTUS_CONFIANZA_MINIMA_OCR", "60"))


def intentos_ocr() -> int:
    """IntentosOCR (sec. 8.7): de 1 a 5, por defecto 3."""
    valor = int(os.getenv("PORTUS_INTENTOS_OCR", "3"))
    camara_garita.validar_intentos(valor)
    return valor


def segundos_espera_verificacion() -> int:
    """SegundosEsperaVerificacion (sec. 8.7, destino controlador): de 5 a 30, por defecto 10."""
    valor = int(os.getenv("PORTUS_SEGUNDOS_ESPERA_VERIFICACION", "10"))
    if not 5 <= valor <= 30:
        raise ValueError("SegundosEsperaVerificacion fuera de rango (5 a 30)")
    return valor


def validar_motivo(motivo: str) -> str:
    motivo = (motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise ValueError(f"el motivo debe tener al menos {MOTIVO_MINIMO} caracteres")
    return motivo


def placas_catalogo(db) -> list[str]:
    return [v.placa for v in db.query(Vehiculo).all() if v.placa]


def placas_restringidas(db) -> list[str]:
    return [p.placa for p in db.query(PlacaRestringida).filter(PlacaRestringida.activa.is_(True)).all()]


def decidir_entrada(db, uid: str, lectura: Optional[dict]) -> verificacion.Decision:
    vehiculo = db.get(Vehiculo, uid)
    return camara_garita.evaluar_garita(
        etiqueta_registrada=vehiculo is not None,
        placa_registrada=(vehiculo.placa if vehiculo else "") or "",
        restringidas=placas_restringidas(db),
        catalogo=placas_catalogo(db),
        umbral_ocr=umbral_ocr(),
        lectura=lectura,
    )


def registrar_lectura(db, uid: str, lectura: Optional[dict], resultado: str,
                      causa: Optional[str] = None, turno_id: Optional[int] = None,
                      pendiente: bool = False, decidido_por: str = "servidor",
                      motivo: Optional[str] = None) -> LecturaPlaca:
    fila = LecturaPlaca(
        vehiculo_uid=uid,
        placa_leida=(lectura or {}).get("texto", ""),
        confianza=float((lectura or {}).get("confianza", 0.0)),
        resultado=resultado,
        causa=causa,
        foto=(lectura or {}).get("foto"),
        turno_id=turno_id,
        pendiente=pendiente,
        decidido_por=decidido_por,
        motivo_decision=motivo,
    )
    db.add(fila)
    db.flush()
    return fila


def verificaciones_pendientes(db) -> list[LecturaPlaca]:
    return db.query(LecturaPlaca).filter(LecturaPlaca.pendiente.is_(True)).order_by(LecturaPlaca.ts).all()


def retencion_pendiente_de(db, turno_id: int) -> Optional[LecturaPlaca]:
    """La retencion RT07/RT08 se crea despues del pesaje de entrada (sec. 6.2)."""
    return (
        db.query(LecturaPlaca)
        .filter(LecturaPlaca.turno_id == turno_id, LecturaPlaca.resultado == "retencion_pendiente")
        .first()
    )


def restringir(db, placa: str, motivo: str, usuario: str) -> PlacaRestringida:
    limpia = "".join(c for c in placa.upper() if c.isalnum())
    if not limpia:
        raise ValueError("placa vacia")
    validar_motivo(motivo)
    activa_existente = (
        db.query(PlacaRestringida).filter(PlacaRestringida.placa == limpia, PlacaRestringida.activa.is_(True)).first()
    )
    if activa_existente is not None:
        raise ValueError("la placa ya esta restringida")
    fila = PlacaRestringida(placa=limpia, motivo=motivo, usuario=usuario)
    db.add(fila)
    db.flush()
    return fila


def liberar(db, restriccion_id: int, motivo: str, usuario: str) -> PlacaRestringida:
    validar_motivo(motivo)
    fila = db.get(PlacaRestringida, restriccion_id)
    if fila is None or not fila.activa:
        raise ValueError("restriccion no encontrada o ya liberada")
    fila.activa = False
    fila.liberada_por = usuario
    fila.liberada_at = datetime.utcnow()
    fila.motivo_liberacion = motivo
    db.flush()
    return fila
