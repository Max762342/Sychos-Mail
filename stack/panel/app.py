"""Sychos Control Panel — Postfaecher anlegen und verwalten.

Laeuft auf dem Host (gunicorn, 127.0.0.1:8090) und spricht mit
  * Postgres  -> Login-Datenbank / Konten (127.0.0.1:5432, DB "panel")
  * docker    -> `docker exec sychos-mailserver setup ...` (Konten im Mailserver)
                 `docker exec sychos-mailserver doveadm quota get ...` (Speicher)

Das Panel ist die Quelle der Wahrheit fuer Postfaecher; der Mailserver wird
daraus synchron gehalten. Ein Postfach bekommt standardmaessig 3 GB.
"""
from __future__ import annotations

import os
import re
import secrets
import string
import subprocess
import time
from datetime import datetime, timedelta

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

try:  # psycopg 3 (Python 3.12+ / 3.14, fertige Wheels)
    import psycopg
    from psycopg.rows import dict_row as _dict_row

    DB_ERROR = psycopg.Error

    def _connect(url: str):
        return psycopg.connect(url, row_factory=_dict_row)
except ImportError:  # pragma: no cover - aeltere Umgebungen
    import psycopg2
    import psycopg2.extras

    DB_ERROR = psycopg2.Error

    def _connect(url: str):
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


DOMAIN = env("DOMAIN", "sychos.de")
APP_NAME = env("APP_NAME", "Sychos Mail")
DEFAULT_QUOTA_MB = int(env("DEFAULT_QUOTA_MB", "3072"))
MAIL_CONTAINER = env("MAIL_CONTAINER", "sychos-mailserver")
DOCKER_BIN = env("DOCKER_BIN", "docker")
PANEL_DATABASE_URL = env(
    "PANEL_DATABASE_URL",
    "postgres://sychos:sychos@127.0.0.1:5432/panel",
)
ADMIN_EMAIL = env("PANEL_ADMIN_EMAIL", f"admin@{DOMAIN}")
ADMIN_PASSWORD = env("PANEL_ADMIN_PASSWORD", "")

LOCALPART_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,29}[a-z0-9])?$")

app = Flask(__name__)
app.secret_key = env("PANEL_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env("PANEL_COOKIE_SECURE", "1") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=1024 * 1024,
)


# --------------------------------------------------------------------------
# Datenbank
# --------------------------------------------------------------------------
def db():
    if "db" not in g:
        conn = _connect(PANEL_DATABASE_URL)
        conn.autocommit = False
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql: str, args=(), commit: bool = False):
    conn = db()
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        rows = cur.fetchall() if cur.description else []
    if commit:
        conn.commit()
    return rows


def query_one(sql: str, args=(), commit: bool = False):
    rows = query(sql, args, commit=commit)
    return rows[0] if rows else None


def log_event(actor, action: str, detail: str = "") -> None:
    try:
        query("INSERT INTO events (actor, action, detail) VALUES (%s, %s, %s)",
              (actor, action, detail), commit=True)
    except DB_ERROR:
        db().rollback()


def record_credentials(email: str, password: str, quota_mb) -> None:
    """Haengt neue Zugangsdaten an credentials.log (600) — Quelle fuer die
    Zugangsdaten-Datei auf dem Desktop."""
    path = env("CREDENTIALS_FILE", "/opt/sychos-mail/stack/credentials.log")
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M}\t{email}\t{password}\t{quota_mb}\n")
        os.chmod(path, 0o600)
    except OSError:
        pass



