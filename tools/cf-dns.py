#!/usr/bin/env python3
"""Cloudflare-DNS per API verwalten (Sychos Mail).

    python tools/cf-dns.py verify                 # Token pruefen
    python tools/cf-dns.py zones                  # Zonen + Status
    python tools/cf-dns.py records sychos.com     # Records einer Zone
    python tools/cf-dns.py fix-origin             # origin.<zone> -> Tunnel-CNAME
    python tools/cf-dns.py set <zone> <typ> <name> <inhalt> [--no-proxy]
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
HERE = Path(__file__).resolve().parent


def cfg() -> dict:
    values = {}
    path = HERE / "cf.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def call(token: str, method: str, path: str, payload=None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return json.loads(body)
        except ValueError:
            return {"success": False, "errors": [{"message": f"HTTP {exc.code}: {body[:200]!r}"}]}


def show_errors(result: dict) -> None:
    for err in result.get("errors") or []:
        print("  Fehler:", err.get("message") or err)


def zone_id(token: str, name: str) -> str:
    res = call(token, "GET", f"/zones?name={name}")
    if not res.get("success") or not res.get("result"):
        show_errors(res)
        raise SystemExit(f"Zone {name} nicht gefunden/kein Zugriff")
    return res["result"][0]["id"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    conf = cfg()
    token = conf.get("CF_API_TOKEN", "")
    if not token:
        print("Kein CF_API_TOKEN in tools/cf.env")
        return 2

    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["verify", "zones", "records", "fix-origin", "set", "accounts", "del"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--no-proxy", action="store_true")
    args = ap.parse_args()

    if args.action == "verify":
        res = call(token, "GET", "/user/tokens/verify")
        status = (res.get("result") or {}).get("status", "?") if res.get("success") else "ungueltig"
        print("Token:", status)
        if not res.get("success"):
            show_errors(res)
            return 1
        return 0

    if args.action == "zones":
        res = call(token, "GET", "/zones?per_page=50")
        if not res.get("success"):
            show_errors(res)
            return 1
        for z in res["result"]:
            acc = z.get("account") or {}
            print(f"  {z['name']:<20} status={z['status']:<10} account={acc.get('name','?')} ({acc.get('id','?')})")
        return 0

    if args.action == "records":
        zone = args.args[0]
        zid = zone_id(token, zone)
        res = call(token, "GET", f"/zones/{zid}/dns_records?per_page=100")
        if not res.get("success"):
            show_errors(res)
            return 1
        print(f"{'Typ':<8} {'Name':<28} {'Ziel':<44} Proxy")
        for r in res["result"]:
            proxied = "an" if r.get("proxied") else "-"
            print(f"  {r['type']:<8} {r['name']:<28} {str(r.get('content'))[:44]:<44} {proxied}")
        return 0

    if args.action == "accounts":
        res = call(token, "GET", "/accounts?per_page=20")
        if not res.get("success"):
            show_errors(res)
            return 1
        for a in res["result"]:
            sub = call(token, "GET", f"/accounts/{a['id']}/workers/subdomain")
            subdomain = (sub.get("result") or {}).get("subdomain", "?") if sub.get("success") else "kein Zugriff"
            print(f"  {a['name']:<24} id={a['id']}  workers.dev-Subdomain={subdomain}")
        return 0

    if args.action == "del":
        if len(args.args) < 2:
            print("Aufruf: del <zone> <name>")
            return 2
        zone, name = args.args[:2]
        zid = zone_id(token, zone)
        res = call(token, "GET", f"/zones/{zid}/dns_records?name={name}")
        records = res.get("result") or []
        if not records:
            print("  nichts zu loeschen")
            return 0
        for rec in records:
            out = call(token, "DELETE", f"/zones/{zid}/dns_records/{rec['id']}")
            print(f"  geloescht: {rec['type']} {rec['name']}" if out.get("success") else "  Fehler")
            if not out.get("success"):
                show_errors(out)
        return 0

    if args.action == "fix-origin":
        fqdn = conf.get("CF_MAIL_ORIGIN", "origin.sychos.com")
        zone = fqdn.split(".", 1)[1]
        target = f"{conf['CF_TUNNEL_ID']}.cfargotunnel.com"
        zid = zone_id(token, zone)
        res = call(token, "GET", f"/zones/{zid}/dns_records?name={fqdn}")
        existing = res.get("result") or []
        payload = {"type": "CNAME", "name": fqdn, "content": target, "proxied": True,
                   "ttl": 1, "comment": "Sychos Mail API-Origin (Tunnel)"}
        if existing:
            for rec in existing:
                print(f"  aendere {rec['type']} {rec['name']} ({rec.get('content')}) -> CNAME {target}")
                upd = call(token, "PUT", f"/zones/{zid}/dns_records/{rec['id']}", payload)
                if not upd.get("success"):
                    show_errors(upd)
                    return 1
            print("  OK:", fqdn, "->", target)
        else:
            created = call(token, "POST", f"/zones/{zid}/dns_records", payload)
            if not created.get("success"):
                show_errors(created)
                return 1
            print("  OK angelegt:", fqdn, "->", target)
        return 0

    if args.action == "set":
        if len(args.args) < 4:
            print("Aufruf: set <zone> <typ> <name> <inhalt> [--no-proxy]")
            return 2
        zone, rtype, name, content = args.args[:4]
        zid = zone_id(token, zone)
        payload = {"type": rtype.upper(), "name": name, "content": content, "ttl": 1}
        if rtype.upper() in {"A", "AAAA", "CNAME"}:
            payload["proxied"] = not args.no_proxy
        res = call(token, "GET", f"/zones/{zid}/dns_records?name={name}&type={rtype.upper()}")
        existing = res.get("result") or []
        if existing:
            upd = call(token, "PUT", f"/zones/{zid}/dns_records/{existing[0]['id']}", payload)
            ok = upd.get("success")
            print("  aktualisiert" if ok else "  Fehler")
            if not ok:
                show_errors(upd)
                return 1
        else:
            created = call(token, "POST", f"/zones/{zid}/dns_records", payload)
            ok = created.get("success")
            print("  angelegt" if ok else "  Fehler")
            if not ok:
                show_errors(created)
                return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
