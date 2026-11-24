#!/usr/bin/env bash
# DKIM-Schluessel fuer alle Domains erzeugen und die DNS-Eintraege anzeigen.
#   cd /opt/sychos-mail/stack && bash scripts/dkim-setup.sh [domain]
set -euo pipefail
cd "$(dirname "$0")/.."
DOMAIN="${1:-${DOMAIN:-sychos.de}}"
SELECTOR="${DKIM_SELECTOR:-mail}"

echo "== DKIM fuer $DOMAIN (Selector: $SELECTOR) =="
docker compose exec -T mailserver setup config dkim keysize 2048 selector "$SELECTOR" domain "$DOMAIN" || \
  docker compose exec -T mailserver setup config dkim

echo
echo "== Oeffentlicher Schluessel (in DNS als TXT eintragen) =="
for f in $(docker compose exec -T mailserver sh -c "ls /tmp/docker-mailserver/rspamd/dkim/*.public.txt 2>/dev/null || ls /tmp/docker-mailserver/opendkim/keys/*/*.txt 2>/dev/null"); do
  echo "--- $f"
  docker compose exec -T mailserver sh -c "tr -d '\n' < $f; echo"
done
echo
echo "Record-Name:  $SELECTOR._domainkey.$DOMAIN"
echo "Record-Typ:   TXT"
