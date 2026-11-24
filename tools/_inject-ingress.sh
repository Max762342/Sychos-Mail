#!/usr/bin/env bash
# Einmalig: Ingress inject.sychos.de -> Mail-Injektor (127.0.0.1:8099)
set -euo pipefail
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }
CFG=/etc/cloudflared/config.yml
HOST=inject.sychos.de
SERVICE=http://127.0.0.1:8099

SUDO cp "$CFG" "/etc/cloudflared/config.yml.bak-$(date +%Y%m%d-%H%M%S)"

python3 - "$CFG" "$HOST" "$SERVICE" <<'PY'
import sys
path, host, service = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path).read()
if f"hostname: {host}" in text:
    print("Eintrag existiert bereits")
    raise SystemExit(0)
entry = f"  - hostname: {host}\n    service: {service}\n"
marker = "  - service: http_status:404"
text = text.replace(marker, entry + marker, 1) if marker in text else text.rstrip("\n") + "\n" + entry
open("/tmp/cloudflared-new.yml", "w").write(text)
print("eingefuegt:", host, "->", service)
PY

if [ -f /tmp/cloudflared-new.yml ]; then
  SUDO cp /tmp/cloudflared-new.yml "$CFG"
  rm -f /tmp/cloudflared-new.yml
fi

SUDO systemctl restart cloudflared
sleep 6
SUDO systemctl is-active cloudflared
SUDO grep -E 'hostname:' "$CFG"
curl -s -o - -w '\n' https://inject.sychos.de/healthz || true
