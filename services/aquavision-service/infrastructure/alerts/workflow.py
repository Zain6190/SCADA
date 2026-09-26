# infrastructure/alerts/workflow.py
# Role-based alert workflow engine:
#   - State machine for alerts (layer 1) and instructions (layer 2)
#   - Append-only event log (water_alert_audit_log)
#   - Role/assignment authorization (the permission matrix)
#   - SLA scanning: ACK deadlines, overdue instructions, auto-close
#   - Notification routing to role-based recipients (Email/Slack, deduped)
# See docs/alert-workflow-design.md for the full design.
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.db.models import (
    AlertInstruction,
    Role,
    User,
    UserRole,
    WaterAlertAuditLog,
    WaterAsset,
    WaterOperationalAlert,
)

logger = logging.getLogger("aquavision.alerts.workflow")

# ─── Constants ────────────────────────────────────────────────────────────────

OPEN_STATUSES = ("NEW", "ACKNOWLEDGED", "INVESTIGATING", "ESCALATED")
CLOSED_STATUSES = ("RESOLVED", "FALSE_OR_INVALID_DATA", "AUTO_RESOLVED")

# ACK SLA by severity (creation -> must be acknowledged)
SLA_BY_SEVERITY = {
    "CRITICAL": timedelta(minutes=15),
    "WARNING": timedelta(hours=4),
}

# Informational alerts auto-close after this age (UC-4)
INFO_AUTO_CLOSE_AFTER = timedelta(hours=24)
INFO_SEVERITIES = ("WATCH", "ADVISORY")

# Role matrix (docs/alert-workflow-design.md §5)
ACTION_ROLES: Dict[str, Set[str]] = {
    "ack": {"admin", "water_supervisor", "field_officer", "aquavision_analyst"},
    "investigate": {"admin", "water_supervisor", "field_officer", "aquavision_analyst"},
    "escalate": {"admin", "water_supervisor"},
    "assign": {"admin", "water_supervisor"},
    "issue_instruction": {"admin", "water_supervisor", "aquavision_analyst"},
    "progress": {"admin", "water_supervisor", "field_officer", "aquavision_analyst"},
    "report": {"admin", "water_supervisor", "field_officer", "aquavision_analyst"},
    "verify": {"admin", "water_supervisor", "aquavision_analyst"},
    "reject": {"admin", "water_supervisor", "aquavision_analyst"},
    "waive": {"admin"},
    "resolve": {"admin", "water_supervisor", "aquavision_analyst"},
    "create_test": {"admin"},
}

# Valid alert state transitions (layer 1)
ALERT_TRANSITIONS: Dict[str, Set[str]] = {
    "ACKNOWLEDGED": {"NEW"},
    "INVESTIGATING": {"ACKNOWLEDGED", "ESCALATED"},
    "ESCALATED": {"NEW", "ACKNOWLEDGED", "INVESTIGATING"},
    "RESOLVED": {"NEW", "ACKNOWLEDGED", "INVESTIGATING", "ESCALATED"},
    "AUTO_RESOLVED": {"NEW"},
}

# Valid instruction transitions (layer 2)
INSTRUCTION_TRANSITIONS: Dict[str, Set[str]] = {
    "ACCEPTED": {"ISSUED", "OVERDUE"},
    "IN_PROGRESS": {"ACCEPTED", "OVERDUE"},
    "REPORTED": {"ACCEPTED", "IN_PROGRESS", "OVERDUE"},
    "VERIFIED": {"REPORTED"},
    "REJECTED": {"REPORTED"},
    "WAIVED": {"ISSUED", "ACCEPTED", "IN_PROGRESS", "OVERDUE", "REPORTED"},
    "OVERDUE": {"ISSUED", "ACCEPTED", "IN_PROGRESS"},
}

