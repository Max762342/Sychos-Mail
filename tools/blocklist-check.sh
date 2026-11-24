#!/usr/bin/env bash
# Blocklisten-Pruefung ueber den Provider-Resolver (Spamhaus verbietet
# Anfragen von oeffentlichen Resolvern wie 1.1.1.1/8.8.8.8).
set -uo pipefail
IP="${1:-79.140.115.19}"
REV=$(echo "$IP" | awk -F. '{print $4"."$3"."$2"."$1}')

echo "IP: $IP   (reverse: $REV)"
echo "Resolver: $(grep -m1 '^nameserver' /etc/resolv.conf | awk '{print $2}')"
echo

check() {
  local zone=$1 label=$2
  local out
  out=$(dig +short +time=5 +tries=1 "$REV.$zone" 2>/dev/null | tr '\n' ' ')
  if [ -z "$out" ]; then
    echo "  $label: nicht gelistet"
  else
    echo "  $label: GELISTET -> $out"
    case "$out" in
      *127.0.0.2*|*127.0.0.10*|*127.0.0.11*) echo "      = PBL: IP-Bereich eines Privatanschlusses (Gmail lehnt direkte Zustellung ab)" ;;
      *127.0.0.4*|*127.0.0.5*|*127.0.0.6*|*127.0.0.7*) echo "      = XBL: als Spam-/Exploit-Quelle gemeldet" ;;
      *127.0.0.3*) echo "      = PBL (vom Provider gepflegt): dynamischer Anschluss" ;;
      *127.0.0.9*) echo "      = SBL: Spam-Quelle" ;;
      *127.255.255*) echo "      = Abfrage abgelehnt (Resolver nicht erlaubt)" ;;
    esac
  fi
}

echo "== Spamhaus =="
check zen.spamhaus.org "zen.spamhaus.org"
echo "== weitere Listen =="
check bl.spamcop.net "bl.spamcop.net"
check b.barracudacentral.org "b.barracudacentral.org"
check dnsbl.sorbs.net "dnsbl.sorbs.net"
check psbl.surriel.com "psbl.surriel.com"

echo
echo "== PTR =="
dig +short -x "$IP" | sed 's/^/  /' || true
[ -z "$(dig +short -x "$IP")" ] && echo "  (kein PTR gesetzt)"

echo
echo "== Erreichbarkeit eingehend Port 25 (lokal lauscht es?) =="
ss -lnt | grep -E ':25 ' || echo "  Port 25 lauscht NICHT"
