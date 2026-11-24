#!/usr/bin/env python3
"""End-to-End-Test fuer den Sychos-Mailserver.

Prueft IMAPS (993), SMTPS (465), Submission (587) und die Quota-Abfrage,
indem ein Postfach eine Mail an ein zweites schickt und sie dort ankommt.

    python tools/verify.py --user-a test@sychos.de --pass-a geheim \
                           --user-b test2@sychos.de --pass-b geheim2
"""
import argparse
import imaplib
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def step(name, fn):
    try:
        result = fn()
        print(f"  OK    {name}" + (f"  -> {result}" if result else ""))
        return True
    except Exception as exc:  # noqa: BLE001 - Diagnose soll weiterlaufen
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.178.53")
    ap.add_argument("--imap-port", type=int, default=993)
    ap.add_argument("--smtp-port", type=int, default=465)
    ap.add_argument("--submission-port", type=int, default=587)
    ap.add_argument("--user-a", required=True)
    ap.add_argument("--pass-a", required=True)
    ap.add_argument("--user-b", required=True)
    ap.add_argument("--pass-b", required=True)
    args = ap.parse_args()

    failures = []
    subject = f"Sychos Selbsttest {int(time.time())}"

    print(f"Host {args.host}")

    def imap_a():
        m = imaplib.IMAP4_SSL(args.host, args.imap_port, ssl_context=CTX)
        m.login(args.user_a, args.pass_a)
        typ, data = m.select("INBOX")
        caps = m.capabilities
        return f"INBOX: {data[0].decode() if data and data[0] else '?'}, IDLE={('IDLE' in caps)}"

    def quota():
        m = imaplib.IMAP4_SSL(args.host, args.imap_port, ssl_context=CTX)
        m.login(args.user_a, args.pass_a)
        typ, data = m.getquotaroot("INBOX")
        m.logout()
        flat = [d.decode(errors="replace") for d in data if isinstance(d, bytes)]
        return " | ".join(flat)

    def send():
        msg = EmailMessage()
        msg["From"] = args.user_a
        msg["To"] = args.user_b
        msg["Subject"] = subject
        msg.set_content("Dies ist ein automatischer Test von Sychos Mail.")
        with smtplib.SMTP_SSL(args.host, args.smtp_port, context=CTX, timeout=30) as s:
            code, banner = s.ehlo()
            s.login(args.user_a, args.pass_a)
            s.send_message(msg)
        return f"gesendet an {args.user_b}"

    def submit_starttls():
        with smtplib.SMTP(args.host, args.submission_port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=CTX)
            s.ehlo()
            s.login(args.user_a, args.pass_a)
        return "STARTTLS + Login auf 587"

    def receive():
        m = imaplib.IMAP4_SSL(args.host, args.imap_port, ssl_context=CTX)
        m.login(args.user_b, args.pass_b)
        m.select("INBOX")
        for _ in range(15):
            typ, data = m.search(None, "SUBJECT", f'"{subject}"')
            ids = (data[0] or b"").split()
            if ids:
                typ, body = m.fetch(ids[-1], "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])")
                m.store(ids[-1], "+FLAGS", "(\\Deleted)")
                m.expunge()
                m.logout()
                header = body[0][1].decode(errors="replace").strip().replace("\r\n", " ")
                return f"angekommen: {header}"
            time.sleep(2)
        m.logout()
        raise TimeoutError("Mail kam nach 30 s nicht an")

    if not step("IMAPS 993 Login Postfach A", imap_a):
        failures.append("IMAP A")
    if not step("Quota (GETQUOTAROOT)", quota):
        failures.append("Quota")
    if not step("SMTPS 465 Login + Versand", send):
        failures.append("SMTP 465")
    if not step("Submission 587 STARTTLS + Login", submit_starttls):
        failures.append("SMTP 587")
    if not step("Zustellung an Postfach B", receive):
        failures.append("Zustellung")

    print()
    if failures:
        print("FEHLGESCHLAGEN:", ", ".join(failures))
        return 1
    print("Alles gruen — Mailserver, Login, Versand, Zustellung und Quota funktionieren.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
