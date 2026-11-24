#!/usr/bin/env bash
# Docker auf dem Sychos-Host installieren (einmalig).
# Aufruf auf dem Host:   bash scripts/host-docker-install.sh
# Voraussetzung: sudo-Passwort in /tmp/sychos.pw (chmod 600) oder in $VPS_PASS.
set -euo pipefail
PW_FILE=/tmp/sychos.pw
if [ -n "${VPS_PASS:-}" ]; then
  printf '%s\n' "$VPS_PASS" >"$PW_FILE"
  chmod 600 "$PW_FILE"
fi
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }

echo "== warte auf apt-Sperre =="
for i in $(seq 1 200); do
  if ! fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo "== apt update =="
SUDO apt-get update -qq

echo "== docker installieren =="
SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2

echo "== docker dienst =="
SUDO systemctl enable --now docker
docker --version
docker compose version

echo "== benutzer in docker-gruppe =="
SUDO usermod -aG docker "$USER" || true

echo "== kernel-parameter =="
cat >/tmp/99-sychos-mail.conf <<'EOF'
# Sychos Mail
net.core.somaxconn = 4096
fs.inotify.max_user_watches = 524288
EOF
SUDO cp /tmp/99-sychos-mail.conf /etc/sysctl.d/99-sychos-mail.conf
SUDO sysctl --system >/dev/null
echo FERTIG

