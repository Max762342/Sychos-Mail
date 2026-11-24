#!/usr/bin/env bash
# Injektor installieren: HTTPS (ueber den Tunnel) -> LMTP -> Dovecot.
# Erzeugt beim ersten Lauf ein Shared Secret in /etc/sychos-inject.env.
#
#   bash scripts/inject-install.sh
set -euo pipefail
BASE=/opt/sychos-mail
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }
ENVF=/etc/sychos-inject.env

echo "== Secret erzeugen/pruefen =="
if SUDO test -f "$ENVF"; then
  echo "existiert bereits"
else
  SECRET=$(openssl rand -hex 32)
  # Datei lokal bauen (kein Pipe in sudo!) und dann installieren
  printf 'INJECT_LISTEN=127.0.0.1\nINJECT_PORT=8099\nLMTP_HOST=127.0.0.1\nLMTP_PORT=8024\nINJECT_SECRET=%s\n' \
    "$SECRET" >/tmp/sychos-inject.env
  SUDO install -m 600 -o root -g root /tmp/sychos-inject.env "$ENVF"
  rm -f /tmp/sychos-inject.env
  echo "neu angelegt"
fi
echo -n "Shared Secret: "
SUDO sed -n 's/^INJECT_SECRET=//p' "$ENVF"

echo "== systemd-Dienst =="
sed "s|__USER__|$(id -un)|g" "$BASE/stack/inject/sychos-inject.service" >/tmp/sychos-inject.service
SUDO cp /tmp/sychos-inject.service /etc/systemd/system/sychos-inject.service
SUDO systemctl daemon-reload
SUDO systemctl enable --now sychos-inject
SUDO systemctl restart sychos-inject
sleep 2
SUDO systemctl is-active sychos-inject
curl -s -o - -w '\n' http://127.0.0.1:8099/healthz || true
