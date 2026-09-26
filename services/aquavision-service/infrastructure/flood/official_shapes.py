"""Replace rectangular flood zones with official district polygons when a match exists."""
from __future__ import annotations

import json
from pathlib import Path

_ALIASES = {
    "dgkhan": "deraghazikhan",
    "dg khan": "deraghazikhan",
    "d g khan": "deraghazikhan",
    "dikhan": "deraismailkhan",
    "di khan": "deraismailkhan",
    "d i khan": "deraismailkhan",
    "rahimyar khan": "rahimyarkhan",
    "rahim yar khan": "rahimyarkhan",
    "tandamuhammadkhan": "tandomuhammadkhan",
    "tando mohammad khan": "tandomuhammadkhan",
    "mandibahauddin": "mandibahauddin",
    "mandi bahauddin": "mandibahauddin",
}

SHAPE_FILE = (
    Path(__file__).resolve().parents[4] / "data" / "geo" / "flood_territory_polygons.geojson"
)


def normalize_district(name: str) -> str:
    text = (name or "").lower().replace("district", " ").replace(".", " ").replace("-", " ").replace("_", " ")
    text = " ".join(text.split())
    compact = text.replace(" ", "")
    return _ALIASES.get(text, _ALIASES.get(compact, compact))


def index_geometries(features: list[dict]) -> dict[str, dict]:
    """Map a normalized district name to a GeoJSON Polygon or MultiPolygon."""
    found: dict[str, dict] = {}
    for feature in features:
        props = feature.get("properties") or {}
        name = props.get("name") or props.get("shapeName") or props.get("NAME_2") or props.get("district")
        geometry = feature.get("geometry") or {}
        if not name or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        found[normalize_district(str(name))] = geometry
    return found


def load_shape_file(path: Path | None = None) -> dict[str, dict]:
    target = path or SHAPE_FILE
    if not target.is_file():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return index_geometries(payload.get("features") or [])


def apply_official_geometries(payload: dict, geometries: dict[str, dict]) -> dict:
    """Swap box rings for official boundaries. Unmatched districts keep the box."""
    if not geometries:
        return payload
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        geometry = geometries.get(normalize_district(props.get("district") or ""))
        if geometry is None:
            props["boundary"] = "approximate"
            continue
        feature["geometry"] = geometry
        props["boundary"] = "official"
    return payload
