#!/usr/bin/env python3
"""Prueft von aussen, ob ein TCP-Port am eigenen Anschluss offen ist (check-host.net)."""
import json
import sys
import time
import urllib.request

TARGET = sys.argv[1] if len(sys.argv) > 1 else "79.140.115.19:25"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0"


def call(url: str) -> dict:
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read())


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    start = call(f"https://check-host.net/check-tcp?host={TARGET}&max_nodes=3")
    rid = start.get("request_id")
    print("Ziel:", TARGET, "| Knoten:", ", ".join((start.get("nodes") or {}).keys()))
    if not rid:
        print("Antwort:", start)
        return 1
    for _ in range(12):
        time.sleep(3)
        result = call(f"https://check-host.net/check-result/{rid}")
        if not result:
            continue
        pending = [k for k, v in result.items() if v is None]
        for node, value in result.items():
            if value is None:
                continue
            if isinstance(value, list) and value:
                entry = value[0]
                if isinstance(entry, dict) and entry.get("error"):
                    print(f"  {node:<16} FEHLER: {entry['error']}")
                elif isinstance(entry, list) and len(entry) >= 2:
                    print(f"  {node:<16} verbunden in {entry[1]:.3f}s")
                else:
                    print(f"  {node:<16} {entry}")
        if not pending:
            break
    print("Details:", f"https://check-host.net/check-report/{rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