# --------------------------------------------------------------------------
# Mailserver (docker-mailserver)
# --------------------------------------------------------------------------
def dms(*args: str, confirm: bool = False, timeout: int = 180):
    """Fuehrt `setup <args>` im Mailserver-Container aus. -> (ok, ausgabe)"""
    cmd = [DOCKER_BIN, "exec", "-i", MAIL_CONTAINER, "setup", *args]
    try:
        proc = subprocess.run(
            cmd,
            input="y\n" if confirm else "",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "docker wurde nicht gefunden"
    except subprocess.TimeoutExpired:
        return False, "Zeitueberschreitung bei der Mailserver-Konfiguration"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, out


def dms_delete(email: str):
    """Konto samt Maildaten loeschen (`-y` = ohne Rueckfrage)."""
    ok, out = dms("email", "del", "-y", email)
    if ok:
        return True, out
    return dms("email", "del", email)


def limit_mb_for(email: str) -> int:
    row = query_one("SELECT quota_mb FROM mailboxes WHERE email = %s", (email,))
    return int(row["quota_mb"]) if row else DEFAULT_QUOTA_MB


def quota_usage(email: str):
    """-> dict(pct, used_mb, limit_mb) oder None (Mailserver nicht erreichbar).

    Dovecot meldet Wert und Limit in derselben Einheit — das Verhaeltnis ist
    damit unabhaengig von der Einheit und ergibt direkt den Fuellstand.
    """
    cmd = [DOCKER_BIN, "exec", MAIL_CONTAINER, "doveadm", "quota", "get", "-u", email]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        # Konto ist angelegt, aber noch nie per IMAP geoeffnet -> 0 belegt.
        if "does not exist" in output or "doesn't exist" in output:
            return {"pct": 0, "used_mb": 0.0, "limit_mb": limit_mb_for(email)}
        return None
    limit_mb = limit_mb_for(email)
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        upper = [p.upper() for p in parts]
        if "STORAGE" not in upper:
            continue
        idx = upper.index("STORAGE")
        try:
            value = float(parts[idx + 1])
            limit = float(parts[idx + 2])
        except (IndexError, ValueError):
            continue
        if limit <= 0:
            continue
        return {
            "pct": max(0, min(100, round(value / limit * 100))),
            "used_mb": round(limit_mb * value / limit, 1),
            "limit_mb": limit_mb,
        }
    return None


def container_status() -> list:
    try:
        proc = subprocess.run(
            [DOCKER_BIN, "ps", "-a", "--filter", "name=sychos-",
             "--format", "{{.Names}}|{{.Status}}"],
            capture_output=True, text=True, timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    result = []
    for line in (proc.stdout or "").splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            result.append({"name": name, "status": status,
                           "up": status.startswith("Up")})
    return sorted(result, key=lambda item: item["name"])


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def new_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def format_mb(mb) -> str:
    mb = float(mb or 0)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB".replace(".", ",")
    return f"{mb:.0f} MB"


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def check_csrf() -> None:
    token = request.form.get("csrf", "")
    if not token or token != session.get("csrf"):
        abort(400, "CSRF-Token ungueltig — bitte Seite neu laden.")


def require_login(fn):
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__
    return wrapper


@app.context_processor
def inject_globals():
    return {
        "csrf": csrf_token(),
        "panel_email": session.get("email"),
        "app_name": APP_NAME,
        "domain": DOMAIN,
        "webmail_url": env("WEBMAIL_URL", f"https://{DOMAIN}"),
        "format_mb": format_mb,
    }


# --------------------------------------------------------------------------
# Anmeldung
# --------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        row = query_one("SELECT * FROM panel_users WHERE email = %s", (email,))
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session.permanent = True
            session["uid"] = row["id"]
            session["email"] = row["email"]
            csrf_token()
            query("UPDATE panel_users SET last_login_at = now() WHERE id = %s",
                  (row["id"],), commit=True)
            log_event(row["email"], "login", request.remote_addr or "")
            return redirect(request.args.get("next") or url_for("dashboard"))
        time.sleep(0.4)
        log_event(email or None, "login_fehlgeschlagen", request.remote_addr or "")
        flash("E-Mail oder Passwort ist falsch.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    actor = session.get("email")
    session.clear()
    log_event(actor, "logout")
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Uebersicht
# --------------------------------------------------------------------------
@app.get("/")
@require_login
def dashboard():
    totals = query_one(
        "SELECT count(*) AS konten, count(*) FILTER (WHERE active) AS aktiv,"
        " coalesce(sum(quota_mb), 0) AS quota_summe FROM mailboxes"
    )
    domains = query("SELECT * FROM domains ORDER BY name")
    boxes = query("SELECT * FROM mailboxes ORDER BY email")
    usage = []
    for box in boxes:
        usage.append({"box": box, "quota": quota_usage(box["email"])})
    verbraucht = sum(u["quota"]["used_mb"] for u in usage if u["quota"])
    return render_template(
        "dashboard.html",
        totals=totals,
        domains=domains,
        usage=usage,
        verbraucht=verbraucht,
        container=container_status(),
        default_quota=DEFAULT_QUOTA_MB,
    )


@app.get("/system")
@require_login
def system():
    return render_template(
        "system.html",
        container=container_status(),
        totals=query_one("SELECT count(*) AS konten FROM mailboxes"),
        events=query("SELECT * FROM events ORDER BY id DESC LIMIT 100"),
    )


# --------------------------------------------------------------------------
# Postfaecher
# --------------------------------------------------------------------------
@app.post("/postfaecher/neu")
@require_login
def create_mailbox():
    check_csrf()
    local = (request.form.get("local") or "").strip().lower()
    domain_id = request.form.get("domain_id", type=int)
    display = (request.form.get("display_name") or "").strip() or None
    quota_mb = request.form.get("quota_mb", type=int) or DEFAULT_QUOTA_MB
    password = (request.form.get("password") or "").strip()

    if not LOCALPART_RE.match(local):
        flash("Der Name darf nur Kleinbuchstaben, Ziffern, Punkt, "
              "Bindestrich und Unterstrich enthalten (2–31 Zeichen).", "error")
        return redirect(url_for("dashboard"))

    dom = query_one("SELECT * FROM domains WHERE id = %s", (domain_id,))
    if not dom:
        flash("Bitte eine Domain auswaehlen.", "error")
        return redirect(url_for("dashboard"))

    email = f"{local}@{dom['name']}"
    if query_one("SELECT 1 FROM mailboxes WHERE email = %s", (email,)):
        flash(f"{email} gibt es bereits.", "error")
        return redirect(url_for("dashboard"))

    generated = False
    if not password:
        password = new_password()
        generated = True
    if len(password) < 8:
        flash("Das Passwort muss mindestens 8 Zeichen haben.", "error")
        return redirect(url_for("dashboard"))
    if not 100 <= quota_mb <= 1024 * 1024:
        flash("Speicher muss zwischen 100 MB und 1 TB liegen.", "error")
        return redirect(url_for("dashboard"))

    ok, out = dms("email", "add", email, password)
    if not ok:
        flash(f"Der Mailserver hat das Konto abgelehnt: {out}", "error")
        return redirect(url_for("dashboard"))

    quota_ok, quota_out = dms("quota", "set", email, f"{quota_mb}M")
    try:
        query(
            "INSERT INTO mailboxes (email, domain_id, display_name, quota_mb,"
            " password_hash) VALUES (%s, %s, %s, %s, %s)",
            (email, dom["id"], display, quota_mb, generate_password_hash(password)),
            commit=True,
        )
    except DB_ERROR as exc:
        db().rollback()
        dms_delete(email)
        flash(f"Datenbankfehler — Konto wurde zurueckgerollt: {exc}", "error")
        return redirect(url_for("dashboard"))

    if not quota_ok:
        flash(f"Konto angelegt, Quota konnte aber nicht gesetzt werden: {quota_out}",
              "warn")

    log_event(session.get("email"), "postfach_angelegt",
              f"{email} ({quota_mb} MB)")
    record_credentials(email, password, f"{quota_mb} MB")
    session["created"] = {
        "email": email,
        "password": password,
        "quota_mb": quota_mb,
        "generated": generated,
    }
    return redirect(url_for("mailbox_created"))


@app.get("/postfaecher/erstellt")
@require_login
def mailbox_created():
    data = session.pop("created", None)
    if not data:
        return redirect(url_for("dashboard"))
    return render_template("mailbox_created.html", box=data)


@app.post("/postfaecher/<int:mid>/passwort")
@require_login
def reset_password(mid: int):
    check_csrf()
    box = query_one("SELECT * FROM mailboxes WHERE id = %s", (mid,))
    if not box:
        abort(404)
    password = (request.form.get("password") or "").strip()
    generated = False
    if not password:
        password = new_password()
        generated = True
    if len(password) < 8:
        flash("Das Passwort muss mindestens 8 Zeichen haben.", "error")
        return redirect(url_for("dashboard"))
    ok, out = dms("email", "update", box["email"], password)
    if not ok:
        flash(f"Passwort konnte nicht gesetzt werden: {out}", "error")
        return redirect(url_for("dashboard"))
    query("UPDATE mailboxes SET password_hash = %s, updated_at = now() WHERE id = %s",
          (generate_password_hash(password), mid), commit=True)
    log_event(session.get("email"), "passwort_geaendert", box["email"])
    record_credentials(box["email"], password, f"{box['quota_mb']} MB (Passwort geändert)")
    session["created"] = {
        "email": box["email"],
        "password": password,
        "quota_mb": box["quota_mb"],
        "generated": generated,
    }
    return redirect(url_for("mailbox_created"))


@app.post("/postfaecher/<int:mid>/quota")
@require_login
def change_quota(mid: int):
    check_csrf()
    box = query_one("SELECT * FROM mailboxes WHERE id = %s", (mid,))
    if not box:
        abort(404)
    quota_mb = request.form.get("quota_mb", type=int) or DEFAULT_QUOTA_MB
    if not 100 <= quota_mb <= 1024 * 1024:
        flash("Speicher muss zwischen 100 MB und 1 TB liegen.", "error")
        return redirect(url_for("dashboard"))
    ok, out = dms("quota", "set", box["email"], f"{quota_mb}M")
    if not ok:
        flash(f"Quota konnte nicht gesetzt werden: {out}", "error")
        return redirect(url_for("dashboard"))
    query("UPDATE mailboxes SET quota_mb = %s, updated_at = now() WHERE id = %s",
          (quota_mb, mid), commit=True)
    log_event(session.get("email"), "quota_geaendert",
              f"{box['email']} -> {quota_mb} MB")
    flash(f"{box['email']} hat jetzt {format_mb(quota_mb)} Speicher.", "success")
    return redirect(url_for("dashboard"))


@app.post("/postfaecher/<int:mid>/loeschen")
@require_login
def delete_mailbox(mid: int):
    check_csrf()
    box = query_one("SELECT * FROM mailboxes WHERE id = %s", (mid,))
    if not box:
        abort(404)
    confirm = (request.form.get("bestaetigung") or "").strip().lower()
    if confirm != str(box["email"]).lower():
        flash("Zum Loeschen bitte die vollstaendige Adresse eintippen.", "error")
        return redirect(url_for("dashboard"))
    ok, out = dms_delete(box["email"])
    if not ok:
        flash(f"Der Mailserver hat das Loeschen abgelehnt: {out}", "error")
        return redirect(url_for("dashboard"))
    query("DELETE FROM mailboxes WHERE id = %s", (mid,), commit=True)
    log_event(session.get("email"), "postfach_geloescht", box["email"])
    flash(f"{box['email']} wurde geloescht.", "success")
    return redirect(url_for("dashboard"))


@app.post("/domains")
@require_login
def add_domain():
    check_csrf()
    name = (request.form.get("name") or "").strip().lower()
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", name):
        flash("Ungueltiger Domainname.", "error")
        return redirect(url_for("dashboard"))
    try:
        query("INSERT INTO domains (name) VALUES (%s)", (name,), commit=True)
    except DB_ERROR:
        db().rollback()
        flash(f"{name} ist bereits vorhanden.", "warn")
        return redirect(url_for("dashboard"))
    log_event(session.get("email"), "domain_hinzugefuegt", name)
    flash(f"Domain {name} hinzugefuegt — DNS (MX/SPF/DKIM) nicht vergessen.", "success")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------
# Start / Erst-Einrichtung
# --------------------------------------------------------------------------
def ensure_admin() -> None:
    """Legt den ersten Panel-Benutzer aus .env an (idempotent)."""
    if not ADMIN_PASSWORD:
        return
    if query_one("SELECT 1 FROM panel_users WHERE email = %s", (ADMIN_EMAIL,)):
        return
    query("INSERT INTO panel_users (email, password_hash) VALUES (%s, %s)",
          (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)), commit=True)


_bootstrapped = False


@app.before_request
def _bootstrap():
    global _bootstrapped
    if _bootstrapped:
        return
    try:
        ensure_admin()
        _bootstrapped = True
    except DB_ERROR:
        # Datenbank noch nicht bereit — beim nächsten Request erneut versuchen.
        db().rollback()


if __name__ == "__main__":
    with app.app_context():
        ensure_admin()
    app.run(host="127.0.0.1", port=int(env("PANEL_PORT", "8090")), debug=False)
