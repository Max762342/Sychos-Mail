#!/usr/bin/env python3
"""Prueft/fuehrt Cloudflare Email Routing aus (Token muss es erlauben)."""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from importlib import import_module

cf = import_module("cf-dns")
conf = cf.cfg()
token = conf["CF_API_TOKEN"]
zone = "sychos.de"
zid = cf.zone_id(token, zone)

mode = sys.argv[1] if len(sys.argv) > 1 else "status"

if mode == "status":
    for path in ("/email/routing", "/email/routing/rules", "/email/routing/addresses"):
        res = cf.call(token, "GET", f"/zones/{zid}{path}")
        if res.get("success"):
            result = res.get("result")
            if isinstance(result, list):
                print(f"{path}: {len(result)} Eintraege")
                for item in result[:5]:
                    print("   ", json.dumps(item)[:180])
            else:
                print(f"{path}: {json.dumps(result)[:300]}")
        else:
            print(f"{path}: keine Berechtigung")
            cf.show_errors(res)

elif mode == "enable":
    res = cf.call(token, "POST", f"/zones/{zid}/email/routing/enable")
    print("enable:", "ok" if res.get("success") else "abgelehnt")
    cf.show_errors(res)

elif mode == "catchall":
    worker = sys.argv[2] if len(sys.argv) > 2 else "sychos-mail"
    body = {"name": "catch-all -> worker", "enabled": True,
            "matchers": [{"type": "all"}],
            "actions": [{"type": "worker", "value": [worker]}]}
    res = cf.call(token, "PUT", f"/zones/{zid}/email/routing/rules/catch_all", body)
    print("catch_all:", "ok" if res.get("success") else "abgelehnt")
    cf.show_errors(res)
