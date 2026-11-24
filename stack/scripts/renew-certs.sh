#!/usr/bin/env bash
# Let's-Encrypt-Zertifikat erneuern (per cron aufrufen).
#   CF_TOKEN=<token> bash scripts/renew-certs.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${CF_TOKEN:?Cloudflare API-Token in CF_TOKEN setzen}"
MAIL_HOSTNAME="${MAIL_HOSTNAME:-mail.sychos.de}"

docker run --rm \
  -v "$PWD/tls:/out" \
  -v "$PWD/.acme:/acme" \
  -e CF_Token="$CF_TOKEN" \
  neilpang/acme.sh \
  --cron --home /acme \
  --key-file /out/key \
  --fullchain-file /out/cert \
  --reloadcmd "true"

docker compose restart mailserver
echo "Zertifikat erneuert:"
openssl x509 -in tls/cert -noout -enddate
