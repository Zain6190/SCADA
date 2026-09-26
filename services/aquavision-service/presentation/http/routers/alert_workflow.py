# presentation/http/routers/alert_workflow.py
# Role-based alert workflow API (docs/alert-workflow-design.md):
#   GET  /water/alerts/queue                 - role-filtered work queue + counts
#   GET  /water/alerts/{id}/timeline         - events + instructions (audit trail)
#   GET  /water/alerts/escalations           - SLA breaches / escalations board
#   GET  /water/alerts/kpis                  - workflow health (admin)
#   GET  /water/alerts/instruction-templates - standard instruction library
#   GET  /water/workflow/assignables         - assignee picker by role
#   POST /water/alerts/{id}/assign           - assign an owner
#   POST /water/alerts/{id}/instructions     - issue an instruction (UC-1)
#   POST /water/instructions/{id}/accept|progress|report|verify|reject|waive
#   POST /water/alerts/test                  - admin: send a test notification
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from infrastructure.alerts import workflow
from infrastructure.alerts.workflow import (
    INSTRUCTION_TEMPLATES, OPEN_STATUSES, WorkflowError, actor_from_token,
)
from infrastructure.auth.jwt import get_current_user
from infrastructure.db.engine import get_session
from infrastructure.db.models import (
    AlertInstruction, WaterAsset, WaterAlertAuditLog, WaterOperationalAlert,
)

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class InstructionOut(BaseModel):
    id: int
    alert_id: int
    asset_id: int
    asset_name: Optional[str] = None
    alert_type: Optional[str] = None
    alert_severity: Optional[str] = None
    alert_status: Optional[str] = None
    alert_message: Optional[str] = None
    issued_by: str
    issued_role: str
    assigned_to: str
    instruction_text: str
    template_key: Optional[str] = None
    due_at: Optional[datetime] = None
    status: str
    report_text: Optional[str] = None
    report_data: Optional[dict] = None
    reported_at: Optional[datetime] = None
    reported_by: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertMini(BaseModel):
    id: int
    asset_id: int
    asset_name: Optional[str] = None
    alert_type: str
    severity: str
    status: str
    message: str
    alert_source: Optional[str] = None
    created_at: datetime
    sla_due_at: Optional[datetime] = None
    sla_breached: bool = False
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    escalated_to: Optional[str] = None
    escalated_at: Optional[datetime] = None
    episode_id: Optional[int] = None
    flood_probability: Optional[float] = None

    class Config:
        from_attributes = True


class QueueOut(BaseModel):
    scope: str
    role: str
    instructions_my: List[InstructionOut]
    instructions_to_verify: List[InstructionOut]
    alerts_new: List[AlertMini]
    alerts_escalated: List[AlertMini]
    counts: dict


class TimelineItem(BaseModel):
    kind: str  # "event" | "instruction"
    at: datetime
    action: str
    actor: str
    actor_role: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    notes: Optional[str] = None
    instruction_id: Optional[int] = None
    payload: Optional[dict] = None
    instruction: Optional[InstructionOut] = None


class AssignInput(BaseModel):
    assigned_to: str
    assigned_to_user_id: Optional[int] = None


class IssueInstructionInput(BaseModel):
    instruction_text: str = Field(min_length=5, max_length=4000)
    assigned_to: str
    assigned_to_user_id: Optional[int] = None
    due_at: Optional[datetime] = None
    template_key: Optional[str] = None


class ReportInput(BaseModel):
    report_text: str = Field(min_length=5, max_length=8000)
    report_data: Optional[dict] = None


class NoteInput(BaseModel):
    note: str = Field(min_length=3, max_length=4000)


class AssignableOut(BaseModel):
    id: int
    name: str
    email: str
    username: str
    role: str


class TestAlertOut(BaseModel):
    alert_id: int
    channels_configured: bool
    dispatch: Optional[dict] = None
    recipients: List[str]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _asset_names(session: Session, asset_ids) -> dict:
    if not asset_ids:
        return {}
    rows = session.execute(
        select(WaterAsset.id, WaterAsset.canonical_name).where(WaterAsset.id.in_(asset_ids))
    ).all()
    return {r[0]: r[1] for r in rows}


