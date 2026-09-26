-- 009_alert_ageout.sql — one-off inbox baseline for the alert-workflow rollout.
--
-- The August threshold alerts (RULE, created 2026-08-16) are historically real
-- but operationally stale: SLA backfill (008) marked them breached, so the
-- scanner escalated 15 of them. A fresh supervisor inbox should reflect
-- current reality, not six-week-old flood-season events.
--
-- Closes every still-open alert older than 7 days (plus any open TEST alert)
-- as RESOLVED/SYSTEM and writes an append-only audit row per alert.
-- Idempotent: only rows still open are touched.

WITH stale AS (
    SELECT id, status
    FROM aquavision.water_operational_alerts
    WHERE status NOT IN ('RESOLVED', 'FALSE_OR_INVALID_DATA', 'AUTO_RESOLVED')
      AND (created_at < now() - interval '7 days' OR alert_type = 'TEST')
),
updated AS (
    UPDATE aquavision.water_operational_alerts a
    SET status = 'RESOLVED',
        resolved_by = 'SYSTEM',
        resolved_at = now(),
        resolution = 'Aged out during workflow rollout (historical alert, no current action required)'
    FROM stale s
    WHERE a.id = s.id
    RETURNING a.id, s.status AS old_status
)
INSERT INTO aquavision.water_alert_audit_log
    (alert_id, action, performed_by, performed_at, old_status, new_status, notes, actor_role, payload)
SELECT
    id,
    'AGEOUT',
    'SYSTEM',
    now(),
    old_status,
    'RESOLVED',
    'Bulk age-out migration 009: historical alerts closed during alert-workflow rollout',
    'SYSTEM',
    jsonb_build_object('migration', '009_alert_ageout', 'reason', 'inbox_baseline')
FROM updated;
