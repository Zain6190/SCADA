"""District flood territories along the Indus, Kabul, and Chenab corridors.

Polygons are approximate WGS84 boxes in the same style as the demo regions in
packages/backend/db/init.sql. They are not official administrative boundaries.
District membership follows the segment mapping in update_population.py.
"""

from __future__ import annotations

from dataclasses import dataclass


SEVERITY_RANK = {
    "NONE": 0,
    "LOW": 1,
    "MODERATE": 2,
    "HIGH": 3,
    "EXTREME": 4,
    "CRITICAL": 5,
}

ALERT_MIN_RANK = SEVERITY_RANK["MODERATE"]


def _box(west: float, south: float, east: float, north: float) -> list[list[float]]:
    """Closed GeoJSON ring as [lng, lat]."""
    return [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]


# name, province, ring. Order is upstream to downstream so the map is stable.
_DISTRICT_ROWS: list[tuple[str, str, list[list[float]]]] = [
    ("Haripur", "KPK", _box(72.65, 33.80, 73.20, 34.30)),
    ("Swabi", "KPK", _box(72.15, 33.95, 72.70, 34.40)),
    ("Mardan", "KPK", _box(71.90, 34.05, 72.40, 34.50)),
    ("Nowshera", "KPK", _box(71.70, 33.80, 72.20, 34.20)),
    ("Peshawar", "KPK", _box(71.30, 33.85, 71.85, 34.25)),
    ("Mianwali", "Punjab", _box(71.15, 32.25, 71.85, 32.95)),
    ("Bhakkar", "Punjab", _box(70.75, 31.25, 71.45, 31.95)),
    ("Dera Ismail Khan", "KPK", _box(70.25, 31.45, 70.95, 32.20)),
    ("Dera Ghazi Khan", "Punjab", _box(70.15, 29.70, 70.95, 30.55)),
    ("Muzaffargarh", "Punjab", _box(70.85, 29.55, 71.55, 30.30)),
    ("Rajanpur", "Punjab", _box(69.85, 28.70, 70.55, 29.50)),
    ("Rahim Yar Khan", "Punjab", _box(70.00, 28.05, 70.85, 28.70)),
    ("Kashmore", "Sindh", _box(69.15, 28.05, 69.85, 28.65)),
    ("Ghotki", "Sindh", _box(69.05, 27.75, 69.75, 28.25)),
    ("Sukkur", "Sindh", _box(68.45, 27.45, 69.15, 28.00)),
    ("Khairpur", "Sindh", _box(68.30, 27.05, 69.00, 27.60)),
    ("Matiari", "Sindh", _box(68.25, 25.55, 68.85, 26.10)),
    ("Hyderabad", "Sindh", _box(68.10, 25.15, 68.70, 25.65)),
    ("Tando Muhammad Khan", "Sindh", _box(68.25, 24.90, 68.85, 25.30)),
    ("Sialkot", "Punjab", _box(74.20, 32.20, 74.90, 32.80)),
    ("Gujrat", "Punjab", _box(73.70, 32.30, 74.40, 32.95)),
    ("Mandi Bahauddin", "Punjab", _box(73.10, 32.20, 73.85, 32.90)),
]

# (source_asset_id, downstream_asset_id) -> district names, equal population share.
_SEGMENT_DISTRICTS: dict[tuple[int, int], list[str]] = {
    (1, 4): ["Haripur", "Swabi", "Mardan", "Nowshera"],
    (4, 5): ["Dera Ismail Khan", "Mianwali", "Bhakkar"],
    (5, 6): ["Rajanpur", "Dera Ghazi Khan", "Rahim Yar Khan", "Kashmore"],
    (6, 7): ["Sukkur", "Khairpur", "Ghotki"],
    (7, 8): ["Hyderabad", "Matiari", "Tando Muhammad Khan"],
    (9, 4): ["Nowshera", "Peshawar", "Mardan"],
    (10, 11): ["Sialkot", "Gujrat", "Mandi Bahauddin"],
    (11, 6): ["Muzaffargarh", "Rajanpur"],
}


@dataclass(frozen=True)
class SegmentMembership:
    source_asset_id: int
    downstream_asset_id: int
    population_share: float


