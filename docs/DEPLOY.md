# Sychos Mail — Installation & Betrieb

Alles liegt auf dem Host unter `/opt/sychos-mail`:

```
/opt/sychos-mail
├── stack/                 # der laufende Stack (docker compose)
│   ├── docker-compose.yml
│   ├── .env               # Geheimnisse (chmod 600!)
│   ├── mailserver.env     # docker-mailserver-Konfiguration
│   ├── tls/               # Zertifikat für Postfix/Dovecot
│   ├── postgres-init/     # Datenbankschema (nur beim ersten Start)
│   ├── panel/             # Control Panel (Flask, systemd-Dienst)
│   ├── cloudflared/       # Tunnel-Konfiguration
│   └── scripts/           # Setup- und Wartungsskripte
└── webmail/               # Quellcode der Web-Oberfläche (Rust + Svelte)
```

| Dienst | Container / Unit | Port(s) | Zweck |
|---|---|---|---|
| Postfix + Dovecot | `sychos-mailserver` | 25, 465, 587, 993, 143 | SMTP/IMAP, Quota, DKIM |
| Postgres | `sychos-postgres` | 127.0.0.1:5432 | Login-Datenbank + Sessions |
| Webmail | `sychos-webmail` | 127.0.0.1:8080 | Sychos Mail UI |
| Control Panel | `sychos-panel` (systemd) | 127.0.0.1:8090 | Postfächer verwalten |
| Cloudflare Tunnel | `sychos-cloudflared` | – | sychos.de → 8080, admin.sychos.de → 8090 |

---

## 1. Was automatisch eingerichtet wurde

1. Docker + Compose auf dem Host installiert, `sychos2` in der Gruppe `docker`.
2. Projekt nach `/opt/sychos-mail` kopiert.
3. Selbstsigniertes TLS-Zertifikat für `mail.sychos.de` erzeugt (`scripts/tls-selfsigned.sh`).
4. Stack gebaut und gestartet (`docker compose up -d --build`).
5. Control Panel als systemd-Dienst (`systemctl status sychos-panel`).
6. Postfach `admin@sychos.de` (3 GB) + `postmaster@sychos.de`-Alias angelegt.
7. DKIM-Schlüssel für `sychos.de` erzeugt.
8. `cloudflared` auf dem Host installiert (Tunnel selbst: siehe Abschnitt 2b).

### Ist-Zustand (geprüft)

| Prüfung | Ergebnis |
|---|---|
| Container | `sychos-mailserver` healthy, `sychos-webmail` up, `sychos-postgres` healthy |
| IMAP-Login (993, SSL) | funktioniert |
| SMTP-Versand (465) + Submission (587, STARTTLS) | funktioniert |
| Zustellung Postfach → Postfach | funktioniert |
| Quota pro Postfach | `3145728 KB` = **3 GB** |
| Webmail-UI + Login über die API | HTTP 200, Session-Cookie gesetzt |
| Control Panel (Login, Anlegen, Passwort, Löschen) | `scripts/selftest.sh` — alle Tests grün |

Alles noch einmal von Hand:

```bash
cd /opt/sychos-mail/stack
docker compose up -d --build          # Stack (bauen + starten)
bash scripts/panel-install.sh         # Panel-Dienst installieren/aktualisieren
docker compose ps                     # Status
docker compose logs -f mailserver     # Logs
bash scripts/selftest.sh              # Panel-Tests
```

---

## 2. Cloudflare (sychos.de)

Die Web-Oberflächen laufen über einen Cloudflare Tunnel — es muss **kein**
Port 80/443 am Router freigegeben werden, und die Wohnungs-IP bleibt verborgen.

### 2a. Domain zu Cloudflare bringen (einmalig)

1. Im Cloudflare-Dashboard **Add a site** → `sychos.de` → Free-Plan.
2. Cloudflare zeigt zwei Nameserver, z. B. `alina.ns.cloudflare.com` und
   `bob.ns.cloudflare.com`.
3. Bei **IONOS** (dort liegen die Nameserver aktuell):
   *Domain → sychos.de → Nameserver → „Andere Nameserver verwenden"*,
   beide Cloudflare-Namen eintragen, speichern.
4. Warten, bis Cloudflare „Active" meldet (15 Minuten bis einige Stunden).

> Wichtig: **Email Routing** in Cloudflare **nicht** aktivieren — das würde die
> MX-Einträge überschreiben.

### 2b. Tunnel anlegen

```bash
cd /opt/sychos-mail/stack
bash scripts/cloudflare-setup.sh
```

Das Skript installiert `cloudflared`, öffnet die Browser-Anmeldung, legt den
Tunnel `sychos-mail` an, setzt die DNS-Routen für `sychos.de`, `www.sychos.de`,
`origin.sychos.de` und `admin.sychos.de` und startet den Tunnel-Container.

Der Tunnel selbst liefert danach **nur noch**:

* `https://origin.sychos.de` → Webmail-Container (API-Ursprung für den Worker)
* `https://admin.sychos.de` → Control Panel

Die eigentliche Webseite `https://sychos.de` kommt aus dem **Cloudflare Worker**
(`worker/`), siehe [`WORKER.md`](WORKER.md). Vorteil: die Oberfläche liegt an der
Cloudflare-Edge und lädt auch dann, wenn der Heimserver schläft.

