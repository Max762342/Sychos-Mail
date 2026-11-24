#!/usr/bin/env bash
# Test: Rohmail in den Injektor geben (lokal) und ueber die oeffentliche
# Tunnel-Adresse; danach im Postfach nachsehen.
set -uo pipefail
SECRET=$(sudo -S -p '' sed -n 's/^INJECT_SECRET=//p' /etc/sychos-inject.env </tmp/sychos.pw)
SUBJECT="Sychos Injektor Test $(date +%H%M%S)"
echo "Betreff: $SUBJECT"

cat >/tmp/mail.txt <<EOF
From: Gmail Test <test@gmail.com>
To: admin@sychos.de
Subject: $SUBJECT
Date: $(date -R)
Message-ID: <$(date +%s)@gmail.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Hallo aus dem Injektor-Test. Diese Mail kam NICHT ueber Port 25.
EOF

python3 - "$SUBJECT" <<'PY' >/tmp/mail.json
import base64, json, sys
raw = open("/tmp/mail.txt", "rb").read()
print(json.dumps({"to": ["admin@sychos.de"], "raw_b64": base64.b64encode(raw).decode()}))
PY

echo "== lokal (127.0.0.1:8099) =="
curl -sS -o /tmp/r1.txt -w "HTTP %{http_code}\n" -X POST http://127.0.0.1:8099/inject \
  -H 'content-type: application/json' -H "x-inject-secret: $SECRET" --data-binary @/tmp/mail.json
cat /tmp/r1.txt; echo

echo "== ueber Tunnel (https://inject.sychos.de) =="
curl -sS -o /tmp/r2.txt -w "HTTP %{http_code}\n" -X POST https://inject.sychos.de/inject \
  -H 'content-type: application/json' -H "x-inject-secret: $SECRET" --data-binary @/tmp/mail.json
head -c 200 /tmp/r2.txt; echo

echo "== ohne Secret (muss 403 sein) =="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST http://127.0.0.1:8099/inject \
  -H 'content-type: application/json' --data-binary @/tmp/mail.json

echo "== Service-Log =="
sudo -S -p '' journalctl -u sychos-inject --no-pager -n 6 </tmp/sychos.pw
rm -f /tmp/mail.json /tmp/mail.txt /tmp/r1.txt /tmp/r2.txt
