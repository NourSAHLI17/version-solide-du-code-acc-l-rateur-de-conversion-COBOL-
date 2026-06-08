# Stop all processes bound to the API port (default 8002) and uvicorn/python workers for this app.
# Dot-source from start-api-8002.ps1 / restart-api-8002.ps1, or run directly:
#   .\scripts\Stop-ApiPort8002.ps1

param(
    [int]$Port = 8002,
    [int]$MaxWaitSeconds = 20
)

$ErrorActionPreference = "Continue"

function Get-ListenerPids {
    param([int]$ListenPort)
    @(Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { $_.OwningProcess } |
        Where-Object { $_ -gt 0 } |
        Sort-Object -Unique)
}

function Get-DescendantPids {
    param([int]$RootPid)
    $found = New-Object System.Collections.Generic.List[int]
    $queue = [System.Collections.Queue]::new()
    $queue.Enqueue($RootPid)
    while ($queue.Count -gt 0) {
        $parent = [int]$queue.Dequeue()
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ParentProcessId -eq $parent } |
            ForEach-Object {
                $child = [int]$_.ProcessId
                if ($child -gt 0 -and -not $found.Contains($child)) {
                    [void]$found.Add($child)
                    $queue.Enqueue($child)
                }
            }
    }
    $found
}

function Get-UvicornPortPids {
    param([int]$ListenPort)
    $pattern = "port\s+$ListenPort|:$ListenPort|127\.0\.0\.1:$ListenPort"
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(python|pythonw|uvicorn)(\.exe)?$' -and
            $_.CommandLine -and
            ($_.CommandLine -match 'uvicorn' -or $_.CommandLine -match 'app\.main:app') -and
            ($_.CommandLine -match $pattern)
        } |
        ForEach-Object { [int]$_.ProcessId } |
        Where-Object { $_ -gt 0 } |
        Sort-Object -Unique
}

function Stop-ProcessTree {
    param([int]$ProcId)
    if ($ProcId -le 0) { return }
    foreach ($child in Get-DescendantPids -RootPid $ProcId) {
        Stop-ProcessTree -ProcId $child
    }
    Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
}

Write-Host "[stop-api] Freeing port $Port ..."

$serviceRoot = Split-Path $PSScriptRoot -Parent
$pidFile = Join-Path $serviceRoot ".run\api-$Port.pid"

$deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
$pass = 0
while ((Get-Date) -lt $deadline) {
    $pass++
    $targets = @{}
    foreach ($procId in Get-ListenerPids -ListenPort $Port) { $targets[$procId] = $true }
    foreach ($procId in Get-UvicornPortPids -ListenPort $Port) { $targets[$procId] = $true }

    if (Test-Path $pidFile) {
        $saved = Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($saved -match '^\d+$') { $targets[[int]$saved] = $true }
    }

    if ($targets.Count -eq 0) {
        break
    }

    foreach ($procId in $targets.Keys) {
        Write-Host "[stop-api] Stopping PID $procId (pass $pass)"
        Stop-ProcessTree -ProcId $procId
        # taskkill /T is more reliable on Windows for orphaned reload workers
        & taskkill.exe /PID $procId /T /F 2>$null | Out-Null
    }

    Start-Sleep -Milliseconds 800
    if ((Get-ListenerPids -ListenPort $Port).Count -eq 0) {
        break
    }
}

$remaining = @(Get-ListenerPids -ListenPort $Port)
if ($remaining.Count -gt 0) {
    Write-Warning "[stop-api] Port $Port still has listener(s): $($remaining -join ', ')"
    exit 1
}

if (Test-Path $pidFile) {
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "[stop-api] Port $Port is free."
exit 0
