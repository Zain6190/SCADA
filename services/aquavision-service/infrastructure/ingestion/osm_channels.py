# infrastructure/ingestion/osm_channels.py
# Module 6.4: load Pakistan's river and canal geometry from OpenStreetMap.
#
# Uses the Overpass API rather than the Geofabrik country extract. Geofabrik's
# Pakistan file is 149.6 MB as PBF or 351.3 MB as shapefile and needs osmium to
# read; Overpass returns just the waterways we asked for, as JSON, in seconds.
#
# Verified live against Overpass:
#   waterway=canal in Pakistan          10,542 ways
#   waterway=canal AND named             1,976 ways
#
# The scope settles the monitoring filter: "focuses mainly on major canals and
# wider segments where reliable monitoring is possible". Everything is loaded
# for completeness, but only NAMED channels are marked is_monitored - a 10 m
# distributary cannot be resolved by a 10 m Sentinel-2 pixel, and drawing it as
# monitored would put noise on the map.
#
# Usage:
#   python -m infrastructure.ingestion.osm_channels --type canal --out data/raw/real/osm/canals.geojson
#   python -m infrastructure.ingestion.osm_channels --type canal --load

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests

logger = logging.getLogger("aquavision.ingest.osm")

# Overpass is a free, shared, rate-limited service. A single instance will
# refuse or drop connections under load, so try the public mirrors in turn
# rather than failing the whole load because one host is busy.
# overpass.osm.ch is deliberately NOT here: it serves a Swiss regional extract
# and answers a Pakistan query with HTTP 200 and zero elements, which is worse
# than an error because it looks like a successful empty result.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OVERPASS_URL = OVERPASS_MIRRORS[0]

# (connect, read). A single scalar timeout applies to BOTH phases, so a long
# value meant a stalled connect sat for minutes instead of moving to the next
# mirror. Overpass answers slowly - a country query took 62 s - but should
# always connect instantly, so the two phases need very different budgets.
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 600
SOURCE_NAME = "OpenStreetMap via Overpass"

# OSM waterway value -> our channel_type
WATERWAY_TYPES = {
    "canal": "canal",
    "river": "river",
}

# IRSA prints canal names in its own shorthand. Mapping them to OSM names is
# what lets a daily discharge reading attach to a drawn shape.
# Keys are the labels the IRSA parser emits; values are matched against the OSM
# name after separator normalisation, so hyphenation differences do not matter.
#
# Verified against 4,727 OSM canals in and around Pakistan:
#   C-J Link  -> "Chashma-Jhelum link canal"          matched
#   CRBC      -> "Chashma Right Bank Canal"           matched
#   Thal      -> "Thal Plain canal"                   matched
#   T-P Link  -> "Muzaffargarh Canal Taunsa-Panjnad Canal"  matched (shared way)
#   Muzafarghar Canal -> shares the way above; the longest-match rule assigns it
#   Dera Ghazi Khan Canal -> NOT PRESENT in OSM. The only similar name is
#       "Ghazi Canal", which is Ghazi-Barotha on the upper Indus - a different
#       canal entirely. It is left unmatched rather than mapped to the wrong
#       shape; the condition runner reports it as lacking geometry.
IRSA_TO_OSM = {
    "C-J Link": "Chashma Jhelum Link",
    "T-P Link": "Taunsa Panjnad Link",
    "CRBC": "Chashma Right Bank Canal",
    "Thal": "Thal Canal",
    "Muzafarghar Canal": "Muzaffargarh Canal",
    "Dera Ghazi Khan Canal": "Dera Ghazi Khan Canal",
}

# Which barrage each IRSA-labelled canal takes water from (asset ids from
# db/seed.sql). Used to populate feeds_from_asset_id.
IRSA_CANAL_SOURCE_ASSET = {
    "C-J Link": 3,               # Chashma Barrage
    "CRBC": 3,                   # Chashma Barrage
    "Thal": 4,                   # Kalabagh
    "T-P Link": 5,               # Taunsa Barrage
    "Muzafarghar Canal": 5,      # Taunsa Barrage
    "Dera Ghazi Khan Canal": 5,  # Taunsa Barrage
}


