#Requires -Version 5.1
<#
.SYNOPSIS
    Read-only SQL console / summary over the database configured in .env (DATABASE_URL).
.DESCRIPTION
    Runs psql from inside the ibcp-postgis container, connecting to whatever DATABASE_URL
    points at (Neon in .env, or the local Postgres container if overridden).

      .\scripts\Query-DB.ps1                 # 8 standard defense queries
      .\scripts\Query-DB.ps1 -Query "SELECT 1"  # arbitrary read-only SQL
      .\scripts\Query-DB.ps1 -Tables          # list tables + row counts

    If DATABASE_URL targets localhost, the host is rewritten to host.docker.internal so the
    query can reach the host-mapped port from inside the container.
.EXAMPLE
    .\scripts\Query-DB.ps1
#>
param(
    [string]$Query = '',
    [switch]$Tables,
    [string]$Url = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if (-not $Url) {
    $envFile = Join-Path $root '.env'
    if (-not (Test-Path $envFile)) { throw ".env not found at $envFile (set -Url to pass a connection string)" }
    $line = Select-String -Path $envFile -Pattern '^DATABASE_URL=' | Select-Object -First 1
    if (-not $line) { throw 'DATABASE_URL not found in .env' }
    $Url = ($line.Line -replace '^DATABASE_URL=', '')
}
# localhost is not reachable from inside a container -> use the host gateway instead
$Url = $Url -replace '://localhost(:\d+)?/', '://host.docker.internal$1/' -replace '://127\.0\.0\.1(:\d+)?/', '://host.docker.internal$1/'

function Invoke-Sql([string]$Sql, [string]$Header) {
    Write-Host ''
    if ($Header) { Write-Host ('-- ' + $Header) -ForegroundColor Cyan }
    $out = docker exec -i ibcp-postgis psql $Url -X -v ON_ERROR_STOP=0 -c $Sql 2>&1
    $out | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        $text = ($out | Out-String)
        if ($text -match 'could not connect|connection to server') {
            Write-Warning 'cannot reach the database - is it up?  .\scripts\Start-All.ps1'
            throw 'database connection failed'
        }
        Write-Warning 'query failed (see above) - continuing'
    }
}

$psqlUp = docker ps --filter 'name=ibcp-postgis' --format '{{.Names}}'
if (-not $psqlUp) { throw 'ibcp-postgis container is not running.  .\scripts\Start-All.ps1' }

if ($Query) {
    Invoke-Sql $Query 'custom query'
    exit 0
}

if ($Tables) {
    Invoke-Sql "SELECT schemaname || '.' || relname AS table, n_live_tup AS approx_rows FROM pg_stat_user_tables ORDER BY n_live_tup DESC;" 'tables (by size)'
    exit 0
}

Write-Host '== IBCP-SCADA database summary (read-only) ==' -ForegroundColor Cyan

Invoke-Sql "SELECT count(*) AS users, count(*) FILTER (WHERE is_active) AS active, count(*) FILTER (WHERE last_login_at IS NOT NULL) AS ever_logged_in FROM shared.users;" 'users / RBAC accounts (shared.users)'

Invoke-Sql "SELECT source_authority, count(*) AS obs, min(observed_at)::date AS first, max(observed_at)::date AS last FROM aquavision.water_observations GROUP BY source_authority ORDER BY obs DESC;" 'observations by source authority'

Invoke-Sql "SELECT asset_id, observed_at, water_level_ft, inflow_cusecs, outflow_cusecs FROM aquavision.water_observations WHERE asset_id = 1 ORDER BY observed_at DESC LIMIT 5;" 'latest 5 readings - asset 1 (Tarbela)'

Invoke-Sql "SELECT week_start_date, region_id, wai_score, severity, rainfall_anomaly, et_anomaly FROM aquavision.water_indicators_weekly ORDER BY week_start_date DESC LIMIT 5;" 'latest weekly WAI indicators'

Invoke-Sql "SELECT alert_type, severity, count(*) FROM aquavision.water_alerts GROUP BY alert_type, severity ORDER BY count DESC;" 'alerts by type / severity'

Invoke-Sql "SELECT status, count(*) FROM aquavision.water_alerts GROUP BY status;" 'alert queue by status'

Invoke-Sql "SELECT pipeline_type, status, started_at, completed_at FROM aquavision.pipeline_runs ORDER BY started_at DESC LIMIT 5;" 'last 5 pipeline runs'

Invoke-Sql "SELECT service_name, status, last_heartbeat_at FROM aquavision.scheduler_heartbeats ORDER BY last_heartbeat_at DESC LIMIT 10;" 'scheduler heartbeats (latest per service)'

Write-Host ''
Write-Host 'Custom SQL : .\scripts\Query-DB.ps1 -Query "SELECT now()"' -ForegroundColor DarkGray
Write-Host 'Tables     : .\scripts\Query-DB.ps1 -Tables' -ForegroundColor DarkGray
