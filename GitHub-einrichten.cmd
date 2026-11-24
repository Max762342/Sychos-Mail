@echo off
title Sychos Mail - GitHub einrichten
cd /d "%~dp0"
echo ============================================
echo  Sychos Mail - Repository auf GitHub
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\github-login.ps1" %*
echo.
echo (Fenster kann geschlossen werden)
if "%~1"=="" pause
