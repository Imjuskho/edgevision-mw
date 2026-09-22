#!/usr/bin/env bash
# Regenerate the self-signed dev TLS certificate for the Vite dev server.
#
# The dev server serves HTTPS (so mobile browsers expose navigator.mediaDevices
# and camera APIs work over the LAN). The cert SAN must include the LAN IP the
# devices connect to. Run this again whenever the machine's IP changes.
#
# Usage: ./scripts/gen-cert.sh [LAN_IP]
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

LAN_IP="${1:-}"
if [ -z "$LAN_IP" ]; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [ -z "$LAN_IP" ]; then
  LAN_IP="127.0.0.1"
  echo "Could not detect the LAN IP via en0; falling back to 127.0.0.1." >&2
  echo "Pass it explicitly: ./scripts/gen-cert.sh 192.168.x.x" >&2
fi

mkdir -p "$DIR/.cert"

openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout "$DIR/.cert/key.pem" \
  -out "$DIR/.cert/cert.pem" \
  -subj "/CN=EdgeVision Studio Dev" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:${LAN_IP}"

echo "TLS certificate regenerated with SAN IP:${LAN_IP}"
echo "Restart the dev server, then open https://${LAN_IP}:3000 and accept the cert."