# Pakistan bounding box (S, W, N, E). Used as a fallback because not every
# Overpass mirror carries the ISO3166-1 area relations - one of them answered
# the area query with HTTP 200 and zero elements, which is worse than an error.
PAKISTAN_BBOX = (23.5, 60.8, 37.2, 77.9)


def build_query(waterway: str, named_only: bool = False, timeout: int = 600,
                use_bbox: bool = False) -> str:
    name_filter = '["name"]' if named_only else ""
    if use_bbox:
        s, w, n, e = PAKISTAN_BBOX
        selector = f"({s},{w},{n},{e})"
        return (f"[out:json][timeout:{timeout}];\n"
                f'(way["waterway"="{waterway}"]{name_filter}{selector};);\n'
                f"out geom;")
    return f"""
[out:json][timeout:{timeout}];
area["ISO3166-1"="PK"][admin_level=2]->.pk;
(way["waterway"="{waterway}"]{name_filter}(area.pk););
out geom;
""".strip()


def fetch(waterway: str, named_only: bool = False,
          timeout: tuple = (CONNECT_TIMEOUT, READ_TIMEOUT)) -> dict:
    """Run one Overpass query. Overpass is rate limited; retry politely."""
    import time

    # Overpass returns 406 for a raw body with no form encoding, and asks that
    # clients identify themselves.
    headers = {"User-Agent": "AquaVision-AI/1.0 (IBCP-SCADA FYP; module 6.4 channel loader)"}
    last = None

    # Try the area-based query on every mirror, then fall back to a bounding
    # box. An empty result is treated as FAILURE, not success: a mirror without
    # the ISO3166-1 relations answers the area query with 200 and zero elements,
    # and silently writing an empty layer is the worst possible outcome.
    for use_bbox in (False, True):
        query = build_query(waterway, named_only, use_bbox=use_bbox)
        strategy = "bbox" if use_bbox else "area"

        for mirror in OVERPASS_MIRRORS:
            for attempt in range(3):
                try:
                    logger.info("Overpass [%s] -> %s (try %d)", strategy, mirror, attempt + 1)
                    resp = requests.post(mirror, data={"data": query},
                                         headers=headers, timeout=timeout)
                    if resp.status_code in (429, 504):
                        raise requests.HTTPError(f"{resp.status_code} transient", response=resp)
                    resp.raise_for_status()
                    payload = resp.json()
                    n = len(payload.get("elements", []))
                    if n == 0:
                        raise ValueError("returned 0 elements")
                    logger.info("  %d elements from %s [%s]", n, mirror, strategy)
                    payload["_aquavision_strategy"] = strategy
                    if use_bbox:
                        logger.warning(
                            "  bbox strategy OVERSHOOTS Pakistan's borders - results "
                            "include neighbouring countries and need clipping")
                    return payload
                except (requests.HTTPError, requests.ConnectionError,
                        requests.Timeout, ValueError) as exc:
                    last = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    logger.warning("  %s failed (%s)", mirror,
                                   status or f"{type(exc).__name__}: {exc}")
                    # A refused/stalled connect is transient here, not fatal:
                    # curl reaches the same host seconds later. Retry before
                    # giving up on the mirror.
                    transient = status in (429, 502, 503, 504) or isinstance(
                        exc, (requests.ConnectionError, requests.Timeout))
                    if attempt < 2 and transient:
                        time.sleep(15 * (attempt + 1))
                    else:
                        break            # move on to the next mirror

    raise RuntimeError(
        f"All Overpass mirrors failed for waterway={waterway} on both the area "
        f"and bbox strategies; last error: {last}"
    )


def _length_km(coords: List[List[float]]) -> float:
    """Great-circle length of a coordinate list, in km."""
    import math

    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = p2 - p1
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        total += 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return total


