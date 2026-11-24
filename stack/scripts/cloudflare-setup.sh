#!/usr/bin/env bash
# Cloudflare Tunnel fuer sychos.de einrichten (interaktiv, auf dem Host).
#
#   cd /opt/sychos-mail/stack && bash scripts/cloudflare-setup.sh
#
# Voraussetzungen:
#   1. Domain sychos.de liegt in einem Cloudflare-Account (Nameserver bei IONOS
#      auf die Cloudflare-NS umgestellt).
#   2. Ein Browser fuer `cloudflared tunnel login` ist erreichbar — der Befehl
#      gibt eine URL aus, die du aufrufst und dann die Domain autorisierst.
set -euo pipefail
cd "$(dirname "$0")/.."
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }
TUNNEL_NAME="${TUNNEL_NAME:-sychos-mail}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "== cloudflared installieren =="
  curl -fsSL -o /tmp/cloudflared.deb \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  SUDO dpkg -i /tmp/cloudflared.deb >/dev/null
fi
cloudflared --version

if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
  echo
  echo "== Anmeldung bei Cloudflare =="
  echo "Bitte die gleich angezeigte URL im Browser oeffnen und sychos.de auswaehlen."
  cloudflared tunnel login
fi

echo "== Tunnel $TUNNEL_NAME =="
if cloudflared tunnel list --output json 2>/dev/null | grep -q "\"name\":\"$TUNNEL_NAME\""; then
  TUNNEL_ID=$(cloudflared tunnel list --output json \
    | python3 -c "import json,sys;print([t['id'] for t in json.load(sys.stdin) if t['name']=='$TUNNEL_NAME'][0])")
  echo "vorhanden: $TUNNEL_ID"
else
  cloudflared tunnel create "$TUNNEL_NAME" | tee /tmp/tunnel-create.txt
  TUNNEL_ID=$(grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' \
    /tmp/tunnel-create.txt | head -1)
fi
echo "Tunnel-ID: $TUNNEL_ID"

echo "== DNS-Routen =="
for host in sychos.de www.sychos.de origin.sychos.de admin.sychos.de; do
  cloudflared tunnel route dns "$TUNNEL_NAME" "$host" 2>&1 | tail -1 || true
done

echo "== Zugangsdatei + Konfiguration =="
mkdir -p cloudflared
cp "$HOME/.cloudflared/$TUNNEL_ID.json" cloudflared/
chmod 600 cloudflared/"$TUNNEL_ID".json
sed "s/__TUNNEL_ID__/$TUNNEL_ID/g" cloudflared/config.example.yml > cloudflared/config.yml

echo "== Tunnel-Container starten =="
docker compose --profile tunnel up -d cloudflared
sleep 5
docker logs --tail 15 sychos-cloudflared 2>&1 || true

echo
echo "Fertig. Teste:  https://admin.sychos.de  (Panel) und https://origin.sychos.de (Ursprung)"
echo
echo "Naechster Schritt — Webseite auf Cloudflare (Worker):"
echo "  1. Ordner worker/ in ein GitHub-Repository pushen"
echo "  2. Secrets CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID im Repo setzen"
echo "  3. Push auf main -> GitHub Actions baut die UI und deployt sychos.de"
echo "  Details: docs/WORKER.md"