def _instruction_outs(session: Session, instructions: List[AlertInstruction]) -> List[InstructionOut]:
    alerts = {}
    if instructions:
        alert_ids = {i.alert_id for i in instructions}
        rows = session.execute(
            select(WaterOperationalAlert).where(WaterOperationalAlert.id.in_(alert_ids))
        ).scalars().all()
        alerts = {a.id: a for a in rows}
    names = _asset_names(session, [i.asset_id for i in instructions])
    out = []
    for i in instructions:
        item = InstructionOut.model_validate(i)
        item.asset_name = names.get(i.asset_id)
        alert = alerts.get(i.alert_id)
        if alert:
            item.alert_type = alert.alert_type
            item.alert_severity = alert.severity
            item.alert_status = alert.status
            item.alert_message = alert.message
        out.append(item)
    return out


def _alert_mini(alert: WaterOperationalAlert, asset_name: Optional[str]) -> AlertMini:
    breached = bool(
        alert.status == "NEW"
        and alert.sla_due_at
        and alert.sla_due_at < datetime.now(timezone.utc)
    )
    return AlertMini(
        id=alert.id,
        asset_id=alert.asset_id,
        asset_name=asset_name,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        alert_source=alert.alert_source,
        created_at=alert.created_at,
        sla_due_at=alert.sla_due_at,
        sla_breached=breached,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        escalated_to=alert.escalated_to,
        escalated_at=alert.escalated_at,
        episode_id=alert.episode_id,
        flood_probability=float(alert.flood_probability) if alert.flood_probability else None,
    )


def _require_board_role(actor: workflow.Actor) -> None:
    if not (actor.all_roles & {"admin", "water_supervisor"}):
        raise WorkflowError(
            "Requires role: admin or water_supervisor", status_code=403
        )


# ─── Queue ───────────────────────────────────────────────────────────────────

