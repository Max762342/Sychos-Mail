#!/usr/bin/env python3
"""Live-Check der ausgerollten Sychos-Mail-Seite (Cloudflare Worker).

    python tools/verify-live.py --url https://sychos.de --user admin@sychos.de --password ...
"""
import argparse
import http.cookiejar
import json
import ssl
import sys
import time
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def get(url: str, **kwargs):
    """Request mit Browser-UA (Cloudflare Bot Fight Mode blockt Python-UA mit 403)."""
    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("user-agent", UA)
    headers.setdefault("accept", "text/html,application/json;q=0.9,*/*;q=0.8")
    return urllib.request.Request(url, headers=headers, **kwargs)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://sychos.de")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--wait", type=int, default=0, help="Sekunden warten (Deploy abwarten)")
    args = ap.parse_args()

    if args.wait:
        time.sleep(args.wait)

    base = args.url.rstrip("/")
    jar = http.cookiejar.CookieJar()
    failures = []

    def check(name, fn):
        start = time.time()
        try:
            detail = fn()
            ms = int((time.time() - start) * 1000)
            print(f"  OK    {name} in {ms} ms" + (f"  -> {detail}" if detail else ""))
        except Exception as exc:  # noqa: BLE001
            ms = int((time.time() - start) * 1000)
            print(f"  FAIL  {name} in {ms} ms: {type(exc).__name__}: {exc}")
            failures.append(name)

    def ui():
        req = get(base + "/", headers={"accept": "text/html"})
        with urllib.request.urlopen(req, timeout=30, context=CTX) as res:
            html = res.read().decode("utf-8", "replace")
            assert res.status == 200, res.status
            assert "Sychos Mail" in html, "Titel fehlt im HTML"
            assert res.headers.get("x-frame-options") == "DENY", "Security-Header fehlt"
            return f"{len(html)} Bytes, {res.headers.get('server', '?')}"

    def health():
        with urllib.request.urlopen(get(base + "/healthz"), timeout=30, context=CTX) as res:
            data = json.loads(res.read())
            return f"api={data.get('api')}"

    def config():
        with urllib.request.urlopen(get(base + "/api/config"), timeout=45, context=CTX) as res:
            data = json.loads(res.read())
            return f"app_name={data.get('app_name')!r} v{data.get('version')}"

    def login():
        body = json.dumps({"email": args.user, "password": args.password}).encode()
        req = get(base + "/api/login", data=body, method="POST",
                  headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60, context=CTX) as res:
            data = json.loads(res.read())
            cookies = res.headers.get_all("set-cookie") or []
            assert res.status == 200, res.status
            assert data.get("email") == args.user, data
            assert cookies, "kein Set-Cookie"
            for c in cookies:
                head = c.split(";")[0]
                name, value = head.split("=", 1)
                jar.set_cookie(http.cookiejar.Cookie(
                    0, name, value, None, False, ".sychos.de" if "sychos.de" in base else "",
                    False, False, "/", True, False, None, True, None, None, {}))
            return f"angemeldet als {data['email']}, csrf={bool(data.get('csrf'))}"

    def session():
        values = {c.name: c.value for c in jar}
        if not values:
            raise AssertionError("kein Cookie aus dem Login")
        req = get(base + "/api/session",
                  headers={"cookie": "; ".join(f"{k}={v}" for k, v in values.items())})
        with urllib.request.urlopen(req, timeout=45, context=CTX) as res:
            data = json.loads(res.read())
            assert data.get("email") == args.user, data
            return f"Session gilt fuer {data['email']}"

    def folders():
        values = {c.name: c.value for c in jar}
        req = get(base + "/api/folders",
                  headers={"cookie": "; ".join(f"{k}={v}" for k, v in values.items())})
        with urllib.request.urlopen(req, timeout=60, context=CTX) as res:
            data = json.loads(res.read())
            return f"{len(data)} Ordner (IMAP erreichbar): " + ", ".join(f.get("name", "?") for f in data[:4])

    print(f"Ziel: {base}")
    check("UI-Auslieferung (/)", ui)
    check("/healthz", health)
    check("/api/config (Tunnel -> Webmail)", config)
    check("Login (/api/login)", login)
    check("Session (/api/session)", session)
    check("Ordnerliste (/api/folders = IMAP)", folders)

    print()
    if failures:
        print("FEHLGESCHLAGEN:", ", ".join(failures))
        return 1
    print("Alles gruen — Webseite, API-Tunnel und Mail-Login funktionieren.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
