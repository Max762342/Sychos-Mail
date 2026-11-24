#!/usr/bin/env bash
# Testkonten (Selbsttests) aus Mailserver und Datenbank entfernen.
#   bash scripts/cleanup-testdata.sh
set -uo pipefail
C=sychos-mailserver
cd "$(dirname "$0")/.."

for addr in $(docker exec $C setup email list </dev/null \
  | grep -oE '[a-z0-9._%+-]+@[a-z0-9.-]+' | sort -u); do
  case "$addr" in
    selftest*|probe*|quotaprobe*|test1@*|test2@*)
      echo "loesche $addr"
      docker exec -i $C setup email del -y "$addr" </dev/null >/dev/null 2>&1 || true
      docker compose exec -T postgres psql -U sychos -d panel -q \
        -c "DELETE FROM mailboxes WHERE email = '$addr';" </dev/null >/dev/null 2>&1 || true
      ;;
  esac
done

echo "== verbleibende Konten =="
docker exec $C setup email list </dev/null
docker compose exec -T postgres psql -U sychos -d panel </dev/null -c \
  "SELECT email, quota_mb FROM mailboxes ORDER BY email;"

if [ -f credentials.log ]; then
  awk -F'\t' '$2 !~ /^(selftest|probe|quotaprobe|test1@|test2@)/' credentials.log >credentials.log.tmp
  mv credentials.log.tmp credentials.log
  chmod 600 credentials.log
fi
