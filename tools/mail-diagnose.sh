#!/usr/bin/env bash
# Mail-Diagnose: ausgehende Ports, PTR, SPF/DMARC, Blocklisten
set -uo pipefail

test_port() {
  local host=$1 port=$2
  if timeout 10 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
    echo "  $host:$port -> erreichbar"
  else
    echo "  $host:$port -> BLOCKIERT/keine Verbindung"
  fi
}

echo "== ausgehende Mail-Ports =="
test_port gmail-smtp-in.l.google.com 25
test_port smtp.web.de 25
test_port smtp.ionos.de 587
test_port smtp.ionos.de 465

echo
echo "== eigene IP + PTR =="
IP=$(curl -s --max-time 8 https://api.ipify.org)
echo "  IP: $IP"
echo -n "  PTR: "
dig +short -x "$IP" @1.1.1.1 | tr '\n' ' '
echo

echo
echo "== SPF / DMARC / DKIM fuer sychos.de =="
echo -n "  SPF:   "; dig +short TXT sychos.de @1.1.1.1 | tr '\n' ' '; echo
echo -n "  DMARC: "; dig +short TXT _dmarc.sychos.de @1.1.1.1 | tr '\n' ' '; echo
echo -n "  DKIM:  "; dig +short TXT mail._domainkey.sychos.de @1.1.1.1 | cut -c1-40; echo
echo -n "  MX:    "; dig +short MX sychos.de @1.1.1.1 | tr '\n' ' '; echo

echo
echo "== Blocklisten (127.0.0.x = gelistet) =="
REV=$(echo "$IP" | awk -F. '{print $4"."$3"."$2"."$1}')
for bl in zen.spamhaus.org bl.spamcop.net b.barracudacentral.org dnsbl.sorbs.net; do
  R=$(dig +short "$REV.$bl" @1.1.1.1 | head -1)
  if [ -n "$R" ]; then echo "  $bl -> GELISTET ($R)"; else echo "  $bl -> sauber"; fi
done

echo
echo "== Postfix-Queue / letzte Zustellfehler =="
docker exec sychos-mailserver postqueue -p 2>/dev/null | tail -5 || true
docker exec sychos-mailserver sh -c 'grep -hE "status=(bounced|deferred)" /var/log/mail/mail.log 2>/dev/null | tail -5' || true