@dataclass(frozen=True)
class DistrictTerritory:
    name: str
    province: str
    ring: list[list[float]]
    memberships: tuple[SegmentMembership, ...]


def _build_territories() -> tuple[DistrictTerritory, ...]:
    by_name: dict[str, list[SegmentMembership]] = {name: [] for name, _, _ in _DISTRICT_ROWS}
    for (src, dst), names in _SEGMENT_DISTRICTS.items():
        share = 1.0 / len(names)
        for name in names:
            by_name[name].append(SegmentMembership(src, dst, share))
    return tuple(
        DistrictTerritory(name, province, ring, tuple(by_name[name]))
        for name, province, ring in _DISTRICT_ROWS
    )


TERRITORIES: tuple[DistrictTerritory, ...] = _build_territories()


def districts_on_segment(source_asset_id: int, downstream_asset_id: int) -> list[str]:
    return list(_SEGMENT_DISTRICTS.get((source_asset_id, downstream_asset_id), []))


@dataclass(frozen=True)
class AssetFlood:
    asset_id: int
    name: str
    probability: float
    severity: str
    recommendation: str


@dataclass(frozen=True)
class SegmentImpact:
    population: int
    bridges: int
    hospitals: int


@dataclass(frozen=True)
class LocatedPoint:
    """A town or asset that should be marked when it falls inside a danger zone."""

    name: str
    kind: str
    lat: float
    lng: float
    district: str | None = None


# Towns that sit inside each corridor district. Coordinates are approximate.
_PLACES: tuple[LocatedPoint, ...] = (
    LocatedPoint("Haripur", "town", 33.99, 72.93, "Haripur"),
    LocatedPoint("Khalabat", "town", 34.06, 72.88, "Haripur"),
    LocatedPoint("Swabi", "town", 34.12, 72.47, "Swabi"),
    LocatedPoint("Mardan", "town", 34.20, 72.05, "Mardan"),
    LocatedPoint("Nowshera", "town", 34.02, 71.98, "Nowshera"),
    LocatedPoint("Akora Khattak", "town", 33.99, 72.12, "Nowshera"),
    LocatedPoint("Peshawar", "town", 34.01, 71.58, "Peshawar"),
    LocatedPoint("Mianwali", "town", 32.58, 71.53, "Mianwali"),
    LocatedPoint("Isa Khel", "town", 32.67, 71.28, "Mianwali"),
    LocatedPoint("Bhakkar", "town", 31.63, 71.07, "Bhakkar"),
    LocatedPoint("Dera Ismail Khan", "town", 31.83, 70.90, "Dera Ismail Khan"),
    LocatedPoint("Dera Ghazi Khan", "town", 30.05, 70.63, "Dera Ghazi Khan"),
    LocatedPoint("Kot Chutta", "town", 29.88, 70.45, "Dera Ghazi Khan"),
    LocatedPoint("Muzaffargarh", "town", 30.07, 71.19, "Muzaffargarh"),
    LocatedPoint("Rajanpur", "town", 29.10, 70.33, "Rajanpur"),
    LocatedPoint("Rahim Yar Khan", "town", 28.42, 70.30, "Rahim Yar Khan"),
    LocatedPoint("Kashmore", "town", 28.43, 69.58, "Kashmore"),
    LocatedPoint("Kandhkot", "town", 28.24, 69.18, "Kashmore"),
    LocatedPoint("Ghotki", "town", 28.00, 69.32, "Ghotki"),
    LocatedPoint("Mirpur Mathelo", "town", 28.02, 69.55, "Ghotki"),
    LocatedPoint("Sukkur", "town", 27.70, 68.86, "Sukkur"),
    LocatedPoint("Rohri", "town", 27.69, 68.90, "Sukkur"),
    LocatedPoint("Khairpur", "town", 27.53, 68.76, "Khairpur"),
    LocatedPoint("Matiari", "town", 25.60, 68.45, "Matiari"),
    LocatedPoint("Hala", "town", 25.81, 68.42, "Matiari"),
    LocatedPoint("Hyderabad", "town", 25.40, 68.36, "Hyderabad"),
    LocatedPoint("Tando Muhammad Khan", "town", 25.12, 68.54, "Tando Muhammad Khan"),
    LocatedPoint("Sialkot", "town", 32.49, 74.53, "Sialkot"),
    LocatedPoint("Gujrat", "town", 32.57, 74.08, "Gujrat"),
    LocatedPoint("Mandi Bahauddin", "town", 32.58, 73.49, "Mandi Bahauddin"),
)


