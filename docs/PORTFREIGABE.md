# Portfreigabe: was sie bringt und was nicht

## Kurzfassung

| Ziel | Portfreigabe nötig? | reicht Portfreigabe? |
|---|---|---|
| **Postfach von außen abrufen** (Handy/Thunderbird, IMAP 993, SMTP 465) | ja (993/465/587) | **ja** ✅ |
| **Mail von außen empfangen** (Port 25) | ja | **nein** ❌ — ohne PTR landen viele Mails im Spam/werden abgewiesen |
| **Mail an Gmail senden** | nein | **nein** ❌ — Gmail blockt Privatanschluss-IPs (`550 5.7.1`) |

## Was auf dem Server schon fertig ist

* Dovecot/Postfix lauschen auf 25, 143, 465, 587, 993 (Container-Ports sind veröffentlicht)
* Fail2ban aktiv, TLS-Zertifikat vorhanden (selbstsigniert; Let's Encrypt per `scripts/letsencrypt.sh`)
* DKIM (`mail._domainkey`), SPF, DMARC (`p=none`) gesetzt
* `mail.sychos.de` → A-Record (DNS only) auf die öffentliche IP vorhanden

## Freigaben in der FRITZ!Box

`Internet → Freigaben → Portfreigaben → Gerät hinzufügen → 192.168.178.53`

Für jeden Port eine „Andere Anwendung":

| Name | Protokoll | Port extern → intern |
|---|---|---|
| Sychos SMTP | TCP | 25 → 25 |
| Sychos SMTPS | TCP | 465 → 465 |
| Sychos Submission | TCP | 587 → 587 |
| Sychos IMAPS | TCP | 993 → 993 |
| Sychos IMAP | TCP | 143 → 143 |

Tipp: der FRITZ!Box die IP fest zuweisen (`Heimnetz → Netzwerk → Gerät → Immer
dieselbe IP`), sonst brechen die Freigaben nach einem Neustart.

## Danach (macht die Automatik)

```powershell
# 1. Prüfen, ob Port 25 wirklich von außen offen ist
python tools\port-check.py 79.140.115.19:25

# 2. MX direkt auf den eigenen Server (statt Cloudflare/IONOS)
python tools\cf-dns.py set sychos.de MX sychos.de mail.sychos.de --prio 10
python tools\cf-dns.py set sychos.de TXT sychos.de "v=spf1 mx ~all"

# 3. Test von außen
python tools\imap-check.py --user admin@sychos.de --password <pw> --subject test
```

Wenn Port 25 offen ist, kann der Email-Routing-Umweg (Cloudflare → Worker →
Injektor) abgeschaltet werden — dann kommt die Mail direkt.

## Was auch mit Freigabe offen bleibt

1. **Ohne PTR senden viele Provider nicht/kaum.** Beim Privatanschluss ist kein
   PTR setzbar → manche Server weisen dich ab („reverse DNS does not match"),
   Gmail weist dich **immer** ab.
2. **Versand braucht weiter einen Relay** (IONOS-Postfach, Brevo, SES):
   `bash scripts/set-relay.sh smtp.ionos.de 587 <postfach> <pw>`
3. **Die IP ist dynamisch.** Bei jedem Wechsel der öffentlichen IP (Telekom
   macht das alle 24 h bis Wochen) muss `mail.sychos.de` nachgezogen werden —
   ohne DynDNS bricht die Zustellung. Empfehlung: Cloudflare-DDNS-Skript per
   cron (`tools/cf-dns.py set ... A mail.sychos.de <neue-ip>`).

**Fazit:** Portfreigabe macht den Webmail/Client-Zugriff von überall möglich und
spart den Injektor-Umweg — aber der Versand an Gmail scheitert weiterhin an der
Privatanschluss-IP. Ein VPS löst beides.
