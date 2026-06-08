# Start the COBOL Modernization API on port 8002 with GnuCOBOL + copybook paths for live behavioral testing.
# Usage (from cobol-modernization-service):
#   .\scripts\start-api-8002.ps1
#   .\scripts\start-api-8002.ps1 -Reload
# Restart (stop port 8002, then start):
#   .\scripts\restart-api-8002.ps1

param(
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$serviceRoot = Split-Path $PSScriptRoot -Parent
$port = 8002

$stopScript = Join-Path $PSScriptRoot "Stop-ApiPort8002.ps1"
& $stopScript -Port $port
if ($LASTEXITCODE -ne 0) {
    Write-Error "[start-api] Could not free port $port. Run Stop-ApiPort8002.ps1 manually or close stray python/uvicorn processes."
}

$runDir = Join-Path $serviceRoot ".run"
if (-not (Test-Path $runDir)) {
    New-Item -ItemType Directory -Path $runDir | Out-Null
}

$GnuCobolBin = Join-Path $env:LOCALAPPDATA "GnuCOBOL\bin"
if (Test-Path $GnuCobolBin) {
    if ($env:Path -notlike "*$GnuCobolBin*") {
        $env:Path = "$GnuCobolBin;$env:Path"
    }
    $GnuGcc = Join-Path (Split-Path $GnuCobolBin -Parent) "mingw64\bin\gcc.exe"
    if (Test-Path $GnuGcc) {
        $env:COB_CC = $GnuGcc
        $mingwBin = Split-Path $GnuGcc -Parent
        if ($env:Path -notlike "*$mingwBin*") {
            $env:Path = "$mingwBin;$env:Path"
        }
    }
    Write-Host "[start-api] GnuCOBOL bin on PATH: $GnuCobolBin"
} else {
    Write-Warning "[start-api] GnuCOBOL not found at $GnuCobolBin - live COBOL tests will report cobc unavailable."
}

$ensureGmp = Join-Path $PSScriptRoot "ensure-gnucobol-gmp.ps1"
if (Test-Path $ensureGmp) {
    & $ensureGmp
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[start-api] GMP install script failed; COMP-3 COBOL may not compile until fixed."
    }
}

$fixtureCopybooks = Join-Path $serviceRoot "tests\fixtures\usecase3\copybooks"
$extraCopyDirs = @($fixtureCopybooks)
$existing = $env:COBOL_COPYBOOK_DIRS
if ($existing) {
    $extraCopyDirs += $existing -split ";"
}
$env:COBOL_COPYBOOK_DIRS = ($extraCopyDirs | Where-Object { $_ -and (Test-Path $_) }) -join ";"
if ($env:COBOL_COPYBOOK_DIRS) {
    Write-Host "[start-api] COBOL_COPYBOOK_DIRS=$($env:COBOL_COPYBOOK_DIRS)"
}

Set-Location $serviceRoot

$uvicornArgs = @(
    "-m", "uvicorn", "app.main:app",
    "--host", "127.0.0.1",
    "--port", "$port"
)
if ($Reload) {
    $uvicornArgs += "--reload"
    Write-Host "[start-api] Reload enabled (one reloader parent; stop via restart-api-8002.ps1 before starting again)."
} else {
    Write-Host "[start-api] Single-process mode (no --reload). Use -Reload for auto-reload during development."
}

Write-Host "[start-api] Starting uvicorn on http://127.0.0.1:$port cwd=$serviceRoot"
Write-Host "[start-api] Single-file behavioral prep: copybook expansion + standalone Java sanitization enabled."

# Foreground: record shell PID so stop script can target this tree if needed.
$pidFile = Join-Path $runDir "api-$port.pid"
Set-Content -Path $pidFile -Value $PID -Encoding ascii

try {
    & python @uvicornArgs
} finally {
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}
