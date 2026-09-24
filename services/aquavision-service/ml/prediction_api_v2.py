# ml/prediction_api_v2.py
# API endpoints for AquaVision Prediction Model v2.0
# GET  /water/v2/predict/{asset_id}          - Multi-lead prediction
# GET  /water/v2/predict/{asset_id}/{lead}   - Single lead prediction
# GET  /water/v2/national-overview            - NDMA dashboard view
# GET  /water/v2/asset/{asset_id}/forecast    - Chart data for frontend

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAsset

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Pydantic Response Models ────────────────────────────────────────────────

class DischargeResponse(BaseModel):
    value_m3s: float
    confidence_lower_m3s: float
    confidence_upper_m3s: float
    value_cusecs: float
    confidence_lower_cusecs: float
    confidence_upper_cusecs: float
    unit: str = "m3/s"
    # Interval provenance: "quantile_q10_q90" | "residual_p90" | "r2_band" |
    # "physics_band" | "pct_heuristic"
    ci_method: Optional[str] = None


class WaterStressResponse(BaseModel):
    value: int
    category: str
    trend: int
    components: Dict[str, int]


class FloodRiskResponse(BaseModel):
    value: int
    category: str
    confidence: Optional[float] = None
    drivers: List[Dict[str, str]]


class RainfallResponse(BaseModel):
    value_mm: float
    probability: float
    unit: str = "mm"


class LeadTimeResponse(BaseModel):
    lead_time_days: int
    water_stress: WaterStressResponse
    flood_risk: FloodRiskResponse
    discharge: DischargeResponse
    rainfall: RainfallResponse
    confidence: Optional[float] = None


class AlertResponse(BaseModel):
    level: str
    type: str
    message: str
    action: str
    lead_time: str
    timestamp: str


