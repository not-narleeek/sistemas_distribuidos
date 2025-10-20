#!/bin/bash
set -euo pipefail

echo "[build] Construyendo imágenes Docker del sistema distribuido..."
docker compose build