def _normalise_name(text: str) -> str:
    """Lowercase and flatten separators so hyphenation cannot break a match.

    OSM writes "Taunsa-Panjnad Canal" where the IRSA report writes "T-P Link";
    matching on raw substrings missed half the mapped canals.
    """
    import re as _re
    return _re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def match_irsa_label(osm_name: Optional[str]) -> Optional[str]:
    """Return the IRSA label for this OSM channel, if one corresponds.

    Matches when every significant word of the mapped OSM name appears in the
    channel's name, rather than requiring a contiguous substring. "Chashma
    Jhelum Link" must match "Chashma-Jhelum Link Canal" and "CJ Link Canal".
    """
    if not osm_name:
        return None
    haystack = _normalise_name(osm_name)
    haystack_words = set(haystack.split())

    # A single OSM way can carry two canals' names - "Muzaffargarh Canal
    # Taunsa-Panjnad Canal" matches both Muzafarghar and T-P Link. Collect every
    # candidate and take the most specific, so dict iteration order does not
    # silently decide which canal a shape belongs to.
    candidates = []
    for irsa_label, osm_fragment in IRSA_TO_OSM.items():
        needle = _normalise_name(osm_fragment)
        if needle in haystack:
            candidates.append((len(needle), irsa_label))
            continue
        # Word-subset fallback: order and separators may differ.
        needle_words = {w for w in needle.split() if w not in ("canal", "link")}
        if needle_words and needle_words <= haystack_words:
            candidates.append((len(" ".join(needle_words)), irsa_label))

    if not candidates:
        return None
    # Longest match wins; the label breaks ties so the result is stable.
    return max(candidates, key=lambda c: (c[0], c[1]))[1]


def to_features(payload: dict, channel_type: str) -> List[dict]:
    """Convert Overpass 'out geom' elements into GeoJSON LineString features."""
    retrieved = datetime.now(timezone.utc).isoformat()
    features = []

    for el in payload.get("elements", []):
        if el.get("type") != "way":
            continue
        geometry = el.get("geometry") or []
        if len(geometry) < 2:
            continue  # a single node is not a channel

        coords = [[p["lon"], p["lat"]] for p in geometry]
        tags = el.get("tags", {})
        name = tags.get("name")
        irsa_label = match_irsa_label(name)

        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "osm_id": el.get("id"),
                "name": name or f"unnamed {channel_type} {el.get('id')}",
                "channel_type": (
                    "link_canal" if (name and "link" in name.lower()) else channel_type
                ),
                "has_name": bool(name),
                # The scope's filter: monitor named channels only.
                "is_monitored": bool(name),
                "irsa_label": irsa_label,
                "feeds_from_asset_id": IRSA_CANAL_SOURCE_ASSET.get(irsa_label),
                "length_km": round(_length_km(coords), 3),
                "province": tags.get("addr:state"),
                "source_name": SOURCE_NAME,
                "source_url": OVERPASS_URL,
                "retrieved_at": retrieved,
            },
        })

    return features


def strategy_of(payload: dict) -> str:
    """Which query strategy produced this payload, for provenance."""
    return payload.get("_aquavision_strategy", "unknown")


def summarise(features: List[dict]) -> dict:
    named = [f for f in features if f["properties"]["has_name"]]
    matched = [f for f in features if f["properties"]["irsa_label"]]
    return {
        "total": len(features),
        "named": len(named),
        "monitored": len(named),
        "irsa_matched": len(matched),
        "irsa_labels": sorted({f["properties"]["irsa_label"] for f in matched}),
        "total_length_km": round(sum(f["properties"]["length_km"] for f in features), 1),
        "named_length_km": round(sum(f["properties"]["length_km"] for f in named), 1),
    }


