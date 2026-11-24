<#
.SYNOPSIS
  GitHub-Anmeldung + Repository fuer Sychos Mail anlegen und pushen.

.DESCRIPTION
  1. prueft, ob die GitHub CLI (gh) installiert ist (installiert sie bei Bedarf)
  2. meldet sich bei GitHub an (Browser/Device-Code), falls noch nicht geschehen
  3. stellt sicher, dass der Token die Scopes "repo" und "workflow" hat
  4. legt das Repository an (oder nutzt ein vorhandenes) und pusht "main"
  5. setzt optional die Actions-Secrets CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID
  6. aktiviert GitHub Pages mit "GitHub Actions" als Quelle

.BEISPIELE
  powershell -ExecutionPolicy Bypass -File tools\github-login.ps1
  powershell -ExecutionPolicy Bypass -File tools\github-login.ps1 -RepoName sychos-mail -Public
  powershell -ExecutionPolicy Bypass -File tools\github-login.ps1 -NonInteractive
  powershell -ExecutionPolicy Bypass -File tools\github-login.ps1 -DryRun     # nur anzeigen
  powershell -ExecutionPolicy Bypass -File tools\github-login.ps1 -Account kevu2256   # zu diesem Konto wechseln
  powershell -ExecutionPolicy Bypass -File tools\github-login.ps1 -Switch    # neues Konto anmelden
#>
[CmdletBinding()]
param(
    [string]$RepoName = "sychos-mail",
    [switch]$Public,
    [switch]$NonInteractive,
    [switch]$DryRun,
    # Konto wechseln
    [string]$Account,
    [switch]$Switch,
    # Repo unter dem aktiven Konto neu anlegen und origin umbiegen
    [switch]$RecreateRepo
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Write-Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  OK   $text" -ForegroundColor Green }
function Write-Warn2($text){ Write-Host "  !    $text" -ForegroundColor Yellow }
function Write-Bad($text)  { Write-Host "  X    $text" -ForegroundColor Red }
function Write-Skip($text) { Write-Host "  ->   WUERDE: $text" -ForegroundColor DarkCyan }
function Stop-Here {
    if (-not $NonInteractive) { Read-Host "Enter zum Beenden" }
    exit 1
}

Write-Host "Sychos Mail - GitHub einrichten" -ForegroundColor White
Write-Host "Projekt: $ProjectRoot"

# ---------------------------------------------------------------- 1. gh CLI --
Write-Step "1/6 GitHub CLI (gh)"
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    $candidate = Join-Path $env:LOCALAPPDATA "GitHubCLI\bin\gh.exe"
    if (Test-Path $candidate) {
        $env:PATH = "$env:PATH;$(Split-Path $candidate -Parent)"
        $gh = Get-Command gh -ErrorAction SilentlyContinue
    }
}
if (-not $gh) {
    Write-Warn2 "gh ist nicht installiert - versuche Installation mit winget"
    try {
        winget install --id GitHub.cli --source winget --accept-package-agreements --accept-source-agreements
        $env:PATH = "$env:PATH;$env:LOCALAPPDATA\GitHubCLI\bin"
    } catch {
        Write-Bad "Installation fehlgeschlagen. Manuell: https://cli.github.com/"
        Stop-Here
    }
}
Write-Ok ((gh --version | Select-Object -First 1))

# ------------------------------------------------------------- 2. Anmeldung --
Write-Step "2/6 Anmeldung bei github.com"
$statusText = (gh auth status 2>&1 | Out-String)
$known = @()
foreach ($m in [regex]::Matches($statusText, 'account (\S+)')) {
    if ($known -notcontains $m.Groups[1].Value) { $known += $m.Groups[1].Value }
}
if ($known.Count -gt 0) { Write-Host ("  bekannte Konten: " + ($known -join ", ")) }

$needsLogin = ($LASTEXITCODE -ne 0) -or ($known.Count -eq 0)

