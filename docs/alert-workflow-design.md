# AquaVision Alerts — Role-Based Workflow Design
# ================================================
# Created: 2026-09-26
# Status: BUILT & VERIFIED (2026-09-26) — see §10 Build status
#
# Grounded in what already exists:
#   - aquavision.water_operational_alerts (status NEW/ACKNOWLEDGED/INVESTIGATING,
#     assigned_to, acknowledged_by/at, resolved_by/at, resolution, notes,
#     escalated_at, alert_source RULE|ML, episode_id, downstream impact fields)
#   - aquavision.asset_operational_notes (endpoints currently placeholders)
#   - roles in shared.roles: admin, water_supervisor, field_officer,
#     aquavision_analyst, viewer
#   - require_role() / permissions / region scopes (infrastructure/auth)
#   - NotificationDispatcher (Email + Slack, DB dedup)
#
# Design principle: alerts are EVENTS, instructions are WORK, events are HISTORY.
# Nothing is ever marked resolved by the system pretending a human acted.

---

## 1. Personas (real roles in the DB)

| Role | Count | Job in the alert loop |
|---|---|---|
| `admin` | 2 | Sets policy, receives escalations, approves closures, audits |
| `water_supervisor` | 5 | First responder for escalation: acknowledges, **issues instructions**, verifies resolution |
| `field_officer` | 8 | The "operator": executes instructions on site, submits readings/report, proposes resolution |
| `aquavision_analyst` | 1 | Model/data alerts: investigates accuracy, drift, feed quality |
| `viewer` | 17 | Read-only (sees timeline, cannot act) |

Permission rule: **every action writes an event with actor + role** — no action
is anonymous, and a field officer can never close an admin-owned alert.

---

## 2. Two-layer state model

**Layer 1 — Alert (the event)** — extends the existing `status` column:

```
NEW ──ack──► ACKNOWLEDGED ──work starts──► INVESTIGATING ──► RESOLVED
 │                │                             │
 │                └── SLA breach ──► ESCALATED ──┴──► (back to supervisor)
 └── auto ──► AUTO_RESOLVED        (informational alerts only, no human work)
```

- `ESCALATED` uses the existing `escalated_at` column (nothing is lost).
- `RESOLVED` requires a **resolution report** (text, min length) + actor.

**Layer 2 — Instruction (the work)** — new table `alert_instructions`:

```
ISSUED ──► ACCEPTED ──► IN_PROGRESS ──► REPORTED ──► VERIFIED
   │                                        │            │
   └── rejected/reissued ◄──────────────────┘            └── alert → RESOLVED
   └── due_at missed ──► OVERDUE ──► auto-escalate alert
```

