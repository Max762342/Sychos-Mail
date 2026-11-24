#!/usr/bin/env bash
# Erstes Postfach anlegen (docker-mailserver braucht innerhalb von 2 Minuten
# mindestens ein Konto, sonst startet der Container neu).
#
#   ADMIN_PW='...' bash scripts/seed-initial.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ADMIN_MAIL="${ADMIN_MAIL:-admin@sychos.de}"
ADMIN_PW="${ADMIN_PW:?ADMIN_PW setzen}"
DOMAIN_PART="${ADMIN_MAIL#*@}"
QUOTA="${QUOTA:-3072}"

echo "== Konto $ADMIN_MAIL =="
if docker compose exec -T mailserver setup email list </dev/null 2>/dev/null | grep -qix "$ADMIN_MAIL"; then
  echo "existiert bereits"
else
  docker compose exec -T mailserver setup email add "$ADMIN_MAIL" "$ADMIN_PW" </dev/null
fi

echo "== Quota ${QUOTA} MB =="
docker compose exec -T mailserver setup quota set "$ADMIN_MAIL" "${QUOTA}M" </dev/null \
  || echo "WARNUNG: setup quota set fehlgeschlagen — bitte 'setup help' pruefen"

echo "== postmaster-Alias =="
docker compose exec -T mailserver setup alias add "postmaster@$DOMAIN_PART" "$ADMIN_MAIL" </dev/null || true

echo "== Datenbank =="
docker compose exec -T postgres psql -U sychos -d panel -v ON_ERROR_STOP=1 -q <<SQL
INSERT INTO domains (name) VALUES ('$DOMAIN_PART') ON CONFLICT (name) DO NOTHING;
INSERT INTO mailboxes (email, domain_id, quota_mb)
VALUES ('$ADMIN_MAIL', (SELECT id FROM domains WHERE name = '$DOMAIN_PART'), $QUOTA)
ON CONFLICT (email) DO NOTHING;
SQL

printf '%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M')" "$ADMIN_MAIL" "$ADMIN_PW" "$QUOTA" \
  >>credentials.log
chmod 600 credentials.log
echo "== fertig =="
