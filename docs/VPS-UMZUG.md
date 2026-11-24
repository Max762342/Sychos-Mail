# Mailserver auf einen VPS umziehen (ohne Portfreigabe zu Hause)

## Warum

Am Privatanschluss gilt dauerhaft:

* **Eingehend Port 25 ist nicht erreichbar** (3 externe Knoten: Timeout)
* **Gmail lehnt ausgehende Mail ab**: `550-5.7.1 [79.140.115.19] … not authorized
  to send email directly to our servers. Please use the SMTP relay …`
* **Kein PTR** für die IP (kann beim Privatanschluss nicht gesetzt werden)
* Cloudflare Tunnel kann **kein SMTP** transportieren (Cloudflare-Edge nimmt
  Port 25 nicht an — geprüft)

Ein VPS (Hetzner CX22, Netcup VPS 200 o. ä., ~4 €/Monat) hat eine eigene
öffentliche IPv4 mit erlaubtem Port 25 und setzbarem PTR.

## Ablauf (ca. 20 Minuten)

### 1. VPS bestellen
Ubuntu 24.04/26.04, 2 GB RAM, eigene IPv4. Beim Hoster **PTR/rDNS**
auf `mail.sychos.de` setzen (Kundenmenü → Netzwerk → Reverse DNS).

### 2. Stack kopieren (vom Windows-Rechner aus)

```powershell
# in tools/vps.env die neuen Zugangsdaten eintragen, dann:
python tools\deploy.py upload stack webmail
```

### 3. Auf dem VPS einrichten

```bash
ssh <user>@<vps-ip>
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # danach neu einloggen
cd /opt/sychos-mail/stack        # bzw. dorthin, wo der Upload landete
bash scripts/tls-selfsigned.sh
docker compose up -d --build
ADMIN_PW='<Postfach-Passwort>' bash scripts/seed-initial.sh
bash scripts/panel-install.sh
bash scripts/selftest.sh
```

### 4. DNS umstellen (Cloudflare, Zone sychos.de)

```powershell
python tools\cf-dns.py set sychos.de A mail.sychos.de <VPS-IP> --no-proxy
python tools\cf-dns.py set sychos.de MX sychos.de mail.sychos.de   # Prio 10
python tools\cf-dns.py set sychos.de TXT sychos.de 'v=spf1 mx ~all'
```

MX **muss** „DNS only" sein, `mail.sychos.de` ebenfalls.

### 5. Webseite bleibt, wo sie ist

* `sychos.de` → Cloudflare Worker (unverändert)
* `origin.sychos.de` → Tunnel auf den **Heimserver**? Nein: der Webmail-Container
  läuft jetzt auf dem VPS. Also am VPS einen cloudflared-Tunnel aufsetzen und
  `origin.sychos.de` dorthin zeigen lassen (oder den Worker-`API_ORIGIN` direkt
  auf `https://mail.sychos.de`-Port 8080 setzen, dann braucht es keinen Tunnel).
  Empfehlung: kleiner Tunnel auf dem VPS für `origin.sychos.de` + `admin.sychos.de`.
* Alternativ komplett umziehen: Heimserver abschalten, Tunnel `dbgate` auf den
  VPS umziehen (gleiche `config.yml`, gleiche ID-Datei).

### 6. Prüfen

```powershell
python tools\verify-live.py --url https://sychos.de --user admin@sychos.de --password <pw>
```

Auf dem VPS zusätzlich:

```bash
# ausgehend: Gmail muss "250 OK" liefern statt 550
docker exec sychos-mailserver sh -c 'grep -h "status=sent" /var/log/mail/mail.log | tail -5'
# PTR prüfen
dig +short -x $(curl -s https://api.ipify.org)
```

## Zwischenlösung, falls kein VPS

`docs/MAIL-DELIVERY.md` → Lösung A: IONOS-Postfach als Eingang (fetchmail) und
Versand-Relay. Funktioniert ohne Portfreigabe, aber die Mails laufen über IONOS.
