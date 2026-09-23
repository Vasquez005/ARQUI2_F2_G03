#!/usr/bin/env bash
set -euo pipefail

INTEGRADO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$INTEGRADO_DIR/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"

check_proc() {
  local name="$1"
  local pidfile="$PID_DIR/$name.pid"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "[$name] RUNNING (pid $pid)"
      return
    fi
    echo "[$name] STALE PID ($pid, no activo)"
    return
  fi
  echo "[$name] NOT STARTED"
}

check_http() {
  local name="$1"
  local url="$2"
  if command -v curl >/dev/null 2>&1; then
    local code
    code="$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)"
    if [[ "$code" == "200" ]]; then
      echo "[$name] HTTP 200 $url"
    else
      echo "[$name] HTTP $code $url"
    fi
  else
    echo "[$name] curl no disponible"
  fi
}

echo "=== PORTUS STATUS ==="
echo "Runtime: $RUNTIME_DIR"
echo

check_proc "mosquitto"
check_proc "backend_b"
check_proc "bridge_ab"
check_proc "web_c"
check_proc "bot_d"

echo
echo "=== ENDPOINTS ==="
check_http "web_c" "http://localhost:8000/"
check_http "backend_b_health" "http://localhost:8100/health"

echo
echo "=== LOG TAIL (20) ==="
for name in backend_b bridge_ab web_c bot_d; do
  logfile="$LOG_DIR/$name.log"
  echo
  echo "--- $name ---"
  if [[ -f "$logfile" ]]; then
    tail -n 20 "$logfile" || true
  else
    echo "(sin log)"
  fi
done
