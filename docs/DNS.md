# DNS-Einträge für sychos.de

Diese Records müssen im DNS stehen (nach dem Umzug zu Cloudflare: dort im
Dashboard unter **DNS → Records**). Alles, was mit Mail zu tun hat, muss
**DNS only** (graue Wolke) sein — Cloudflare proxyt kein SMTP/IMAP.

| Typ | Name | Wert | Proxy |
|---|---|---|---|
| A | `mail` | *öffentliche IP des Servers* | **DNS only** |
| MX | `sychos.de` | `mail.sychos.de` (Priorität 10) | – |
| TXT | `sychos.de` | `v=spf1 mx ~all` | – |
| TXT | `mail._domainkey.sychos.de` | *siehe `scripts/dkim-setup.sh`* | – |
| TXT | `_dmarc.sychos.de` | `v=DMARC1; p=quarantine; rua=mailto:postmaster@sychos.de` | – |
| CNAME | `autoconfig` | `mail.sychos.de` | DNS only |
| CNAME | `autodiscover` | `mail.sychos.de` | DNS only |
| CNAME | `sychos.de` | *Tunnel-Ziel, wird vom Skript gesetzt* | proxied |
| CNAME | `www` | *Tunnel-Ziel, wird vom Skript gesetzt* | proxied |
| CNAME | `admin` | *Tunnel-Ziel, wird vom Skript gesetzt* | proxied |

Der DKIM-Eintrag wird erzeugt mit:

> Hinweis: Auf `sychos.de` liegen Web- und Mail-Einträge nebeneinander — der
> CNAME für die Webseite ist **proxied**, MX und TXT sind **DNS only**. Cloudflare
> löst den CNAME am Zonen-Apex intern auf, das stört die MX-Einträge nicht.
> **Email Routing** in Cloudflare bitte ausgeschaltet lassen.

```bash
cd /opt/sychos-mail/stack && bash scripts/dkim-setup.sh sychos.de
```

Der Befehl gibt den kompletten TXT-Wert aus (beginnt mit `v=DKIM1; k=rsa; p=…`).

## PTR / Reverse-DNS

Empfangende Mailserver (Gmail, Outlook, IONOS …) prüfen, ob die IP des
Senders zu `mail.sychos.de` zurückauflöst. Der PTR-Eintrag wird **nicht** beim
Domain-Anbieter, sondern beim **Internet-Anschluss** gesetzt:

* Bei einem echten VPS (Hetzner, Netcup, Contabo …) im Kundenmenü →
  „Reverse DNS / rDNS" → `mail.sychos.de`.
* Bei einem Privatanschluss (Telekom, Vodafone …) ist das meist **nicht
  möglich** — dann landen ausgehende Mails im Spam oder werden abgelehnt.
  Lösung: Versand über einen Smarthost (`DEFAULT_RELAY_HOST` in
  `mailserver.env`, z. B. IONOS oder Amazon SES).

## Ports

| Port | Protokoll | Wofür | MUSS von außen erreichbar sein? |
|---|---|---|---|
| 25 | SMTP | Mail von anderen Servern empfangen | **ja** (sonst kommt keine Mail an) |
| 465 | SMTPS | Webmail + Mail-Apps senden | ja (oder 587) |
| 587 | Submission | Mail-Apps senden (STARTTLS) | ja (oder 465) |
| 993 | IMAPS | Webmail + Mail-Apps lesen | ja (oder 143) |
| 8080 | HTTP | Webmail intern | nein (Tunnel) |
| 8090 | HTTP | Panel intern | nein (Tunnel) |

Am Router (FRITZ!Box: *Internet → Freigaben → Portfreigaben*) müssen
25, 465, 587 und 993 auf `192.168.178.53` weitergeleitet werden.

**Ehrliche Einschätzung:** Viele Privatanschlüsse (Telekom) blockieren Port 25
sowohl ein- als auch ausgehend. Dann funktioniert dieser Stack im LAN und über
Cloudflare vollständig, aber Mail aus dem Internet kommt nicht an und
ausgehende Mail wird abgelehnt. In dem Fall: Stack 1:1 auf einen echten VPS
umziehen (gleiche Dateien, `MAIL_HOSTNAME` bleibt) oder einen Relay-Dienst
davorschalten.
