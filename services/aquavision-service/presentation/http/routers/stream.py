# presentation/http/routers/stream.py
# Server-Sent Events: DB change detection that pushes flood-map refresh hints.
import asyncio
import logging
import time
from typing import Dict, Optional, Set

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from infrastructure.db.engine import engine

logger = logging.getLogger("aquavision.api.stream")

router = APIRouter(tags=["Live"])

TICK_SECONDS = 2.0
PING_SECONDS = 15.0
MIN_EMIT_GAP_SECONDS = 1.0

SIGNALS: Dict[str, str] = {
    "observations": (
        "SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
        "FROM aquavision.water_observations"
    ),
    "alerts": (
        "SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
        "|| '|' || coalesce(max(acknowledged_at)::text, '-') "
        "FROM aquavision.water_operational_alerts"
    ),
    "ot_commands": (
        "SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
        "FROM aquavision.water_ot_commands"
    ),
    "ffd": (
        "SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
        "FROM aquavision.water_ffd_observations"
    ),
}

COMBINED_SQL = (
    "SELECT "
    "(SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
    " FROM aquavision.water_observations), "
    "(SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
    " || '|' || coalesce(max(acknowledged_at)::text, '-') "
    " FROM aquavision.water_operational_alerts), "
    "(SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
    " FROM aquavision.water_ot_commands), "
    "(SELECT count(*)::text || '|' || coalesce(max(created_at)::text, '-') "
    " FROM aquavision.water_ffd_observations)"
)

SIGNAL_EVENTS: Dict[str, tuple] = {
    "observations": ("overview", "territory"),
    "alerts": ("overview",),
    "ot_commands": ("territory",),
    "ffd": ("overview",),
}

EVENT_KINDS = ("overview", "territory")


def read_signals() -> Dict[str, Optional[str]]:
    """Read all change signals in one roundtrip (SIGNALS column order).

    Four separate per-tick queries took 4-8s (pool checkout waits behind the
    OT tick / ingestion sessions); a single combined statement keeps a tick
    near one network roundtrip. Falls back to per-signal reads when the
    combined statement fails, so one missing table cannot silence the rest.

    None means "no value" (table missing / transient error). None == None does
    not diff, so a persistently broken signal stays silent instead of firing
    events on every tick, and a recovered signal fires once.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(text(COMBINED_SQL)).first()
        if row is not None and len(row) == len(SIGNALS):
            return {
                name: (str(value) if value is not None else None)
                for name, value in zip(SIGNALS.keys(), row)
            }
    except Exception as exc:
        logger.debug("combined signal read failed, falling back: %s", exc)

    out: Dict[str, Optional[str]] = {}
    for name, sql in SIGNALS.items():
        try:
            with engine.connect() as conn:
                row = conn.execute(text(sql)).first()
                out[name] = str(row[0]) if row is not None else None
        except Exception as exc:
            logger.debug("stream signal %s unreadable: %s", name, exc)
            out[name] = None
    return out


def changed_events(
    prev: Dict[str, Optional[str]], curr: Dict[str, Optional[str]]
) -> Set[str]:
    """Map changed signals to the React Query keys the client should refetch."""
    events: Set[str] = set()
    for name, kinds in SIGNAL_EVENTS.items():
        if curr.get(name) != prev.get(name):
            events.update(kinds)
    return events


async def event_stream():
    yield "retry: 3000\n\n"
    baseline = await asyncio.to_thread(read_signals)
    last_emit = {kind: 0.0 for kind in EVENT_KINDS}
    pending: Set[str] = set()
    last_ping = time.monotonic()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            current = await asyncio.to_thread(read_signals)
        except Exception as exc:
            logger.warning("stream tick failed: %s", exc)
            continue
        pending.update(changed_events(baseline, current))
        baseline = current
        now = time.monotonic()
        for kind in sorted(pending):
            if now - last_emit[kind] >= MIN_EMIT_GAP_SECONDS:
                yield f"event: {kind}\ndata: {{}}\n\n"
                last_emit[kind] = now
                pending.discard(kind)
        if now - last_ping >= PING_SECONDS:
            yield ": ping\n\n"
            last_ping = now


@router.get("/stream")
async def stream_events():
    """Push refresh hints when flood-map inputs change (DB change detection).

    The client keeps its 30s polling fallback; SSE only makes repaints arrive
    in ~2-3s instead of up to 30s.
    """
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
