#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the IBCP-SCADA scheduler - either the Docker service or directly on this machine.
.DESCRIPTION
    -Mode Docker (default): starts the compose service `scheduler` (container ibcp-scheduler,
        command `python -m scheduler.main`) and optionally follows its logs.
    -Mode Local: loads DATABASE_URL from .env and runs `python -m scheduler.main` in the
        foreground from services/aquavision-service (requires: pip install -r requirements.txt).
    The scheduler uses the `schedule` library and loops forever (run_pending every 60 s).
    Stop the local run with Ctrl+C; stop the container with: docker stop ibcp-scheduler
.EXAMPLE
    .\scripts\Start-Scheduler.ps1
    .\scripts\Start-Scheduler.ps1 -Logs
    .\scripts\Start-Scheduler.ps1 -Mode Local
#>
param(
    [ValidateSet('Docker', 'Local')]
    [string]$Mode = 'Docker',
    [switch]$Logs
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if ($Mode -eq 'Docker') {
    Write-Host '== Scheduler : Docker mode (service `scheduler`, container ibcp-scheduler) ==' -ForegroundColor Cyan
    Push-Location $root
    try {
        docker compose up -d scheduler
        if ($LASTEXITCODE -ne 0) { throw 'docker compose up -d scheduler failed' }
    } finally {
        Pop-Location
    }
    docker ps --filter 'name=ibcp-scheduler' --format "table {{.Names}}`t{{.Status}}"
    Write-Host ''
    Write-Host 'Jobs: IRSA 01:30 | FFD 01:00 | retrain Sun 03:00-03:58 | WAI pipeline Sun 04:00' -ForegroundColor DarkGray
    Write-Host '      weather 6-hourly | GEE 04:30 | predictions 02:30 | heartbeat 5-min' -ForegroundColor DarkGray
    if ($Logs) {
        Write-Host ''
        docker compose logs -f scheduler
    } else {
        Write-Host 'Follow logs: docker compose logs -f scheduler' -ForegroundColor DarkGray
    }
} else {
    Write-Host '== Scheduler : Local mode (python -m scheduler.main) ==' -ForegroundColor Cyan
    $envFile = Join-Path $root '.env'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^DATABASE_URL=' | Select-Object -First 1
        if ($line) {
            $env:DATABASE_URL = ($line.Line -replace '^DATABASE_URL=', '')
            Write-Host 'DATABASE_URL loaded from .env'
        }
    } else {
        Write-Warning '.env not found - relying on existing DATABASE_URL environment variable'
    }
    $svc = Join-Path $root 'services\aquavision-service'
    if (-not (Test-Path (Join-Path $svc 'scheduler\main.py'))) { throw "scheduler not found under $svc" }
    Push-Location $svc
    try {
        Write-Host "Running: python -m scheduler.main  (Ctrl+C to stop)"
        Write-Host ''
        python -m scheduler.main
    } finally {
        Pop-Location
    }
}
