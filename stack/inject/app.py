"""Sychos Mail — Mail-Injektor.

Nimmt eine Mail per HTTPS (über den Cloudflare Tunnel) an und liefert sie per
LMTP an docker-mailserver. Damit kommt Mail an, ohne dass zu Hause Port 25
offen sein muss:

    Gmail -> Cloudflare Email Routing -> Email Worker (HTTPS POST)
          -> inject.sychos.de (Tunnel) -> dieser Dienst -> LMTP -> Dovecot

Der Dienst lauscht nur auf 127.0.0.1 und verlangt einen Shared Secret.
"""
from __future__ import annotations

import base64
import json
import os
import smtplib
import socketserver
import sys
from email import message_from_bytes
from email.utils import getaddresses
from http.server import BaseHTTPRequestHandler

LMTP_HOST = os.environ.get("LMTP_HOST", "127.0.0.1")
LMTP_PORT = int(os.environ.get("LMTP_PORT", "8024"))
SMTP_HOST = os.environ.get("SMTP_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "25"))
DELIVER = os.environ.get("DELIVER", "smtp")  # "smtp" (Postfix, mit Rspamd) oder "lmtp"
SECRET = os.environ.get("INJECT_SECRET", "")
MAX_BYTES = 40 * 1024 * 1024
LISTEN = os.environ.get("INJECT_LISTEN", "127.0.0.1")
PORT = int(os.environ.get("INJECT_PORT", "8099"))


def deliver(recipients: list[str], raw: bytes) -> dict:
    """Raw-Mail an Postfix (SMTP) bzw. Dovecot (LMTP) uebergeben."""
    msg = message_from_bytes(raw)
    sender = str(msg.get("From", "unknown@invalid")).strip()
    try:
        sender = getaddresses([sender])[0][1] or "unknown@invalid"
    except (IndexError, ValueError):
        sender = "unknown@invalid"
    sender = sender.replace("\r", "").replace("\n", "")

    if DELIVER == "lmtp":
        client = smtplib.LMTP(LMTP_HOST, LMTP_PORT, timeout=60)
    else:
        client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60)
    with client:
        refused = client.sendmail(sender, recipients, raw)
    if refused:
        return {"ok": False, "refused": refused}
    return {"ok": True, "delivered": recipients, "via": DELIVER}


class Handler(BaseHTTPRequestHandler):
    server_version = "SychosInject/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        if status >= 400:
            self.send_header("connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send(200, {"ok": True, "service": "sychos-inject", "lmtp": f"{LMTP_HOST}:{LMTP_PORT}"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        # Body IMMER zuerst lesen (sonst bleibt er in der Keep-Alive-Verbindung
        # liegen und wird als naechste Anfrage interpretiert).
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        if 0 < length <= MAX_BYTES:
            body = self.rfile.read(length)
        else:
            body = b""

        if self.path != "/inject":
            self._send(404, {"error": "not found"})
            return
        if not SECRET or self.headers.get("x-inject-secret", "") != SECRET:
            self._send(403, {"error": "forbidden"})
            return
        if not body:
            self._send(413, {"error": "bad size"})
            return

        try:
            payload = json.loads(body)
            raw = base64.b64decode(payload["raw_b64"], validate=True)
            recipients = [r.strip().lower() for r in payload["to"] if r.strip()]
        except (ValueError, KeyError, TypeError):
            self._send(400, {"error": "bad payload"})
            return
        if not recipients:
            self._send(400, {"error": "no recipients"})
            return

        try:
            result = deliver(recipients, raw)
        except (smtplib.SMTPException, OSError) as exc:
            self._send(502, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        self._send(200 if result["ok"] else 250, result)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    if not SECRET:
        print("INJECT_SECRET fehlt - Start abgebrochen", file=sys.stderr)
        raise SystemExit(1)
    print(f"sychos-inject auf {LISTEN}:{PORT}, LMTP {LMTP_HOST}:{LMTP_PORT}", flush=True)
    with Server((LISTEN, PORT), Handler) as httpd:
        httpd.serve_forever()
