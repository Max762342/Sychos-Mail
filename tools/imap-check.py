#!/usr/bin/env python3
"""Sucht per IMAP nach einem Betreff und zeigt die neuesten Treffer.

    python tools/imap-check.py --user admin@sychos.de --password ... --subject "Injektor"
"""
import argparse
import imaplib
import ssl
import sys

try:
    import certifi

    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.178.53")
    ap.add_argument("--port", type=int, default=993)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--subject", default="")
    ap.add_argument("--folder", default="INBOX")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--insecure", action="store_true",
                    help="Zertifikat nicht pruefen (LAN, selbstsigniert)")
    args = ap.parse_args()

    ctx = CTX
    if args.insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    with imaplib.IMAP4_SSL(args.host, args.port, ssl_context=ctx) as imap:
        imap.login(args.user, args.password)
        typ, data = imap.select(args.folder, readonly=True)
        print(f"{args.folder}: {data[0].decode() if data else '?'} Nachrichten")

        if args.subject:
            typ, data = imap.search(None, "SUBJECT", f'"{args.subject}"')
        else:
            typ, data = imap.search(None, "ALL")
        ids = (data[0] or b"").split()
        print(f"Treffer: {len(ids)}")

        for uid in ids[-args.limit:]:
            typ, parts = imap.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            header = parts[0][1].decode("utf-8", "replace").strip().replace("\r\n", " | ")
            print(f"  [{uid.decode()}] {header}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
