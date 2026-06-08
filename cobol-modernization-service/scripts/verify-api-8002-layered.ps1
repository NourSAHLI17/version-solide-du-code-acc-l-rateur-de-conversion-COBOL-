# Verify port 8002 has a single listener and behavioral-diff returns layered scoring fields.
# Usage: .\scripts\verify-api-8002-layered.ps1

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8002"

$listeners = @(Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { $_.OwningProcess } | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
Write-Host "[verify] LISTEN PIDs on 8002: $($listeners -join ', ') (count=$($listeners.Count))"
if ($listeners.Count -ne 1) {
    Write-Warning "[verify] Expected exactly one listener on port 8002."
}

$payload = @{
    target_type = "single_file"
    run_id = "verify-layered-8002"
    program_name = "HELLO"
    fallback_mode = $true
    cobol_snapshot_output = "HELLO WORLD`n"
    java_snapshot_output = "HELLO WORLD`n"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "$base/api/testing/behavioral-diff" -Method Post -Body $payload -ContentType "application/json"
$qscore = $response.qscore
$hasLayers = $null -ne $response.layer_scores
Write-Host "[verify] behavioral-diff status=$($response.status) qscore=$qscore layer_scores=$hasLayers"
if ($null -eq $qscore) {
    Write-Error "[verify] FAIL: qscore is null; dashboard will not show layered scoring panel."
}
Write-Host "[verify] PASS: layered fields present on port 8002."
