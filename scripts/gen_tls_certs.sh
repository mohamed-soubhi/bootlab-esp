#!/usr/bin/env bash
# gen_tls_certs.sh — generate lab TLS Root CA and ESP32 server certificates (BL-025).
# Refuses to overwrite existing certificates/keys.
#   CA cert/key       : keys/ca.pem, keys/ca.key
#   ESP32 server cert/key: keys/server_cert.pem, keys/server_key.pem
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEYS="$REPO/keys"
mkdir -p "$KEYS"
chmod 700 "$KEYS"

CA_KEY="$KEYS/ca.key"
CA_CERT="$KEYS/ca.pem"
SERVER_KEY="$KEYS/server_key.pem"
SERVER_CERT="$KEYS/server_cert.pem"

# 1. Generate Root CA if missing
if [ -f "$CA_CERT" ] && [ -f "$CA_KEY" ]; then
    echo "SKIP: CA certificate and key already exist ($CA_CERT)"
else
    echo "Generating Lab Root CA..."
    openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 3650 \
        -keyout "$CA_KEY" -out "$CA_CERT" \
        -subj "/C=US/ST=Lab/L=Lab/O=Bootlab/OU=Security/CN=Bootlab Lab Root CA"
    chmod 600 "$CA_KEY"
    chmod 644 "$CA_CERT"
    echo "  -> $CA_KEY, $CA_CERT"
fi

# 2. Generate ESP32 Server Certificate if missing
if [ -f "$SERVER_CERT" ] && [ -f "$SERVER_KEY" ]; then
    echo "SKIP: ESP32 server certificate and key already exist ($SERVER_CERT)"
else
    echo "Generating ESP32 server key and certificate (signed by Lab Root CA)..."
    SERVER_CSR="$KEYS/server.csr"
    EXT_FILE="$KEYS/server_ext.cnf"

    cat <<EOF > "$EXT_FILE"
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = esp-idf-lab.local
DNS.2 = localhost
IP.1 = 192.168.1.152
IP.2 = 127.0.0.1
EOF

    openssl req -new -nodes -newkey rsa:2048 -sha256 \
        -keyout "$SERVER_KEY" -out "$SERVER_CSR" \
        -subj "/C=US/ST=Lab/L=Lab/O=Bootlab/OU=Device/CN=esp-idf-lab.local"

    openssl x509 -req -in "$SERVER_CSR" -CA "$CA_CERT" -CAkey "$CA_KEY" \
        -CAcreateserial -out "$SERVER_CERT" -days 1825 -sha256 \
        -extfile "$EXT_FILE"

    rm -f "$SERVER_CSR" "$EXT_FILE" "$KEYS/ca.srl"
    chmod 600 "$SERVER_KEY"
    chmod 644 "$SERVER_CERT"
    echo "  -> $SERVER_KEY, $SERVER_CERT"
fi

# 3. Verify files
echo "Verifying generated certificates..."
openssl verify -CAfile "$CA_CERT" "$SERVER_CERT"

# 4. Ensure keys/ and *.pem remain ignored by git
if git -C "$REPO" status --porcelain keys/ 2>/dev/null | grep -q .; then
    echo "WARN: keys/ appears in git status (should be ignored)"; exit 1
fi
echo "git status: no key or cert files tracked (OK)"
