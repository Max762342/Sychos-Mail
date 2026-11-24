#!/usr/bin/env python3
"""Verschickt die Willkommensmail an ein Postfach und prueft den Eingang.

    python tools/welcome.py --user admin@sychos.de --password ...
"""
import argparse
import imaplib
import smtplib
import ssl
import time
from email.message import EmailMessage

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TEXT = """Willkommen bei Sychos Mail!

Dein Postfach ist eingerichtet und hat 3 GB Speicher.

Webmail ...... https://sychos.de
Verwaltung ... https://admin.sychos.de
IMAP ......... mail.sychos.de:993 (SSL/TLS)
SMTP ......... mail.sychos.de:465 (SSL/TLS) oder 587 (STARTTLS)
Benutzername . deine komplette E-Mail-Adresse

Tipps:
  * Im Webmail: "c" schreibt eine neue Mail, "/" sucht, "j"/"k" blaettert.
  * Ordner, Signaturen und Absender-Identitaeten stellst du in den Einstellungen ein.
  * Anhaenge bis 25 MB, Nachrichten bis 50 MB.

Viel Spass!
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.178.53")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    args = ap.parse_args()

    msg = EmailMessage()
    msg["From"] = f"Sychos Mail <{args.user}>"
    msg["To"] = args.user
    msg["Subject"] = "Willkommen bei Sychos Mail"
    msg.set_content(TEXT)

    with smtplib.SMTP_SSL(args.host, 465, context=CTX, timeout=30) as smtp:
        smtp.login(args.user, args.password)
        smtp.send_message(msg)
    print(f"Willkommensmail an {args.user} gesendet")

    imap = imaplib.IMAP4_SSL(args.host, 993, ssl_context=CTX)
    imap.login(args.user, args.password)
    imap.select("INBOX")
    for _ in range(15):
        typ, data = imap.search(None, "SUBJECT", '"Willkommen bei Sychos Mail"')
        if (data[0] or b"").split():
            typ, quota = imap.getquotaroot("INBOX")
            imap.logout()
            print("Im Postfach angekommen — Login per IMAP funktioniert.")
            return 0
        time.sleep(2)
    imap.logout()
    print("Mail noch nicht sichtbar (Zustellung braucht evtl. laenger).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