if ($Switch) {
    Write-Host "Neues Konto anmelden (Browser/Device-Code) ..."
    if ($DryRun) { Write-Skip "gh auth login --hostname github.com --git-protocol https --web" }
    else {
        gh auth login --hostname github.com --git-protocol https --web
        if ($LASTEXITCODE -ne 0) { Write-Bad "Anmeldung fehlgeschlagen."; Stop-Here }
    }
} elseif ($Account) {
    if ($known -contains $Account) {
        Write-Host "Wechsle zu Konto $Account ..."
        if ($DryRun) { Write-Skip "gh auth switch --user $Account" }
        else {
            gh auth switch --user $Account 2>&1 | ForEach-Object { "  $_" }
            if ($LASTEXITCODE -ne 0) { Write-Bad "Wechsel zu $Account fehlgeschlagen."; Stop-Here }
        }
    } else {
        Write-Warn2 "$Account ist auf diesem PC nicht angemeldet - starte Anmeldung"
        if ($DryRun) { Write-Skip "gh auth login (Konto $Account)" }
        else {
            gh auth login --hostname github.com --git-protocol https --web
            if ($LASTEXITCODE -ne 0) { Write-Bad "Anmeldung fehlgeschlagen."; Stop-Here }
        }
    }
} elseif ($needsLogin) {
    Write-Host "Du wirst gleich zu GitHub weitergeleitet. Code im Browser bestaetigen."
    if ($DryRun) { Write-Skip "gh auth login --web" }
    else {
        gh auth login --hostname github.com --git-protocol https --web
        if ($LASTEXITCODE -ne 0) { Write-Bad "Anmeldung fehlgeschlagen."; Stop-Here }
    }
}

$who = (gh api user --jq .login 2>$null | Out-String).Trim()
if (-not $who) { Write-Bad "Kein aktives GitHub-Konto ermittelbar."; Stop-Here }
Write-Ok "aktives Konto: $who"

# Git soll die Anmeldung der GitHub CLI benutzen (sonst greift ein alter
# Windows-Credential-Manager-Eintrag und push geht als falscher Benutzer raus).
if ($DryRun) { Write-Skip "gh auth setup-git --hostname github.com" }
else {
    gh auth setup-git --hostname github.com 2>&1 | Out-Null
    $helper = (git config --global --get credential.helper 2>$null | Out-String).Trim()
    Write-Ok "Git-Credential-Helper: $helper"
}

# --------------------------------------------------------------- 3. Scopes ---
Write-Step "3/6 Token-Berechtigungen"
$status = (gh auth status 2>&1 | Out-String)
$missing = @()
foreach ($need in @("repo", "workflow")) {
    if ($status -notmatch "'$need'") { $missing += $need }
}
if ($missing.Count -gt 0) {
    Write-Warn2 ("fehlende Scopes: " + ($missing -join ", ") + " - fordere sie an")
    if ($DryRun) { Write-Skip "gh auth refresh -h github.com -s repo,workflow" }
    else { gh auth refresh -h github.com -s repo,workflow }
} else {
    Write-Ok "Scopes repo + workflow vorhanden"
}

if ($DryRun) { Write-Warn2 "DRY-RUN: es wird nichts angelegt, gepusht oder gesetzt." }

# ------------------------------------------------------------ 4. Repository --
Write-Step "4/6 Repository"
Set-Location $ProjectRoot

if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) {
    Write-Bad "Kein Git-Repository in $ProjectRoot - bitte zuerst 'git init' ausfuehren."
    Stop-Here
}

if (-not $NonInteractive) {
    $answer = Read-Host "Repository-Name [$RepoName]"
    if ($answer) { $RepoName = $answer }
}
$visibility = if ($Public) { "public" } else { "private" }
if (-not $NonInteractive) {
    $v = Read-Host "Sichtbar? (p)rivat oder (o)effentlich [privat]"
    if ($v -match "^(o|oe|off|public)") { $visibility = "public" }
}

gh repo view "$who/$RepoName" --json name 2>&1 | Out-Null
$exists = ($LASTEXITCODE -eq 0)

# Zeigt origin noch auf ein anderes Konto (nach einem Kontowechsel)?
$remoteUrl = (git remote get-url origin 2>$null | Out-String).Trim()
$remoteOwner = $null
if ($remoteUrl -match "github\.com[/:]([^/]+)/([^/.]+)") { $remoteOwner = $matches[1] }

if ($remoteOwner -and $remoteOwner -ne $who) {
    if ($RecreateRepo) {
        Write-Warn2 "origin zeigt auf $remoteOwner - lege $RepoName unter $who neu an"
        $exists = $false
    } else {
        Write-Warn2 "origin zeigt auf $remoteOwner/$RepoName, aktives Konto ist $who"
        Write-Host  "  Push-Rechte pruefen. Fuer ein neues Repo unter $who : -RecreateRepo"
        $exists = $true
    }
}