- One alert → 0..n instructions (admin AND supervisor may issue; supervisor's
  cannot be overridden by field staff, admin's outranks).
- Alert can only reach `RESOLVED` when all its instructions are `VERIFIED`
  (or explicitly waived by admin with a reason).

**Layer 3 — Event log** — new table `alert_events` (append-only): actor, role,
action, from_status, to_status, comment, payload JSON, timestamp. This is the
"timeline" the UI shows and the audit trail the admin trusts.

---

## 3. Notification routing (who gets poked, when)

| Channel | Rule |
|---|---|
| In-app (bell + role queue) | Always; filtered by role & region scope |
| Email | CRITICAL/ESCALATED only, or any alert untouched > SLA/2 |
| Slack | Same as email if configured |
| Dedup | Same alert+role not re-notified within 30 min (reuse dispatcher dedup) |

| Severity | Notify first | ACK SLA | If breached |
|---|---|---|---|
| CRITICAL | supervisor **and** admin (immediate) | 15 min | escalate to admin + email |
| HIGH | supervisor | 30 min | escalate to admin |
| WARNING | supervisor | 4 h | remind supervisor |
| WATCH / INFO | role queue only (digest) | — | auto-resolve after validity window |

SLA clock starts at alert creation. Escalation is an **event**, not a new row.

---

## 4. THE USE CASES

### UC-1 — Flood forecast escalation (supervisor → instruction → operator → report → close)
*The core loop you described.*
- **Trigger:** ML `FORECAST_DANGER_7D`, or forecast flood-risk ≥ 70 for any asset
  (`alert_source='ML'`).
- **Flow:**
  1. System raises alert (NEW) → in-app + email to **water_supervisor + admin**.
  2. Supervisor **acknowledges** (→ ACKNOWLEDGED) and **issues instruction** to a
     field officer, e.g. *"Patrol right-bank bund km 42–48; measure 06:00 & 18:00;
     report before due_at 2026-09-28 12:00"*.
  3. Field officer **accepts** (→ ACCEPTED), goes **IN_PROGRESS**, later submits
     **action report** (readings, observations, what was done) → REPORTED.
  4. Supervisor **verifies** report → VERIFIED → alert → **RESOLVED** with
     resolution summary; admin sees closure in the audit timeline.
  5. No report by `due_at` → instruction OVERDUE → alert auto-**ESCALATED**
     (admin notified). No ACK by SLA → same escalation.
- **Data captured:** instruction text, due time, readings in report, both actors,
  full event timeline.

### UC-2 — Live threshold breach (immediate danger, operator-first)
- **Trigger:** current level ≥ danger/critical ft (`alert_source='RULE'`),
  or rate-of-change spike.
- **Flow:** CRITICAL alert → **field_officer on duty + supervisor + admin**
  simultaneously (no waiting). Field officer must ACK in 15 min; then works the
  site (INVESTIGATING), logs readings via the instruction/report path, proposes
  resolution with measured values. Supervisor verifies; admin only involved if
  SLA breached or severity = critical closure policy says so.
- **Difference from UC-1:** speed — operator is primary actor, supervisor verifies,
  admin is escalation-backstop.

### UC-3 — Top-down operating order (no alert — proactive instruction)
*Admin/supervisor initiate work; the alert system records it.*
- **Trigger:** manual — e.g. admin decides *"pre-position gates before the
  forecast rain"*, or a WATCH alert that supervisors want actioned anyway.
- **Flow:** supervisor/admin creates an **asset-scoped instruction** (optionally
  linked to WATCH/forecast alert) → field officer accepts → executes → report →
  supervisor verifies → closed. Same tables, `alert` may be `WATCH` or a
  synthetic `ADVISORY` alert.
- **Value:** the same queue and timeline serve reactive and proactive work —
  operators get ONE task list.

### UC-4 — Heavy rainfall watch (informational, auto-closing)
- **Trigger:** RAINFALL alert > 80 mm in lead window, or flood-risk 30–50 (WARNING).
- **Flow:** notified supervisor only (no ACK obligation). System **auto-resolves**
  when the lead window passes (`AUTO_RESOLVED`, reason = window expired) —
  UNLESS a threshold/forecast-danger alert for the same asset fired meanwhile,
  which upgrades it into UC-1 (instructions already issued carry over).
- **Rule:** informational alerts never lie in the inbox forever, and never
  silently die if conditions escalated.

### UC-5 — Data feed / sensor outage (analyst + operator)
- **Trigger:** IRSA feed stale > 24 h, sensor heartbeat lost, forecast batch
  returned 0 rows, weather refresh failing (from ingestion/health monitors).
- **Flow:** alert (HIGH, type `DATA_QUALITY`) → **field_officer** (check gauge /
  comms) + **aquavision_analyst** (assess data impact). Analyst issues instruction
  *"verify station X, capture manual reading"*. Officer reports manual reading;
  analyst confirms backfill → RESOLVED with the gap annotated (never fabricated
  data — manual reading enters as `data_origin='MANUAL'`).
- **SLA:** if outage > 48 h → escalate to admin (decision: switch to alternate
  source / notify WAPDA).

### UC-6 — Model accuracy degradation (analyst → admin)
- **Trigger:** weekly check (or after daily `compute_accuracy`): organic MAPE >
  40% for a horizon with n ≥ 5, or measured coverage outside 0.75–0.85, or a
  model marked `NOT_VALIDATED` that should have organic rows by now.
- **Flow:** alert (type `MODEL_QUALITY`, severity HIGH) → **aquavision_analyst +
  admin**. Analyst investigates (data drift? bad ingest? regime change?), issues
  instruction to self/other analyst *"retrain asset X, compare vs persistence"*,
  reports with before/after R² + coverage → admin verifies closure.
- **Value:** the accuracy loop we just built gets a human follow-up loop —
  a metric nobody acts on is decoration.

### UC-7 — Severe water stress → restriction order (WAI loop)
- **Trigger:** WAI ≤ 20 (Severe) or ≤ 40 (Critical) for 3 consecutive days, or
  a `WATER_STRESS` CRITICAL from v2 predictions.
- **Flow:** supervisor + admin notified (CRITICAL). Admin/supervisor issue
  restriction instructions to field officers (*"reduce release X, monitor canal
  Y weekly"*), field officers submit weekly progress reports, supervisor
  verifies each, admin closes when WAI recovers above threshold (system
  auto-suggests closure when the WAI condition ends — human still confirms).
- **Cadence:** long-running instruction with recurring reports (not one-shot).

### UC-8 — Episode-based escalation (grouping during a flood)
- **Trigger:** ≥ 3 alerts on the same river reach within 24 h (existing
  `episode_id` + downstream-impact fields already on the table).
- **Flow:** episode gets one **umbrella alert** escalated to admin with the
  downstream impact summary (population/bridges/hospitals fields already exist);
  per-asset alerts keep their UC-1/UC-2 loops; resolving the umbrella requires
  all member alerts resolved.
- **Value:** admin is not spammed 5 times for one flood wave — they get one
  rollup with impact, drill-down to children.

---

## 5. Role × action matrix

| Action | viewer | field_officer | water_supervisor | aquavision_analyst | admin |
|---|---|---|---|---|---|
| See alerts (region-scoped) | ✓ | ✓ | ✓ | ✓ | ✓ |
| ACK alert | — | ✓ (assigned/severity ≤ HIGH) | ✓ | ✓ (MODEL/DATA only) | ✓ |
| Issue instruction | — | — | ✓ | ✓ (MODEL/DATA only) | ✓ |
| Accept / progress instruction | — | ✓ (assigned) | ✓ | ✓ | ✓ |
| Submit report / propose resolve | — | ✓ (own instruction) | ✓ | ✓ | ✓ |
| Verify & close | — | — | ✓ | ✓ (own domain) | ✓ (any, with reason) |
| Waive instruction | — | — | — | — | ✓ (reason required) |
| Escalate / reassign / set SLA | — | —| ✓ (up) | — | ✓ |
| View audit timeline | ✓ | ✓ | ✓ | ✓ | ✓ |

Region scope (`user_region_scopes`) applies on top: everyone only sees their
regions unless admin.

---

## 6. Data model additions (migration 008)

```sql
alert_instructions(
  id, alert_id FK, asset_id, issued_by, issued_role, assigned_to,
  text, due_at, status ISSUED|ACCEPTED|IN_PROGRESS|REPORTED|VERIFIED|
                REJECTED|OVERDUE|WAIVED,
  report_text, report_data JSONB, report_attachments JSONB,
  reported_at, verified_by, verified_at, created_at, updated_at)

alert_events(
  id, alert_id FK, instruction_id FK NULL, actor, actor_role,
  action, from_status, to_status, comment, payload JSONB, created_at)

-- alert gains: workflow_status (if extending), instruction-required flag,
-- sla_due_at, escalated_to  — reuse existing status/escalated_at where enough
```

`asset_operational_notes` stays for free-text notes; instructions are structured
work items that reference alerts.

## 7. API surface (new)

```
POST /water/alerts/{id}/ack              (role-guarded)
POST /water/alerts/{id}/escalate
POST /water/alerts/{id}/instructions     {to, text, due_at}
POST /water/instructions/{id}/accept | /progress | /report | /verify | /reject
POST /water/alerts/{id}/resolve          {resolution}  (blocked if open instructions)
GET  /water/alerts/{id}/timeline         (events + instructions merged)
GET  /water/queue                        (role-filtered: my alerts / my tasks / team)
GET  /water/escalations                  (admin board: SLA breaches, open escalations)
```

All writes go through one `apply_alert_action()` helper that validates the
role matrix, moves state, and appends the event — so the audit log can never
be skipped.

## 8. Dashboard surfaces

1. **Operator (field_officer):** "My Tasks" — accepted/in-progress instructions,
   due times, one-tap report form (readings + note), alert context drawer.
2. **Supervisor inbox:** ACK/SLA timers, issue-instruction form (template
   library: patrol / gate check / manual reading), verification pane.
3. **Admin board:** escalations, SLA breaches, episode rollups, closures pending
   approval, audit timeline viewer.
4. **Analyst desk:** MODEL/DATA alerts + validation page deep-links.
5. **Global:** bell icon (in-app notifications), role-filtered alert list
   (existing operator/alerts page upgraded), timeline drawer on alert detail.

## 9. Build order (suggested)

1. Migration 008 + `apply_alert_action()` + endpoints + event log (core, no UI)
2. Notification routing (in-app bell + email on CRITICAL/escalated)
3. Supervisor instruction UI (issue/verify) + operator task queue
4. Admin escalation board + episode rollup (UC-8)
5. Auto-resolve/expiry jobs in scheduler (UC-4) + WAI/quality triggers (UC-5/6/7)

Out of scope (deliberate): SMS/call-out, mobile app — email + in-app first.

---

## 10. Build status (2026-09-26)

All five build-order steps are implemented and verified:

| Step | Landed in |
|---|---|
| 1. Migration 008 + workflow engine + endpoints + event log | `migrations/008_alert_workflow.sql` (applied), `infrastructure/alerts/workflow.py`, `presentation/http/routers/alert_workflow.py`, upgraded ack/escalate/resolve in `operational.py`, `WorkflowError` handler in `main.py` |
| 2. Notification routing | `workflow.notify()` — role emails (admin + water_supervisor) + `ALERT_RECIPIENTS` env, dispatcher dedup; graceful when SMTP unset (dev) |
| 3. Supervisor issue/verify UI + operator task queue | `water/operator/alerts` (issue modal, timeline, SLA badges), **new** `water/operator/tasks` (accept/report/verify), nav entry "My Tasks" |
| 4. Admin escalation board | `admin/alerts` — KPI strip (MTTR, ACK%, open/escalated), escalations card, Send-test button (nonce-dedup bypass) |
| 5. Scheduler jobs | `scheduler/main.py::job_alert_sla_scan` every 5 min (SLA escalate, overdue instructions, UC-4 informational auto-close); ML_V2 alert persistence in `prediction_v2.py::_persist_alerts` |

Verification: 235 unit tests pass (31 new in `tests/unit/test_alert_workflow.py`); live UC-1
smoke (admin issues → report → verify → alert auto-RESOLVED, viewer ack → 403, test-alert →
7 role recipients, scanner run: 15 SLA escalations + 6 auto-closes, scheduler tick confirmed
via heartbeat); `tsc --noEmit` + `next build` clean.

Deliberate deferrals:
- **Region scoping** (UC-7): `water_assets.province` is all NULL and no asset↔region map
  exists — queue scope supports auto|my|team|all without it; revisit when assets carry regions.
- **Episode rollups (UC-8)** on the admin board: data available via `episode_id`, UI pending.
- SMTP: recipients resolve, delivery activates when SMTP env is configured.
