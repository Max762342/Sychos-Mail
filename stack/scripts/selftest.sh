#!/usr/bin/env bash
# Funktionstest des Control Panels (ohne Browser) — legt ein Testpostfach an,
# prueft die 3-GB-Quota und loescht es wieder.
#   bash scripts/selftest.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PANEL_DIR="$PWD/panel"
set -a
while IFS='=' read -r key value; do
  case "$key" in ''|'#'*) continue ;; esac
  export "$key=$value"
done < .env
set +a
cd "$PANEL_DIR"
PANEL_COOKIE_SECURE=0 .venv/bin/python selftest.py
