#!/usr/bin/env bash
set -euo pipefail

INTEGRADO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$INTEGRADO_DIR/.runtime/pids"

if [[ ! -d "$PID_DIR" ]]; then
  echo "[PORTUS] No hay procesos registrados."
  exit 0
fi

stop_proc() {
  local pidfile="$1"
  local name
  name="$(basename "$pidfile" .pid)"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "[STOP] $name (pid $pid)"
      kill "$pid" || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" || true
      fi
    fi
    rm -f "$pidfile"
  fi
}

for f in "$PID_DIR"/*.pid; do
  [[ -e "$f" ]] || continue
  stop_proc "$f"
done

echo "[PORTUS] Servicios detenidos."