@router.get("/alerts/queue", response_model=QueueOut)
async def get_queue(
    scope: str = Query("auto", pattern="^(auto|my|team|all)$"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Role-filtered work queue (the bell/badge data source).

    scope=auto picks by role: field_officer->my, supervisor/analyst->team,
    admin->all, viewer->all (read-only in the UI).
    """
    actor = actor_from_token(user)
    roles = actor.all_roles
    if scope == "auto":
        if "admin" in roles:
            scope = "all"
        elif roles & {"water_supervisor", "aquavision_analyst"}:
            scope = "team"
        else:
            scope = "my"

    open_instr_states = ("ISSUED", "ACCEPTED", "IN_PROGRESS", "OVERDUE")

    # My actionable instructions
    my_q = select(AlertInstruction).where(
        AlertInstruction.status.in_(open_instr_states),
    )
    if scope == "my":
        my_q = my_q.where(
            or_(
                AlertInstruction.assigned_to == actor.username,
                AlertInstruction.assigned_to_user_id == actor.user_id,
            )
        )
    my_instr = session.execute(
        my_q.order_by(AlertInstruction.due_at.is_(None), AlertInstruction.due_at)
    ).scalars().all()

    # Reported instructions awaiting verification
    verify_q = select(AlertInstruction).where(AlertInstruction.status == "REPORTED")
    if scope == "my":
        verify_q = verify_q.where(
            or_(
                AlertInstruction.issued_by == actor.username,
                AlertInstruction.assigned_to == actor.username,
            )
        )
    verify_instr = session.execute(
        verify_q.order_by(AlertInstruction.reported_at)
    ).scalars().all()

    # Alerts needing acknowledgment
    new_alerts = session.execute(
        select(WaterOperationalAlert)
        .where(WaterOperationalAlert.status == "NEW")
        .order_by(
            WaterOperationalAlert.severity.desc(),
            WaterOperationalAlert.created_at,
        ).limit(100)
    ).scalars().all()

    # Escalated alerts
    escalated = session.execute(
        select(WaterOperationalAlert)
        .where(WaterOperationalAlert.status == "ESCALATED")
        .order_by(WaterOperationalAlert.escalated_at.is_(None), WaterOperationalAlert.escalated_at)
        .limit(100)
    ).scalars().all()

    alert_ids = {a.id for a in new_alerts + escalated}
    names = _asset_names(session, [a.asset_id for a in new_alerts + escalated])

    out_alerts = [_alert_mini(a, names.get(a.asset_id)) for a in new_alerts]
    out_escalated = [_alert_mini(a, names.get(a.asset_id)) for a in escalated]

    counts = {
        "instructions_my": len(my_instr),
        "instructions_to_verify": len(verify_instr),
        "alerts_new": len(out_alerts),
        "alerts_escalated": len(out_escalated),
        "alerts_sla_breached": sum(1 for a in out_alerts if a.sla_breached),
        "badge": len(my_instr) + len(verify_instr)
                 + sum(1 for a in out_alerts if a.sla_breached)
                 + len(out_escalated),
    }
    return QueueOut(
        scope=scope,
        role=actor.role,
        instructions_my=_instruction_outs(session, my_instr),
        instructions_to_verify=_instruction_outs(session, verify_instr),
        alerts_new=out_alerts,
        alerts_escalated=out_escalated,
        counts=counts,
    )


# ─── Timeline ────────────────────────────────────────────────────────────────

@router.get("/alerts/{alert_id}/timeline", response_model=List[TimelineItem])
async def get_timeline(
    alert_id: int,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Merged audit timeline: events + instruction states (append-only source)."""
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    events = session.execute(
        select(WaterAlertAuditLog)
        .where(WaterAlertAuditLog.alert_id == alert_id)
        .order_by(WaterAlertAuditLog.performed_at, WaterAlertAuditLog.id)
    ).scalars().all()
    instructions = session.execute(
        select(AlertInstruction)
        .where(AlertInstruction.alert_id == alert_id)
        .order_by(AlertInstruction.created_at, AlertInstruction.id)
    ).scalars().all()
    instr_outs = {i.id: o for i, o in zip(instructions, _instruction_outs(session, instructions))}

    items: List[TimelineItem] = []
    for e in events:
        items.append(TimelineItem(
            kind="event",
            at=e.performed_at,
            action=e.action,
            actor=e.performed_by,
            actor_role=e.actor_role,
            old_status=e.old_status,
            new_status=e.new_status,
            notes=e.notes,
            instruction_id=e.instruction_id,
            payload=e.payload,
            instruction=instr_outs.get(e.instruction_id) if e.instruction_id else None,
        ))
    for i in instructions:
        # Represent the instruction's CURRENT state as a timeline node too
        # (events already carry transitions; this node carries the full object).
        items.append(TimelineItem(
            kind="instruction",
            at=i.created_at,
            action="INSTRUCTION_CREATED",
            actor=i.issued_by,
            actor_role=i.issued_role,
            notes=i.instruction_text,
            instruction_id=i.id,
            instruction=instr_outs.get(i.id),
        ))
    items.sort(key=lambda x: (x.at, x.kind))
    return items


# ─── Escalations board ───────────────────────────────────────────────────────

@router.get("/alerts/escalations", response_model=dict)
async def get_escalations(
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Admin/supervisor board: ESCALATED alerts, SLA breaches, overdue work."""
    actor = actor_from_token(user)
    _require_board_role(actor)

    now = datetime.now(timezone.utc)
    escalated = session.execute(
        select(WaterOperationalAlert)
        .where(WaterOperationalAlert.status == "ESCALATED")
        .order_by(WaterOperationalAlert.escalated_at)
    ).scalars().all()
    breached = session.execute(
        select(WaterOperationalAlert)
        .where(
            WaterOperationalAlert.status == "NEW",
            WaterOperationalAlert.sla_due_at.isnot(None),
            WaterOperationalAlert.sla_due_at < now,
        )
        .order_by(WaterOperationalAlert.sla_due_at)
    ).scalars().all()
    overdue = session.execute(
        select(AlertInstruction)
        .where(AlertInstruction.status == "OVERDUE")
        .order_by(AlertInstruction.due_at)
    ).scalars().all()

    names = _asset_names(
        session,
        [a.asset_id for a in escalated + breached],
    )
    return {
        "escalated": [_alert_mini(a, names.get(a.asset_id)) for a in escalated],
        "sla_breached": [_alert_mini(a, names.get(a.asset_id)) for a in breached],
        "instructions_overdue": _instruction_outs(session, overdue),
        "counts": {
            "escalated": len(escalated),
            "sla_breached": len(breached),
            "instructions_overdue": len(overdue),
        },
    }


# ─── KPIs ────────────────────────────────────────────────────────────────────

@router.get("/alerts/kpis", response_model=dict)
async def get_kpis(
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Workflow health for the admin board."""
    actor = actor_from_token(user)
    _require_board_role(actor)
    return workflow.compute_kpis(session)


# ─── Templates / assignables ─────────────────────────────────────────────────

@router.get("/alerts/instruction-templates", response_model=dict)
async def get_instruction_templates(user: dict = Depends(get_current_user)):
    return INSTRUCTION_TEMPLATES


@router.get("/workflow/assignables", response_model=List[AssignableOut])
async def list_assignables(
    role: str = Query("field_officer"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Active users holding the given role (assignee picker)."""
    from infrastructure.db.models import Role as RoleModel, User as UserModel, UserRole as UserRoleModel
    rows = session.execute(
        select(UserModel, RoleModel.name)
        .join(UserRoleModel, UserRoleModel.user_id == UserModel.id)
        .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
        .where(
            RoleModel.name == role,
            UserModel.is_active.is_(True),
            UserModel.access_status == "ACTIVE",
        )
        .order_by(UserModel.name)
    ).all()
    return [
        AssignableOut(
            id=u.id, name=u.name, email=u.email,
            username=(u.email.split("@")[0] if "@" in (u.email or "") else u.name),
            role=rname,
        )
        for u, rname in rows
    ]


# ─── Alert actions ───────────────────────────────────────────────────────────

@router.post("/alerts/{alert_id}/assign", response_model=AlertMini)
async def assign(
    alert_id: int,
    payload: AssignInput,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    actor = actor_from_token(user)
    workflow.assign_alert(
        session, alert, actor,
        assigned_to=payload.assigned_to,
        assigned_to_user_id=payload.assigned_to_user_id,
    )
    return _alert_mini(alert, _asset_names(session, [alert.asset_id]).get(alert.asset_id))


@router.post("/alerts/{alert_id}/instructions", response_model=InstructionOut)
async def issue_instruction(
    alert_id: int,
    payload: IssueInstructionInput,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """UC-1 step 2: supervisor/admin issues an instruction on an alert."""
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    actor = actor_from_token(user)
    if payload.template_key and payload.template_key not in INSTRUCTION_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template '{payload.template_key}'")
    if payload.due_at and payload.due_at.tzinfo is None:
        payload.due_at = payload.due_at.replace(tzinfo=timezone.utc)
    instr = workflow.issue_instruction(
        session, alert, actor,
        instruction_text=payload.instruction_text,
        assigned_to=payload.assigned_to,
        assigned_to_user_id=payload.assigned_to_user_id,
        due_at=payload.due_at,
        template_key=payload.template_key,
    )
    outs = _instruction_outs(session, [instr])
    return outs[0]


# ─── Instruction actions ─────────────────────────────────────────────────────

def _load_instruction(instruction_id: int, session: Session) -> AlertInstruction:
    instr = session.get(AlertInstruction, instruction_id)
    if not instr:
        raise HTTPException(status_code=404, detail="Instruction not found")
    return instr


@router.post("/instructions/{instruction_id}/accept", response_model=InstructionOut)
async def accept(
    instruction_id: int,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    instr = _load_instruction(instruction_id, session)
    workflow.accept_instruction(session, instruction_id, actor_from_token(user))
    session.expire_all()
    return _instruction_outs(session, [_load_instruction(instruction_id, session)])[0]


@router.post("/instructions/{instruction_id}/progress", response_model=InstructionOut)
async def progress(
    instruction_id: int,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    instr = _load_instruction(instruction_id, session)
    workflow.progress_instruction(session, instruction_id, actor_from_token(user))
    session.expire_all()
    return _instruction_outs(session, [_load_instruction(instruction_id, session)])[0]


@router.post("/instructions/{instruction_id}/report", response_model=InstructionOut)
async def report(
    instruction_id: int,
    payload: ReportInput,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """UC-1 step 3: field officer submits the action report."""
    _load_instruction(instruction_id, session)
    workflow.report_instruction(
        session, instruction_id, actor_from_token(user),
        report_text=payload.report_text,
        report_data=payload.report_data,
    )
    session.expire_all()
    return _instruction_outs(session, [_load_instruction(instruction_id, session)])[0]


@router.post("/instructions/{instruction_id}/verify", response_model=InstructionOut)
async def verify(
    instruction_id: int,
    payload: NoteInput,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """UC-1 step 4: supervisor verifies the report (may auto-resolve alert)."""
    _load_instruction(instruction_id, session)
    workflow.verify_instruction(
        session, instruction_id, actor_from_token(user), note=payload.note
    )
    session.expire_all()
    return _instruction_outs(session, [_load_instruction(instruction_id, session)])[0]


@router.post("/instructions/{instruction_id}/reject", response_model=InstructionOut)
async def reject(
    instruction_id: int,
    payload: NoteInput,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _load_instruction(instruction_id, session)
    workflow.reject_instruction(
        session, instruction_id, actor_from_token(user), reason=payload.note
    )
    session.expire_all()
    return _instruction_outs(session, [_load_instruction(instruction_id, session)])[0]


@router.post("/instructions/{instruction_id}/waive", response_model=InstructionOut)
async def waive(
    instruction_id: int,
    payload: NoteInput,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _load_instruction(instruction_id, session)
    workflow.waive_instruction(
        session, instruction_id, actor_from_token(user), reason=payload.note
    )
    session.expire_all()
    return _instruction_outs(session, [_load_instruction(instruction_id, session)])[0]


# ─── Test notification (admin) ───────────────────────────────────────────────

@router.post("/alerts/test", response_model=TestAlertOut)
async def send_test_alert(
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Admin: create a TEST alert and dispatch through the real pipeline,
    proving SMTP/Slack are configured (nice-to-have #8)."""
    actor = actor_from_token(user)
    workflow.authorize(actor, "create_test")

    asset = session.execute(
        select(WaterAsset)
        .where(WaterAsset.is_active.is_(True))
        .order_by(WaterAsset.id)
        .limit(1)
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=409, detail="No active assets available")

    # Unique-open index: close any previous open TEST alert for this asset
    previous = session.execute(
        select(WaterOperationalAlert).where(
            WaterOperationalAlert.asset_id == asset.id,
            WaterOperationalAlert.alert_type == "TEST",
            WaterOperationalAlert.status.in_(OPEN_STATUSES),
        )
    ).scalars().all()
    for p in previous:
        p.status = "RESOLVED"
        p.resolved_by = "SYSTEM"
        p.resolved_at = datetime.now(timezone.utc)
        p.resolution = "Superseded by a newer test alert"
        workflow.log_event(
            session, alert_id=p.id, action="RESOLVED",
            performed_by="SYSTEM", actor_role="SYSTEM",
            old_status="NEW", new_status="RESOLVED",
            notes="Superseded by a newer test alert",
        )

    alert = WaterOperationalAlert(
        asset_id=asset.id,
        alert_type="TEST",
        severity="WATCH",
        message=f"Test notification requested by {actor.username}",
        status="NEW",
        alert_source="TEST",
        alert_domain="OPERATIONAL",
    )
    session.add(alert)
    session.flush()
    workflow.log_event(
        session, alert_id=alert.id, action="CREATED",
        performed_by=actor.username, actor_role=actor.role,
        old_status=None, new_status="NEW",
        notes=alert.message, payload={"test": True},
    )

    recipients = workflow.role_emails(session, ["admin", "water_supervisor"])
    dispatch = workflow.notify(
        session,
        notification_type="TEST",
        severity="WATCH",
        title="AquaVision test notification",
        message=alert.message,
        recipients=recipients,
        asset_id=asset.id,
        asset_name=asset.canonical_name,
        details={"test": True, "requested_by": actor.username},
        nonce=uuid4().hex[:8],
    )
    session.commit()
    return TestAlertOut(
        alert_id=alert.id,
        channels_configured=dispatch is not None,
        dispatch=dispatch,
        recipients=recipients,
    )
