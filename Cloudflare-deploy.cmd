@echo off
title Sychos Mail - Cloudflare Build und Deploy
cd /d "%~dp0worker"

echo ============================================================
echo  Sychos Mail - Cloudflare Worker bauen und deployen
echo ============================================================
echo.
echo  Schritt 1: Anmeldung bei Cloudflare (Browser, einmalig)
echo  Schritt 2: Deploy des Workers
echo.
echo  Die UI ist fertig gebaut (dist/ liegt im Repo), es wird also
echo  nichts weiter uebersetzt - nur hochgeladen.
echo.
pause

echo.
echo === 1/2 Cloudflare-Login ===
call .\node_modules\.bin\wrangler.cmd login
if errorlevel 1 goto fehler

echo.
echo === 2/2 Deploy (ohne eigene Domain, workers.dev) ===
call .\node_modules\.bin\wrangler.cmd deploy --config wrangler.preview.toml
if errorlevel 1 goto fehler

echo.
echo ============================================================
echo  Fertig. Die URL oben (https://sychos-mail.<name>.workers.dev)
echo  zeigt die Svelte-UI, /healthz den Status.
echo ============================================================
goto ende

:fehler
echo.
echo  Fehlgeschlagen. Haeufige Ursachen:
echo   - Login nicht abgeschlossen (Schritt 1 wiederholen)
echo   - Account hat keine Workers-Freigabe
echo   - Netzwerk/Proxy blockt api.cloudflare.com

:ende
echo.
pause
