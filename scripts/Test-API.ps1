#Requires -Version 5.1
<#
.SYNOPSIS
    Live API test suite - logs in, then calls one representative endpoint per domain and
    prints status + latency. Mirrors the Swagger "Try it out" examples in
    docs/FYP-Defense/06-api-swagger.md
.DESCRIPTION
    Default run is READ-ONLY (plus the login POST). Use -WithMutations to also exercise the
    write endpoints (stress-alert acknowledge, Soft OT setpoint, sensor ingest).

    Every request is exactly what Swagger sends:
      1  POST /auth/login                { "username": "admin", "password": "admin123" }
      2  GET  /auth/me                   Authorization: Bearer <token>
      ... one GET per domain (see $tests) ...
.EXAMPLE
    .\scripts\Test-API.ps1
    .\scripts\Test-API.ps1 -WithMutations
#>
param(
    [string]$Base = 'http://localhost:8100',
    [string]$User = 'admin',
    [string]$Password = 'admin123',
    [switch]$WithMutations
)
$ErrorActionPreference = 'Stop'
$results = New-Object System.Collections.ArrayList

function Invoke-Test {
    param([string]$Name, [string]$Method, [string]$Path, [hashtable]$Headers, $Body)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $code = 'ERR'; $note = ''
    try {
        $params = @{ Uri = ($Base + $Path); Method = $Method; UseBasicParsing = $true; TimeoutSec = 60 }
        if ($Headers) { $params.Headers = $Headers }
        if ($Body -ne $null) {
            $params.ContentType = 'application/json'
            $params.Body = ($Body | ConvertTo-Json -Depth 5)
        }
        $r = Invoke-WebRequest @params
        $code = $r.StatusCode
        if ($r.Content) {
            try {
                $j = $r.Content | ConvertFrom-Json
                if ($j -is [array]) { $note = "items=$($j.Count)" }
                elseif ($j.PSObject.Properties.Name -contains 'access_token') { $note = 'JWT issued' }
                elseif ($j.PSObject.Properties.Name -contains 'total') { $note = "total=$($j.total)" }
                elseif ($j.PSObject.Properties.Name -contains 'points') { $note = "points=$($j.points.Count)" }
                elseif ($j.PSObject.Properties.Name -contains 'assets_total') { $note = "assets=$($j.assets_with_models)/$($j.assets_total)" }
                elseif ($j.detail -is [string] -and $j.detail.Length -lt 60) { $note = $j.detail }
            } catch { $note = [string]$r.Content.Substring(0, [Math]::Min(40, $r.Content.Length)) }
        }
    } catch {
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } else { $code = 'ERR'; $note = $_.Exception.Message.Substring(0, [Math]::Min(70, $_.Exception.Message.Length)) }
    }
    $sw.Stop()
    [void]$results.Add([pscustomobject]@{ N = $Name; Method = $Method; Path = $Path; Code = $code; Ms = $sw.ElapsedMilliseconds; Note = $note })
}

Write-Host "== IBCP-SCADA API tests against $Base ==" -ForegroundColor Cyan

$loginBody = @{ username = $User; password = $Password }
try {
    $login = Invoke-RestMethod -Uri ($Base + '/auth/login') -Method Post -ContentType 'application/json' -Body ($loginBody | ConvertTo-Json)
} catch {
    Write-Host 'LOGIN FAILED - is the API up?  .\scripts\Start-All.ps1' -ForegroundColor Red
    throw
}
$token = $login.access_token
$auth = @{ Authorization = 'Bearer ' + $token }
Write-Host "Logged in as $User (roles: $($login.user.roles -join ','))" -ForegroundColor Green

Invoke-Test 'login'              'POST' '/auth/login'        $null      $loginBody
Invoke-Test 'current user'       'GET'  '/auth/me'           $auth
Invoke-Test 'health'             'GET'  '/health/live'       $null
Invoke-Test 'overview KPIs'      'GET'  '/water/overview'    $auth
Invoke-Test 'operational assets' 'GET'  '/water/operational/assets' $auth
Invoke-Test 'observations'       'GET'  '/water/operational/assets/1/observations?days=7' $auth
Invoke-Test 'prediction v1'      'GET'  '/water/ml/predictions/1' $auth
Invoke-Test 'prediction v2'      'GET'  '/water/v2/predict/1' $auth
Invoke-Test 'anomaly summary'    'GET'  '/water/ml/anomalies/summary?days=30' $auth
Invoke-Test 'anomaly history'    'GET'  '/water/ml/anomalies/1/history?days=30' $auth
Invoke-Test 'model performance'  'GET'  '/water/ml/model-performance' $auth
Invoke-Test 'weekly indicators'  'GET'  '/water/indicators?limit=5' $auth
Invoke-Test 'regions'            'GET'  '/water/regions'     $auth
Invoke-Test 'stress alerts'      'GET'  '/water/stress-alerts?limit=5' $auth
Invoke-Test 'alert queue'        'GET'  '/water/alerts/queue' $auth
Invoke-Test 'flood map'          'GET'  '/water/flood-map/territory' $auth
Invoke-Test 'soft OT status'     'GET'  '/water/ot/status'    $auth
Invoke-Test 'sensor status'      'GET'  '/water/sensors/status' $auth

if ($WithMutations) {
    Write-Host ''
    Write-Host '-- mutations enabled --' -ForegroundColor Yellow
    try {
        $alerts = Invoke-RestMethod -Uri ($Base + '/water/stress-alerts?limit=1&status=New') -Headers $auth
        $id = $alerts.items[0].id
        if ($id) {
            Invoke-Test 'stress alert ack' 'POST' ("/water/stress-alerts/$id/ack") $auth $null
        } else { Write-Host 'no New stress alert to acknowledge' -ForegroundColor DarkGray }
    } catch { Write-Warning "ack test failed: $($_.Exception.Message)" }
    try {
        $sp = @{ asset_id = 1; tag = 'AO.gate_cmd_pct'; value = 50.0 }
        Invoke-Test 'OT setpoint' 'POST' '/water/ot/hmi/setpoint' $auth $sp
    } catch { Write-Warning "setpoint test failed: $($_.Exception.Message)" }
    try {
        $reading = @{ asset_id = 1; observed_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); water_level_ft = 1522.0; inflow_cusecs = 50000; outflow_cusecs = 48000 }
        Invoke-Test 'sensor ingest' 'POST' '/water/sensors/ingest' $auth @{ readings = @($reading) }
    } catch { Write-Warning "sensor test failed: $($_.Exception.Message)" }
}

Write-Host ''
$results | Format-Table @{ L = 'Test'; E = { $_.N } }, @{ L = 'Method'; E = { $_.Method } }, @{ L = 'Code'; E = { $_.Code } }, @{ L = 'Ms'; E = { $_.Ms } }, @{ L = 'Note'; E = { $_.Note } } -AutoSize | Out-String -Width 140 | Write-Host

$ok = @($results | Where-Object { $_.Code -eq 200 -or $_.Code -eq 201 }).Count
$bad = @($results | Where-Object { $_.Code -ne 200 -and $_.Code -ne 201 }).Count
if ($bad -eq 0) { Write-Host "ALL $ok TESTS PASSED" -ForegroundColor Green } else { Write-Host "$ok passed, $bad failed" -ForegroundColor Yellow }
