# Mail-Zustellung: warum Gmail (nicht) ankommt

## Befund (gemessen am 24.11.2026)

| Prüfung | Ergebnis |
|---|---|
| Ausgehend Port 25 (Server → gmail-smtp-in:25) | **offen** (Telekom blockt hier nicht) |
| Eingehend Port 25 (3 externe Knoten → 79.140.115.19:25) | **Timeout** — von außen nicht erreichbar |
| PTR (Reverse-DNS) von 79.140.115.19 | **keiner gesetzt** |
| MX für sychos.de | `mx00.ionos.de`, `mx01.ionos.de` (nicht unser Server) |
| DMARC | war defekt (CNAME auf `dmarc.ionos.de`) → jetzt TXT `p=none` |
| DKIM `mail._domainkey.sychos.de` | gesetzt, 2048 Bit |

**Original-Ablehnung von Gmail** (aus `/var/log/mail/mail.log`):

```
550-5.7.1 [79.140.115.19] The IP you're using to send mail is not authorized to
550-5.7.1 send email directly to our servers. Please use the SMTP relay at your
550 5.7.1  service provider instead.
```

Das ist keine Konfigurationssache: Gmail führt eine Liste von **Privatanschluss-IP-Bereichen**
und lehnt direkte Zustellungen daraus grundsätzlich ab. Auch SPF/DKIM/PTR ändern daran nichts.

## Was daraus folgt

* **Ausgehend** (sychos.de → Gmail): braucht einen **Smarthost/Relay**.
* **Eingehend** (Gmail → sychos.de): braucht **Port 25 von außen**. Ist am Anschluss
  nicht erreichbar → Mail landet beim MX (`IONOS`) und nicht auf dem Server.

## Lösung A – ganz ohne Port 25 (empfohlen für diesen Anschluss)

1. **Ausgehend über IONOS** (SPF passt bereits: `include:_spf-eu.ionos.com`):

   ```bash
   cd /opt/sychos-mail/stack
   bash scripts/set-relay.sh smtp.ionos.de 587 info@sychos.de 'IONOS-PASSWORT'
   ```

2. **Eingehend von IONOS abholen** (fetchmail holt die Mails ins lokale Postfach):

   ```bash
   bash scripts/set-inbound-fetch.sh imap.ionos.de info@sychos.de 'IONOS-PASSWORT' admin@sychos.de
   ```

   Damit gilt: Gmail → `info@sychos.de` (MX IONOS) → fetchmail → Dovecot → Webmail.
   Versand: Webmail → IONOS-Relay → Gmail. **Port 25 am Anschluss bleibt ungenutzt.**

Nötig dafür: ein **IONOS-Postfach** auf `sychos.de` + dessen Passwort.

> Achtung: Das **IONOS-Kundenkonto** (`maxyngrahn@gmail.com` + Kundenkennwort) ist
> **kein** Mail-Login. Getestet am 24.11.2026:
> `smtp.ionos.de:587 → 535 Authentication credentials invalid`,
> `imap.ionos.de:993 → authentication failed`.
> Ein Postfach ist eine Adresse **auf der Domain**, z. B. `info@sychos.de`,
> `mail@sychos.de` oder `admin@sychos.de`, angelegt im IONOS Control Center
> unter *E-Mail → Postfach*. Von dort bekommt man Adresse + Postfach-Passwort.

## Lösung B – richtiger Mailserver

Ein VPS mit Port 25 und PTR (z. B. Hetzner/Netcup, ab ~4 €/Monat).

1. `stack/` + `webmail/` auf den VPS kopieren, `docker compose up -d --build`
2. `MAIL_HOSTNAME=mail.sychos.de`, `bash scripts/tls-selfsigned.sh` / `letsencrypt.sh`
3. DNS: `mail.sychos.de` A → VPS-IP (DNS only), **MX → mail.sychos.de**
4. PTR beim Hoster auf `mail.sychos.de` setzen
5. SPF anpassen: `v=spf1 mx include:_spf-eu.ionos.com ~all`
6. Cloudflare-Tunnel läuft weiter (zeigt auf den Host, nicht auf die IP) — Worker/UI unverändert

## Lösung C – eingehende Mail ohne Port 25 (umgesetzt)

Cloudflare Email Routing nimmt die Mail auf Port 25 an (Cloudflare-Netz) und
übergibt sie an einen **Email Worker**, der sie per HTTPS über den Tunnel an
einen kleinen **Injektor** auf dem Server schickt. Der legt sie per SMTP in
Postfix/Dovecot ab — **kein offener Port, kein Portforwarding**.

```
Gmail -> MX: Cloudflare Email Routing (route1.mx.cloudflare.net)
      -> Email Worker (sychos-mail, email-Handler)
      -> POST https://inject.sychos.de/inject  (Shared Secret)
      -> sychos-inject (127.0.0.1:8099)
      -> SMTP 127.0.0.1:25 -> Postfix -> Rspamd -> Dovecot -> Webmail
```

Bestandteile:

| Teil | Datei / Dienst |
|---|---|
| Injektor | `stack/inject/app.py`, Dienst `sychos-inject` (systemd), `127.0.0.1:8099` |
| Secret | `/etc/sychos-inject.env` (root, 600) — muss in Cloudflare als `INJECT_SECRET` liegen |
| Worker-Handler | `worker/src/index.js` → `email()` |
| Tunnel-Ingress | `inject.sychos.de → http://127.0.0.1:8099` |
| Installation | `bash scripts/inject-install.sh` |

Getestet (24.11.2026): POST an `https://inject.sychos.de/inject` → `200`,
Mail lag anschließend im Postfach `admin@sychos.de` (IMAP, Header unverändert).

### Cloudflare-Schritte (einmalig, Dashboard)

1. **Email → Email Routing → Enable** (setzt die MX-Records auf Cloudflare)
2. **Routing → Catch-all address → Action: Send to a Worker → `sychos-mail`**
3. **Workers → sychos-mail → Settings → Variables → Add → Secret**
   `INJECT_SECRET` = Wert aus `/etc/sychos-inject.env`

Danach erreicht jede Mail an `*@sychos.de` das Webmail — ohne Port 25.

**Versand bleibt davon unberührt:** Gmail lehnt direkte Zustellung aus
Privatanschluss-IPs ab. Dafür ist weiterhin ein Relay nötig (Lösung A, erster
Befehl) oder ein VPS (Lösung B).


* Port 25 ausgehend ist offen
* DNS/Cloudflare/Worker: `sychos.de` liefert die UI, `/api/*` geht durch den Tunnel
* Login, IMAP, Quota, DKIM-Schlüssel: funktionieren
