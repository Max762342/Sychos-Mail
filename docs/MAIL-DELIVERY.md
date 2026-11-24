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

## Lösung B – richtiger Mailserver

Ein VPS mit Port 25 und PTR (z. B. Hetzner/Netcup, ab ~4 €/Monat).

1. `stack/` + `webmail/` auf den VPS kopieren, `docker compose up -d --build`
2. `MAIL_HOSTNAME=mail.sychos.de`, `bash scripts/tls-selfsigned.sh` / `letsencrypt.sh`
3. DNS: `mail.sychos.de` A → VPS-IP (DNS only), **MX → mail.sychos.de**
4. PTR beim Hoster auf `mail.sychos.de` setzen
5. SPF anpassen: `v=spf1 mx include:_spf-eu.ionos.com ~all`
6. Cloudflare-Tunnel läuft weiter (zeigt auf den Host, nicht auf die IP) — Worker/UI unverändert

## Nicht die Ursache (geprüft)

* Port 25 ausgehend ist offen
* DNS/Cloudflare/Worker: `sychos.de` liefert die UI, `/api/*` geht durch den Tunnel
* Login, IMAP, Quota, DKIM-Schlüssel: funktionieren