class PredictionResponse(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    timestamp: str
    predictions: Dict[str, LeadTimeResponse]
    alerts: List[AlertResponse]
    model_metadata: Dict


class ProvincePrediction(BaseModel):
    province: str
    wai_score: int
    category: str
    assets: List[PredictionResponse]


class NationalOverviewResponse(BaseModel):
    timestamp: str
    national_wai: float
    national_status: str
    provinces: List[ProvincePrediction]
    critical_alerts: List[AlertResponse]
    assets_monitored: int


class ForecastChartResponse(BaseModel):
    dates: List[str]
    actual: List[Optional[float]]
    forecast_3d: List[Optional[float]]
    forecast_7d: List[Optional[float]]
    forecast_14d: List[Optional[float]]
    confidence_lower: List[Optional[float]]
    confidence_upper: List[Optional[float]]
    warning_level: Optional[float]
    danger_level: Optional[float]


# ─── API Endpoints ───────────────────────────────────────────────────────────

@router.get("/v2/predict/{asset_id}", response_model=PredictionResponse)
async def get_prediction(
    asset_id: int,
    lead_times: str = Query("3,7,14", description="Comma-separated lead times"),
    session: Session = Depends(get_session),
):
    """Get multi-lead prediction for an asset.

    Returns Water Stress (0-100), Flood Risk (0-100), Discharge (m3/s with CI),
    and Rainfall Alert (mm with probability) for each lead time.
    """
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        from ml.models.prediction_v2 import AquaVisionPredictionModel

        model = AquaVisionPredictionModel(session=session)
        lt_list = [int(l.strip()) for l in lead_times.split(",")]

        result = model.predict(
            asset_id=asset_id,
            asset_name=asset.canonical_name,
            asset_type=asset.asset_type or "barrage",
            lead_times=lt_list,
        )

        return PredictionResponse(
            asset_id=result.asset_id,
            asset_name=result.asset_name,
            asset_type=result.asset_type,
            timestamp=result.timestamp,
            predictions={
                k: LeadTimeResponse(
                    lead_time_days=v.lead_time_days,
                    water_stress=WaterStressResponse(**v.water_stress.__dict__),
                    flood_risk=FloodRiskResponse(**v.flood_risk.__dict__),
                    discharge=DischargeResponse(**v.discharge.__dict__),
                    rainfall=RainfallResponse(**v.rainfall.__dict__),
                    confidence=v.confidence,
                )
                for k, v in result.predictions.items()
            },
            alerts=[AlertResponse(**a) for a in result.alerts],
            model_metadata=result.model_metadata,
        )

    except Exception as e:
        logger.error(f"Prediction failed for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/v2/predict/{asset_id}/{lead_time}", response_model=LeadTimeResponse)
async def get_single_lead_prediction(
    asset_id: int,
    lead_time: int,
    session: Session = Depends(get_session),
):
    """Get prediction for a single lead time."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if lead_time not in [3, 7, 14]:
        raise HTTPException(status_code=400, detail="Lead time must be 3, 7, or 14 days")

    try:
        from ml.models.prediction_v2 import AquaVisionPredictionModel

        model = AquaVisionPredictionModel(session=session)
        result = model.predict(
            asset_id=asset_id,
            asset_name=asset.canonical_name,
            asset_type=asset.asset_type or "barrage",
            lead_times=[lead_time],
        )

        forecast = result.predictions[f"{lead_time}_day"]
        return LeadTimeResponse(
            lead_time_days=forecast.lead_time_days,
            water_stress=WaterStressResponse(**forecast.water_stress.__dict__),
            flood_risk=FloodRiskResponse(**forecast.flood_risk.__dict__),
            discharge=DischargeResponse(**forecast.discharge.__dict__),
            rainfall=RainfallResponse(**forecast.rainfall.__dict__),
            confidence=forecast.confidence,
        )

    except Exception as e:
        logger.error(f"Prediction failed for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/v2/national-overview", response_model=NationalOverviewResponse)
async def get_national_overview(
    session: Session = Depends(get_session),
):
    """National overview for NDMA dashboard.

    Returns WAI scores and predictions for all provinces and assets.
    """
    from ml.models.prediction_v2 import AquaVisionPredictionModel

    model = AquaVisionPredictionModel(session=session)

    # Get all active assets
    assets = session.query(WaterAsset).filter(WaterAsset.is_active == True).all()

    # Group by province
    province_assets = {}
    for asset in assets:
        province = asset.province or "Unknown"
        if province not in province_assets:
            province_assets[province] = []
        province_assets[province].append(asset)

    provinces = []
    all_alerts = []

    for province, prov_assets in province_assets.items():
        asset_predictions = []
        wai_scores = []

        for asset in prov_assets:
            try:
                result = model.predict(
                    asset_id=asset.id,
                    asset_name=asset.canonical_name,
                    asset_type=asset.asset_type or "barrage",
                    lead_times=[7],
                )
                asset_predictions.append(asdict(result))

                # Get WAI from 7-day forecast
                forecast_7d = result.predictions.get("7_day")
                if forecast_7d:
                    wai_scores.append(forecast_7d.water_stress.value)

                all_alerts.extend(result.alerts)
            except Exception as e:
                logger.warning(f"Prediction failed for asset {asset.id}: {e}")

        avg_wai = sum(wai_scores) / len(wai_scores) if wai_scores else 50
        from domain.water_classifier import classify_severity

        provinces.append(ProvincePrediction(
            province=province,
            wai_score=int(avg_wai),
            category=classify_severity(avg_wai),
            assets=asset_predictions,
        ))

    # National WAI
    all_wai = [p.wai_score for p in provinces]
    national_wai = sum(all_wai) / len(all_wai) if all_wai else 50

    from domain.water_classifier import classify_severity

    # Filter critical alerts
    critical_alerts = [a for a in all_alerts if a.get("level") in ("CRITICAL", "HIGH")]

    return NationalOverviewResponse(
        timestamp=datetime.utcnow().isoformat(),
        national_wai=round(national_wai, 1),
        national_status=classify_severity(national_wai),
        provinces=provinces,
        critical_alerts=critical_alerts,
        assets_monitored=len(assets),
    )


@router.get("/v2/asset/{asset_id}/forecast-chart", response_model=ForecastChartResponse)
async def get_forecast_chart_data(
    asset_id: int,
    session: Session = Depends(get_session),
):
    """Get time series data for forecast chart (for frontend)."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    from sqlalchemy import text as sql_text

    # Get historical observations (last 30 days)
    rows = session.execute(
        sql_text("""
            SELECT observed_at, discharge_cusecs, water_level_ft
            FROM aquavision.water_observations
            WHERE asset_id = :aid
            ORDER BY observed_at DESC
            LIMIT 30
        """),
        {"aid": asset_id},
    ).mappings().all()

    dates = []
    actual = []

    for row in reversed(rows):
        dates.append(row["observed_at"].strftime("%Y-%m-%d") if row["observed_at"] else "")
        actual.append(float(row["discharge_cusecs"]) if row["discharge_cusecs"] else None)

    # Get predictions for each lead time
    from ml.models.prediction_v2 import AquaVisionPredictionModel

    model = AquaVisionPredictionModel(session=session)
    result = model.predict(
        asset_id=asset_id,
        asset_name=asset.canonical_name,
        asset_type=asset.asset_type or "barrage",
        lead_times=[3, 7, 14],
    )

    # Build forecast arrays
    forecast_3d = [None] * len(dates)
    forecast_7d = [None] * len(dates)
    forecast_14d = [None] * len(dates)
    conf_lower = [None] * len(dates)
    conf_upper = [None] * len(dates)

    # Add forecast points
    from datetime import timedelta

    today = datetime.utcnow().date()
    for lt_key, forecast in result.predictions.items():
        lt = forecast.lead_time_days
        forecast_date = today + timedelta(days=lt)
        date_str = forecast_date.strftime("%Y-%m-%d")

        if date_str not in dates:
            dates.append(date_str)
            actual.append(None)
            forecast_3d.append(None)
            forecast_7d.append(None)
            forecast_14d.append(None)
            conf_lower.append(None)
            conf_upper.append(None)

        idx = dates.index(date_str)
        if lt == 3:
            forecast_3d[idx] = forecast.discharge.value_cusecs
        elif lt == 7:
            forecast_7d[idx] = forecast.discharge.value_cusecs
        elif lt == 14:
            forecast_14d[idx] = forecast.discharge.value_cusecs
        # Interval belongs to this lead time's forecast point (all lead times)
        conf_lower[idx] = forecast.discharge.confidence_lower_cusecs
        conf_upper[idx] = forecast.discharge.confidence_upper_cusecs

    # Sort by date
    sorted_indices = sorted(range(len(dates)), key=lambda i: dates[i])
    dates = [dates[i] for i in sorted_indices]
    actual = [actual[i] for i in sorted_indices]
    forecast_3d = [forecast_3d[i] for i in sorted_indices]
    forecast_7d = [forecast_7d[i] for i in sorted_indices]
    forecast_14d = [forecast_14d[i] for i in sorted_indices]
    conf_lower = [conf_lower[i] for i in sorted_indices]
    conf_upper = [conf_upper[i] for i in sorted_indices]

    return ForecastChartResponse(
        dates=dates,
        actual=actual,
        forecast_3d=forecast_3d,
        forecast_7d=forecast_7d,
        forecast_14d=forecast_14d,
        confidence_lower=conf_lower,
        confidence_upper=conf_upper,
        # warning_level_ft / critical_level_ft are ELEVATION in feet — plotting
        # them against a cusecs axis would mix units. No rating curve ⇒ None.
        warning_level=None,
        danger_level=None,
    )
