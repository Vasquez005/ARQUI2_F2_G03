#!/usr/bin/env bash
# Baja el YOLO de placas preentrenado (el .pt no viene en ejemplo-placas).
# Por defecto v1n (cabe en la Raspberry). Para el mismo peso del repo:
#   PORTUS_MODELO=v1x bash descargar_modelo.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DIR/models"
VER="${PORTUS_MODELO:-v1n}"
ARCH="license-plate-finetune-${VER}.pt"
DEST="$DIR/models/$ARCH"
URL="https://huggingface.co/morsetechlab/yolov11-license-plate-detection/resolve/main/${ARCH}"
if [[ -f "$DEST" ]]; then
  echo "[OK] ya esta $DEST"
  exit 0
fi
echo "[DESCARGANDO] $URL"
curl -L --fail -o "$DEST" "$URL"
echo "[OK] $DEST"
