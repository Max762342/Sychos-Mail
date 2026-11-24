#!/usr/bin/env bash
# Ausgehende Mail ueber einen Smarthost (Relay) senden.
# Noetig, weil Gmail/Outlook Mails von Privatanschluessen grundsaetzlich
# ablehnen ("The IP you're using to send mail is not authorized...").
#
#   bash scripts/set-relay.sh smtp.ionos.de 587 info@sychos.de 'PASSWORT'
#   bash scripts/set-relay.sh              # zeigt aktuellen Stand
set -euo pipefail
cd "$(dirname "$0")/.."
ENVF=mailserver.env

show() {
  echo "== aktueller Relay-Stand =="
  grep -E '^(DEFAULT_RELAY_HOST|RELAY_USER|RELAY_PASSWORD)=' "$ENVF" | sed 's/\(RELAY_PASSWORD=\).*/\1***/'
  echo "== Postfix im Container =="
  docker exec sychos-mailserver postconf -n 2>/dev/null | grep -E 'relayhost|smtp_sasl_auth_enable|smtp_tls_security_level' || true
}

if [ $# -eq 0 ]; then show; exit 0; fi

HOST="${1:?Relay-Host fehlt, z.B. smtp.ionos.de}"
PORT="${2:-587}"
USER="${3:?Relay-Benutzer fehlt}"
PASS="${4:?Relay-Passwort fehlt}"

python3 - "$ENVF" "$HOST" "$PORT" "$USER" "$PASS" <<'PY'
import re
import sys

path, host, port, user, password = sys.argv[1:6]
text = open(path).read()


def upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"(?m)^{key}=.*$", text):
        return re.sub(rf"(?m)^{key}=.*$", line, text)
    return text.rstrip("\n") + "\n" + line + "\n"


text = upsert(text, "DEFAULT_RELAY_HOST", f"[{host}]:{port}")
text = upsert(text, "RELAY_USER", user)
text = upsert(text, "RELAY_PASSWORD", password)
open(path, "w").write(text)
print(f"gesetzt: DEFAULT_RELAY_HOST=[{host}]:{port}, RELAY_USER={user}")
PY

echo "== Container neu erzeugen =="
docker compose up -d mailserver
sleep 12
show

echo
echo "== Testversand an den Relay =="
docker exec sychos-mailserver sh -c \
  'printf "EHLO test\nQUIT\n" | openssl s_client -quiet -connect '"$HOST:$PORT"' -servername '"$HOST"' 2>/dev/null | head -3' || true
