#Requires -Version 5.1
<#
.SYNOPSIS
    Prints every trained model's accuracy metrics: R2, MAE, RMSE, skill-vs-persistence.
.DESCRIPTION
    Reads the metrics files produced by training (no server or database required):

      1. WAI regional model    services/ml-pipeline/models/artifacts/metrics.json
      2. Flood predictors      services/aquavision-service/data/models/model_metadata.json
      3. RTU telemetry models  services/aquavision-service/ml/artifacts/rtu_metrics.json
      4. PLC attack detector   services/aquavision-service/ml/artifacts/plc_metrics.json
      5. Regional anomaly IF   services/ml-pipeline/models/artifacts/anomaly_metrics.json

    skill = 1 - (model MAE / persistence MAE).   Positive = model beats "predict the same
    as yesterday" (persistence baseline).
.EXAMPLE
    .\scripts\Show-Metrics.ps1
    .\scripts\Show-Metrics.ps1 -WaiOnly
#>
param(
    [switch]$WaiOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$svc = Join-Path $root 'services\aquavision-service'
$pipe = Join-Path $root 'services\ml-pipeline'

function Show-Title([string]$t) {
    Write-Host ''
    Write-Host ('== ' + $t + ' ' + ('=' * [Math]::Max(0, 62 - $t.Length))) -ForegroundColor Cyan
}
function Skill([double]$modelMae, [double]$baseMae) {
    if ($baseMae -eq 0) { return $null }
    return [Math]::Round(1 - ($modelMae / $baseMae), 4)
}
function Verdict([double]$s) {
    if ($null -eq $s) { return '' }
    if ($s -ge 0) { return 'BEATS persistence' } else { return 'trails persistence' }
}

$waiPath = Join-Path $pipe 'models\artifacts\metrics.json'
if (-not (Test-Path $waiPath)) { throw "missing $waiPath" }
$wai = Get-Content $waiPath -Raw | ConvertFrom-Json

Show-Title 'WAI regional model (XGBoost, weekly)'
Write-Host ("Model version   : {0}   train/test: {1}/{2} months" -f $wai.model_version, $wai.n_train, $wai.n_test)
Write-Host ("Regressor  R2   : {0}   MAE {1}   RMSE {2}" -f $wai.regressor.r2, $wai.regressor.mae, $wai.regressor.rmse)
Write-Host ("Persistence R2  : {0}   MAE {1}   RMSE {2}   (baseline = repeat current WAI)" -f $wai.persistence_baseline.r2, $wai.persistence_baseline.mae, $wai.persistence_baseline.rmse)
$skillReg = Skill $wai.regressor.mae $wai.persistence_baseline.mae
Write-Host ("Regressor skill : {0}  {1}" -f $skillReg, (Verdict $skillReg))
Write-Host ("Blend alpha     : {0}  ->  R2 {1}   MAE {2}   RMSE {3}" -f $wai.blend.alpha, $wai.blend.r2, $wai.blend.mae, $wai.blend.rmse)
$skillBlend = Skill $wai.blend.mae $wai.persistence_baseline.mae
Write-Host ("Blend skill     : {0}  {1}" -f $skillBlend, (Verdict $skillBlend))
Write-Host ("Classifier acc  : {0}   (5 severity classes)" -f $wai.classifier.accuracy)
Write-Host ("CI coverage 80% : {0}   inflation {1}" -f $wai.interval.ci_coverage_80, $wai.interval.ci_inflation)
Write-Host ("Test window     : {0} .. {1}" -f $wai.test_month_range[0], $wai.test_month_range[1])
if ($WaiOnly) { exit 0 }

$metaPath = Join-Path $svc 'data\models\model_metadata.json'
if (Test-Path $metaPath) {
    $meta = Get-Content $metaPath -Raw | ConvertFrom-Json
    Show-Title 'Flood predictors (XGBoost per asset x horizon)'
    Write-Host ("Metadata generated: {0}   version {1}" -f $meta.generated_at, $meta.model_version)
    $rows = @()
    foreach ($p in $meta.assets.PSObject.Properties) {
        foreach ($m in $p.Value.models.PSObject.Properties) {
            $v = $m.Value
            if ($v.r2 -ne $null) {
                $rows += [pscustomobject]@{
                    Asset = $v.asset_name
                    Model = $m.Name
                    Status = $v.model_status
                    R2 = [Math]::Round([double]$v.r2, 4)
                    MAE = [Math]::Round([double]$v.mae, 2)
                    RMSE = [Math]::Round([double]$v.rmse, 2)
                    MAPE = $v.mape
                }
            } elseif ($v.accuracy -ne $null) {
                $rows += [pscustomobject]@{
                    Asset = $v.asset_name
                    Model = $m.Name
                    Status = $v.model_status
                    Acc = $v.accuracy
                    AUC = $v.auc
                    F1 = $v.f1
                    Prec = $v.precision
                    Rec = $v.recall
                }
            }
        }
    }
    $flood = $rows | Where-Object { $_.Model -like 'flood_predictor_*' } |
        Sort-Object @{ Expression = { if ($_.Model -match '_(\d+)$') { [int]$Matches[1] } else { 999 } } }, Asset
    if ($flood) {
        $flood | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
        $avgR2 = ($flood | Measure-Object -Property R2 -Average).Average
        Write-Host ("Average flood-predictor R2: {0}   ({1} models = 11 assets x 4 horizons)" -f [Math]::Round($avgR2, 4), $flood.Count)
    }
    $cls = $rows | Where-Object { $_.Model -like 'flood_classifier*' } | Sort-Object Asset
    if ($cls) {
        Write-Host 'Flood classifier (GradientBoosting, 7-day binary: peak above threshold):'
        $cls | Format-Table Asset, Status, Acc, AUC, F1, Prec, Rec -AutoSize | Out-String -Width 120 | Write-Host
    }
} else {
    Write-Warning "model_metadata.json not found at $metaPath (run: POST /water/ml/train)"
}

$rtuPath = Join-Path $svc 'ml\artifacts\rtu_metrics.json'
if (Test-Path $rtuPath) {
    $rtu = Get-Content $rtuPath -Raw | ConvertFrom-Json
    Show-Title 'RTU telemetry models (6-hour horizon)'
    Write-Host ("Source: {0}   cadence {1}   origin {2}" -f $rtu.source, $rtu.cadence, $rtu.data_origin)
    $rtuRows = @()
    foreach ($s in $rtu.sites.PSObject.Properties) {
        $f = $s.Value.forecast
        $rtuRows += [pscustomobject]@{
            Site = $s.Name
            Readings = $s.Value.readings
            'MAE ft' = $f.mae_ft
            'RMSE ft' = $f.rmse_ft
            R2 = $f.r2
            'Persistence MAE' = $f.persistence_mae_ft
            'Skill vs persistence' = $f.skill_vs_persistence
        }
    }
    $rtuRows | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
}

$plcPath = Join-Path $svc 'ml\artifacts\plc_metrics.json'
if (Test-Path $plcPath) {
    $plc = Get-Content $plcPath -Raw | ConvertFrom-Json
    Show-Title 'PLC / OT attack detector (HAI 23.05 dataset)'
    Write-Host ("Signals: {0} discrete + {1} continuous   command-feedback pairs: {2}" -f `
        $plc.signal_classes.discrete_DI_DO, $plc.signal_classes.continuous_AI_AO, $plc.command_feedback_pairs.Count)
    $ad = $plc.attack_detector
    if ($ad) {
        Write-Host ("Attack detector (HistGradientBoosting): precision {0}  recall {1}  F1 {2}  ROC-AUC {3}" -f `
            $ad.precision, $ad.recall, $ad.f1, $ad.roc_auc)
    }
    if ($plc.unsupervised_vs_labels) {
        foreach ($d in $plc.unsupervised_vs_labels.PSObject.Properties) {
            Write-Host ("Unsupervised {0}: flagged {1}  precision {2}  recall {3}  F1 {4}" -f `
                $d.Name, $d.Value.flagged, $d.Value.precision, $d.Value.recall, $d.Value.f1)
        }
    }
}

$anomPath = Join-Path $pipe 'models\artifacts\anomaly_metrics.json'
if (Test-Path $anomPath) {
    $anom = Get-Content $anomPath -Raw | ConvertFrom-Json
    Show-Title 'Regional anomaly detector (IsolationForest)'
    Write-Host ("Rows {0}   anomalies {1}   rate {2}   contamination {3}" -f `
        $anom.n_rows, $anom.n_anomalies, $anom.anomaly_rate, $anom.contamination)
}

Write-Host ''
Write-Host 'Formulas:  skill = 1 - modelMAE/persistenceMAE   |   R2 = 1 - SS_res/SS_tot' -ForegroundColor DarkGray
Write-Host 'Per-asset anomaly scores (IsolationForest): GET /water/ml/anomalies/summary' -ForegroundColor DarkGray
