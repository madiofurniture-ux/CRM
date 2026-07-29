# Run the full MADIO CRM test suite.
#
#   .\deploy\run-tests.ps1                 # safe: in-memory DB, touches nothing real
#   .\deploy\run-tests.ps1 -Live           # against your local server + real Atlas
#   .\deploy\run-tests.ps1 -Base "https://madio-crm-api.onrender.com"
#
# Default mode boots the REAL FastAPI app with an in-memory MongoDB, so it works
# even when Atlas is unreachable and can never touch production data.

param(
    [switch]$Live,
    [string]$Base = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$fail = 0

Write-Host "`n=== 1/2  Unit tests (business logic) ===" -ForegroundColor Cyan
python -m pytest backend/tests/test_lifecycle.py -q
if ($LASTEXITCODE -ne 0) { $fail = 1 }

Write-Host "`n=== 2/2  End-to-end API tests ===" -ForegroundColor Cyan

if ($Base) {
    Write-Host "target: $Base (remote)"
    python backend/tests/test_api_e2e.py --base $Base
    if ($LASTEXITCODE -ne 0) { $fail = 1 }
}
elseif ($Live) {
    Write-Host "target: http://127.0.0.1:8000 (expects your own server + real Atlas)"
    python backend/tests/test_api_e2e.py --base "http://127.0.0.1:8000"
    if ($LASTEXITCODE -ne 0) { $fail = 1 }
}
else {
    $port = 8899
    Write-Host "target: in-memory server on port $port (production data untouched)"
    $srv = Start-Process -FilePath "python" `
        -ArgumentList "backend/tests/run_local_server.py","--port",$port `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput "$env:TEMP\madio_test_srv.log" `
        -RedirectStandardError "$env:TEMP\madio_test_srv.err"
    try {
        $ready = $false
        foreach ($i in 1..40) {
            Start-Sleep -Seconds 2
            try {
                if ((Invoke-WebRequest "http://127.0.0.1:$port/api/" -TimeoutSec 4 -UseBasicParsing).StatusCode -eq 200) {
                    $ready = $true; break
                }
            } catch { }
        }
        if (-not $ready) {
            Write-Error "Test server did not start. See $env:TEMP\madio_test_srv.err"
            exit 1
        }
        python backend/tests/test_api_e2e.py --base "http://127.0.0.1:$port"
        if ($LASTEXITCODE -ne 0) { $fail = 1 }
    }
    finally {
        if ($srv -and -not $srv.HasExited) { Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
} else {
    Write-Host "TESTS FAILED - see output above" -ForegroundColor Red
}
exit $fail
