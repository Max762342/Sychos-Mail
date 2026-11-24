#!/usr/bin/env bash
# Einmalige Vorbereitung des Hosts: Projektverzeichnis + sudo-Passwortdatei.
# Aufruf:  python tools/vps.py @stack/scripts/host-bootstrap.sh
set -euo pipefail
BASE=/opt/sychos-mail

if [ -n "${VPS_PASS:-}" ]; then
  printf '%s\n' "$VPS_PASS" >/tmp/sychos.pw
  chmod 600 /tmp/sychos.pw
fi
SUDO() { sudo -S -p '' "$@" <"$PW_FILE"; }
PW_FILE=/tmp/sychos.pw

echo "== Verzeichnis $BASE =="
cat "$PW_FILE" | sudo -S -p '' mkdir -p "$BASE"
cat "$PW_FILE" | sudo -S -p '' chown -R "$(id -un)":"$(id -gn)" "$BASE"

echo "== IP-Weiterleitung (fuer Docker) =="
cat "$PW_FILE" | sudo -S -p '' sh -c 'modprobe br_netfilter 2>/dev/null || true; echo "net.ipv4.ip_forward = 1" >/etc/sysctl.d/98-sychos-docker.conf; sysctl --system >/dev/null 2>&1 || true'

ls -ld "$BASE"
echo FERTIG
