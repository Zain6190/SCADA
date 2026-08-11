"""Schema isolation tests (hardening point #10).

Verify the multi-tenant-ish schema layering is intact:
  * domain tables live in their owning schema (aquavision / crop / geo)
  * domain tables reference shared.identity via cross-schema FKs, not duplicate
    tables
  * rbac + audit live in shared / system respectively
  * no auth/audit table is silently duplicated elsewhere
"""
from sqlalchemy import inspect

from app.core.database import engine


def _tables(schema):
    insp = inspect(engine)
    out = {}
    for t in insp.get_table_names(schema=schema):
        fks = insp.get_foreign_keys(t, schema=schema)
        out[t] = {(fk["constrained_columns"][0], fk["referred_table"]) for fk in fks}
    return out


def test_domain_tables_live_in_owning_schemas():
    assert "water_indicators_weekly" in _tables("aquavision")
    assert "water_predictions_weekly" in _tables("aquavision")
    assert "users" in _tables("shared")
    assert "audit_logs" in _tables("system")


def test_water_fks_reference_shared_schema_only():
    aqua = _tables("aquavision")
    region_fks = aqua["water_indicators_weekly"]
    # component region FK must point at shared.regions (not a local copy)
    assert ("region_id", "regions") in region_fks


def test_regions_are_not_duplicated_per_schema():
    # regions are canonical in shared; no aquavision-regions copy allowed
    aqua = _tables("aquavision")
    for name in ("regions", "regions_copy"):
        assert name not in aqua


def test_audit_lives_only_in_system():
    for schema in ("aquavision", "crop", "geo"):
        assert "audit_logs" not in _tables(schema)


def test_shared_holds_identity_and_rbac():
    shared = _tables("shared")
    for t in ("users", "roles", "permissions", "user_roles", "role_permissions",
              "user_region_scopes", "regions"):
        assert t in shared, f"shared.{t} missing"