def threshold_flood_classification(
    *,
    discharge: float | None,
    inflow: float | None,
    level: float | None,
    warning_level_ft: float | None,
    critical_level_ft: float | None,
) -> tuple[float, str, str] | None:
    """Mirror the operational asset fallback when no ML flood row exists."""
    value = discharge or inflow or level
    if value and warning_level_ft and critical_level_ft:
        warn = float(warning_level_ft)
        crit = float(critical_level_ft)
        if crit > warn and value >= warn:
            ratio = min((value - warn) / (crit - warn), 1.0)
            probability = round(0.05 + ratio * 0.85, 4)
            if ratio > 0.8:
                severity = "CRITICAL"
            elif ratio > 0.5:
                severity = "HIGH"
            elif ratio > 0.2:
                severity = "MODERATE"
            else:
                severity = "LOW"
            return probability, severity, f"Level at {ratio * 100:.0f}% of critical threshold"
    elif value and discharge:
        return 0.05, "LOW", "Normal operations - threshold-based estimate"
    return None


def _rank(severity: str | None) -> int:
    return SEVERITY_RANK.get((severity or "NONE").upper(), 0)


def _ring_contains(ring: list[list[float]], lng: float, lat: float) -> bool:
    """Ray cast. `ring` is a closed [lng, lat] loop."""
    points = ring[:-1] if ring and ring[0] == ring[-1] else ring
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _interior_points(ring: list[list[float]], count: int, lane: float = 0.35) -> list[tuple[float, float]]:
    """Spread `count` points inside the ring, inset from the edge. Returns (lat, lng)."""
    if count <= 0:
        return []
    body = ring[:-1] if ring and ring[0] == ring[-1] else ring
    lngs = [point[0] for point in body]
    lats = [point[1] for point in body]
    west, east = min(lngs), max(lngs)
    south, north = min(lats), max(lats)
    pad_x = (east - west) * 0.22
    pad_y = (north - south) * 0.22
    span_x = max(east - west - 2 * pad_x, 0.01)
    span_y = max(north - south - 2 * pad_y, 0.01)
    points: list[tuple[float, float]] = []
    for index in range(count):
        t = (index + 1) / (count + 1)
        lng = west + pad_x + span_x * t
        lat = south + pad_y + span_y * lane
        if not _ring_contains(ring, lng, lat):
            lng = (west + east) / 2
            lat = (south + north) / 2
        points.append((lat, lng))
    return points


def _zone_contents(
    territory: DistrictTerritory,
    *,
    bridges: int,
    hospitals: int,
    located: list[LocatedPoint],
) -> list[dict]:
    """Towns, bridges, hospitals, and assets that sit inside a threatened district."""
    contents: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, name: str, lat: float, lng: float) -> None:
        key = (kind, name)
        if key in seen:
            return
        seen.add(key)
        contents.append(
            {
                "kind": kind,
                "name": name,
                "lat": round(lat, 5),
                "lng": round(lng, 5),
                "district": territory.name,
            }
        )

    for place in _PLACES:
        if place.district == territory.name:
            add(place.kind, place.name, place.lat, place.lng)
    for place in located:
        if place.district and place.district != territory.name:
            continue
        if place.district == territory.name or _ring_contains(territory.ring, place.lng, place.lat):
            add(place.kind, place.name, place.lat, place.lng)
    for index, (lat, lng) in enumerate(_interior_points(territory.ring, bridges, lane=0.32), start=1):
        add("bridge", f"Bridge {index}", lat, lng)
    for index, (lat, lng) in enumerate(_interior_points(territory.ring, hospitals, lane=0.72), start=1):
        add("hospital", f"Hospital {index}", lat, lng)
    return contents


