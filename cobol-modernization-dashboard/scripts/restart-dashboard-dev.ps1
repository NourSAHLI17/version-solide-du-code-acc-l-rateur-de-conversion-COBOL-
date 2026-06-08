# Stop processes listening on port 3000 and start Next.js dev on 127.0.0.1:3000.
# Usage (from cobol-modernization-dashboard):
#   .\scripts\restart-dashboard-dev.ps1

$ErrorActionPreference = "Continue"
$port = 3000

Write-Host "[restart-dashboard] Stopping listeners on port $port..."
for ($pass = 1; $pass -le 5; $pass++) {
    $pids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { $_.OwningProcess } | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    foreach ($procId in $pids) {
        Write-Host "[restart-dashboard] Stopping PID $procId (pass $pass)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        & taskkill.exe /PID $procId /T /F 2>$null | Out-Null
    }
    Start-Sleep -Milliseconds 800
    if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        break
    }
}

$still = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($still) {
    Write-Warning "[restart-dashboard] Port $port still in use. Close remaining Node processes and retry."
    exit 1
}

Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "[restart-dashboard] Starting npm run dev (127.0.0.1:$port)..."
npm run dev
