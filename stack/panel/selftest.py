#!/usr/bin/env python3
"""Funktionstest des Control Panels ohne Browser (Flask-Testclient).

Prüft: Anmeldung, Dashboard, Postfach anlegen (inkl. Mailserver + 3-GB-Quota),
Anzeige in der Liste, Löschen. Muss auf dem Host im venv laufen:

    cd /opt/sychos-mail/stack/panel
    set -a; . ../.env; set +a
    PANEL_COOKIE_SECURE=0 .venv/bin/python selftest.py
"""
import os
import re
import secrets
import sys

os.environ["PANEL_COOKIE_SECURE"] = "0"

import app as panel  # noqa: E402  (nach dem Setzen der Umgebung)

FAILS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("  OK    " if condition else "  FAIL  ") + name + (f"  -> {detail}" if detail else ""))
    if not condition:
        FAILS.append(name)


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    return match.group(1) if match else ""


def main() -> int:
    panel.app.config.update(SESSION_COOKIE_SECURE=False, TESTING=True)
    client = panel.app.test_client()

    print("== Anmeldung ==")
    resp = client.get("/login")
    check("Login-Seite laedt", resp.status_code == 200, f"HTTP {resp.status_code}")

    resp = client.post("/login", data={"email": "falsch@sychos.de", "password": "x"})
    check("Falsches Passwort wird abgelehnt", resp.status_code == 200)

    resp = client.post(
        "/login",
        data={"email": panel.ADMIN_EMAIL, "password": panel.ADMIN_PASSWORD},
        follow_redirects=False,
    )
    check("Admin-Login", resp.status_code == 302, f"HTTP {resp.status_code}")

    print("== Dashboard ==")
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    check("Dashboard laedt", resp.status_code == 200, f"HTTP {resp.status_code}")
    check("CSRF-Token vorhanden", bool(csrf_from(html)))
    check("Tabelle/Postfachbereich da", "Postfächer" in html)

    token = csrf_from(html)
    with panel.app.app_context():
        domain_row = panel.query_one("SELECT * FROM domains ORDER BY id LIMIT 1")
    check("Domain in der Datenbank", domain_row is not None)

    print("== Postfach anlegen ==")
    local = "selftest" + secrets.token_hex(3)
    email = f"{local}@{domain_row['name']}"
    resp = client.post(
        "/postfaecher/neu",
        data={"csrf": token, "local": local, "domain_id": domain_row["id"],
              "quota_mb": "3072"},
        follow_redirects=False,
    )
    check("Anlegen umgeleitet", resp.status_code == 302, f"HTTP {resp.status_code}")

    resp = client.get("/postfaecher/erstellt")
    page = resp.get_data(as_text=True)
    check("Erfolgsseite zeigt Adresse", email in page, email)
    password = re.search(r"<code>([A-Za-z0-9]{18})</code>", page)
    check("Passwort wird angezeigt", password is not None)

    with panel.app.app_context():
        row = panel.query_one("SELECT * FROM mailboxes WHERE email = %s", (email,))
    check("Postfach in der Datenbank", row is not None)
    check("Quota = 3 GB", row is not None and row["quota_mb"] == 3072,
          f"{row['quota_mb'] if row else '?'} MB")

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    check("Postfach in der Liste", email in html)

    print("== Quota am Mailserver ==")
    with panel.app.app_context():
        usage = panel.quota_usage(email)
    check("doveadm liefert Quota", usage is not None,
          f"{usage}" if usage else "keine Antwort")
    if usage:
        check("Quota-Limit 3072 MB", usage["limit_mb"] == 3072, f"{usage['limit_mb']} MB")

    print("== Passwort neu setzen ==")
    token = csrf_from(html)
    resp = client.post(
        f"/postfaecher/{row['id']}/passwort",
        data={"csrf": token, "password": "NeuesPasswort123"}, follow_redirects=False,
    )
    check("Passwort setzen umgeleitet", resp.status_code == 302, f"HTTP {resp.status_code}")

    print("== Loeschen ==")
    resp = client.post(
        f"/postfaecher/{row['id']}/loeschen",
        data={"csrf": token, "bestaetigung": email}, follow_redirects=False,
    )
    check("Loeschen umgeleitet", resp.status_code == 302, f"HTTP {resp.status_code}")
    with panel.app.app_context():
        gone = panel.query_one("SELECT 1 FROM mailboxes WHERE email = %s", (email,))
    if gone is not None:
        page = client.get("/").get_data(as_text=True)
        for msg in re.findall(r'<div class="flash[^"]*">(.*?)</div>', page, re.S):
            print("        Hinweis vom Panel:", " ".join(msg.split()))
    check("Postfach aus der Datenbank entfernt", gone is None)

    print("== System-Seite ==")
    resp = client.get("/system")
    check("Systemseite laedt", resp.status_code == 200, f"HTTP {resp.status_code}")

    print()
    if FAILS:
        print(f"{len(FAILS)} Test(s) fehlgeschlagen: {', '.join(FAILS)}")
        return 1
    print("Alle Panel-Tests gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