# Standard instruction templates (UC-3, structured reports)
INSTRUCTION_TEMPLATES: Dict[str, Dict] = {
    "patrol_bund": {
        "title": "Bund / bank patrol",
        "text": "Patrol the flagged reach. Record water level (ft), any seepage/"
                "piping, and breaches. Photograph critical sections.",
        "report_fields": ["level_ft", "seepage", "breach_observed", "photo_ref"],
    },
    "gate_check": {
        "title": "Gate / regulator check",
        "text": "Inspect gates and regulators. Confirm gate positions, report "
                "jammed or unresponsive gates, and record current openings.",
        "report_fields": ["gate_positions", "malfunction", "opening_ft"],
    },
    "manual_reading": {
        "title": "Manual gauge reading",
        "text": "Capture a manual gauge reading at the station. Note sensor "
                "status and any calibration drift observed.",
        "report_fields": ["reading_ft", "sensor_status", "observed_at"],
    },
    "comms_check": {
        "title": "Sensor / comms verification",
        "text": "Verify sensor power and communication link. If faulty, record "
                "diagnostics and expected repair time.",
        "report_fields": ["power_ok", "link_ok", "diagnostics", "eta_repair"],
    },
    "restriction_monitor": {
        "title": "Water-stress restriction monitoring",
        "text": "Monitor release and canal delivery per restriction order. "
                "Record daily release and any non-compliance observed.",
        "report_fields": ["release_cusecs", "canal_status", "non_compliance"],
    },
}


# ─── Errors / actor ───────────────────────────────────────────────────────────

class WorkflowError(Exception):
    """Domain error mapped to HTTP by the API layer."""
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Actor:
    username: str
    role: str
    user_id: Optional[int] = None
    roles: Set[str] = field(default_factory=set)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def all_roles(self) -> Set[str]:
        return self.roles | {self.role} if self.role else self.roles


def actor_from_token(user: dict) -> Actor:
    """Build an Actor from a decoded JWT payload."""
    username = user.get("username") or "unknown"
    role = user.get("role") or ""
    roles = set(user.get("roles") or [])
    if role:
        roles.add(role)
    user_id = None
    sub = user.get("sub")
    if sub is not None:
        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            user_id = None
    return Actor(username=username, role=role, user_id=user_id, roles=roles)


