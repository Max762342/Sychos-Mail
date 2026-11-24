#!/usr/bin/env python3
"""End-to-End-Test der Cloudflare-Architektur ohne Cloudflare.

Startet
  1. einen SSH-Tunnel  localhost:18080 -> Webmail auf dem Server (127.0.0.1:8080)
  2. den Worker lokal (tools/preview-server.mjs, Port 3100) mit den echten Assets
     und API_ORIGIN=http://127.0.0.1:18080
und prueft dann: UI-Auslieferung, /healthz, Login ueber /api (Cookie durch den
Proxy), Session-Abfrage, SPA-Fallback.

    python tools/check-worker-e2e.py --user admin@sychos.de --password ...
"""
import argparse
import http.cookiejar
import json
import os
import select
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
LOCAL_PORT = 18080
PREVIEW_PORT = 3100


def load_env() -> dict:
    cfg = {}
    for line in (Path(__file__).with_name("vps.env")).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    return cfg


class ForwardServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self):
        transport = self.server.transport
        remote = (self.server.remote_host, self.server.remote_port)
        try:
            channel = transport.open_channel("direct-tcpip", remote, self.request.getpeername())
        except Exception:
            return
        if channel is None:
            return
        try:
            while True:
                readable, _, _ = select.select([self.request, channel], [], [], 30)
                if self.request in readable:
                    data = self.request.recv(65536)
                    if not data:
                        break
                    channel.sendall(data)
                if channel in readable:
                    data = channel.recv(65536)
                    if not data:
                        break
                    self.request.sendall(data)
        except (OSError, EOFError):
            pass
        finally:
            channel.close()


def start_tunnel(cfg):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg["VPS_HOST"], port=int(cfg["VPS_PORT"]), username=cfg["VPS_USER"],
                   password=cfg["VPS_PASS"], timeout=20, look_for_keys=False,
                   allow_agent=False)
    server = ForwardServer(("127.0.0.1", LOCAL_PORT), ForwardHandler)
    server.transport = client.get_transport()
    server.remote_host = "127.0.0.1"
    server.remote_port = 8080
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, client


def wait_for_port(port: int, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1)
            try:
                sock.connect(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.4)
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    args = ap.parse_args()

    cfg = load_env()
    server, ssh = start_tunnel(cfg)
    print(f"SSH-Tunnel 127.0.0.1:{LOCAL_PORT} -> {cfg['VPS_HOST']}:127.0.0.1:8080")

    env = dict(os.environ, API_ORIGIN=f"http://127.0.0.1:{LOCAL_PORT}", PORT=str(PREVIEW_PORT))
    preview = subprocess.Popen(
        ["node", str(ROOT / "tools" / "preview-server.mjs")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    failures = []
    try:
        if not wait_for_port(PREVIEW_PORT):
            print("Vorschau-Server startet nicht.")
            return 1
        base = f"http://127.0.0.1:{PREVIEW_PORT}"
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def check(name, fn):
            try:
                detail = fn()
                print(f"  OK    {name}" + (f"  -> {detail}" if detail else ""))
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
                failures.append(name)

        def ui():
            with opener.open(f"{base}/", timeout=30) as res:
                html = res.read().decode("utf-8", "replace")
                assert res.status == 200, res.status
                assert "Sychos Mail" in html, "Titel fehlt"
                assert res.headers.get("x-frame-options") == "DENY"
                return "index.html + Sicherheits-Header"

        def health():
            with urllib.request.urlopen(f"{base}/healthz", timeout=30) as res:
                data = json.loads(res.read())
                assert data["ok"] is True
                return f"api={data['api']}"

        def login():
            body = json.dumps({"email": args.user, "password": args.password}).encode()
            req = urllib.request.Request(
                f"{base}/api/login", data=body, method="POST",
                headers={"content-type": "application/json"},
            )
            with opener.open(req, timeout=60) as res:
                payload = json.loads(res.read())
                assert res.status == 200, res.status
                assert payload.get("email") == args.user, payload
                names = [c.name for c in jar]
                assert "wm_session" in names, names
                return f"angemeldet als {payload['email']} (Cookie {names[0]})"

        def session():
            # Cookie explizit mitschicken: es ist mit "Secure" gesetzt und wuerde
            # ueber http (Vorschau) sonst nicht gesendet — auf Cloudflare ist es https.
            values = {c.name: c.value for c in jar}
            assert "wm_session" in values, values
            req = urllib.request.Request(
                f"{base}/api/session",
                headers={"cookie": f"wm_session={values['wm_session']}"},
            )
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read())
                assert data.get("email") == args.user, data
                return f"Session gilt fuer {data['email']}"

        def config():
            with opener.open(f"{base}/api/config", timeout=30) as res:
                data = json.loads(res.read())
                return f"app_name={data.get('app_name')!r}"

        def spa_fallback():
            req = urllib.request.Request(f"{base}/mail?f=INBOX", headers={"accept": "text/html"})
            with opener.open(req, timeout=30) as res:
                html = res.read().decode("utf-8", "replace")
                assert res.status == 200 and "Sychos Mail" in html, res.status
                return "tiefer Link liefert die App"

        print("Tests:")
        check("UI wird ausgeliefert", ui)
        check("/healthz", health)
        check("Login ueber den Proxy (Cookies)", login)
        check("Session bleibt gueltig", session)
        check("/api/config", config)
        check("SPA-Fallback", spa_fallback)
    finally:
        preview.terminate()
        try:
            preview.wait(timeout=10)
        except subprocess.TimeoutExpired:
            preview.kill()
        server.shutdown()
        ssh.close()

    print()
    if failures:
        print("FEHLGESCHLAGEN:", ", ".join(failures))
        return 1
    print("Alles gruen — statische UI + API-Proxy verhalten sich wie auf Cloudflare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
