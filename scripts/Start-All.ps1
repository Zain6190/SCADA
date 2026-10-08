#Requires -Version 5.1
<#
.SYNOPSIS
    Starts the full IBCP-SCADA stack (db, api, scheduler, frontend) and waits for API health.
.DESCRIPTION
    Uses the latest built images - no rebuild. Prints UI/Swagger URLs and container status
    when done. Run from anywhere inside the repo.
.EXAMPLE
    .\scripts\Start-All.ps1
    .\scripts\Start-All.ps1 -Logs
#>
param(
    [switch]$Logs
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host '== IBCP-SCADA : starting containers (latest images) ==' -ForegroundColor Cyan
Push-Location $root
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

    $health = 'http://localhost:8100/health/live'
    Write-Host -NoNewline 'Waiting for API '
    $up = $false
    for ($i = 1; $i -le 36; $i++) {
        Start-Sleep -Seconds 5
        try {
            $r = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $up = $true; Write-Host "OK ($($i * 5)s)" -ForegroundColor Green; break }
        } catch { }
        Write-Host -NoNewline '.'
    }
    if (-not $up) { Write-Host ' TIMEOUT' -ForegroundColor Red; exit 1 }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Services:' -ForegroundColor Cyan
docker ps --filter 'name=ibcp' --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"

Write-Host ''
Write-Host 'URLs:' -ForegroundColor Cyan
Write-Host '  UI      http://localhost:3000/'
Write-Host '  Swagger http://localhost:8100/docs'
Write-Host '  Health  http://localhost:8100/health/live'
Write-Host '  Login   admin / admin123'
Write-Host ''
Write-Host 'Next: .\scripts\Test-API.ps1  |  .\scripts\Query-DB.ps1  |  .\scripts\Show-Metrics.ps1' -ForegroundColor DarkGray

if ($Logs) {
    Write-Host ''
    docker compose logs -f scheduler
}
