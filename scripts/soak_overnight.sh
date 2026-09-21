#!/usr/bin/env bash
# BL-060: launch the live IDF soak from WSL against the Windows-native python (R14: never open the port under WSL).
# Syncs sources to the Windows scratch mirror, copies the server key ONLY for the run (removed on exit, even on Ctrl-C),
# runs tests_hil.soak, and copies the result back into scripts/evidence/.
#   scripts/soak_overnight.sh [cycles=100] [--resume]
# Needs the owner's go-ahead for the window (the board is flashed ~cycles times). Do not run other HIL jobs meanwhile.
set -euo pipefail
CYCLES="${1:-100}"; RESUME="${2:-}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W=/mnt/c/MSA/embedded-OS/bootlab-esp
WIN='C:\MSA\embedded-OS\bootlab-esp'
STAMP="${SOAK_STAMP:-$(date +%F)}"
OUT_REL="scripts/evidence/bl060_soak_${STAMP}"
PORT="${SOAK_PORT:-COM14}"; IP="${SOAK_BOARD_IP:-192.168.1.152}"

rsync -a --delete "$REPO/tests_hil/" "$W/tests_hil/" --exclude __pycache__ --exclude 'reports*'
rsync -a --delete "$REPO/host/" "$W/host/" --exclude __pycache__
cp "$REPO/keys/server_key.pem" "$W/keys/server_key.pem"
cleanup() {
  rm -f "$W/keys/server_key.pem"
  mkdir -p "$REPO/$OUT_REL"
  cp -r "$W/soak_out/." "$REPO/$OUT_REL/" 2>/dev/null || true
  echo "server key removed; results copied to $OUT_REL"
}
trap cleanup EXIT

powershell.exe -Command "cd $WIN; \$env:PYTHONPATH='.venv_win_ble\Lib\site-packages;host;.'; python -u -m tests_hil.soak --port $PORT --board-ip $IP --keys-dir keys --env-file credentials.env --cycles $CYCLES --out soak_out $RESUME" < /dev/null
