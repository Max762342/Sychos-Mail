#!/usr/bin/env bash
# Selbstsigniertes TLS-Zertifikat fuer den Mailserver erzeugen (intern).
# Wird nur gebraucht, solange noch kein echtes Let's-Encrypt-Zertifikat da ist.
#
# docker-mailserver erwartet die Dateien ohne Endung: tls/cert und tls/key
#   bash scripts/tls-selfsigned.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tls
if [ -s tls/cert ] && [ -s tls/key ]; then
  echo "Zertifikat vorhanden — nichts zu tun."
  exit 0
fi
MAIL_HOST="${MAIL_HOSTNAME:-mail.sychos.de}"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -subj "/CN=${MAIL_HOST}" \
  -addext "subjectAltName=DNS:${MAIL_HOST},DNS:mailserver,DNS:localhost,IP:127.0.0.1" \
  -keyout tls/key -out tls/cert 2>/dev/null
chmod 640 tls/key tls/cert
openssl x509 -in tls/cert -noout -subject -enddate

