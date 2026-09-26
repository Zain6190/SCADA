# Match official ADM2 polygons onto the seeded district rows by name.
# The region id on each match is the existing id.
from __future__ import annotations

DISTRICT_NAMES = [
    "Bahawalnagar",
    "Bahawalpur",
    "Rahim Yar Khan",
    "Dera Ghazi Khan",
    "Muzaffargarh",
    "Rajanpur",
    "Sukkur",
    "Larkana",
    "Jacobabad",
    "Thatta",
    "Hyderabad",
    "Nowshera",
    "Dera Ismail Khan",
    "Charsadda",
]

_ALIASES = {
    "mirpurkhas": "mirpurkhas",
    "mirpur khas": "mirpurkhas",
    "dgkhan": "deraghazikhan",
    "d g khan": "deraghazikhan",
    "dikhan": "deraismailkhan",
    "d i khan": "deraismailkhan",
    "rahimyar khan": "rahimyarkhan",
    "rahim yar khan": "rahimyarkhan",
}


def normalize_name(name: str) -> str:
    text = (name or "").lower().replace("district", " ").replace(".", " ").replace("-", " ").replace("_", " ")
    text = " ".join(text.split())
    compact = text.replace(" ", "")
    return _ALIASES.get(text, _ALIASES.get(compact, compact))


def named_polygons(features: list[dict]) -> list[dict]:
    """Official polygons for the 16 seeded names. Matching does not assign new ids."""
    wanted = {normalize_name(name): name for name in DISTRICT_NAMES}
    found = []
    seen = set()
    for feature in features:
        props = feature.get("properties") or {}
        label = props.get("shapeName") or props.get("NAME_2") or props.get("name") or ""
        key = normalize_name(label)
        if key not in wanted or key in seen or not feature.get("geometry"):
            continue
        seen.add(key)
        found.append({"name": wanted[key], "geometry": feature["geometry"]})
    return found


def match_districts(existing: list[dict], features: list[dict]) -> list[dict]:
    """Return polygon updates for seeded districts. Ids are copied, never renumbered."""
    by_name = {normalize_name(row["name"]): row for row in existing if row.get("name")}
    updates = []
    seen = set()
    for feature in features:
        props = feature.get("properties") or {}
        label = props.get("shapeName") or props.get("NAME_2") or props.get("name") or ""
        key = normalize_name(label)
        row = by_name.get(key)
        if row is None or row["id"] in seen:
            continue
        geometry = feature.get("geometry")
        if not geometry:
            continue
        seen.add(row["id"])
        updates.append({
            "id": row["id"],
            "name": row["name"],
            "geometry": geometry,
        })
    return updates
