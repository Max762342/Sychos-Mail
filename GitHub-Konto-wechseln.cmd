@echo off
title Sychos Mail - GitHub-Konto wechseln
cd /d "%~dp0"
echo ============================================
echo  GitHub-Konto wechseln (Sychos Mail)
echo ============================================
echo.
echo  Es oeffnet sich gleich GitHub im Browser.
echo  Dort mit dem NEUEN Konto anmelden und den
echo  angezeigten Code bestaetigen.
echo.
echo  Aktuell angemeldet:
gh auth status 2>&1 | findstr /C:"account" /C:"Logged in"
echo.
pause
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\github-login.ps1" -Switch %*
echo.
echo (Fenster kann geschlossen werden)
echo Altes Konto entfernen:  gh auth logout --user <alter-name>
pause