def _split_counts(total: int, count: int) -> list[int]:
    """Split an integer total into `count` nearly equal parts that sum to total."""
    if count <= 0:
        return []
    total = max(int(total or 0), 0)
    base, extra = divmod(total, count)
    return [base + (1 if i < extra else 0) for i in range(count)]


def _asset_view(
    asset_id: int,
    classifications: dict[int, AssetFlood],
    asset_names: dict[int, str],
) -> AssetFlood:
    found = classifications.get(asset_id)
    if found is not None:
        name = found.name or asset_names.get(asset_id) or f"Asset {asset_id}"
        return AssetFlood(
            asset_id=asset_id,
            name=name,
            probability=float(found.probability or 0.0),
            severity=(found.severity or "NONE").upper(),
            recommendation=found.recommendation or "",
        )
    return AssetFlood(
        asset_id=asset_id,
        name=asset_names.get(asset_id, f"Asset {asset_id}"),
        probability=0.0,
        severity="NONE",
        recommendation="",
    )


def build_flood_territory(
    classifications: dict[int, AssetFlood],
    impacts: dict[tuple[int, int], SegmentImpact],
    asset_names: dict[int, str] | None = None,
    located: list[LocatedPoint] | None = None,
) -> dict:
    """Paint every catalog district from upstream flood predictions.

    A district on more than one segment keeps the worst severity. Population,
    bridges, and hospitals are the sum of that district's share of each segment,
    and those shares add back to the segment total.
    """
    names = asset_names or {}
    places = located or []
    allocated: dict[tuple[int, int], dict[str, dict[str, int]]] = {}
    for (src, dst), district_names in _SEGMENT_DISTRICTS.items():
        impact = impacts.get((src, dst), SegmentImpact(0, 0, 0))
        n = len(district_names)
        allocated[(src, dst)] = {
            district_names[i]: {
                "population": pops,
                "bridges": bridges,
                "hospitals": hospitals,
            }
            for i, (pops, bridges, hospitals) in enumerate(
                zip(
                    _split_counts(impact.population, n),
                    _split_counts(impact.bridges, n),
                    _split_counts(impact.hospitals, n),
                )
            )
        }

    features = []
    alerts = []
    for territory in TERRITORIES:
        population = 0
        bridges = 0
        hospitals = 0
        best_key = (-1, -1.0, 0)
        best: AssetFlood | None = None
        for membership in territory.memberships:
            key = (membership.source_asset_id, membership.downstream_asset_id)
            share = allocated.get(key, {}).get(territory.name)
            if share:
                population += share["population"]
                bridges += share["bridges"]
                hospitals += share["hospitals"]
            view = _asset_view(membership.source_asset_id, classifications, names)
            candidate = (_rank(view.severity), float(view.probability), -view.asset_id)
            if candidate > best_key:
                best_key = candidate
                best = view
        if best is None:
            best = AssetFlood(0, "Unknown", 0.0, "NONE", "")
        alert = _rank(best.severity) >= ALERT_MIN_RANK
        inside = (
            _zone_contents(territory, bridges=bridges, hospitals=hospitals, located=places)
            if alert
            else []
        )
        properties = {
            "district": territory.name,
            "province": territory.province,
            "flood_probability": round(float(best.probability), 4),
            "flood_severity": best.severity,
            "population_exposed": population,
            "bridges": bridges,
            "hospitals": hospitals,
            "recommendation": best.recommendation,
            "source_asset_id": best.asset_id,
            "source_asset_name": best.name,
            "alert": alert,
            "inside": inside,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [territory.ring]},
                "properties": properties,
            }
        )
        if alert:
            alerts.append(
                {
                    "district": territory.name,
                    "province": territory.province,
                    "severity": best.severity,
                    "flood_probability": properties["flood_probability"],
                    "population_exposed": population,
                    "bridges": bridges,
                    "hospitals": hospitals,
                    "recommendation": best.recommendation,
                    "source_asset_id": best.asset_id,
                    "source_asset_name": best.name,
                    "inside_count": len(inside),
                    "inside": inside,
                }
            )

    alerts.sort(
        key=lambda row: (
            -_rank(row["severity"]),
            -row["population_exposed"],
            row["district"],
        )
    )
    return {"type": "FeatureCollection", "features": features, "alerts": alerts}
