-- ============================================================================
-- Migration 008: Alert workflow (instructions, event log, SLA, dedup)
-- ============================================================================
-- Adds:
--   1. Closes duplicate open alerts (prereq for unique index)
--   2. sla_due_at + escalated_to on water_operational_alerts
--   3. aquavision.alert_instructions (supervisor -> officer work items)
--   4. Event-log enrichment on water_alert_audit_log + append-only trigger
--   5. Unique partial index: one open alert per (asset, alert_type)
--   6. SLA backfill for existing open alerts
-- ============================================================================

BEGIN;

-- ── 1. Close duplicate open alerts (keep newest per asset+type) ─────────────
UPDATE aquavision.water_operational_alerts a
SET status     = 'RESOLVED',
    resolved_by = 'SYSTEM',
    resolved_at = now(),
    resolution  = 'Superseded: duplicate open alert closed by migration 008'
FROM (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY asset_id, alert_type
               ORDER BY created_at DESC, id DESC
           ) AS rn
    FROM aquavision.water_operational_alerts
    WHERE status NOT IN ('RESOLVED', 'FALSE_OR_INVALID_DATA', 'AUTO_RESOLVED')
) d
WHERE a.id = d.id
  AND d.rn > 1;

-- ── 2. Alert workflow columns ───────────────────────────────────────────────
ALTER TABLE aquavision.water_operational_alerts
    ADD COLUMN IF NOT EXISTS sla_due_at  timestamptz,
    ADD COLUMN IF NOT EXISTS escalated_to text;

-- ── 3. Instruction table (layer 2: the actual work) ─────────────────────────
CREATE TABLE IF NOT EXISTS aquavision.alert_instructions (
    id                bigserial PRIMARY KEY,
    alert_id          bigint      NOT NULL
        REFERENCES aquavision.water_operational_alerts(id) ON DELETE CASCADE,
    asset_id          integer     NOT NULL
        REFERENCES aquavision.water_assets(id),
    issued_by         text        NOT NULL,          -- JWT username of issuer
    issued_role       text        NOT NULL,
    assigned_to       text        NOT NULL,          -- JWT username of assignee
    assigned_to_user_id bigint    REFERENCES shared.users(id),
    instruction_text  text        NOT NULL,
    template_key      text,
    due_at            timestamptz,
    status            text        NOT NULL DEFAULT 'ISSUED'
        CHECK (status IN ('ISSUED','ACCEPTED','IN_PROGRESS','REPORTED',
                          'VERIFIED','REJECTED','OVERDUE','WAIVED')),
    report_text       text,
    report_data       jsonb,
    reported_at       timestamptz,
    reported_by       text,
    verified_by       text,
    verified_at       timestamptz,
    decision_note     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_instr_assigned
    ON aquavision.alert_instructions (assigned_to, status);
CREATE INDEX IF NOT EXISTS ix_instr_alert
    ON aquavision.alert_instructions (alert_id);
CREATE INDEX IF NOT EXISTS ix_instr_open
    ON aquavision.alert_instructions (status)
    WHERE status IN ('ISSUED','ACCEPTED','IN_PROGRESS','OVERDUE','REPORTED');

-- ── 4a. Event log enrichment ────────────────────────────────────────────────
ALTER TABLE aquavision.water_alert_audit_log
    ADD COLUMN IF NOT EXISTS actor_role    text,
    ADD COLUMN IF NOT EXISTS instruction_id bigint
        REFERENCES aquavision.alert_instructions(id),
    ADD COLUMN IF NOT EXISTS payload       jsonb;

-- ── 4b. Append-only guarantee (tamper-proof audit trail) ────────────────────
CREATE OR REPLACE FUNCTION aquavision.reject_audit_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'water_alert_audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_append_only ON aquavision.water_alert_audit_log;
CREATE TRIGGER trg_audit_append_only
    BEFORE UPDATE OR DELETE ON aquavision.water_alert_audit_log
    FOR EACH ROW EXECUTE FUNCTION aquavision.reject_audit_mutation();

-- ── 5. One open alert per (asset, alert_type) ───────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_open_type
    ON aquavision.water_operational_alerts (asset_id, alert_type)
    WHERE status NOT IN ('RESOLVED', 'FALSE_OR_INVALID_DATA', 'AUTO_RESOLVED');

-- ── 6. SLA backfill: CRITICAL 15 min, WARNING 4 h, informational none ──────
UPDATE aquavision.water_operational_alerts
SET sla_due_at = created_at + CASE severity
        WHEN 'CRITICAL' THEN interval '15 minutes'
        WHEN 'WARNING'  THEN interval '4 hours'
        ELSE NULL
    END
WHERE status = 'NEW'
  AND sla_due_at IS NULL;

COMMIT;
