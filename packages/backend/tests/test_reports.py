import json

from tests.conftest import auth


def test_report_endpoints_require_export_permission(client, viewer):
    # Viewer holds only AQUAVISION_READ -> export & generate must 403.
    r = client.get("/api/v1/water/export/indicators.csv", headers=auth(viewer))
    assert r.status_code == 403
    r = client.get("/api/v1/water/export/latest/regions.geojson", headers=auth(viewer))
    assert r.status_code == 404  # endpoint does not exist at this path
    r = client.get("/api/v1/water/export/regions.geojson", headers=auth(viewer))
    assert r.status_code == 403
    r = client.post("/api/v1/water/reports/generate", headers=auth(viewer))
    assert r.status_code == 403


def test_export_indicators_csv(client, operator):
    # Operator also lacks AQUAVISION_EXPORT.
    r = client.get("/api/v1/water/export/indicators.csv", headers=auth(operator))
    assert r.status_code == 403


def test_admin_can_list_reports(client, admin):
    r = client.get("/api/v1/water/reports", headers=auth(admin))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_csv_export_shape(client, admin):
    r = client.get("/api/v1/water/export/indicators.csv", headers=auth(admin))
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    # Header row presence + at least one data row.
    lines = r.content.decode("utf-8-sig").strip().splitlines()
    assert len(lines) >= 2
    header = lines[0].split(",")
    assert "region_id" in header and "wai_score" in header


def test_geojson_regions_export(client, admin):
    r = client.get("/api/v1/water/export/regions.geojson", headers=auth(admin))
    assert r.status_code == 200
    assert "geo+json" in r.headers["content-type"]
    fc = json.loads(r.content.decode("utf-8"))
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    first = fc["features"][0]
    assert first["type"] == "Feature"
    assert first["geometry"]["type"] == "Polygon" or "geometry" in first
    assert first["properties"].get("region_id") is not None


def test_geojson_indicators_export(client, admin):
    r = client.get("/api/v1/water/export/indicators.geojson", headers=auth(admin))
    assert r.status_code == 200
    fc = json.loads(r.content.decode("utf-8"))
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    assert fc["features"][0]["geometry"]["type"] == "Point"


def test_generate_weekly_pdf(client, admin):
    r = client.post("/api/v1/water/reports/generate", headers=auth(admin))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "Success"
    assert body["file_path"].endswith(".pdf")
    assert body["week_start_date"]  # non-empty date

    # Generated report must be downloadable as a real PDF.
    rid = body["id"]
    d = client.get(f"/api/v1/water/reports/{rid}/download", headers=auth(admin))
    assert d.status_code == 200
    assert d.headers["content-type"] == "application/pdf"
    assert d.content[:4] == b"%PDF"


def test_generate_report_audited(client, admin):
    before = client.get("/api/v1/water/reports", headers=auth(admin)).json()
    r = client.post("/api/v1/water/reports/generate", headers=auth(admin))
    assert r.status_code == 201
    after = client.get("/api/v1/water/reports", headers=auth(admin)).json()
    assert len(after) == len(before) + 1


def test_download_missing_report_404(client, admin):
    r = client.get("/api/v1/water/reports/999999/download", headers=auth(admin))
    assert r.status_code == 404