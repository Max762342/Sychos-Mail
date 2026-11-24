#!/usr/bin/env bash
# Ingress-Eintrag am lokalen Tunnel ergaenzen (Backup + Restart + Test).
#   bash tools/add-ingress.sh <hostname> <service-url>
#   z. B. bash tools/add-ingress.sh admin.sychos.de http://127.0.0.1:8090
set -euo pipefail
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }
CFG=/etc/cloudflared/config.yml
HOST="${1:?hostname fehlt}"
SERVICE="${2:?service-url fehlt}"

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
echo "--- Test ---"
curl -sS -o /dev/null -w "https://$HOST -> HTTP %{http_code}\n" "https://$HOST/login" || true