if ($exists) {
    Write-Ok "Repository: $who/$RepoName"
    if (-not $remoteUrl) {
        if ($DryRun) { Write-Skip "git remote add origin https://github.com/$who/$RepoName.git" }
        else { git remote add origin "https://github.com/$who/$RepoName.git" }
    }
} else {
    Write-Host "Lege Repository $who/$RepoName ($visibility) an ..."
    if ($DryRun) {
        Write-Skip "gh repo create $RepoName --$visibility --source . --remote origin --push"
    } else {
        if ($remoteUrl) {
            # origin existiert schon -> set-url statt add
            gh repo create $RepoName "--$visibility" --description "Sychos Mail - Mailserver, Webmail, Cloudflare Worker" --source .
            if ($LASTEXITCODE -ne 0) { Write-Bad "Repository konnte nicht angelegt werden."; Stop-Here }
            git remote set-url origin "https://github.com/$who/$RepoName.git"
        } else {
            gh repo create $RepoName "--$visibility" --source . --remote origin --push `
                --description "Sychos Mail - Mailserver, Webmail, Cloudflare Worker"
            if ($LASTEXITCODE -ne 0) { Write-Bad "Repository konnte nicht angelegt werden."; Stop-Here }
        }
        Write-Ok "angelegt"
    }
}

if ($DryRun) {
    Write-Skip "git push -u origin main"
} else {
    git push -u origin main
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "Push meldete einen Fehler - Ausgabe oben pruefen" }
    else { Write-Ok "main gepusht" }
}

# --------------------------------------------------------------- 5. Secrets --
Write-Step "5/6 Actions-Secrets (optional, Enter = ueberspringen)"
if ($NonInteractive -or $DryRun) {
    Write-Warn2 "uebersprungen"
    Write-Host "Spaeter: gh secret set CLOUDFLARE_API_TOKEN --repo $who/$RepoName"
    Write-Host "        gh secret set CLOUDFLARE_ACCOUNT_ID --repo $who/$RepoName"
} else {
    Write-Host "Cloudflare API-Token (Rechte: Workers Scripts:Edit, Workers Routes:Edit, Zone Workers Routes:Edit)"
    $token = Read-Host "CLOUDFLARE_API_TOKEN" -AsSecureString
    $tokenPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($token))
    if ($tokenPlain) {
        $tokenPlain | gh secret set CLOUDFLARE_API_TOKEN --repo "$who/$RepoName"
        if ($LASTEXITCODE -eq 0) { Write-Ok "CLOUDFLARE_API_TOKEN gesetzt" }
        else { Write-Bad "Token konnte nicht gesetzt werden" }
    } else { Write-Warn2 "Token uebersprungen" }

    $account = Read-Host "CLOUDFLARE_ACCOUNT_ID"
    if ($account) {
        $account | gh secret set CLOUDFLARE_ACCOUNT_ID --repo "$who/$RepoName"
        if ($LASTEXITCODE -eq 0) { Write-Ok "CLOUDFLARE_ACCOUNT_ID gesetzt" }
        else { Write-Bad "Account-ID konnte nicht gesetzt werden" }
    } else { Write-Warn2 "Account-ID uebersprungen" }
}

# ----------------------------------------------------------------- 6. Pages --
Write-Step "6/6 GitHub Pages"
if ($DryRun) {
    Write-Skip "gh api --method POST repos/$who/$RepoName/pages (build_type=workflow)"
} else {
    '{"build_type":"workflow"}' | gh api --method POST "repos/$who/$RepoName/pages" --input - *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Pages aktiviert (Quelle: GitHub Actions)"
    } else {
        Write-Warn2 "Pages evtl. schon aktiv - manuell: Settings > Pages > Source: GitHub Actions"
    }
}

Write-Host "`nFertig." -ForegroundColor Green
if ($DryRun) { Write-Host "DRY-RUN - es wurde nichts veraendert." -ForegroundColor Yellow }
Write-Host "Repo:     https://github.com/$who/$RepoName"
Write-Host "Actions:  https://github.com/$who/$RepoName/actions"
Write-Host "Secrets:  https://github.com/$who/$RepoName/settings/secrets/actions"
Write-Host "Pages:    https://github.com/$who/$RepoName/settings/pages"
Write-Host "`nErster Deploy: Actions-Lauf abwarten -> https://sychos.de"
if (-not $NonInteractive) { Read-Host "`nEnter zum Schliessen" }