Die Zugangsdaten für das Panel stehen in `.env`
(`PANEL_ADMIN_EMAIL` / `PANEL_ADMIN_PASSWORD`).


---

## 3. Postfächer

### Im Panel (empfohlen)

1. `https://admin.sychos.de` öffnen, mit `admin@sychos.de` + Passwort aus `.env` anmelden.
2. „Neues Postfach": Name eingeben, Domain wählen, Speicher (Standard **3072 MB = 3 GB**).
3. Passwort leer lassen → es wird ein sicheres Passwort erzeugt und **einmalig**
   angezeigt (mit IMAP/SMTP-Daten zum Kopieren).

Weitere Aktionen pro Postfach: Passwort neu setzen, Speicher ändern, löschen
(Löschen muss mit der vollständigen Adresse bestätigt werden).

### Per Kommandozeile

```bash
cd /opt/sychos-mail/stack
bash scripts/create-mailbox.sh max@sychos.de 'GeheimesPasswort'
QUOTA=5120 bash scripts/create-mailbox.sh gross@sychos.de
```

Beides landet in derselben Datenbank (`panel.mailboxes`) und im Mailserver.

> Jedes neu angelegte Postfach wird mit Passwort an
> `/opt/sychos-mail/stack/credentials.log` (Rechte 600) protokolliert. Das ist die
> Quelle für die Zugangsdaten-Datei auf dem Desktop —
> `python tools/gen-credentials.py` erzeugt sie neu. Die Datei enthält
> Klartext-Passwörter, also nicht weitergeben.

---

## 4. Zertifikate

Aktuell läuft ein **selbstsigniertes** Zertifikat (`stack/tls/`). Das ist für den
internen Verkehr zwischen Webmail und Mailserver in Ordnung, aber Mail-Programme
zeigen dann eine Warnung. Für ein echtes Zertifikat (Let's Encrypt, DNS-01 über
Cloudflare — kein offener Port nötig):

```bash
cd /opt/sychos-mail/stack
CF_TOKEN=<Cloudflare-API-Token mit Zone:DNS:Edit> bash scripts/letsencrypt.sh
# danach in .env: WEBMAIL_INSECURE_TLS=0
docker compose up -d
```

Erneuerung monatlich per cron:

```cron
17 4 1 * * cd /opt/sychos-mail/stack && CF_TOKEN=... bash scripts/letsencrypt.sh >>/var/log/sychos-letsencrypt.log 2>&1
```

---

## 5. Backup

Alles Wichtige steckt in Docker-Volumes und zwei Dateien:

```bash
mkdir -p /backup
# Maildaten (Maildirs)
docker run --rm -v sychos-mail_dms-mail:/data -v /backup:/backup alpine \
  tar czf /backup/mail-$(date +%F).tar.gz -C /data .
# Konten, Quotas, Ereignisse
docker exec sychos-postgres pg_dump -U sychos -d panel | gzip > /backup/panel-$(date +%F).sql.gz
# Konfiguration + Zertifikate
tar czf /backup/config-$(date +%F).tar.gz -C /opt/sychos-mail stack/.env \
  stack/mailserver.env stack/tls
```

Wiederherstellen: `docker compose down`, Mail-Archiv ins Volume
`sychos-mail_dms-mail` entpacken, `pg_dump` mit `psql` einspielen,
`docker compose up -d`.

---

## 6. Fehlersuche

| Symptom | Prüfen |
|---|---|
| Webmail zeigt „reconnecting" | `docker compose logs -f mailserver` — läuft Dovecot? |
| Login im Webmail scheitert | Postfach im Panel vorhanden? Passwort über „Passwort setzen" neu setzen |
| Panel: „Docker ist nicht erreichbar" | `id -nG` muss `docker` enthalten, sonst `sudo usermod -aG docker $USER`, neu einloggen, `systemctl restart sychos-panel` |
| Keine Mail von außen | Port 25 am Router offen? PTR gesetzt? → `docs/DNS.md` |
| Ausgehende Mail im Spam | SPF/DKIM/DMARC + PTR prüfen, sonst Smarthost (`DEFAULT_RELAY_HOST`) |
| `https://sychos.de` nicht erreichbar | Worker-Logs: `cd worker && npx wrangler tail`; DNS-Route/Worker-Route im Cloudflare-Dashboard prüfen |
| Webmail lädt, aber „reconnecting"/502 | `https://origin.sychos.de/api/config` aufrufen; Tunnel: `docker logs sychos-cloudflared` |
| Quota fehlt im Panel | `docker compose exec mailserver doveadm quota get -u max@sychos.de` |

```bash
docker compose ps
docker compose logs --tail 50 mailserver
docker compose exec mailserver setup help
docker compose exec mailserver doveadm quota get -u max@sychos.de
systemctl status sychos-panel
```

---

## 7. Umzug auf einen echten VPS

Der Stack ist ortsunabhängig:

1. Docker installieren, `stack/` + `webmail/` nach `/opt/sychos-mail` kopieren.
2. `.env` und `mailserver.env` übernehmen, Volumes/Backup einspielen.
3. `bash scripts/tls-selfsigned.sh` (oder direkt `letsencrypt.sh`).
4. `docker compose up -d --build`, `bash scripts/panel-install.sh`.
5. DNS: `mail.sychos.de` auf die neue IP, MX prüfen, PTR beim Hoster setzen.
6. Cloudflare-Tunnel bleibt unverändert (er hängt am Host, nicht an der IP).
