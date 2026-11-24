#!/usr/bin/env python3
"""Testet SMTP/IMAP-Logins gegen IONOS (ohne etwas zu speichern).

    python tools/test-ionos-login.py <benutzer> <passwort>
"""
import smtplib
import socket
import ssl
import sys

try:
    import certifi

    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # Windows-Python ohne CA-Bundle
    CTX = ssl.create_default_context()
    CTX.check_hostname = False
    CTX.verify_mode = ssl.CERT_NONE
    print("(Hinweis: CA-Bundle fehlt, Zertifikat wird nicht geprueft — nur fuer diesen Test)")


def test_smtp(user: str, password: str) -> str:
    try:
        with smtplib.SMTP("smtp.ionos.de", 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=CTX)
            smtp.ehlo()
            smtp.login(user, password)
            return "OK (Login akzeptiert)"
    except smtplib.SMTPAuthenticationError as exc:
        return f"Login abgelehnt: {exc.smtp_code} {exc.smtp_error[:120]!r}"
    except (smtplib.SMTPException, socket.error, ssl.SSLError) as exc:
        return f"Fehler: {type(exc).__name__}: {exc}"


def test_imap(user: str, password: str) -> str:
    import imaplib

    try:
        with imaplib.IMAP4_SSL("imap.ionos.de", 993, ssl_context=CTX) as imap:
            imap.login(user, password)
            return "OK (Login akzeptiert)"
    except imaplib.IMAP4.error as exc:
        return f"Login abgelehnt: {str(exc)[:120]}"
    except (socket.error, ssl.SSLError) as exc:
        return f"Fehler: {type(exc).__name__}: {exc}"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    user, password = sys.argv[1], sys.argv[2]
    print(f"Benutzer: {user}")
    print("SMTP smtp.ionos.de:587 ->", test_smtp(user, password))
    print("IMAP imap.ionos.de:993 ->", test_imap(user, password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
