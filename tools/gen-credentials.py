#!/usr/bin/env python3
"""Erzeugt die Zugangsdaten-Datei auf dem Desktop aus dem laufenden System.

Liest per SSH: stack/.env (Panel-Zugang, DB), stack/credentials.log (Postfaecher)
und den Container-Status. Ergebnis:

    C:\\Users\\Schueler\\Desktop\\Sychos-Mail-Zugangsdaten.txt

    python tools/gen-credentials.py
"""
import io
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
TARGET = Path.home() / "Desktop" / "Sychos-Mail-Zugangsdaten.txt"
REMOTE = "/opt/sychos-mail/stack"


def load_env() -> dict:
    cfg = {}
    for line in (Path(__file__).with_name("vps.env")).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    return cfg


def remote(cfg, command: str) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg["VPS_HOST"], port=int(cfg["VPS_PORT"]), username=cfg["VPS_USER"],
                   password=cfg["VPS_PASS"], timeout=20, look_for_keys=False,
                   allow_agent=False)
    try:
        _, stdout, _ = client.exec_command(command, timeout=120)
        return stdout.read().decode("utf-8", "replace")
    finally:
        client.close()


def parse_env(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def dkim_record(cfg) -> str:
    """Liest den oeffentlichen DKIM-Schluessel aus dem Mailserver-Container."""
    raw = remote(
        cfg,
        "docker exec sychos-mailserver sh -c 'cat /tmp/docker-mailserver/rspamd/dkim/*.public.txt' "
        "2>/dev/null || true",
    )
    if not raw.strip():
        return ""
    # BIND-Format: mail._domainkey IN TXT ( "v=DKIM1; k=rsa; " "p=MIIB..." ) ;
    parts = re.findall(r'"([^"]*)"', raw)
    value = "".join(parts) if parts else raw.replace("\n", "").replace("\t", "")
    return " ".join(value.split())


def local_git(*args: str) -> str:
    """Fuehrt git im Projektordner aus (fuer Repo-/Remote-Infos)."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20
        )
        return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def github_block(env: dict) -> str:
    remote = local_git("remote", "get-url", "origin")
    if not remote:
        return "  (kein Git-Remote gesetzt)\n"
    match = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", remote)
    if not match:
        return f"  Repo: {remote}\n"
    owner, repo = match.group(1), match.group(2)
    web = f"https://github.com/{owner}/{repo}"
    pages = f"https://{owner}.github.io/{repo}/"
    return (
        f"  Repo:     {web}\n"
        f"  Pages:    {pages}\n"
        f"  Actions:  {web}/actions\n"
        f"  Secrets:  {web}/settings/secrets/actions\n"
        f"  Deploy:   git push  (GitHub Actions baut die UI und deployt den Worker)\n"
        f"  Secrets setzen:\n"
        f"    gh secret set CLOUDFLARE_API_TOKEN --repo {owner}/{repo}\n"
        f"    gh secret set CLOUDFLARE_ACCOUNT_ID --repo {owner}/{repo}\n"
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = load_env()
    env_text = remote(cfg, f"cat {REMOTE}/.env")
    env = parse_env(env_text)
    creds = remote(cfg, f"cat {REMOTE}/credentials.log 2>/dev/null || true")
    status = remote(cfg, "docker ps --filter name=sychos- --format '{{.Names}}|{{.Status}}' 2>&1")
    public_ip = remote(cfg, "curl -s --max-time 8 https://api.ipify.org || echo unbekannt")
    dkim = dkim_record(cfg)
    local_ip = cfg.get("VPS_HOST", "")

    domain = env.get("DOMAIN", "sychos.de")
    mail_host = env.get("MAIL_HOSTNAME", f"mail.{domain}")
    panel_mail = env.get("PANEL_ADMIN_EMAIL", f"admin@{domain}")
    panel_pass = env.get("PANEL_ADMIN_PASSWORD", "")
    db_pass = env.get("POSTGRES_PASSWORD", "")
    quota = int(env.get("DEFAULT_QUOTA_MB", "3072"))

    rows = []
    for line in creds.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append(parts)
    # Neueste Zugangsdaten pro Adresse gewinnt
    latest = {}
    for parts in rows:
        latest[parts[1]] = parts
    mailboxes = [latest[k] for k in sorted(latest)]

    out = io.StringIO()
    w = out.write
    w("=" * 66 + "\n")
    w("  SYCHOS MAIL — ZUGANGSDATEN\n")
    w("=" * 66 + "\n")
    w(f"Erstellt: {datetime.now():%d.%m.%Y %H:%M}\n\n")

    w("-- CONTROL PANEL (Postfaecher verwalten) " + "-" * 24 + "\n")
    w(f"  URL:      https://admin.{domain}\n")
    w(f"  lokal:    http://127.0.0.1:8090  (nur auf dem Server)\n")
    w(f"  E-Mail:   {panel_mail}\n")
    w(f"  Passwort: {panel_pass}\n\n")

    w("-- WEBMAIL (Postfach lesen/schreiben) " + "-" * 28 + "\n")
    w(f"  URL:      https://{domain}\n")
    w(f"  Login:    <eigene E-Mail-Adresse> + Postfach-Passwort\n\n")

    w("-- POSTFAECHER " + "-" * 50 + "\n")
    if mailboxes:
        for stamp, email, password, extra in [(p[0], p[1], p[2], p[3] if len(p) > 3 else "") for p in mailboxes]:
            try:
                quota_text = f"{int(extra)} MB (= {int(extra)/1024:g} GB)"
            except (TypeError, ValueError):
                quota_text = extra or f"{quota} MB"
            w(f"  {email}\n")
            w(f"    Passwort: {password}\n")
            w(f"    Speicher: {quota_text}\n")
            w(f"    IMAP:     {mail_host}:993  (SSL/TLS)\n")
            w(f"    SMTP:     {mail_host}:465  (SSL/TLS)  oder  :587 (STARTTLS)\n")
            w(f"    angelegt: {stamp}\n\n")
    else:
        w("  (noch keine Postfaecher angelegt)\n\n")

    w("-- MAILSERVER " + "-" * 51 + "\n")
    w(f"  Hostname:       {mail_host}\n")
    w(f"  IMAP / SMTP:    993 / 465 (SSL), 587 (STARTTLS), 143 (STARTTLS)\n")
    w(f"  SMTP eingehend: 25\n")
    w(f"  Oeffentliche IP: {public_ip.strip()}\n\n")

    w("-- DIREKT AUF DEM SERVER " + "-" * 41 + "\n")
    w(f"  ssh {cfg['VPS_USER']}@{cfg['VPS_HOST']}\n")
    w(f"  Passwort:            {cfg['VPS_PASS']}\n")
    w(f"  Projekt:             /opt/sychos-mail\n")
    w(f"  Postgres-Passwort:   {db_pass}\n")
    w(f"  DB-Verbindung:       postgres://sychos:{db_pass}@127.0.0.1:5432/panel\n\n")

    w("-- STATUS DER CONTAINER " + "-" * 41 + "\n")
    for line in status.splitlines():
        if "|" in line:
            name, state = line.split("|", 1)
            w(f"  {name:<22} {state}\n")
    w("\n")

    w("-- GITHUB (Quellcode + Cloudflare-Deploy) " + "-" * 24 + "\n")
    w(github_block(env))

    w("-- DNS-EINTRAEGE (Cloudflare / IONOS) " + "-" * 29 + "\n")
    w(f"  A     mail                 {public_ip.strip()}      (DNS only, graue Wolke)\n")
    w(f"  MX    @                    {mail_host}  Prio 10   (DNS only)\n")
    w("  TXT   @                    v=spf1 mx ~all\n")
    w("  TXT   _dmarc               v=DMARC1; p=quarantine; rua=mailto:postmaster@"
      + domain + "\n")
    w(f"  TXT   mail._domainkey      {dkim or '(noch nicht erzeugt — scripts/dkim-setup.sh)'}\n")
    w(f"  CNAME autoconfig           {mail_host}   (DNS only)\n")
    w(f"  CNAME autodiscover         {mail_host}   (DNS only)\n")
    w("  PTR   Reverse-DNS der IP   " + mail_host + "   (beim Hoster/Anschluss setzen!)\n\n")

    w("-- NOCH ZU TUN " + "-" * 52 + "\n")
    w("  1. Domain sychos.de zu Cloudflare ziehen (Nameserver bei IONOS aendern).\n")
    w("  2. Auf dem Server:  cd /opt/sychos-mail/stack && bash scripts/cloudflare-setup.sh\n")
    w("     -> Tunnel fuer origin.sychos.de (API) + admin.sychos.de (Panel).\n")
    w("  3. Cloudflare-Secrets im GitHub-Repo setzen (dann deployt Actions sychos.de):\n")
    w("       gh secret set CLOUDFLARE_API_TOKEN --repo <owner>/sychos-mail\n")
    w("       gh secret set CLOUDFLARE_ACCOUNT_ID --repo <owner>/sychos-mail\n")
    w("  4. Router: Ports 25, 465, 587, 993 -> " + local_ip + " weiterleiten\n")
    w("     (FRITZ!Box: Internet > Freigaben > Portfreigaben).\n")
    w("  5. DNS-Eintraege oben eintragen (DKIM-Wert steht dabei).\n")
    w("  6. Echtes TLS-Zertifikat (optional): CF_TOKEN=... bash scripts/letsencrypt.sh\n\n")
    w("Hinweis: Diese Datei enthaelt Klartext-Passwoerter. Nicht weitergeben.\n")
    w("Quelle der Postfaecher: /opt/sychos-mail/stack/credentials.log\n")

    TARGET.write_text(out.getvalue(), encoding="utf-8")
    print(f"geschrieben: {TARGET}")
    print(f"Postfaecher: {len(mailboxes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
