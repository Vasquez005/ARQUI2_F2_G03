"""Catalogos fijos de PORTUS Fase 2 (Fase_2_PORTUS.md secciones 7, 8.2, 4.6).

Todo lo que el PDF define como "exactamente los siguientes" vive aqui como
constante, para que no queden numeros/strings mágicos repartidos en el codigo.
"""

import os

ROLES = ("TERMINAL", "NAVIERA", "AGENTE", "AUTORIDAD")  # TRANSPORTISTA vive en el bot (D)

# ── Estados del turno (sec. 7) y sus transiciones permitidas ──
PROGRAMADO = "Programado"
EN_GARITA = "EnGarita"
EN_PESAJE_ENTRADA = "EnPesajeEntrada"
EN_RUTA = "EnRuta"
EN_TRANSFERENCIA = "EnTransferencia"
EN_PESAJE_SALIDA = "EnPesajeSalida"
EN_SALIDA = "EnSalida"
RETENIDO = "Retenido"
CERRADO = "Cerrado"
ANULADO = "Anulado"

ESTADOS_TURNO = (
    PROGRAMADO, EN_GARITA, EN_PESAJE_ENTRADA, EN_RUTA, EN_TRANSFERENCIA,
    EN_PESAJE_SALIDA, EN_SALIDA, RETENIDO, CERRADO, ANULADO,
)
ESTADOS_FINALES = (CERRADO, ANULADO)

# Transiciones "hacia adelante" explicitas
TRANSICIONES = {
    PROGRAMADO: (EN_GARITA, ANULADO),
    EN_GARITA: (EN_PESAJE_ENTRADA, RETENIDO, ANULADO),
    EN_PESAJE_ENTRADA: (EN_RUTA, RETENIDO, ANULADO),
    # RETENIDO desde cualquier estado activo: RT05 / RT06 se ordenan en cualquier momento (sec. 8.2)
    EN_RUTA: (EN_TRANSFERENCIA, RETENIDO, ANULADO),
    EN_TRANSFERENCIA: (EN_PESAJE_SALIDA, EN_TRANSFERENCIA, RETENIDO, ANULADO),  # aborto puede volver al mismo estado
    EN_PESAJE_SALIDA: (EN_SALIDA, RETENIDO, ANULADO),
    EN_SALIDA: (CERRADO, RETENIDO),
    RETENIDO: (EN_RUTA, EN_SALIDA, ANULADO),  # a donde regresa depende de la resolucion
}

# ── Causas de retencion (sec. 8.2) y rol facultado para resolverlas ──
RT01 = "RT01"  # Discrepancia de peso al ingreso
RT02 = "RT02"  # Discrepancia de peso a la salida
RT03 = "RT03"  # Canal rojo de selectivo
RT04 = "RT04"  # Llegada fuera de la ventana asignada
RT05 = "RT05"  # Retencion documental
RT06 = "RT06"  # Retencion manual operativa

CAUSAS_RETENCION = (RT01, RT02, RT03, RT04, RT05, RT06)

ROL_FACULTADO_POR_CAUSA = {
    RT01: "TERMINAL",
    RT02: "TERMINAL",
    RT03: "AUTORIDAD",
    RT04: "TERMINAL",
    RT05: "AUTORIDAD",
    RT06: "TERMINAL",
}

RESOLUCIONES = ("aclarar", "corregir", "rechazar")

# ── Catalogo minimo de alarmas (sec. 4.6) ──
CATALOGO_ALARMAS = {
    "AL01": ("critica", "Enlace con el controlador perdido"),
    "AL02": ("critica", "Paro de emergencia accionado"),
    "AL03": ("critica", "Perdida de referencia de posicion de la grua"),
    "AL04": ("critica", "Perdida de carga durante el traslado"),
    "AL05": ("alta", "Agarre de contenedor no confirmado"),
    "AL06": ("alta", "Trabajo de grua abortado"),
    "AL07": ("alta", "Inconsistencia entre altura fisica e inventario"),
    "AL08": ("alta", "Movimiento del vehiculo durante la transferencia"),
    "AL09": ("media", "Pesaje fuera de tolerancia"),
    "AL10": ("media", "Vehiculo incorrecto en la salida"),
    "AL11": ("media", "Parqueo de retencion lleno"),
    "AL12": ("media", "Retencion que supera treinta minutos"),
    "AL13": ("baja", "Permanencia de contenedor superior a dos horas"),
    "AL14": ("baja", "Comando remoto rechazado por el controlador"),
}

SEVERIDADES_AUTO_RECONOCIBLES = ("media", "baja")  # boton "Reconocer todas" (sec. 4.6)

# Umbrales de las alarmas por tiempo. Se pueden bajar por variable de entorno
# para la demostracion (no hay que esperar 2 h frente al catedratico).
MINUTOS_AL12_RETENCION = int(os.getenv("PORTUS_MIN_AL12", "30"))
MINUTOS_AL13_PATIO = int(os.getenv("PORTUS_MIN_AL13", "120"))
SEGUNDOS_REVISION_ALARMAS = 30

DISPOSITIVOS = ("UNO_ENTRADA", "UNO_SALIDA", "MEGA_GRUA")

# ── Citas (sec. 9) y vinculacion del bot (sec. 6.1) ──
MINUTOS_FRANJA = 15
CITAS_POR_FRANJA = 2
TOLERANCIA_VENTANA_MIN = 5
MINUTOS_EXPIRA_CODIGO = 60
ZONA_HORARIA = "America/Guatemala"  # la BD guarda UTC; a las personas se les muestra hora local
UMBRAL_ENLACE_PERDIDO_S = 15  # ~3 latidos de 5s (sec. 10.2)
