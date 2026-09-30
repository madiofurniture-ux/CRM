# Run the whole MADIO CRM on this machine so you can click through it before go-live.
#
#   .\deploy\run-local.ps1
#
# It will:
#   1. check whether MongoDB Atlas is reachable
#        reachable  -> uses YOUR REAL DATA (edits are permanent)
#        unreachable-> uses a local in-memory copy (safe sandbox, nothing saved)
#   2. start the backend
#   3. build the frontend if needed, pointed at that backend
#   4. serve it and open your browser
#
# Press Ctrl+C in this window to stop everything.

param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [switch]$ForceSandbox,   # ignore Atlas even if reachable
    [switch]$Rebuild         # force a fresh frontend build
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$NodeDir = "C:\Users\jagad\AppData\Local\nodejs-portable\node-v20.18.1-win-arm64"
if (Test-Path $NodeDir) { $env:PATH = "$NodeDir;$env:PATH" }

# Reuse the PINs already recorded in backend\role-pins.env so a sandbox run has
# the SAME logins as live. Without this the sandbox mints a fresh random PIN for
# every role on every run, and there is no way to log in.
$PinFile = Join-Path $Root "backend\role-pins.env"
$KnownPins = $false
if (Test-Path $PinFile) {
    $line = Select-String -Path $PinFile -Pattern '^SEED_PINS=' | Select-Object -First 1
    if ($line) {
        $env:SEED_PINS = ($line.Line -replace '^SEED_PINS=', '').Trim()
        $KnownPins = $true
    }
}

# -- 1. can we reach Atlas? ------------------------------------------------
$useReal = $false
if (-not $ForceSandbox) {
    Write-Host "Checking MongoDB Atlas..." -NoNewline
    $probe = python -c @"
import os,sys
from pathlib import Path
for l in Path('backend/.env').read_text(encoding='utf-8').splitlines():
    if '=' in l and not l.startswith('#'):
        k,v=l.split('=',1); os.environ.setdefault(k.strip(),v.strip())
try:
    from pymongo import MongoClient
    MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=8000).admin.command('ping')
    print('OK')
except Exception as e:
    m=str(e)
    if 'Authentication failed' in m or 'bad auth' in m: print('AUTH')
    else: print('UNREACHABLE')
"@ 2>$null
    if ($probe -match "OK") { $useReal = $true; Write-Host " connected" -ForegroundColor Green }
    elseif ($probe -match "AUTH") { Write-Host " wrong password (rotated?)" -ForegroundColor Yellow }
    else { Write-Host " unreachable" -ForegroundColor Yellow }
}

Write-Host ""
if ($useReal) {
    Write-Host "MODE: LIVE DATA  - changes you make are SAVED to Atlas" -ForegroundColor Red
} else {
    Write-Host "MODE: SANDBOX    - in-memory copy, nothing is saved" -ForegroundColor Cyan
    Write-Host "      (real 643-item inventory; other data is sample)"
    if (-not $ForceSandbox) {
        Write-Host "      To use live data: allow your IP in Atlas -> Network Access," -ForegroundColor DarkGray
        Write-Host "      and un-pause the cluster if it is paused." -ForegroundColor DarkGray
    }
}
Write-Host ""

# -- 2. backend ------------------------------------------------------------
$apiLog = Join-Path $env:TEMP "madio_api.log"
if ($useReal) {
    $api = Start-Process python -ArgumentList "-m","uvicorn","server:app","--port",$ApiPort `
           -WorkingDirectory (Join-Path $Root "backend") -PassThru -WindowStyle Hidden `
           -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.err"
} else {
    $api = Start-Process python -ArgumentList "backend/tests/run_local_server.py","--port",$ApiPort `
           -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
           -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.err"
}

Write-Host "Starting backend on port $ApiPort..." -NoNewline
$ready = $false
foreach ($i in 1..45) {
    Start-Sleep -Seconds 2
    try {
        if ((Invoke-WebRequest "http://127.0.0.1:$ApiPort/api/" -TimeoutSec 4 -UseBasicParsing).StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "See $apiLog.err"
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    exit 1
}
Write-Host " ready" -ForegroundColor Green

# -- 3. frontend build -----------------------------------------------------
$apiUrl   = "http://127.0.0.1:$ApiPort"
$buildDir = Join-Path $Root "frontend\build"
$envFile  = Join-Path $Root "frontend\.env"
$needs = $Rebuild -or -not (Test-Path (Join-Path $buildDir "index.html"))
if (-not $needs -and (Test-Path $envFile)) {
    if ((Get-Content $envFile -Raw) -notmatch [regex]::Escape($apiUrl)) { $needs = $true }
}
if ($needs) {
    Write-Host "Building frontend for $apiUrl (about 1 min)..."
    & (Join-Path $PSScriptRoot "build-frontend.ps1") -BackendUrl $apiUrl | Out-Null
    Write-Host "Build done." -ForegroundColor Green
} else {
    Write-Host "Reusing existing build (already points at $apiUrl)."
}

# -- 4. serve + open -------------------------------------------------------
$web = Start-Process python -ArgumentList "deploy/serve_spa.py","--dir","frontend/build","--port",$WebPort `
       -WorkingDirectory $Root -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

$url = "http://127.0.0.1:$WebPort"
Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "  MADIO CRM is running:  $url"
Write-Host "  API:                   $apiUrl/api/"
Write-Host ""
Write-Host "  Logins are ROLES: promoter, admin, mf, map, mdw, accounting, reception"
if ($KnownPins) {
    Write-Host "  PINs:   backend\role-pins.env  (same PINs in sandbox and live)"
} else {
    Write-Host "  PINs:   generated randomly this run - see $apiLog" -ForegroundColor Yellow
    Write-Host "          (create backend\role-pins.env to keep them stable)" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "  Worth checking:"
Write-Host "    Inventory            643 items, product photos"
Write-Host "    Projects             opens without error (was crashing)"
Write-Host "    D&W Survey           remarks + Add photo"
Write-Host "    Admin > Financial Year   hide/show a year"
Write-Host "    Admin > Workflows        edit stages, Use my data, enforce"
Write-Host "    Sales                then re-check after hiding a year"
Write-Host ""
Write-Host "  Ctrl+C here to stop." -ForegroundColor DarkGray
Write-Host "======================================================" -ForegroundColor Green

Start-Process $url

try { while ($true) { Start-Sleep -Seconds 3 } }
finally {
    Write-Host "`nStopping..."
    foreach ($p in @($api, $web)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
}
