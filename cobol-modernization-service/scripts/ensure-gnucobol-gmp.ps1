# Install GMP dev headers/libs for GnuCOBOL COMP-3 support (behavioral live COBOL).
# Usage (from cobol-modernization-service):
#   .\scripts\ensure-gnucobol-gmp.ps1
#   .\scripts\ensure-gnucobol-gmp.ps1 -Force

$ErrorActionPreference = "Stop"
$serviceRoot = Split-Path $PSScriptRoot -Parent
$py = Join-Path $serviceRoot "scripts\ensure_gnucobol_gmp.py"
$args = @()
if ($Force) { $args += "--force" }
python $py @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[ensure-gmp] Done. Restart the API if it is already running."
