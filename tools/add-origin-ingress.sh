#!/usr/bin/env bash
# Haengt origin.sychos.com -> Webmail (127.0.0.1:8080) an den bestehenden
# Tunnel "dbgate" und startet cloudflared neu. Mit Backup + Rollback.
set -euo pipefail
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }
CFG=/etc/cloudflared/config.yml
HOST=origin.sychos.com

echo "== Backup =="
SUDO cp "$CFG" "/etc/cloudflared/config.yml.bak-$(date +%Y%m%d-%H%M%S)"

if SUDO grep -q "hostname: $HOST" "$CFG"; then
  echo "Eintrag existiert bereits"
else
  echo "== Ingress fuer $HOST einfuegen =="
  python3 - "$CFG" "$HOST" <<'PY'
import sys
path, host = sys.argv[1], sys.argv[2]
text = open(path).read()
entry = f"  - hostname: {host}\n    service: http://127.0.0.1:8080\n"
marker = "  - service: http_status:404"
if host in text:
    print("schon vorhanden")
elif marker in text:
    text = text.replace(marker, entry + marker, 1)
    open("/tmp/cloudflared-new.yml", "w").write(text)
    print("eingefuegt")
else:
    open("/tmp/cloudflared-new.yml", "w").write(text.rstrip("\n") + "\n" + entry)
    print("angehaengt")
PY
  if [ -f /tmp/cloudflared-new.yml ]; then
    SUDO cp /tmp/cloudflared-new.yml "$CFG"
    rm -f /tmp/cloudflared-new.yml
  fi
fi

echo "== neue Konfiguration =="
SUDO cat "$CFG"

echo "== validieren =="
if ! SUDO cloudflared tunnel ingress validate --config "$CFG"; then
  echo "FEHLER: Konfiguration ungueltig - Rollback"
  LAST=$(SUDO ls -1 /etc/cloudflared/config.yml.bak-* | tail -1)
  SUDO cp "$LAST" "$CFG"
  SUDO systemctl restart cloudflared
  exit 1
fi

echo "== cloudflared neu starten =="
SUDO systemctl restart cloudflared
sleep 8
SUDO systemctl is-active cloudflared || true
SUDO journalctl -u cloudflared --no-pager -n 6

echo "== Test (lokal ueber den Tunnel-Hostname) =="
curl -sS --resolve "$HOST:443:188.114.96.3" -o /tmp/origin-test.json \
  -w "HTTP %{http_code} %{size_download}B\n" "https://$HOST/api/config" || true
head -c 200 /tmp/origin-test.json 2>/dev/null || true
echo
echo "== SSH-Hostnames unveraendert? =="
SUDO grep -E 'hostname: (ssh|friend|origin)' "$CFG"
