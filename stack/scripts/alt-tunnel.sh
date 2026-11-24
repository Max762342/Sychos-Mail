#!/usr/bin/env bash
# Alternativer Tunnel fuer den Mail-Injektor (ohne cloudflared).
# SSH-Reverse-Tunnel zu localhost.run — kostenlos, kein Account, HTTPS-URL.
#
#   bash scripts/alt-tunnel.sh start     # startet, gibt die URL aus
#   bash scripts/alt-tunnel.sh url
#   bash scripts/alt-tunnel.sh stop
set -uo pipefail
PORT="${INJECT_PORT:-8099}"
LOG=/tmp/sychos-alttunnel.log
PIDF=/tmp/sychos-alttunnel.pid

url() {
  grep -oE 'https://[a-z0-9.-]+\.lhr\.life' "$LOG" 2>/dev/null | tail -1
}

case "${1:-start}" in
  stop)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      kill "$(cat "$PIDF")" && echo "gestoppt"
    else
      pkill -f 'ssh -R 80:localhost:' 2>/dev/null && echo "gestoppt" || echo "lief nicht"
    fi
    rm -f "$PIDF"
    ;;
  url)
    url
    ;;
  start)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "laeuft bereits: $(url)"
      exit 0
    fi
    : >"$LOG"
    nohup ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 \
      -o ExitOnForwardFailure=yes -R "80:localhost:$PORT" nokey@localhost.run \
      >"$LOG" 2>&1 &
    echo $! >"$PIDF"
    for _ in $(seq 1 20); do
      [ -n "$(url)" ] && break
      sleep 2
    done
    if [ -z "$(url)" ]; then
      echo "keine URL - Log:"; tail -15 "$LOG"; exit 1
    fi
    echo "$(url)"
    ;;
esac
