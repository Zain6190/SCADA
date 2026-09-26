# Soft PLC interlocks — pure functions, no I/O.
# Fail-safe: freeze or restrict motion; never slam gates.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

MAX_SLEW_PCT_PER_HOUR = 30.0
DIVERGENCE_PCT = 8.0
DEFAULT_RISE_CRITICAL_FT_PER_6H = 1.0
MIN_GATE_WHEN_RISING = 15.0


@dataclass
class InterlockDecision:
    effective_cmd: float
    freeze: bool
    fault: bool
    reasons: List[str] = field(default_factory=list)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def decide_interlocks(
    requested_cmd: float,
    gate_pos: float,
    local_level: float,
    prev_level: float,
    dt_hours: float,
    downstream_critical: bool,
    rise_critical_ft_per_6h: float = DEFAULT_RISE_CRITICAL_FT_PER_6H,
    min_gate_when_rising: float = MIN_GATE_WHEN_RISING,
    jammed: bool = False,
    comms_down: bool = False,
) -> InterlockDecision:
    """Apply fail-safe gate interlocks.

    - Comms loss or jam: hold last position.
    - Downstream critical: do not open further.
    - Local rapid rise: do not close below a minimum opening.
    """
    reasons: List[str] = []
    cmd = _clamp(requested_cmd)
    pos = _clamp(gate_pos)
    freeze = False
    fault = False

    if comms_down:
        reasons.append("comms_loss_hold_last_output")
        freeze = True
        cmd = pos

    if jammed:
        reasons.append("actuator_jam")
        freeze = True
        fault = True
        cmd = pos
        if abs(requested_cmd - pos) > DIVERGENCE_PCT:
            reasons.append("command_feedback_divergence")

    if downstream_critical and not freeze:
        if cmd > pos:
            reasons.append("downstream_critical_no_further_open")
            cmd = pos

    if dt_hours > 0 and not freeze:
        rise_per_6h = (local_level - prev_level) / dt_hours * 6.0
        if rise_per_6h >= rise_critical_ft_per_6h and cmd < min_gate_when_rising:
            reasons.append("rapid_rise_hold_minimum_opening")
            cmd = min_gate_when_rising

    return InterlockDecision(
        effective_cmd=_clamp(cmd),
        freeze=freeze,
        fault=fault,
        reasons=reasons,
    )


def slew_gate(
    position_pct: float,
    command_pct: float,
    dt_hours: float,
    jammed: bool = False,
    max_slew_pct_per_hour: float = MAX_SLEW_PCT_PER_HOUR,
) -> float:
    """Move gate position toward command at a bounded rate."""
    pos = _clamp(position_pct)
    cmd = _clamp(command_pct)
    if jammed or dt_hours <= 0:
        return pos
    max_delta = max_slew_pct_per_hour * dt_hours
    delta = max(-max_delta, min(max_delta, cmd - pos))
    return _clamp(pos + delta)


def _head_factor(level_ft: float, dead_level_ft: float, normal_level_ft: float) -> float:
    head = max(0.0, level_ft - dead_level_ft)
    span = max(1.0, normal_level_ft - dead_level_ft)
    return min(1.5, head / span)


def outflow_from_gate(
    gate_pct: float,
    level_ft: float,
    dead_level_ft: float,
    normal_level_ft: float,
    max_outflow_cusecs: float,
) -> float:
    """Piecewise-linear rating: outflow scales with opening and head."""
    opening = _clamp(gate_pct) / 100.0
    return max(0.0, max_outflow_cusecs * opening * _head_factor(level_ft, dead_level_ft, normal_level_ft))


def gate_from_outflow(
    outflow_cusecs: float,
    level_ft: float,
    dead_level_ft: float,
    normal_level_ft: float,
    max_outflow_cusecs: float,
) -> float:
    """Invert the rating curve so a Soft PLC gate roughly matches official outflow."""
    denom = max_outflow_cusecs * _head_factor(level_ft, dead_level_ft, normal_level_ft)
    if denom <= 1e-9:
        return 0.0
    return _clamp(100.0 * max(0.0, outflow_cusecs) / denom)
