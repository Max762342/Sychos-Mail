#!/usr/bin/env bash
# Kompletter Neuaufbau in einem Rutsch (idempotent):
#   bash scripts/deploy-all.sh
#
# Voraussetzung: sudo-Passwort in /tmp/sychos.pw, Projekt liegt in /opt/sychos-mail.
set -euo pipefail
cd "$(dirname "$0")/.."
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }

echo "### 1/6 Docker"
command -v docker >/dev/null || bash scripts/host-docker-install.sh

echo "### 2/6 TLS"
bash scripts/tls-selfsigned.sh

echo "### 3/6 Mailserver + Postgres + Webmail"
docker compose up -d --build

echo "### 4/6 Warten auf den Mailserver"
for i in $(seq 1 60); do
  if docker compose exec -T mailserver doveadm pw -s SHA512-CRYPT -p probe >/dev/null 2>&1; then
    echo "bereit"; break
  fi
  sleep 3
done

echo "### 5/6 Erstes Postfach (Pflicht, sonst startet der Mailserver neu)"
if ! docker compose exec -T mailserver setup email list 2>/dev/null | grep -q '@'; then
  ADMIN_PW="${ADMIN_PW:-$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | cut -c1-18)}"
  ADMIN_PW="$ADMIN_PW" bash scripts/seed-initial.sh
fi

echo "### 6/6 Control Panel"
bash scripts/panel-install.sh

echo
docker compose ps
echo
echo "Webmail:  http://127.0.0.1:8080   Panel: http://127.0.0.1:8090"
echo "Öffentlich: bash scripts/cloudflare-setup.sh  (Cloudflare Tunnel)"
echo "DKIM:       bash scripts/dkim-setup.sh"
