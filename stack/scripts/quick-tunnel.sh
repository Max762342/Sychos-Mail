#!/usr/bin/env bash
# Startet einen Cloudflare-Quick-Tunnel auf 127.0.0.1:8080 (Webmail) und gibt
# die oeffentliche URL aus. Fuer Tests ohne eigene Domain/Tunnel-Login.
#   bash scripts/quick-tunnel.sh          (startet/zeigt URL)
#   bash scripts/quick-tunnel.sh status
#   bash scripts/quick-tunnel.sh stop
set -uo pipefail
LOG=/tmp/sychos-quicktunnel.log
PIDF=/tmp/sychos-quicktunnel.pid

url_from_log() {
  grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | head -1
}

case "${1:-start}" in
  stop)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      kill "$(cat "$PIDF")" && echo "gestoppt"
    else
      pkill -f 'cloudflared tunnel --url http://127.0.0.1:8080' 2>/dev/null && echo "gestoppt" || echo "lief nicht"
    fi
    rm -f "$PIDF"
    ;;

  status)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "laeuft (PID $(cat "$PIDF"))"
      url_from_log
    else
      echo "laeuft nicht"
      exit 1
    fi
    ;;

  start)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "laeuft bereits: $(url_from_log)"
      exit 0
    fi
    : >"$LOG"
    nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080 \
      >"$LOG" 2>&1 &
    echo $! >"$PIDF"
    for _ in $(seq 1 30); do
      URL=$(url_from_log)
      [ -n "$URL" ] && break
      sleep 2
    done
    URL=$(url_from_log)
    if [ -z "$URL" ]; then
      echo "keine URL erhalten - Log:"
      tail -20 "$LOG"
      exit 1
    fi
    echo "$URL"
    ;;
esac
