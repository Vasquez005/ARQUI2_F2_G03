#!/usr/bin/env bash
set -euo pipefail

# PORTUS Fase 2 - Arranque integrado A+B+C+D
#
# Corregido (ver Observaciones_Backend_PersonaB.md punto 4): antes este script
# calculaba ROOT_DIR subiendo un nivel de mas y buscaba una carpeta
# "portus_fase2_integrado/" que no existe. La estructura real es plana:
# backend/, bridge/, firmware/, docs/ directo en la raiz del proyecto.
#
# Uso:
#   UNO_ENTRADA_PORT=/dev/ttyACM0 \
#   UNO_SALIDA_PORT=/dev/ttyACM1 \
#   MEGA_GRUA_PORT=/dev/ttyACM2 \
#   bash run_all.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

MQTT_HOST="${PORTUS_MQTT_HOST:-localhost}"
MQTT_PORT="${PORTUS_MQTT_PORT:-1883}"
START_LOCAL_MOSQUITTO="${PORTUS_START_LOCAL_MOSQUITTO:-auto}"  # auto|yes|no

UNO_ENTRADA_PORT="${UNO_ENTRADA_PORT:-}"
UNO_SALIDA_PORT="${UNO_SALIDA_PORT:-}"
MEGA_GRUA_PORT="${MEGA_GRUA_PORT:-}"
ARDUINO_BAUD="${ARDUINO_BAUD:-9600}"  # los 3 firmwares usan Serial.begin(9600)

BOT_TOKEN="${PORTUS_BOT_TOKEN:-}"
# B solo escucha en localhost: la web (C) es la unica puerta de entrada HTTP y
# es la que aplica los permisos por rol antes de llamar a B.
BACKEND_BIND="${PORTUS_BACKEND_BIND:-127.0.0.1}"
SECRET_KEY="${PORTUS_SECRET_KEY:-portus_cambiar_clave}"

echo "[PORTUS] ROOT_DIR=$ROOT_DIR"
echo "[PORTUS] MQTT=$MQTT_HOST:$MQTT_PORT"

start_proc() {
  local name="$1"
  local cmd="$2"
  local logfile="$LOG_DIR/$name.log"
  local pidfile="$PID_DIR/$name.pid"

  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[SKIP] $name ya esta corriendo (pid $(cat "$pidfile"))."
    return
  fi

  echo "[START] $name"
  nohup bash -lc "$cmd" >"$logfile" 2>&1 &
  echo $! >"$pidfile"
  sleep 1
  if kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[OK] $name (pid $(cat "$pidfile"))"
  else
    echo "[ERROR] $name no inicio. Revisa: $logfile"
  fi
}

# 0) Mosquitto local (ver docs/mosquitto.md). Si MQTT_HOST no es localhost, o
# si ya hay algo escuchando en el puerto, no se toca.
if [[ "$START_LOCAL_MOSQUITTO" != "no" && "$MQTT_HOST" == "localhost" ]]; then
  if command -v mosquitto >/dev/null 2>&1 && [[ -f "$ROOT_DIR/mosquitto/mosquitto.conf" ]]; then
    if ! (exec 3<>"/dev/tcp/127.0.0.1/$MQTT_PORT") 2>/dev/null; then
      echo "[START] mosquitto (local, dev)"
      nohup mosquitto -c "$ROOT_DIR/mosquitto/mosquitto.conf" >"$LOG_DIR/mosquitto.log" 2>&1 &
      echo $! >"$PID_DIR/mosquitto.pid"
      sleep 1
    else
      exec 3>&- 2>/dev/null || true
      echo "[SKIP] mosquitto ya esta escuchando en $MQTT_PORT"
    fi
  fi
fi

# 1) Backend B
start_proc "backend_b" \
  "cd '$ROOT_DIR/backend' && \
   python3 -m venv .venv >/dev/null 2>&1 || true && \
   .venv/bin/python3 -m pip install -q -r requirements.txt && \
   .venv/bin/python3 seed.py && \
   PORTUS_MQTT_HOST='$MQTT_HOST' PORTUS_MQTT_PORT='$MQTT_PORT' \
   .venv/bin/python3 -m uvicorn app:app --host '$BACKEND_BIND' --port 8100"

# 2) Bridge A+B (solo si hay puertos definidos)
if [[ -n "$UNO_ENTRADA_PORT" && -n "$UNO_SALIDA_PORT" && -n "$MEGA_GRUA_PORT" ]]; then
  start_proc "bridge_ab" \
    "cd '$ROOT_DIR/bridge' && \
     python3 -m venv .venv >/dev/null 2>&1 || true && \
     .venv/bin/python3 -m pip install -q -r requirements.txt && \
     .venv/bin/python3 -u bridge.py \
       --mqtt-host '$MQTT_HOST' \
       --mqtt-port '$MQTT_PORT' \
       --uno-entrada '$UNO_ENTRADA_PORT' \
       --uno-salida '$UNO_SALIDA_PORT' \
       --mega-grua '$MEGA_GRUA_PORT' \
       --baud '$ARDUINO_BAUD'"
else
  echo "[WARN] Bridge serial no iniciado (faltan UNO_ENTRADA_PORT/UNO_SALIDA_PORT/MEGA_GRUA_PORT)."
fi

# 3) Web C
start_proc "web_c" \
  "cd '$ROOT_DIR/web_c' && \
   python3 -m venv .venv >/dev/null 2>&1 || true && \
   .venv/bin/python3 -m pip install -q -r requirements.txt && \
   PORTUS_MQTT_HOST='$MQTT_HOST' PORTUS_MQTT_PORT='$MQTT_PORT' \
   PORTUS_BACKEND_URL='http://127.0.0.1:8100' PORTUS_SECRET_KEY='$SECRET_KEY' \
   .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

# 4) Bot D (requiere token; sin token su modo CLI es interactivo y no sirve en segundo plano)
if [[ -n "$BOT_TOKEN" ]]; then
  start_proc "bot_d" \
    "cd '$ROOT_DIR/bot_d' && \
     python3 -m venv .venv >/dev/null 2>&1 || true && \
     .venv/bin/python3 -m pip install -q -r requirements.txt && \
     PORTUS_MQTT_HOST='$MQTT_HOST' PORTUS_MQTT_PORT='$MQTT_PORT' \
     PORTUS_BOT_TOKEN='$BOT_TOKEN' .venv/bin/python3 -u app/main.py"
else
  echo "[WARN] Bot D no iniciado (falta PORTUS_BOT_TOKEN). Para probarlo sin Telegram: cd bot_d && python3 app/main.py"
fi

cat <<EOF

[PORTUS] Arranque completado.
- Web C:            http://<ip-de-la-pi>:8000
- Backend B health: http://localhost:8100/health (solo desde la propia Pi)

Logs:
  $LOG_DIR

Para ver el estado:
  bash "$ROOT_DIR/status_all.sh"

Para detener todo:
  bash "$ROOT_DIR/stop_all.sh"
EOF
