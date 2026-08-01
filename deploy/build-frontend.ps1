# Build the MADIO CRM frontend for production.
#
# The backend URL is baked into the bundle at BUILD time (Create React App inlines
# every REACT_APP_* variable), so this must be re-run whenever the API URL changes.
#
#   .\deploy\build-frontend.ps1 -BackendUrl "https://madio-crm-api.onrender.com"
#
# Produces: frontend\build\   → drag that folder onto Netlify.

param(
    [Parameter(Mandatory = $true)]
    [string]$BackendUrl
)

$ErrorActionPreference = "Stop"

# Portable Node (no system install needed on this machine)
$NodeDir = "C:\Users\jagad\AppData\Local\nodejs-portable\node-v20.18.1-win-arm64"
if (Test-Path $NodeDir) { $env:PATH = "$NodeDir;$env:PATH" }

try { node --version | Out-Null } catch {
    Write-Error "Node not found. Install Node 20+, or restore the portable copy at $NodeDir"
    exit 1
}

$Root     = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
Set-Location $Frontend

# Normalise: strip any trailing slash so we never emit "https://host//api"
$clean = $BackendUrl.TrimEnd('/')
if ($clean -notmatch '^https?://') {
    Write-Error "BackendUrl must start with http:// or https:// (got '$BackendUrl')"
    exit 1
}
if ($clean -match '/api$') {
    Write-Warning "Drop the trailing /api - the app appends it itself. Using $($clean -replace '/api$','')"
    $clean = $clean -replace '/api$', ''
}

Write-Host "Backend URL : $clean"
Set-Content -Path ".env" -Value "REACT_APP_BACKEND_URL=$clean" -Encoding utf8

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies (first run only, ~2 min)..."
    npm install --no-audit --no-fund --legacy-peer-deps
}

Write-Host "Building..."
$env:CI = "false"          # keep lint warnings from failing the build
npm run build

# Fail loudly rather than shipping a bundle that phones home
$leak = Select-String -Path "build\index.html", "build\static\js\*.js" `
                      -Pattern "posthog", "emergent.sh" -SimpleMatch -List -ErrorAction SilentlyContinue
if ($leak) {
    Write-Error "Third-party telemetry found in the build output - do not deploy:`n$($leak.Path -join "`n")"
    exit 1
}

$imgs = (Get-ChildItem "build\img\*.jpg" -ErrorAction SilentlyContinue).Count
Write-Host ""
Write-Host "BUILD OK" -ForegroundColor Green
Write-Host "  output      : $Frontend\build"
Write-Host "  API target  : $clean/api"
Write-Host "  product pics: $imgs"
Write-Host "  telemetry   : none"
Write-Host ""
Write-Host "Next: drag the 'build' folder onto https://app.netlify.com/drop"
