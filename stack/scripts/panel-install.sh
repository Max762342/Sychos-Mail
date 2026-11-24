#!/usr/bin/env bash
# Sychos Control Panel als systemd-Dienst installieren (auf dem Host ausfuehren).
#   bash scripts/panel-install.sh
set -euo pipefail
BASE=/opt/sychos-mail
STACK=$BASE/stack
PW_FILE=/tmp/sychos.pw
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }

echo "== python venv =="
SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip

echo "== venv + abhaengigkeiten =="
cd "$STACK/panel"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip wheel
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/python -c "import flask, gunicorn; import psycopg; print('module ok', flask.__version__, psycopg.__version__)"

echo "== systemd dienst =="
sed -e "s|__USER__|$(id -un)|g" -e "s|__BASE__|$BASE|g" \
  "$STACK/panel/systemd/sychos-panel.service" >/tmp/sychos-panel.service
SUDO cp /tmp/sychos-panel.service /etc/systemd/system/sychos-panel.service
SUDO systemctl daemon-reload
SUDO systemctl enable --now sychos-panel
sleep 2
SUDO systemctl restart sychos-panel
sleep 2
systemctl --no-pager --lines=8 status sychos-panel || true
echo
echo "== probe =="
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8090/login || true
