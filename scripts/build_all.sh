#!/usr/bin/env bash
# build_all.sh — build all variants using labflash build orchestration (BL-045).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PYTHONPATH=host "$REPO/.venv/bin/python" -m labflash build idf "$@"
