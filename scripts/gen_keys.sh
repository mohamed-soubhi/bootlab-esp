#!/usr/bin/env bash
# gen_keys.sh — generate lab signing keys (BL-006).
# Refuses to overwrite existing keys.
#   Zephyr : ECDSA-P256  keys/zephyr_p256.pem       (imgtool keygen)
#   IDF    : RSA-3072 SBV2 keys/idf_sbv2.pem        (espsecure.py)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEYS="$REPO/keys"
mkdir -p "$KEYS"
chmod 700 "$KEYS"

VENV="$REPO/.venv/bin"
. "$VENV/activate" 2>/dev/null || true

gen_ok=1

# --- Zephyr ECDSA-P256 ---
if [ -f "$KEYS/zephyr_p256.pem" ]; then
    echo "SKIP: $KEYS/zephyr_p256.pem already exists"
else
    echo "Generating Zephyr key (ECDSA-P256)..."
    imgtool keygen -k "$KEYS/zephyr_p256.pem" -t ecdsa-p256 2>&1
    chmod 600 "$KEYS/zephyr_p256.pem"
    echo "  -> $KEYS/zephyr_p256.pem"
fi

# --- IDF Secure Boot v2 (RSA-3072) ---
if [ -f "$KEYS/idf_sbv2.pem" ]; then
    echo "SKIP: $KEYS/idf_sbv2.pem already exists"
else
    echo "Generating IDF key (RSA-3072, SBV2)..."
    espsecure.py generate_signing_key --version 2 --scheme rsa3072 "$KEYS/idf_sbv2.pem" 2>&1
    chmod 600 "$KEYS/idf_sbv2.pem"
    echo "  -> $KEYS/idf_sbv2.pem"
fi

# Verify 2 keys present
n=0
[ -f "$KEYS/zephyr_p256.pem" ] && n=$((n+1))
[ -f "$KEYS/idf_sbv2.pem" ] && n=$((n+1))
echo "keys present: $n/2"
[ "$n" -eq 2 ] || { echo "key generation incomplete"; exit 1; }

# git must show no key files (keys/ ignored)
if git -C "$REPO" status --porcelain keys/ 2>/dev/null | grep -q .; then
    echo "WARN: keys/ appears in git status (should be ignored)"; exit 1
fi
echo "git status: no key files tracked (OK)"
