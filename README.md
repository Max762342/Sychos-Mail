# Sychos Mail

Ein eigener Mail-Anbieter für **sychos.de**: Postfix + Dovecot als Mailserver,
eine eigene Web-Oberfläche (Sychos Mail), ein Control Panel zum Anlegen von
Postfächern und eine Postgres-Login-Datenbank. **Jedes Postfach bekommt 3 GB
Speicher** (einstellbar pro Konto).

## Bestandteile

| Teil | Technik | Verzeichnis |
|---|---|---|
| Mailserver | docker-mailserver v15 → Postfix, Dovecot, Rspamd, ClamAV, Fail2ban | `stack/` |
| Webmail-UI | Rust + Svelte (Fork von [orshih6/webmail](https://github.com/orshih6/webmail)), gebrandet | `webmail/` |
| Control Panel | Flask + Postgres, deutsche Oberfläche | `stack/panel/` |
| Datenbank | Postgres 17 — Konten, Quota, Ereignisprotokoll, Webmail-Sessions | `stack/postgres-init/` |
| Webseite (Edge) | Cloudflare Worker + Workers Assets, `/api/*`-Proxy | `worker/` |
| Startseite | statische Seite für GitHub Pages | `pages/` |
| CI/CD | GitHub Actions: UI bauen, Worker deployen, Pages veröffentlichen | `.github/workflows/` |

## Wie die Domain aufgeteilt ist

```
sychos.de, www.sychos.de   Cloudflare Worker   UI statisch + /api-Proxy
origin.sychos.de           Cloudflare Tunnel   Webmail-Container (API-Ursprung)
admin.sychos.de            Cloudflare Tunnel   Control Panel
mail.sychos.de:993/465     direkt              IMAP/SMTP (kein Cloudflare)
```

## Funktionen

* Postfächer anlegen, löschen, Passwort setzen, Speicher ändern — alles im Panel
* 3 GB Standard-Quota pro Postfach, Füllstandsanzeige pro Konto
* Mehrere Domains pro Installation
* Webmail mit Threads, Suche, Entwürfen, Anhängen (bis 25 MB), Tastaturkürzeln,
  Dark Mode, Handy-Layout
* IMAP/SMTP für alle Mail-Programme (Thunderbird, Apple Mail, Outlook, Handy):
  `mail.sychos.de`, IMAP 993 SSL, SMTP 465 SSL
* Spam-Filterung (Rspamd), Virenscan (ClamAV), DKIM-Signatur, DMARC, SPF
* **Webseite auf Cloudflare**: die Svelte-UI wird als Cloudflare Worker
  ausgeliefert (GitHub → GitHub Actions → Wrangler), nur `/api/*` geht über den
  Tunnel zum Server. Details: [`docs/WORKER.md`](docs/WORKER.md)
* **GitHub Pages** für eine statische Startseite (`pages/`)

## Ist-Zustand (live, getestet)

```
https://sychos.de              Cloudflare Worker   Svelte-UI + /api-Proxy     (live)
https://www.sychos.de          Worker              308 -> sychos.de           (live)
https://origin.sychos.de       Tunnel (dbgate)     Webmail-Container          (API-Ursprung)
https://admin.sychos.de        Tunnel (dbgate)     Control Panel              (live)
mail.sychos.de:993/465         direkt              IMAP/SMTP
```

* **Cloudflare Worker** `sychos-mail` mit Routen `sychos.de/*` + `www.sychos.de/*`,
  Deploy per Cloudflare Workers Builds (GitHub `Max762342/Sychos-Mail`)
* **Tunnel** `dbgate` auf dem Server um `origin.sychos.de` (Webmail) und
  `admin.sychos.de` (Panel) erweitert — `ssh.`/`friend.sychos.com` unverändert
* **Postfach** `admin@sychos.de` mit **3 GB** (`3145728 KB`, per `doveadm quota` geprüft)
* **Live-Check** (`python tools/verify-live.py --url https://sychos.de ...`):
  UI 1835 B in 114 ms · `/healthz` ok · `/api/config` 200 · Login 200 + Cookie ·
  `/api/folders` → 5 Ordner (IMAP erreichbar)
* **Server:** `sychos-mailserver` healthy · `sychos-postgres` healthy ·
  `sychos-webmail` up · `sychos-panel` (systemd) aktiv · `cloudflared` active
* **GitHub Pages:** <https://max762342.github.io/Sychos-Mail/>
* **DNS:** MX/SPF/`_dmarc` bei IONOS, DKIM-TXT `mail._domainkey.sychos.de` gesetzt
* Zugangsdaten: `C:\Users\Schüler\Desktop\Sychos-Mail-Zugangsdaten.txt`

**Noch offen:** MX auf `mail.sychos.de` umstellen (sinnvoll erst, wenn Port 25
am Anschluss erreichbar ist), PTR beim Anschluss setzen, echtes TLS-Zertifikat
(`scripts/letsencrypt.sh`).

## Schnellstart (auf dem Server)

```bash
cd /opt/sychos-mail/stack
docker compose up -d --build     # Mailserver, Postgres, Webmail
bash scripts/panel-install.sh     # Control Panel als systemd-Dienst
bash scripts/cloudflare-setup.sh  # Cloudflare Tunnel für sychos.de
bash scripts/dkim-setup.sh        # DKIM-Schlüssel + DNS-Wert
```

Postfach anlegen — im Panel (`https://admin.sychos.de`) oder per CLI:

```bash
bash scripts/create-mailbox.sh max@sychos.de 'GeheimesPasswort'
```

## Dokumentation

* [`docs/DEPLOY.md`](docs/DEPLOY.md) — Installation, Betrieb, Backup, Fehlersuche
* [`docs/DNS.md`](docs/DNS.md) — MX, SPF, DKIM, DMARC, PTR, Ports
* [`stack/.env`](stack/.env) — Zugangsdaten und Einstellungen

## Wichtig zu wissen

Cloudflare kann **nur Web-Verkehr** (HTTP/HTTPS) tunneln. Postfach-Abgleich und
Mailversand laufen direkt über die Ports 25/465/587/993. Für zuverlässigen
Mail-Empfang aus dem Internet braucht der Anschluss:

1. eine **feste öffentliche IP**,
2. **Port 25 offen** (eingehend),
3. einen **PTR-Eintrag** (`mail.sychos.de`), sonst stufen Gmail & Co. die Mails
   als Spam ein.

Bei einem Privatanschluss ist Punkt 3 oft nicht möglich — dann für den Versand
einen Smarthost in `stack/mailserver.env` eintragen (`DEFAULT_RELAY_HOST`) oder
den Stack auf einen echten VPS umziehen (Dateien bleiben identisch).

## Lizenz

Die Web-Oberfläche steht unter AGPL-3.0 (Fork von `orshih6/webmail`); der Link
zur Quelle ist über `SOURCE_URL` in `.env` gesetzt und erscheint im Login-Footer.
Der angepasste Quellcode (Branding, deutsche Anmeldeseite) liegt zusätzlich auf
dem Server unter `/opt/sychos-mail/webmail`.

## Werkzeuge auf dem Windows-Rechner

| Datei | Zweck |
|---|---|
| `tools/deploy.py` | Dateien per SFTP auf den Server laden, Befehle dort ausführen |
| `tools/vps.py` | Einzelne Befehle/Skripte per SSH auf dem Server starten |
| `tools/verify.py` | End-to-End-Test des Mailservers (IMAP, SMTP, Zustellung, Quota) |
| `tools/welcome.py` | Willkommensmail an ein Postfach schicken und Eingang prüfen |
| `tools/gen-credentials.py` | Erzeugt `Desktop\Sychos-Mail-Zugangsdaten.txt` neu |
| `tools/make-icons.py` | Erzeugt die PNG-Icons der Webmail-PWA aus dem Sychos-Logo |

```powershell
python tools\deploy.py upload stack webmail
python tools\verify.py --user-a admin@sychos.de --pass-a <pw> --user-b admin@sychos.de --pass-b <pw>
python tools\gen-credentials.py
```
