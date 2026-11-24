# Webseite auf Cloudflare — Worker + GitHub

Ziel: `https://sychos.de` soll **auf Cloudflare laufen** (schnell, weltweit, und
die Oberfläche ist da, auch wenn der Heimserver schläft), während die Postfächer
weiter auf deinem Server liegen. Der Quellcode liegt auf GitHub, deployed wird
per GitHub Actions.

## Aufbau

```
Browser
  │
  ├─ https://sychos.de/…            → Cloudflare Worker  (Assets: Svelte-UI)
  │                                     └─ /api/* → https://origin.sychos.de  ─┐
  │                                                                             │
  ├─ https://admin.sychos.de        → Cloudflare Tunnel → Control Panel         │
  │                                                                             │
  └─ mail.sychos.de:993 / :465      → direkt zum Server (kein Cloudflare)       │
                                                                                │
             origin.sychos.de ── Cloudflare Tunnel ──> 127.0.0.1:8080 ──────────┘
```

* **Worker** (`worker/`): liefert die gebaute Svelte-UI aus (Workers Assets),
  proxied `/api/*` an den Tunnel-Ursprung, setzt Sicherheits-Header, leitet
  `www` auf die Hauptdomain um und hat `/healthz`.
* **Cookies bleiben same-origin**: die API liegt unter demselben Host
  (`sychos.de/api/...`), deshalb funktioniert `SameSite=Strict` weiter — kein CORS.
* **Tunnel** (`stack/cloudflared/`): nur noch `origin.sychos.de` (API) und
  `admin.sychos.de` (Panel). `sychos.de` selbst gehört jetzt dem Worker.
* **GitHub Pages** (`pages/`): statische Startseite als Visitenkarte
  (optional, unabhängig vom Mailbetrieb).

## Einmalige Einrichtung

### 1. Tunnel umstellen (auf dem Server)

```bash
cd /opt/sychos-mail/stack
bash scripts/cloudflare-setup.sh
```

Das Skript legt DNS-Routen für `sychos.de`, `www`, `origin` und `admin` an und
startet den Tunnel mit dem neuen `config.yml` (origin + admin).

Prüfen: `curl -I https://origin.sychos.de` → `HTTP/2 200`.

### 2. Repository auf GitHub

```bash
cd "C:\Users\Schüler\Desktop\Sychos Mail"
git init -b main
git add .
git commit -m "Sychos Mail: Mailserver-Stack, Webmail-Fork, Cloudflare Worker"
git remote add origin https://github.com/<dein-account>/sychos-mail.git
git push -u origin main
```

> `stack/.env`, `stack/tls/`, `credentials.log` und `worker/dist/` sind über
> `.gitignore` ausgenommen — dort stehen Passwörter bzw. Build-Artefakte.

### 3. Cloudflare-API-Token

Cloudflare-Dashboard → **My Profile → API Tokens → Create Token →
Custom token** mit:

| Bereich | Berechtigung |
|---|---|
| Account → Workers Scripts | Edit |
| Account → Workers Routes | Edit |
| Zone → Workers Routes | Edit (Zone `sychos.de`) |

Dazu die **Account-ID** (Dashboard → Workers & Pages, rechts oben).

### 4. Secrets im Repository

```bash
gh secret set CLOUDFLARE_API_TOKEN
gh secret set CLOUDFLARE_ACCOUNT_ID
```

Oder per Web-UI: *Settings → Secrets and variables → Actions → New repository secret*.

### 5. Deployen

Ein Push auf `main` (der `worker/`, `webmail/web/` oder den Workflow ändert)
baut die UI und deployt den Worker. Manuell:

```bash
cd worker
npm install                 # wrangler
node build.mjs              # baut webmail/web -> dist/
npx wrangler deploy         # deployt sychos.de + www.sychos.de
```

Ergebnis: `https://sychos.de` liefert die Svelte-UI, `https://sychos.de/healthz`
meldet Status und API-Ziel.

### 6. GitHub Pages (Startseite)

*Settings → Pages → Source: **GitHub Actions***. Danach deployt
`.github/workflows/pages.yml` bei jeder Änderung in `pages/` die Startseite.

## Lokal testen

```bash
cd worker
npm test                    # 10 Tests: Routing, Proxy, Cookies, 502-Fall, Redirect
npx wrangler deploy --dry-run --outdir .dry   # Konfiguration prüfen (ohne Deploy)
npx wrangler dev            # http://localhost:8787 (dist/ muss gefüllt sein)
```

### Kompletter Durchlauf ohne Cloudflare (mit echtem Mailserver)

`tools/check-worker-e2e.py` startet einen SSH-Tunnel zum Webmail auf dem Server,
fährt den Worker lokal (`tools/preview-server.mjs`) mit den gebauten Assets und
prüft die ganze Kette:

```powershell
python tools\check-worker-e2e.py --user admin@sychos.de --password <postfach-passwort>
```

```
  OK    UI wird ausgeliefert  -> index.html + Sicherheits-Header
  OK    /healthz  -> api=http://127.0.0.1:18080
  OK    Login ueber den Proxy (Cookies)  -> angemeldet als admin@sychos.de
  OK    Session bleibt gueltig
  OK    /api/config
  OK    SPA-Fallback
```

Damit ist bewiesen, dass statische Auslieferung, `/api`-Proxy, Cookies und
SPA-Routing genau so funktionieren wie später auf Cloudflare.

Ohne Cloudflare prüfen, ob der Proxy-Ursprung antwortet:

```bash
curl -s https://origin.sychos.de/api/config
```

## Betrieb

| Aufgabe | Befehl |
|---|---|
| Logs ansehen | `cd worker && npx wrangler tail` |
| API-Ziel ändern | `npx wrangler secret put API_ORIGIN` |
| Version zurückrollen | Cloudflare-Dashboard → Workers → Deployments |
| UI neu bauen | `cd worker && node build.mjs && npx wrangler deploy` |

## Grenzen und Hinweise

* **SMTP/IMAP laufen nicht über Cloudflare.** Mail-Clients verbinden sich direkt
  mit `mail.sychos.de` (993/465). Nur die Web-Oberfläche und ihre API nutzen
  Cloudflare.
* **Free-Plan** reicht für den Betrieb: 100.000 Anfragen/Tag, unbegrenzte
  statische Assets. Anhänge bis 25 MB gehen durch den Proxy (Limit 100 MB).
* **Server aus?** Die UI lädt trotzdem, `/api/*` antwortet mit
  `502 mailserver_unreachable` — das Webmail zeigt dann sein „reconnecting"-Banner.
* Der Worker proxied **nur** `/api/*` an ein fest konfiguriertes Ziel
  (`API_ORIGIN`) — er ist kein offener Proxy.
