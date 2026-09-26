# GET /water/flood-map/territory
# District polygons painted from the latest asset flood prediction, plus
# region alerts for moderate severity and above.
import json

from fastapi import APIRouter, Depends
from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAsset, WaterAssetThreshold, WaterDownstreamImpact, WaterObservation, WaterOperationalAlert
from infrastructure.thresholds.engine import official_observation_clause
from infrastructure.flood.official_shapes import apply_official_geometries, index_geometries, load_shape_file
from infrastructure.flood.territories import (
    AssetFlood,
    LocatedPoint,
    SegmentImpact,
    build_flood_territory,
    threshold_flood_classification,
)

router = APIRouter()


def _f(value) -> float | None:
    return float(value) if value is not None else None


def _threshold_kw(thr) -> dict:
    if thr is None:
        return {}
    return {
        "warning_level_ft": _f(thr.warning_level_ft),
        "critical_level_ft": _f(thr.critical_level_ft),
        "warning_discharge": _f(thr.warning_discharge),
        "danger_discharge": _f(thr.danger_discharge),
    }


def load_flood_territory(session: Session) -> dict:
    assets = session.execute(select(WaterAsset).where(WaterAsset.is_active == True)).scalars().all()
    asset_names = {asset.id: asset.canonical_name for asset in assets}
    thresholds = {
        int(t.asset_id): t
        for t in session.execute(select(WaterAssetThreshold)).scalars().all()
    }

    alerts = session.execute(
        select(WaterOperationalAlert)
        .where(WaterOperationalAlert.flood_probability.isnot(None))
        .order_by(desc(WaterOperationalAlert.created_at))
    ).scalars().all()

    classifications: dict[int, AssetFlood] = {}
    for alert in alerts:
        if alert.asset_id in classifications:
            continue
        classifications[alert.asset_id] = AssetFlood(
            asset_id=alert.asset_id,
            name=asset_names.get(alert.asset_id, f"Asset {alert.asset_id}"),
            probability=float(alert.flood_probability or 0.0),
            severity=(alert.flood_severity or "NONE").upper(),
            recommendation=alert.flood_recommendation or "",
        )

    latest_obs = (
        select(
            WaterObservation.asset_id,
            func.max(WaterObservation.observed_at).label("observed_at"),
        )
        .where(official_observation_clause())
        .group_by(WaterObservation.asset_id)
        .subquery()
    )
    observations = session.execute(
        select(WaterObservation).join(
            latest_obs,
            and_(
                WaterObservation.asset_id == latest_obs.c.asset_id,
                WaterObservation.observed_at == latest_obs.c.observed_at,
            ),
        )
    ).scalars().all()
    obs_by_asset = {obs.asset_id: obs for obs in observations}

    for asset in assets:
        if asset.id in classifications:
            continue
        obs = obs_by_asset.get(asset.id)
        if obs is None:
            continue
        fallback = threshold_flood_classification(
            discharge=_f(obs.discharge_cusecs),
            inflow=_f(obs.inflow_cusecs),
            level=_f(obs.water_level_ft),
            **_threshold_kw(thresholds.get(asset.id)),
        )
        if fallback is None:
            continue
        probability, severity, recommendation = fallback
        classifications[asset.id] = AssetFlood(
            asset_id=asset.id,
            name=asset.canonical_name,
            probability=probability,
            severity=severity,
            recommendation=recommendation,
        )

    impacts: dict[tuple[int, int], SegmentImpact] = {}
    rows = session.execute(select(WaterDownstreamImpact)).scalars().all()
    for row in rows:
        if row.downstream_asset_id is None:
            continue
        key = (row.source_asset_id, row.downstream_asset_id)
        candidate = SegmentImpact(
            population=int(row.affected_population_est or 0),
            bridges=int(row.bridges_count or 0),
            hospitals=int(row.hospitals_count or 0),
        )
        current = impacts.get(key)
        if current is None or candidate.population > current.population:
            impacts[key] = candidate

    located = [
        LocatedPoint(asset.canonical_name, "asset", float(asset.latitude), float(asset.longitude))
        for asset in assets
        if asset.latitude is not None and asset.longitude is not None
    ]
    payload = build_flood_territory(classifications, impacts, asset_names, located)
    payload = apply_official_geometries(payload, _official_geometries(session))
    return _apply_process_view(session, payload, thresholds)


def _official_geometries(session: Session) -> dict:
    """Official district polygons from PostGIS, then the cached geo file for any gaps."""
    geometries = load_shape_file()
    rows = session.execute(
        text(
            """
            SELECT name,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.01)) AS geojson
            FROM shared.regions
            WHERE type = 'district' AND geom IS NOT NULL
            """
        )
    ).all()
    features = []
    for name, geojson in rows:
        if not geojson:
            continue
        features.append({"properties": {"name": name}, "geometry": json.loads(geojson)})
    geometries.update(index_geometries(features))
    return geometries


def _apply_process_view(session: Session, payload: dict, thresholds: dict) -> dict:
    """Scenario discharges repaint the district. Track mode keeps the official classification."""
    try:
        from infrastructure.ot.persist import get_runtime
        from ot_runtime.series import flood_discharge
        runtime = get_runtime(db=session, auto_anchor=True)
    except Exception:
        return payload
    if not runtime.series_loaded:
        return payload
    by_asset = {int(row["asset_id"]): row for row in runtime.process_view()}
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        row = by_asset.get(props.get("source_asset_id"))
        if row is None:
            props["ot_source"] = "OFFICIAL"
            continue
        official = (row.get("official") or {}).get("discharge_cusecs")
        scenario = (row.get("ot") or {}).get("discharge_cusecs")
        _discharge, source = flood_discharge(row.get("mode") or "TRACK", official, scenario)
        props["ot_source"] = source
        props["ot_mode"] = row.get("mode")
        props["ot_device_code"] = row.get("device_code")
        if source != "SOFT_OT_SCENARIO":
            continue
        aid = props.get("source_asset_id")
        classified = threshold_flood_classification(
            discharge=_discharge,
            inflow=(row.get("ot") or {}).get("inflow_cusecs"),
            level=(row.get("ot") or {}).get("level_ft"),
            **_threshold_kw(thresholds.get(aid)),
        )
        if classified is None:
            props["recommendation"] = (
                (props.get("recommendation") or "")
                + " Scenario discharge from the Soft OT twin."
            ).strip()
            continue
        probability, severity, recommendation = classified
        props["flood_probability"] = probability
        props["flood_severity"] = severity
        props["recommendation"] = recommendation
        props["alert"] = severity in {"MODERATE", "HIGH", "EXTREME", "CRITICAL"}
    for alert in payload.get("alerts") or []:
        row = by_asset.get(alert.get("source_asset_id"))
        if row and row.get("mode") == "SCENARIO":
            alert["ot_source"] = "SOFT_OT_SCENARIO"
            alert["ot_device_code"] = row.get("device_code")
        else:
            alert["ot_source"] = "OFFICIAL"
    return payload


@router.get("/flood-map/territory")
async def get_flood_territory(session: Session = Depends(get_session)):
    """GeoJSON districts colored by flood prediction, with region alerts."""
    return load_flood_territory(session)