def export_geojson(features: List[dict], out_path: Path) -> None:
    if not features:
        # Refuse to write an empty layer over a good one. An empty GeoJSON that
        # exits 0 reads downstream as "Pakistan has no canals".
        raise ValueError(
            "Refusing to write an empty FeatureCollection - the fetch returned "
            "nothing usable. Re-run; do not treat this as a successful load."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    logger.info("Wrote %d features -> %s (%.1f MB)", len(features), out_path,
                out_path.stat().st_size / 1048576)


# ─── Database load ─────────────────────────────────────────────────────────

def load_to_db(features: List[dict]) -> dict:
    """Upsert features into aquavision.water_channels.

    Geometry is stored as MultiLineString so a channel split across several OSM
    ways can later be merged without a type change.
    """
    from sqlalchemy import text

    from infrastructure.db.engine import SessionLocal

    inserted = updated = skipped = 0
    with SessionLocal() as session:
        for f in features:
            p = f["properties"]
            wkt_coords = ", ".join(f"{lon} {lat}" for lon, lat in f["geometry"]["coordinates"])
            try:
                res = session.execute(text("""
                    INSERT INTO aquavision.water_channels
                        (channel_type, name, osm_id, province, feeds_from_asset_id,
                         irsa_label, length_km, is_monitored, geom,
                         source_name, source_url, retrieved_at)
                    VALUES
                        (:channel_type, :name, :osm_id, :province, :feeds_from_asset_id,
                         :irsa_label, :length_km, :is_monitored,
                         ST_Multi(ST_GeomFromText(:wkt, 4326)),
                         :source_name, :source_url, :retrieved_at)
                    ON CONFLICT (osm_id) WHERE osm_id IS NOT NULL
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        irsa_label = EXCLUDED.irsa_label,
                        feeds_from_asset_id = EXCLUDED.feeds_from_asset_id,
                        is_monitored = EXCLUDED.is_monitored,
                        length_km = EXCLUDED.length_km,
                        geom = EXCLUDED.geom,
                        retrieved_at = EXCLUDED.retrieved_at,
                        updated_at = now()
                    RETURNING (xmax = 0) AS was_insert
                """), {
                    "channel_type": p["channel_type"],
                    "name": p["name"],
                    "osm_id": p["osm_id"],
                    "province": p["province"],
                    "feeds_from_asset_id": p["feeds_from_asset_id"],
                    "irsa_label": p["irsa_label"],
                    "length_km": p["length_km"],
                    "is_monitored": p["is_monitored"],
                    "wkt": f"LINESTRING({wkt_coords})",
                    "source_name": p["source_name"],
                    "source_url": p["source_url"],
                    "retrieved_at": p["retrieved_at"],
                }).first()
                if res and res[0]:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:  # noqa: BLE001 - one bad way must not abort the load
                logger.error("Failed to load osm_id=%s: %s", p.get("osm_id"), exc)
                session.rollback()
                skipped += 1
                continue
        session.commit()

    summary = {"inserted": inserted, "updated": updated, "skipped": skipped}
    logger.info("Load complete: %s", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load Pakistan river/canal geometry from OpenStreetMap"
    )
    parser.add_argument("--type", default="canal", choices=sorted(WATERWAY_TYPES),
                        help="OSM waterway value to fetch")
    parser.add_argument("--named-only", action="store_true",
                        help="Fetch only named ways (smaller, faster)")
    parser.add_argument("--out", default=None, help="Write GeoJSON to this path")
    parser.add_argument("--load", action="store_true",
                        help="Upsert into aquavision.water_channels")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    logger.info("Querying Overpass for waterway=%s%s ...",
                args.type, " (named only)" if args.named_only else "")
    payload = fetch(args.type, named_only=args.named_only)
    strategy = strategy_of(payload)
    feats = to_features(payload, WATERWAY_TYPES[args.type])
    summary = summarise(feats)
    summary["query_strategy"] = strategy
    if strategy == "bbox":
        summary["warning"] = (
            "bbox query - the extent exceeds Pakistan, so some channels belong "
            "to neighbouring countries. Clip against a Pakistan boundary before "
            "reporting national totals.")
    logger.info("Summary: %s", json.dumps(summary, indent=2))

    if args.out:
        export_geojson(feats, Path(args.out))
    if args.load:
        load_to_db(feats)
    if not args.out and not args.load:
        logger.info("Nothing written - pass --out and/or --load")
