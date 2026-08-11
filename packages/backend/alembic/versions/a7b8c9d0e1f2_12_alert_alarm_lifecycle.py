"""12_alert_alarm_lifecycle

Revision ID: a7b8c9d0e1f2
Revises: f1c2d3e4a5b6
Create Date: 2026-08-10 14:00:00.000000

Implements the SCADA alarm lifecycle (ISA-18.2 mindset) on water_alerts:

  Status state machine (stored in water_alerts.status, treated as canonical):
    ACTIVE -> ACKNOWLEDGED -> INVESTIGATING -> ACTION_REQUIRED
           -> RESPONSE_COMPLETED -> WAITING_FOR_VERIFICATION -> RESOLVED
    (any unresolved step may be ESCALATED; late shift may be
     HANDOVER_REQUIRED; resolved is terminal unless reopened)

  Acknowledgment captures responsibility but NEVER resolves an alert:
      acknowledged_by_user_id      Who accepted responsibility.
      initial_assessment           Operator's first read of the situation.
      estimated_response_time      ETA for the initial response.

  Investigation / action / evidence:
      investigation_notes          Findings from checking SCADA/field.
      action_taken                 Approved operational action performed.
      action_result                Measured outcome of the action.
      action_time                  When the action was performed.
      evidence_refs                Document / image / control-system refs (JSONB).

  Escalation:
      escalated_to                 Supervisor / regional / national authority.
      escalated_at                 When escalation happened.

  Verification / resolution:
      verified_by_user_id          Who confirmed the response (supervisor).
      verified_at                  When it was confirmed.
      resolved_by_user_id          Who cleared the alert (supervisor/admin).

Also seeds the water_supervisor role + lifecycle permissions:
  AQUAVISION_VERIFY_RESPONSE  - confirm an operator's response (supervisor)
  AQUAVISION_RESOLVE_ALERT    - clear a resolved alert (supervisor / admin)
  AQUAVISION_SEND_INSTRUCTION - issue work instructions (supervisor, step 3)
These are granted to admin (all-powerful) and the new water_supervisor role.
Idempotent - columns added, seed rows inserted only when missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f1c2d3e4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUPERVISOR_ROLE = "water_supervisor"
SUPERVISOR_PERMS = [
    "AQUAVISION_READ",
    "AQUAVISION_ANALYZE",
    "AQUAVISION_ACKNOWLEDGE_ALERT",
    "AQUAVISION_ADD_NOTE",
    "AQUAVISION_ESCALATE_ALERT",
    "AQUAVISION_SEND_INSTRUCTION",
    "AQUAVISION_VERIFY_RESPONSE",
    "AQUAVISION_RESOLVE_ALERT",
    "AQUAVISION_EXPORT",
    "AQUAVISION_APPROVE_REPORT",
]
# Permissions added to the superuser admin role that it may not already hold.
ADMIN_GRANTS = [
    "AQUAVISION_ESCALATE_ALERT",
    "AQUAVISION_SEND_INSTRUCTION",
    "AQUAVISION_VERIFY_RESPONSE",
    "AQUAVISION_RESOLVE_ALERT",
]


def _ensure_permission(conn, name: str) -> None:
    """Insert a permission row if it does not already exist."""
    if conn.execute(
        sa.text("SELECT 1 FROM shared.permissions p WHERE p.name = :name")
        .bindparams(name=name)
    ).first():
        return
    conn.execute(
        sa.text("INSERT INTO shared.permissions (name) VALUES (:name)")
        .bindparams(name=name)
    )


def _ensure_role(conn, name: str) -> None:
    if conn.execute(
        sa.text("SELECT 1 FROM shared.roles r WHERE r.name = :name")
        .bindparams(name=name)
    ).first():
        return
    conn.execute(
        sa.text(
            "INSERT INTO shared.roles (name, description) VALUES "
            "(:name, 'Supervisor role: coordinates and verifies operational response')"
        ).bindparams(name=name)
    )


def _grant_role_perms(conn, role_name: str, perms) -> None:
    for perm in perms:
        _ensure_permission(conn, perm)
        if conn.execute(
            sa.text(
                """
                SELECT 1 FROM shared.role_permissions rp
                JOIN shared.roles r ON r.id = rp.role_id
                JOIN shared.permissions p ON p.id = rp.permission_id
                WHERE r.name = :role AND p.name = :perm
                """
            ).bindparams(role=role_name, perm=perm)
        ).first():
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO shared.role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM shared.roles r, shared.permissions p
                WHERE r.name = :role AND p.name = :perm
                """
            ).bindparams(role=role_name, perm=perm)
        )


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        "water_alerts",
        sa.Column("acknowledged_by_user_id", sa.BigInteger(),
                  sa.ForeignKey("shared.users.id", ondelete="SET NULL"), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("initial_assessment", sa.Text(), nullable=True,
                  comment="Operator's first read on acknowledging"),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("estimated_response_time", sa.DateTime(timezone=True), nullable=True,
                  comment="ETA for the initial operational response"),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("investigation_notes", sa.Text(), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("action_taken", sa.Text(), nullable=True,
                  comment="Approved operational action performed"),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("action_result", sa.Text(), nullable=True,
                  comment="Measured outcome of the action"),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("action_time", sa.DateTime(timezone=True), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("evidence_refs", JSONB(), nullable=True,
                  server_default=sa.text("'[]'::jsonb")),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("escalated_to", sa.Text(), nullable=True,
                  comment="Supervisor / regional authority / national authority"),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("verified_by_user_id", sa.BigInteger(),
                  sa.ForeignKey("shared.users.id", ondelete="SET NULL"), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_alerts",
        sa.Column("resolved_by_user_id", sa.BigInteger(),
                  sa.ForeignKey("shared.users.id", ondelete="SET NULL"), nullable=True),
        schema="aquavision",
    )
    op.create_index("ix_water_alerts_status", "water_alerts", ["status"], schema="aquavision")

    # The original schema restricted status to the legacy demo values. The
    # lifecycle canonical statuses must be permitted, so replace the check.
    op.drop_constraint("water_alerts_status_check", "water_alerts", schema="aquavision")
    op.create_check_constraint(
        "water_alerts_status_check",
        "water_alerts",
        "status IN ('New', 'Active', 'Acknowledged', 'Resolved', "
        "'ACTIVE', 'ACKNOWLEDGED', 'INVESTIGATING', 'ACTION_REQUIRED', "
        "'RESPONSE_COMPLETED', 'WAITING_FOR_VERIFICATION', 'ESCALATED', "
        "'HANDOVER_REQUIRED', 'RESOLVED')",
        schema="aquavision",
    )

    # Seed lifecycle permissions + supervisor role.
    _ensure_role(conn, SUPERVISOR_ROLE)
    _grant_role_perms(conn, SUPERVISOR_ROLE, SUPERVISOR_PERMS)
    _grant_role_perms(conn, "admin", ADMIN_GRANTS)


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_index("ix_water_alerts_status", table_name="water_alerts", schema="aquavision")
    for col in ("resolved_by_user_id", "verified_at", "verified_by_user_id",
                "escalated_at", "escalated_to", "evidence_refs", "action_time",
                "action_result", "action_taken", "investigation_notes",
                "estimated_response_time", "initial_assessment",
                "acknowledged_by_user_id"):
        op.drop_column("water_alerts", col, schema="aquavision")
    # Removal of seed roles/permissions is intentionally not fully reversed to
    # avoid destroying rows that pre-existed this migration on shared objects.
    conn.execute(
        sa.text("DELETE FROM shared.role_permissions rp WHERE rp.role_id IN "
                "(SELECT id FROM shared.roles WHERE name = :role)")
        .bindparams(role=SUPERVISOR_ROLE)
    )
    conn.execute(
        sa.text("DELETE FROM shared.roles WHERE name = :role")
        .bindparams(role=SUPERVISOR_ROLE)
    )