#!/usr/bin/env bash
# Postfach per Kommandozeile anlegen — gleiches Ergebnis wie im Control Panel,
# standardmaessig 3 GB Speicher.
#
#   bash scripts/create-mailbox.sh max@sychos.de 'GeheimesPasswort'
#   QUOTA=5120 bash scripts/create-mailbox.sh gross@sychos.de
set -euo pipefail
cd "$(dirname "$0")/.."
EMAIL="${1:?Aufruf: $0 <email@domain> [passwort]}"
PASS="${2:-}"
if [ -z "$PASS" ]; then
  PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | cut -c1-18)
fi
QUOTA="${QUOTA:-3072}"   # MB
DOMAIN_PART="${EMAIL#*@}"

echo "== Konto im Mailserver =="
docker compose exec -T mailserver setup email add "$EMAIL" "$PASS" </dev/null
docker compose exec -T mailserver setup quota set "$EMAIL" "${QUOTA}M" </dev/null

echo "== Datenbank (Panel) =="
PGPASSWORD_DUMMY=""
docker compose exec -T postgres psql -U sychos -d panel -v ON_ERROR_STOP=1 -q <<SQL
INSERT INTO domains (name) VALUES ('$DOMAIN_PART') ON CONFLICT (name) DO NOTHING;
INSERT INTO mailboxes (email, domain_id, quota_mb, display_name)
VALUES ('$EMAIL', (SELECT id FROM domains WHERE name = '$DOMAIN_PART'), $QUOTA, NULL)
ON CONFLICT (email) DO UPDATE SET quota_mb = EXCLUDED.quota_mb, updated_at = now();
SQL

echo
echo "---------------------------------------------"
echo " E-Mail:   $EMAIL"
echo " Passwort: $PASS"
echo " Speicher: ${QUOTA} MB"
echo " IMAP:     mail.$DOMAIN_PART:993 (SSL)"
echo " SMTP:     mail.$DOMAIN_PART:465 (SSL)"
echo "---------------------------------------------"

# Fuer die Zugangsdaten-Datei (Panel + Desktop) mitschreiben
printf '%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M')" "$EMAIL" "$PASS" "$QUOTA" \
  >>credentials.log
chmod 600 credentials.log
