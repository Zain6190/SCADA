# Replace the 16 seeded district rectangles with official ADM2 polygons.
# Match is by name. Region ids stay on the existing rows. Provinces are left alone.
#
#   python -m scripts.load_district_polygons
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from gee.districts import DISTRICT_NAMES, named_polygons, normalize_name

DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
DSN = DB_URL.replace("postgresql+psycopg2://", "postgresql://")
API = "https://www.geoboundaries.org/api/current/gbOpen/PAK/ADM2/"
GADM = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PAK_2.json"
OUT = Path(__file__).resolve().parents[3] / "data" / "geo" / "district_polygons.geojson"


def _features_from(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("simplifiedGeometryGeoJSON"):
        return _features_from(payload["simplifiedGeometryGeoJSON"])
    if isinstance(payload, dict) and payload.get("gjDownloadURL") and "features" not in payload:
        return _features_from(payload["gjDownloadURL"])
    return payload.get("features") or []


def download_features() -> list[dict]:
    features = _features_from(API)
    have = {normalize_name(row["name"]) for row in named_polygons(features)}
    missing = [name for name in DISTRICT_NAMES if normalize_name(name) not in have]
    if missing:
        features.extend(_features_from(GADM))
    return features


def apply(conn, updates: list[dict]) -> list[str]:
    cur = conn.cursor()
    kept = []
    for row in updates:
        cur.execute(
            """
            UPDATE shared.regions
            SET geom = ST_Multi(
                ST_CollectionExtract(
                    ST_MakeValid(
                        ST_SimplifyPreserveTopology(
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                            0.01
                        )
                    ),
                    3
                )
            )
            WHERE type = 'district' AND name = %s
            RETURNING id, name
            """,
            (json.dumps(row["geometry"]), row["name"]),
        )
        found = cur.fetchone()
        if found:
            kept.append(f"{found[0]}:{found[1]}")
    conn.commit()
    cur.close()
    return kept


def main() -> None:
    features = download_features()
    updates = named_polygons(features)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": row["name"]},
                "geometry": row["geometry"],
            }
            for row in updates
        ],
    }), encoding="utf-8")
    print(f"[districts] matched {len(updates)} official polygons -> {OUT}")
    try:
        import psycopg2
        conn = psycopg2.connect(DSN)
    except Exception as exc:
        print(f"[districts] database not updated: {exc}")
        return
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM shared.regions WHERE type = 'district' ORDER BY id")
    before = [(rid, name) for rid, name in cur.fetchall()]
    cur.close()
    applied = apply(conn, updates)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM shared.regions WHERE type = 'district' ORDER BY id")
    after = [(rid, name) for rid, name in cur.fetchall()]
    cur.close()
    conn.close()
    print(f"[districts] ids before {before}")
    print(f"[districts] ids after {after}")
    print(f"[districts] applied {applied}")


if __name__ == "__main__":
    main()
