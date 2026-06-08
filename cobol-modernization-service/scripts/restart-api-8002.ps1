# Restart the COBOL Modernization API on port 8002 (free port, then start with GnuCOBOL + copybook paths).
# Usage (from cobol-modernization-service):
#   .\scripts\restart-api-8002.ps1
#   .\scripts\restart-api-8002.ps1 -Reload

param(
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$stopScript = Join-Path $PSScriptRoot "Stop-ApiPort8002.ps1"
Write-Host "[restart-api] Stopping all listeners on port 8002..."
& $stopScript -Port 8002 -MaxWaitSeconds 25
if ($LASTEXITCODE -ne 0) {
    Write-Error "[restart-api] Port 8002 could not be freed. Close remaining python/uvicorn processes and retry."
}

$startScript = Join-Path $PSScriptRoot "start-api-8002.ps1"
Write-Host "[restart-api] Starting API via $startScript"
if ($Reload) {
    & $startScript -Reload
} else {
    & $startScript
}
