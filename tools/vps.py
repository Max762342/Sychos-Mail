#!/usr/bin/env python3
"""Kleiner SSH-Helper fuer den Sychos VPS (Passwort-Auth via paramiko).

Aufruf:
    python tools/vps.py "uname -a" ["zweiter befehl" ...]

Verbindungsdaten kommen aus tools/vps.env (KEY=VALUE). Damit landen sie nicht
im Skript und koennen pro Rechner angepasst werden.
"""
import os
import sys
from pathlib import Path

import paramiko

ENV_FILE = Path(__file__).with_name("vps.env")


def load_env() -> dict:
    cfg = {
        "VPS_HOST": "192.168.178.53",
        "VPS_PORT": "22",
        "VPS_USER": "sychos2",
        "VPS_PASS": "",
    }
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    return cfg


def run_script(client, script: str) -> None:
    """Fuehrt ein Shell-Skript ueber stdin aus (keine Quoting-Probleme)."""
    print("\n=== $ <script>")
    stdin, stdout, stderr = client.exec_command("bash -s", timeout=1800)
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("--- stderr ---")
        print(err.rstrip())
    print(f"[exit {code}]")


def main() -> int:
    # Windows-Konsole ist oft cp1252; Umlaute/Box-Drawing aus der Ausgabe nicht crashen lassen.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cfg = load_env()
    commands = sys.argv[1:] or ["echo hallo"]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=cfg["VPS_HOST"],
        port=int(cfg["VPS_PORT"]),
        username=cfg["VPS_USER"],
        password=cfg["VPS_PASS"],
        timeout=20,
        look_for_keys=False,
        allow_agent=False,
    )
    for cmd in commands:
        if cmd.startswith("@"):
            # "@datei.sh" -> Skript per stdin ausfuehren (robust gegen Quoting)
            path = Path(cmd[1:])
            if not path.is_absolute():
                path = Path.cwd() / path
            run_script(client, f"export VPS_PASS={cfg['VPS_PASS']}\n" + path.read_text(encoding="utf-8"))
            continue
        print(f"\n=== $ {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
        stdin.close()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print("--- stderr ---")
            print(err.rstrip())
        print(f"[exit {code}]")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
