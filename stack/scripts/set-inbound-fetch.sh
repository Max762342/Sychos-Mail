#!/usr/bin/env bash
# Postfach bei einem anderen Anbieter (z. B. IONOS) abholen, weil am eigenen
# Anschluss kein Port 25 von aussen erreichbar ist.
#
#   bash scripts/set-inbound-fetch.sh imap.ionos.de info@sychos.de 'PASSWORT' admin@sychos.de
#
# Danach holt fetchmail die Mails regelmaessig ab und legt sie in das lokale
# Postfach (Dovecot -> Webmail).
set -euo pipefail
cd "$(dirname "$0")/.."
ENVF=mailserver.env

UP_HOST="${1:?IMAP-Host fehlt, z.B. imap.ionos.de}"
UP_USER="${2:?Benutzer beim Anbieter fehlt}"
UP_PASS="${3:?Passwort fehlt}"
LOCAL="${4:?lokales Postfach fehlt, z.B. admin@sychos.de}"

echo "== ENABLE_FETCHMAIL aktivieren =="
python3 - "$ENVF" <<'PY'
import re
import sys

path = sys.argv[1]
text = open(path).read()
if re.search(r"(?m)^ENABLE_FETCHMAIL=", text):
    text = re.sub(r"(?m)^ENABLE_FETCHMAIL=.*$", "ENABLE_FETCHMAIL=1", text)
else:
    text = text.rstrip("\n") + "\nENABLE_FETCHMAIL=1\n"
open(path, "w").write(text)
print("ENABLE_FETCHMAIL=1")
PY

echo "== fetchmail.cf schreiben =="
CFG=/tmp/fetchmail.cf
cat >"$CFG" <<EOF
# Abholung fuer $LOCAL
poll $UP_HOST
  protocol IMAP
  user "$UP_USER" there with password "$UP_PASS" is "$LOCAL" here
  ssl
  fetchall
  keep
  idle
EOF

docker cp "$CFG" sychos-mailserver:/tmp/docker-mailserver/fetchmail.cf
rm -f "$CFG"
docker exec sychos-mailserver sh -c \
  'chown root:root /tmp/docker-mailserver/fetchmail.cf && chmod 600 /tmp/docker-mailserver/fetchmail.cf'

echo "== Container neu erzeugen =="
docker compose up -d mailserver
sleep 12
docker compose logs --tail 20 mailserver | grep -i fetchmail || true

echo
echo "Fertig. Test: Mail an $UP_USER schicken -> sollte im Postfach $LOCAL landen."
