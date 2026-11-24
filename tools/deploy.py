#!/usr/bin/env python3
"""Deploy-Helfer: Dateien per SFTP hochladen und Befehle auf dem Host ausfuehren.

    python tools/deploy.py upload stack webmail      # -> /opt/sychos-mail/
    python tools/deploy.py run "docker compose ps"
    python tools/deploy.py detach "docker compose build"   # Hintergrund + Log

Der Upload ueberspringt Dateien, die neuer als die lokale Version sind
(mtime-Vergleich), damit wiederholte Laeufe schnell bleiben.
"""
import os
import stat
import sys
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
REMOTE_BASE = "/opt/sychos-mail"
SKIP_DIRS = {".git", "node_modules", "target", "__pycache__", ".svelte-kit", "build", "tls"}
SKIP_FILES = {"vps.env", "vps.py", "deploy.py", ".DS_Store"}
TEXT_SUFFIXES = {
    ".sh", ".yml", ".yaml", ".env", ".sql", ".py", ".txt", ".md", ".html",
    ".css", ".js", ".ts", ".svelte", ".json", ".conf", ".service", ".toml",
    ".example", ".rs",
}


def load_env() -> dict:
    cfg = {}
    env_file = Path(__file__).with_name("vps.env")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def connect(cfg):
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
    return client


def ensure_dir(sftp, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except IOError:
            sftp.mkdir(cur)


def upload_dir(sftp, local: Path, remote: str) -> int:
    ensure_dir(sftp, remote)
    count = 0
    for entry in sorted(local.iterdir()):
        if entry.name in SKIP_DIRS or entry.name in SKIP_FILES:
            continue
        rpath = f"{remote}/{entry.name}"
        if entry.is_dir():
            count += upload_dir(sftp, entry, rpath)
            continue
        local_mtime = int(entry.stat().st_mtime)
        try:
            if int(sftp.stat(rpath).st_mtime) >= local_mtime:
                continue
        except IOError:
            pass
        # Textdateien mit LF hochladen — CRLF aus Windows bricht Shell/Env/SQL.
        if entry.suffix.lower() in TEXT_SUFFIXES or entry.name.startswith(".env"):
            data = entry.read_bytes().replace(b"\r\n", b"\n")
            with sftp.open(rpath, "wb") as fh:
                fh.write(data)
        else:
            sftp.put(str(entry), rpath)
        count += 1
    return count


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = load_env()
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    action = sys.argv[1]
    client = connect(cfg)

    try:
        if action == "upload":
            sftp = client.open_sftp()
            total = 0
            for name in sys.argv[2:]:
                local = ROOT / name
                total += upload_dir(sftp, local, f"{REMOTE_BASE}/{name}")
            sftp.close()
            print(f"{total} Dateien hochgeladen nach {REMOTE_BASE}")
            return 0

        if action in {"run", "detach"}:
            cmd = sys.argv[2]
            if action == "run":
                stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)
                out = stdout.read().decode("utf-8", "replace")
                err = stderr.read().decode("utf-8", "replace")
                code = stdout.channel.recv_exit_status()
                print(out.rstrip())
                if err.strip():
                    print("--- stderr ---")
                    print(err.rstrip())
                print(f"[exit {code}]")
                return code

            log = sys.argv[3] if len(sys.argv) > 3 else "/tmp/sychos-deploy.log"
            stamp = time.strftime("%Y%m%d-%H%M%S")
            full = f"cd {REMOTE_BASE}/stack && nohup bash -c {cmd!r} >{log}.{stamp} 2>&1 & echo started {log}.{stamp}"
            stdin, stdout, stderr = client.exec_command(full, timeout=60)
            print(stdout.read().decode("utf-8", "replace").strip())
            return 0

        print(f"unbekannte Aktion: {action}")
        return 2
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