def authorize(actor: Actor, action: str, alert: Optional[WaterOperationalAlert] = None) -> None:
    """Enforce the role matrix (raises 403). Analyst may only work ML-sourced
    alerts for issue/verify/close actions (own domain rule)."""
    allowed = ACTION_ROLES.get(action, set())
    if not (actor.all_roles & allowed):
        raise WorkflowError(
            f"Role '{actor.role}' cannot perform '{action}' "
            f"(requires: {', '.join(sorted(allowed))})",
            status_code=403,
        )
    if (
        action in ("issue_instruction", "verify", "reject", "resolve")
        and "aquavision_analyst" in actor.all_roles
        and not (actor.all_roles & {"admin", "water_supervisor"})
        and alert is not None
        and (alert.alert_source or "RULE") not in ("ML", "ML_V2", "MODEL")
        and (alert.alert_domain or "OPERATIONAL") not in ("MODEL", "DATA_QUALITY", "FORECAST")
    ):
        raise WorkflowError(
            "aquavision_analyst may only work ML/model-domain alerts",
            status_code=403,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Event log ────────────────────────────────────────────────────────────────

def log_event(
    session: Session,
    *,
    alert_id: int,
    action: str,
    performed_by: str,
    actor_role: Optional[str] = None,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    notes: Optional[str] = None,
    instruction_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> WaterAlertAuditLog:
    """Append an event to the (DB-enforced append-only) audit trail."""
    event = WaterAlertAuditLog(
        alert_id=alert_id,
        action=action,
        performed_by=performed_by,
        old_status=old_status,
        new_status=new_status,
        notes=notes,
        actor_role=actor_role,
        instruction_id=instruction_id,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


# ─── Notifications (role-routed) ──────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def role_emails(session: Session, roles: Sequence[str]) -> List[str]:
    """Active user emails for the given roles (junk addresses filtered)."""
    rows = session.execute(
        select(User.email)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            Role.name.in_(list(roles)),
            User.is_active.is_(True),
            User.access_status == "ACTIVE",
        )
    ).scalars().all()
    return [e for e in rows if e and _EMAIL_RE.match(e)]


def _build_notifiers():
    from config.settings import settings
    from infrastructure.notifications.email_notifier import EmailNotifier
    from infrastructure.notifications.slack_notifier import SlackNotifier

    notifiers = []
    if settings.SMTP_HOST and settings.SMTP_USERNAME:
        notifiers.append(EmailNotifier(
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            from_addr=settings.SMTP_FROM or settings.SMTP_USERNAME,
            use_tls=settings.SMTP_USE_TLS,
        ))
    if settings.SLACK_WEBHOOK_URL:
        notifiers.append(SlackNotifier(webhook_url=settings.SLACK_WEBHOOK_URL))
    return notifiers


def notify(
    session: Session,
    *,
    notification_type: str,
    severity: str,
    title: str,
    message: str,
    recipients: Sequence[str],
    asset_id: Optional[int] = None,
    asset_name: Optional[str] = None,
    details: Optional[dict] = None,
    nonce: Optional[str] = None,
) -> Optional[dict]:
    """Dispatch via NotificationDispatcher (persistent dedup). Returns dispatch
    counts, or None when no channels are configured."""
    from config.settings import settings
    from infrastructure.notifications.base import AlertNotification
    from infrastructure.notifications.dispatcher import NotificationDispatcher

    notifiers = _build_notifiers()
    if not notifiers:
        return None

    env_recipients = [r.strip() for r in settings.ALERT_RECIPIENTS.split(",") if r.strip()]
    all_recipients = sorted(set(list(recipients) + env_recipients))
    if not all_recipients:
        all_recipients = ["ops-team@ibcp.gov.pk"]

    notification = AlertNotification(
        alert_key=f"workflow:{notification_type}:{asset_id or 0}:{severity}",
        alert_type=f"{notification_type}_{nonce}" if nonce else notification_type,
        severity=severity,
        asset_id=asset_id,
        asset_name=asset_name,
        title=title[:120],
        message=message,
        source="WORKFLOW",
        details=details,
    )
    dispatcher = NotificationDispatcher(session, notifiers)
    result = dispatcher.dispatch(notification, all_recipients)
    logger.info(
        "Workflow notification %s: sent=%s suppressed=%s failed=%s recipients=%s",
        notification_type, result["sent"], result["suppressed"], result["failed"],
        len(all_recipients),
    )
    return result


def _asset_name(session: Session, asset_id: int) -> str:
    asset = session.get(WaterAsset, asset_id)
    return asset.canonical_name if asset else f"Asset {asset_id}"


# ─── Alert lifecycle (layer 1) ───────────────────────────────────────────────

def sla_due_at(severity: str, created_at: Optional[datetime] = None) -> Optional[datetime]:
    delta = SLA_BY_SEVERITY.get((severity or "").upper())
    if not delta:
        return None
    return (created_at or _now()) + delta


def _check_transition(current: str, new_status: str) -> None:
    allowed = ALERT_TRANSITIONS.get(new_status, set())
    if current not in allowed:
        raise WorkflowError(
            f"Cannot move alert from '{current}' to '{new_status}'"
        )


def ack_alert(session: Session, alert: WaterOperationalAlert, actor: Actor, notes: Optional[str] = None) -> None:
    authorize(actor, "ack", alert)
    if alert.status != "NEW":
        raise WorkflowError(f"Cannot acknowledge alert in status '{alert.status}'")
    old = alert.status
    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = actor.username
    alert.acknowledged_at = _now()
    if notes:
        alert.notes = notes
    sla_met = bool(alert.sla_due_at and alert.acknowledged_at <= alert.sla_due_at)
    log_event(
        session, alert_id=alert.id, action="ACKNOWLEDGED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=old, new_status=alert.status, notes=notes,
        payload={"sla_met": sla_met},
    )
    session.commit()


def investigate_alert(session: Session, alert: WaterOperationalAlert, actor: Actor, notes: Optional[str] = None) -> None:
    authorize(actor, "investigate", alert)
    _check_transition(alert.status, "INVESTIGATING")
    old = alert.status
    alert.status = "INVESTIGATING"
    if not alert.acknowledged_by:
        alert.acknowledged_by = actor.username
        alert.acknowledged_at = _now()
    if notes:
        alert.notes = notes
    log_event(
        session, alert_id=alert.id, action="INVESTIGATING",
        performed_by=actor.username, actor_role=actor.role,
        old_status=old, new_status=alert.status, notes=notes,
    )
    session.commit()


def escalate_alert(
    session: Session,
    alert: WaterOperationalAlert,
    actor: Actor,
    notes: Optional[str] = None,
    to: str = "admin",
    system: bool = False,
) -> None:
    if not system:
        authorize(actor, "escalate", alert)
    _check_transition(alert.status, "ESCALATED")
    old = alert.status
    alert.status = "ESCALATED"
    alert.escalated_at = _now()
    alert.escalated_to = to
    if notes:
        alert.notes = notes
    log_event(
        session, alert_id=alert.id,
        action="ESCALATED_SLA" if system else "ESCALATED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=old, new_status=alert.status,
        notes=notes, payload={"escalated_to": to, "system": system},
    )
    if system or to == "admin":
        notify(
            session,
            notification_type="ALERT_ESCALATED", severity=alert.severity,
            title=f"Escalated: {alert.alert_type} ({alert.severity})",
            message=f"Alert #{alert.id} escalated to {to}: {alert.message}",
            recipients=role_emails(session, ["admin"]),
            asset_id=alert.asset_id, asset_name=_asset_name(session, alert.asset_id),
            details={"alert_id": alert.id, "escalated_to": to},
        )
    session.commit()


def resolve_alert(
    session: Session,
    alert: WaterOperationalAlert,
    actor: Actor,
    resolution: str,
    system: bool = False,
) -> None:
    if not system:
        authorize(actor, "resolve", alert)
    _check_transition(alert.status, "RESOLVED")
    open_instr = session.execute(
        select(func.count(AlertInstruction.id)).where(
            AlertInstruction.alert_id == alert.id,
            AlertInstruction.status.in_(("ISSUED", "ACCEPTED", "IN_PROGRESS", "OVERDUE", "REPORTED")),
        )
    ).scalar()
    if open_instr and not actor.is_admin:
        raise WorkflowError(
            f"Cannot resolve: {open_instr} instruction(s) still open "
            "(report/verify them, or an admin must waive)"
        )
    if not resolution or len(resolution.strip()) < 5:
        raise WorkflowError("Resolution text is required (min 5 characters)")
    old = alert.status
    alert.status = "RESOLVED"
    alert.resolved_by = actor.username
    alert.resolved_at = _now()
    alert.resolution = resolution.strip()
    log_event(
        session, alert_id=alert.id, action="RESOLVED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=old, new_status=alert.status,
        notes=resolution.strip(),
        payload={"waived_open_instructions": open_instr if (open_instr and actor.is_admin) else 0},
    )
    session.commit()


def assign_alert(
    session: Session,
    alert: WaterOperationalAlert,
    actor: Actor,
    assigned_to: str,
    assigned_to_user_id: Optional[int] = None,
) -> None:
    authorize(actor, "assign", alert)
    if alert.status not in OPEN_STATUSES:
        raise WorkflowError(f"Alert is '{alert.status}', cannot assign")
    old_assignee = alert.assigned_to
    alert.assigned_to = assigned_to
    log_event(
        session, alert_id=alert.id, action="ASSIGNED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=alert.status, new_status=alert.status,
        payload={"assigned_to": assigned_to, "previous": old_assignee,
                 "assigned_to_user_id": assigned_to_user_id},
    )
    session.commit()


def auto_resolve_info_alert(
    session: Session,
    alert: WaterOperationalAlert,
    reason: str,
) -> None:
    """UC-4: informational alerts age out automatically."""
    if alert.status != "NEW":
        raise WorkflowError(f"Cannot auto-resolve alert in status '{alert.status}'")
    alert.status = "AUTO_RESOLVED"
    alert.resolved_by = "SYSTEM"
    alert.resolved_at = _now()
    alert.resolution = reason
    log_event(
        session, alert_id=alert.id, action="AUTO_RESOLVED",
        performed_by="SYSTEM", actor_role="SYSTEM",
        old_status="NEW", new_status="AUTO_RESOLVED", notes=reason,
    )


# ─── Instructions (layer 2) ──────────────────────────────────────────────────

def issue_instruction(
    session: Session,
    alert: WaterOperationalAlert,
    actor: Actor,
    *,
    instruction_text: str,
    assigned_to: str,
    assigned_to_user_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
    template_key: Optional[str] = None,
) -> AlertInstruction:
    authorize(actor, "issue_instruction", alert)
    if alert.status not in OPEN_STATUSES:
        raise WorkflowError(f"Alert is '{alert.status}', cannot issue instruction")
    if not instruction_text or len(instruction_text.strip()) < 5:
        raise WorkflowError("Instruction text is required (min 5 characters)")
    if assigned_to == actor.username and actor.role not in ("admin", "aquavision_analyst"):
        raise WorkflowError("Cannot assign an instruction to yourself", status_code=403)

    instr = AlertInstruction(
        alert_id=alert.id,
        asset_id=alert.asset_id,
        issued_by=actor.username,
        issued_role=actor.role,
        assigned_to=assigned_to,
        assigned_to_user_id=assigned_to_user_id,
        instruction_text=instruction_text.strip(),
        template_key=template_key,
        due_at=due_at,
        status="ISSUED",
    )
    session.add(instr)
    session.flush()

    log_event(
        session, alert_id=alert.id, action="INSTRUCTION_ISSUED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=alert.status, new_status=alert.status,
        notes=instruction_text.strip()[:200],
        instruction_id=instr.id,
        payload={"assigned_to": assigned_to, "due_at": due_at.isoformat() if due_at else None,
                 "template_key": template_key},
    )

    assignee_email = None
    if assigned_to_user_id:
        assignee = session.get(User, assigned_to_user_id)
        if assignee and assignee.email and _EMAIL_RE.match(assignee.email):
            assignee_email = assignee.email
    recipients = [assignee_email] if assignee_email else []
    recipients += role_emails(session, ["water_supervisor", "admin"])
    notify(
        session,
        notification_type="INSTRUCTION_ISSUED", severity="WARNING",
        title=f"New instruction on alert #{alert.id}",
        message=f"{actor.username} -> {assigned_to}: {instruction_text.strip()[:200]}"
                + (f" (due {due_at.isoformat()})" if due_at else ""),
        recipients=recipients,
        asset_id=alert.asset_id, asset_name=_asset_name(session, alert.asset_id),
        details={"instruction_id": instr.id, "alert_id": alert.id},
    )
    session.commit()
    return instr


def _get_instruction(session: Session, instruction_id: int) -> AlertInstruction:
    instr = session.get(AlertInstruction, instruction_id)
    if not instr:
        raise WorkflowError("Instruction not found", status_code=404)
    return instr


def _authorize_instruction_actor(instr: AlertInstruction, actor: Actor, action: str) -> None:
    """Actors may act on their own instruction; supervisors/admin/analyst(verify)
    act on any; plain field officers only their own."""
    authorize(actor, action)
    if instr.assigned_to == actor.username:
        return
    if actor.all_roles & {"admin", "water_supervisor"}:
        return
    if action in ("verify", "reject", "waive") and actor.is_admin:
        return
    raise WorkflowError(
        "Instruction is assigned to another user", status_code=403
    )


def _instruction_transition(instr: AlertInstruction, new_status: str) -> str:
    allowed = INSTRUCTION_TRANSITIONS.get(new_status, set())
    if instr.status not in allowed:
        raise WorkflowError(
            f"Cannot move instruction from '{instr.status}' to '{new_status}'"
        )
    old = instr.status
    instr.status = new_status
    instr.updated_at = _now()
    return old


def _instruction_event(
    session: Session,
    instr: AlertInstruction,
    actor: Actor,
    action: str,
    old_status: str,
    notes: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    log_event(
        session, alert_id=instr.alert_id, action=action,
        performed_by=actor.username, actor_role=actor.role,
        old_status=old_status, new_status=instr.status,
        notes=notes, instruction_id=instr.id, payload=payload,
    )


def _maybe_resolve_alert(
    session: Session,
    instr: AlertInstruction,
    actor: Actor,
    session_note: str,
) -> None:
    """Design: verifying/waiving the last open instruction resolves the alert."""
    remaining = session.execute(
        select(func.count(AlertInstruction.id)).where(
            AlertInstruction.alert_id == instr.alert_id,
            AlertInstruction.status.in_(("ISSUED", "ACCEPTED", "IN_PROGRESS", "OVERDUE", "REPORTED")),
        )
    ).scalar()
    if remaining:
        return
    alert = session.get(WaterOperationalAlert, instr.alert_id)
    if not alert or alert.status not in OPEN_STATUSES:
        return
    old = alert.status
    alert.status = "RESOLVED"
    alert.resolved_by = actor.username
    alert.resolved_at = _now()
    alert.resolution = session_note
    log_event(
        session, alert_id=alert.id, action="RESOLVED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=old, new_status="RESOLVED",
        notes=session_note, payload={"auto": True, "last_instruction_id": instr.id},
    )


def accept_instruction(session: Session, instruction_id: int, actor: Actor) -> AlertInstruction:
    instr = _get_instruction(session, instruction_id)
    _authorize_instruction_actor(instr, actor, "progress")
    old = _instruction_transition(instr, "ACCEPTED")
    _instruction_event(session, instr, actor, "INSTRUCTION_ACCEPTED", old)
    session.commit()
    return instr


def progress_instruction(session: Session, instruction_id: int, actor: Actor) -> AlertInstruction:
    instr = _get_instruction(session, instruction_id)
    _authorize_instruction_actor(instr, actor, "progress")
    old = _instruction_transition(instr, "IN_PROGRESS")
    _instruction_event(session, instr, actor, "INSTRUCTION_PROGRESS", old)
    session.commit()
    return instr


def report_instruction(
    session: Session,
    instruction_id: int,
    actor: Actor,
    report_text: str,
    report_data: Optional[dict] = None,
) -> AlertInstruction:
    instr = _get_instruction(session, instruction_id)
    _authorize_instruction_actor(instr, actor, "report")
    if not report_text or len(report_text.strip()) < 5:
        raise WorkflowError("Report text is required (min 5 characters)")
    old = _instruction_transition(instr, "REPORTED")
    instr.report_text = report_text.strip()
    instr.report_data = report_data
    instr.reported_at = _now()
    instr.reported_by = actor.username
    _instruction_event(
        session, instr, actor, "INSTRUCTION_REPORTED", old,
        notes=report_text.strip()[:200], payload={"data": report_data},
    )
    recipients = role_emails(session, ["water_supervisor", "admin"])
    notify(
        session,
        notification_type="INSTRUCTION_REPORTED", severity="WARNING",
        title=f"Report submitted on alert #{instr.alert_id}",
        message=f"{actor.username} reported: {report_text.strip()[:200]}",
        recipients=recipients,
        asset_id=instr.asset_id, asset_name=_asset_name(session, instr.asset_id),
        details={"instruction_id": instr.id, "alert_id": instr.alert_id},
    )
    session.commit()
    return instr


def verify_instruction(
    session: Session,
    instruction_id: int,
    actor: Actor,
    note: Optional[str] = None,
) -> AlertInstruction:
    instr = _get_instruction(session, instruction_id)
    authorize(actor, "verify", session.get(WaterOperationalAlert, instr.alert_id))
    if not note or len(note.strip()) < 3:
        raise WorkflowError("Verification note is required")
    old = _instruction_transition(instr, "VERIFIED")
    instr.verified_by = actor.username
    instr.verified_at = _now()
    instr.decision_note = note.strip()
    _instruction_event(session, instr, actor, "INSTRUCTION_VERIFIED", old, notes=note.strip())
    _maybe_resolve_alert(
        session, instr, actor,
        f"All instructions verified. Last: {note.strip()}",
    )
    session.commit()
    return instr


def reject_instruction(
    session: Session,
    instruction_id: int,
    actor: Actor,
    reason: str,
) -> AlertInstruction:
    instr = _get_instruction(session, instruction_id)
    authorize(actor, "reject", session.get(WaterOperationalAlert, instr.alert_id))
    if not reason or len(reason.strip()) < 3:
        raise WorkflowError("Rejection reason is required")
    old = _instruction_transition(instr, "REJECTED")
    instr.decision_note = reason.strip()
    _instruction_event(session, instr, actor, "INSTRUCTION_REJECTED", old, notes=reason.strip())
    session.commit()
    return instr


def waive_instruction(
    session: Session,
    instruction_id: int,
    actor: Actor,
    reason: str,
) -> AlertInstruction:
    instr = _get_instruction(session, instruction_id)
    authorize(actor, "waive")
    if not reason or len(reason.strip()) < 3:
        raise WorkflowError("Waiver reason is required")
    old = _instruction_transition(instr, "WAIVED")
    instr.decision_note = reason.strip()
    instr.verified_by = actor.username
    instr.verified_at = _now()
    _instruction_event(session, instr, actor, "INSTRUCTION_WAIVED", old, notes=reason.strip())
    _maybe_resolve_alert(
        session, instr, actor,
        f"All instructions closed (waived: {reason.strip()})",
    )
    session.commit()
    return instr


# ─── SLA scanner (scheduler entry point) ─────────────────────────────────────

def scan_slas(session: Session) -> Dict[str, int]:
    """Called every 5 minutes by the scheduler:
    - ACK SLA breach on NEW alerts        -> ESCALATED (admin notified)
    - Instruction due_at missed           -> OVERDUE    (supervisors notified)
    - Aged informational alerts (UC-4)    -> AUTO_RESOLVED
    """
    summary = {"sla_escalated": 0, "instructions_overdue": 0, "info_auto_resolved": 0}
    now = _now()

    # 1. ACK SLA breaches
    breaches = session.execute(
        select(WaterOperationalAlert).where(
            WaterOperationalAlert.status == "NEW",
            WaterOperationalAlert.sla_due_at.isnot(None),
            WaterOperationalAlert.sla_due_at < now,
        )
    ).scalars().all()
    for alert in breaches:
        try:
            escalate_alert(
                session, alert, Actor(username="SYSTEM", role="SYSTEM", roles={"system"}),
                notes=f"ACK SLA breached (due {alert.sla_due_at.isoformat()})",
                to="admin", system=True,
            )
            summary["sla_escalated"] += 1
        except WorkflowError as e:
            logger.warning("SLA escalation skipped for alert %s: %s", alert.id, e)

    # 2. Overdue instructions
    overdue = session.execute(
        select(AlertInstruction).where(
            AlertInstruction.status.in_(("ISSUED", "ACCEPTED", "IN_PROGRESS")),
            AlertInstruction.due_at.isnot(None),
            AlertInstruction.due_at < now,
        )
    ).scalars().all()
    for instr in overdue:
        try:
            old = _instruction_transition(instr, "OVERDUE")
            _instruction_event(
                session, instr,
                Actor(username="SYSTEM", role="SYSTEM", roles={"system"}),
                "INSTRUCTION_OVERDUE", old,
                notes=f"Due {instr.due_at.isoformat()} missed",
            )
            notify(
                session,
                notification_type="INSTRUCTION_OVERDUE", severity="WARNING",
                title=f"Instruction overdue on alert #{instr.alert_id}",
                message=f"Assigned to {instr.assigned_to}: {instr.instruction_text[:160]}",
                recipients=role_emails(session, ["water_supervisor", "admin"]),
                asset_id=instr.asset_id,
                asset_name=_asset_name(session, instr.asset_id),
                details={"instruction_id": instr.id, "alert_id": instr.alert_id},
            )
            summary["instructions_overdue"] += 1
        except WorkflowError as e:
            logger.warning("Overdue transition skipped for instruction %s: %s", instr.id, e)

    # 3. Informational alerts age out (UC-4)
    aged = session.execute(
        select(WaterOperationalAlert).where(
            WaterOperationalAlert.status == "NEW",
            WaterOperationalAlert.severity.in_(INFO_SEVERITIES),
            WaterOperationalAlert.created_at < now - INFO_AUTO_CLOSE_AFTER,
        )
    ).scalars().all()
    for alert in aged:
        try:
            auto_resolve_info_alert(
                session, alert,
                "Auto-closed: informational alert aged past validity window",
            )
            summary["info_auto_resolved"] += 1
        except WorkflowError as e:
            logger.warning("Auto-resolve skipped for alert %s: %s", alert.id, e)

    session.commit()
    return summary


# ─── KPIs (admin board) ──────────────────────────────────────────────────────

def compute_kpis(session: Session) -> Dict:
    now = _now()
    since_30d = now - timedelta(days=30)
    since_7d = now - timedelta(days=7)

    open_by_severity = dict(session.execute(
        select(WaterOperationalAlert.severity, func.count(WaterOperationalAlert.id))
        .where(WaterOperationalAlert.status.in_(OPEN_STATUSES))
        .group_by(WaterOperationalAlert.severity)
    ).all())

    open_by_status = dict(session.execute(
        select(WaterOperationalAlert.status, func.count(WaterOperationalAlert.id))
        .where(WaterOperationalAlert.status.in_(OPEN_STATUSES))
        .group_by(WaterOperationalAlert.status)
    ).all())

    mttr_row = session.execute(
        select(
            func.avg(
                func.extract("epoch", WaterOperationalAlert.resolved_at - WaterOperationalAlert.created_at)
            )
        ).where(
            WaterOperationalAlert.status.in_(CLOSED_STATUSES),
            WaterOperationalAlert.resolved_at.isnot(None),
            WaterOperationalAlert.created_at >= since_30d,
        )
    ).one()
    mttr_hours = round(float(mttr_row[0]) / 3600.0, 1) if mttr_row[0] else None

    sla_total = session.execute(
        select(func.count(WaterOperationalAlert.id)).where(
            WaterOperationalAlert.sla_due_at.isnot(None),
            WaterOperationalAlert.created_at >= since_30d,
        )
    ).scalar() or 0
    sla_met = session.execute(
        select(func.count(WaterOperationalAlert.id)).where(
            WaterOperationalAlert.sla_due_at.isnot(None),
            WaterOperationalAlert.created_at >= since_30d,
            WaterOperationalAlert.acknowledged_at.isnot(None),
            WaterOperationalAlert.acknowledged_at <= WaterOperationalAlert.sla_due_at,
        )
    ).scalar() or 0
    ack_compliance_pct = round(100.0 * sla_met / sla_total, 1) if sla_total else None

    overdue_instructions = session.execute(
        select(func.count(AlertInstruction.id)).where(
            AlertInstruction.status == "OVERDUE",
        )
    ).scalar() or 0
    open_instructions = session.execute(
        select(func.count(AlertInstruction.id)).where(
            AlertInstruction.status.in_(("ISSUED", "ACCEPTED", "IN_PROGRESS", "OVERDUE", "REPORTED")),
        )
    ).scalar() or 0
    escalations_7d = session.execute(
        select(func.count(WaterOperationalAlert.id)).where(
            WaterOperationalAlert.status == "ESCALATED",
            WaterOperationalAlert.escalated_at >= since_7d,
        )
    ).scalar() or 0

    return {
        "open_total": sum(open_by_severity.values()),
        "open_by_severity": open_by_severity,
        "open_by_status": open_by_status,
        "mttr_hours_30d": mttr_hours,
        "ack_sla_compliance_pct": ack_compliance_pct,
        "ack_sla_window_30d": sla_total,
        "overdue_instructions": overdue_instructions,
        "open_instructions": open_instructions,
        "escalations_7d": escalations_7d,
        "generated_at": now.isoformat(),
    }
