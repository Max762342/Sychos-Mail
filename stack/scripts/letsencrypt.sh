#!/usr/bin/env bash
# Echtes Let's-Encrypt-Zertifikat per DNS-01 (Cloudflare) holen.
# DNS-01 braucht keinen offenen Port 80 â€” funktioniert also auch hinter NAT.
#
#   CF_TOKEN=<api-token> bash scripts/letsencrypt.sh
#   danach: WEBMAIL_INSECURE_TLS=0 in .env setzen und Stack neu starten.
#
# Cloudflare-Token: My Profile -> API Tokens -> Create Token ->
#   "Edit zone DNS" fuer die Zone sychos.de.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${CF_TOKEN:?Cloudflare API-Token (Zone:DNS:Edit) in CF_TOKEN setzen}"
MAIL_HOSTNAME="${MAIL_HOSTNAME:-mail.sychos.de}"

mkdir -p tls .acme
echo "== Zertifikat fuer $MAIL_HOSTNAME beantragen =="
docker run --rm \
  -v "$PWD/tls:/out" \
  -v "$PWD/.acme:/acme" \
  -e CF_Token="$CF_TOKEN" \
  neilpang/acme.sh \
  --issue --server letsencrypt --dns dns_cf \
  -d "$MAIL_HOSTNAME" \
  --home /acme \
  --key-file /out/key \
  --fullchain-file /out/cert \
  --reloadcmd "true"

echo "== Mailserver neu starten =="
docker compose restart mailserver
echo
echo "Fertig. Zertifikat:"
openssl x509 -in tls/cert -noout -subject -issuer -enddate
echo
echo "Jetzt in .env: WEBMAIL_INSECURE_TLS=0 setzen, dann 'docker compose up -d'."
echo "Erneuerung: scripts/renew-certs.sh (z. B. monatlich per cron)."
