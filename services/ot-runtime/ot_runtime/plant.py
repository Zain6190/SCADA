# Virtual plant hydrology: dS/dt = inflow - outflow, plus travel-time routing.
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from ot_runtime.catalog import DEVICE_BY_ASSET, DEVICE_CATALOG, TRAVEL_HOURS
from ot_runtime.interlocks import outflow_from_gate


@dataclass
class TankState:
    asset_id: int
    level_ft: float
    inflow_cusecs: float
    outflow_cusecs: float
    discharge_cusecs: float
    gate_pct: float
    surge_cusecs: float = 0.0
    local_inflow_cusecs: float = 0.0


class VirtualPlant:
    """In-memory Indus-style tank / channel network. Not official hydrology."""

    def __init__(self, sim_minutes: float = 15.0) -> None:
        self.sim_minutes = sim_minutes
        self.tanks: Dict[int, TankState] = {}
        # delay lines: (upstream, downstream) -> deque of discharge samples
        self._routes: List[Tuple[int, int, Deque[float]]] = []
        self._init_tanks()
        self._init_routes()

    def _init_tanks(self) -> None:
        for spec in DEVICE_CATALOG:
            outflow = spec.base_inflow_cusecs * 0.95
            self.tanks[spec.asset_id] = TankState(
                asset_id=spec.asset_id,
                level_ft=spec.normal_level_ft * 0.97 if spec.normal_level_ft else 10.0,
                inflow_cusecs=spec.base_inflow_cusecs,
                outflow_cusecs=outflow,
                discharge_cusecs=outflow,
                gate_pct=spec.default_gate_pct,
                local_inflow_cusecs=spec.base_inflow_cusecs,
            )

    def _init_routes(self) -> None:
        dt_hours = self.sim_minutes / 60.0
        for up, down, hours in TRAVEL_HOURS:
            n = max(1, int(round(hours / dt_hours)))
            seed = self.tanks[up].discharge_cusecs
            self._routes.append((up, down, deque([seed] * n, maxlen=n)))

    def seed_levels(self, levels: Dict[int, float]) -> None:
        for asset_id, level in levels.items():
            if asset_id in self.tanks:
                self.tanks[asset_id].level_ft = float(level)

    def _reseed_routes(self) -> None:
        """Rebuild travel-time queues from current upstream discharge (drop yesterday's invented queue)."""
        self._routes.clear()
        self._init_routes()

    def apply_anchor(self, states: Dict[int, Dict[str, float]]) -> None:
        """Seed tanks from official IRSA/FFD values. Null fields keep the previous plant value."""
        for raw_id, patch in states.items():
            asset_id = int(raw_id)
            tank = self.tanks.get(asset_id)
            if not tank or not patch:
                continue
            level = patch.get("level_ft")
            inflow = patch.get("inflow_cusecs")
            outflow = patch.get("outflow_cusecs")
            discharge = patch.get("discharge_cusecs")
            gate_pct = patch.get("gate_pct")
            if level is not None:
                tank.level_ft = float(level)
            if inflow is not None:
                tank.inflow_cusecs = float(inflow)
                tank.local_inflow_cusecs = tank.inflow_cusecs
            if outflow is not None:
                tank.outflow_cusecs = float(outflow)
            if discharge is not None:
                tank.discharge_cusecs = float(discharge)
            elif outflow is not None:
                tank.discharge_cusecs = tank.outflow_cusecs
            elif inflow is not None:
                tank.discharge_cusecs = tank.inflow_cusecs
            if inflow is None and tank.discharge_cusecs and patch.get("discharge_cusecs") is not None:
                tank.inflow_cusecs = tank.discharge_cusecs
                tank.local_inflow_cusecs = tank.discharge_cusecs
            if outflow is None and patch.get("discharge_cusecs") is not None:
                tank.outflow_cusecs = tank.discharge_cusecs
            if gate_pct is not None:
                tank.gate_pct = max(0.0, min(100.0, float(gate_pct)))
        self._reseed_routes()

    def set_gate(self, asset_id: int, gate_pct: float) -> None:
        if asset_id in self.tanks:
            self.tanks[asset_id].gate_pct = max(0.0, min(100.0, gate_pct))

    def add_surge(self, asset_id: int, extra_cusecs: float) -> None:
        if asset_id in self.tanks:
            self.tanks[asset_id].surge_cusecs += extra_cusecs

    def seed_route_history(self, upstream_history: Dict[int, List[float]]) -> None:
        """Fill travel-time queues from real upstream discharge, oldest first."""
        for up, _down, buf in self._routes:
            hist = [float(v) for v in upstream_history.get(up, []) if v is not None]
            if not hist:
                continue
            fill = hist[-buf.maxlen :]
            while len(fill) < buf.maxlen:
                fill.insert(0, fill[0])
            buf.clear()
            for value in fill:
                buf.append(value)

    def step(self, plc_gates: Optional[Dict[int, float]] = None) -> Dict[int, Dict[str, float]]:
        """Advance one simulated interval. Returns per-asset AI dicts."""
        dt_hours = self.sim_minutes / 60.0
        plc_gates = plc_gates or {}

        routed_in: Dict[int, float] = {aid: 0.0 for aid in self.tanks}
        for up, down, buf in self._routes:
            arriving = buf[0] if buf else 0.0
            routed_in[down] = routed_in.get(down, 0.0) + arriving

        for spec in DEVICE_CATALOG:
            tank = self.tanks[spec.asset_id]
            if spec.asset_id in plc_gates:
                tank.gate_pct = plc_gates[spec.asset_id]

            local = tank.local_inflow_cusecs + tank.surge_cusecs
            tank.surge_cusecs *= 0.85  # decay injected surge
            upstream = routed_in.get(spec.asset_id, 0.0)
            # Reservoirs / gauges keep a local catchment; barrages are mostly routed.
            if spec.kind == "RTU" and spec.asset_id in (1, 2, 9, 10, 11):
                tank.inflow_cusecs = local + 0.15 * upstream
            else:
                tank.inflow_cusecs = 0.25 * local + 0.75 * upstream if upstream else local

            if spec.kind == "PLC":
                tank.outflow_cusecs = outflow_from_gate(
                    tank.gate_pct,
                    tank.level_ft,
                    spec.dead_level_ft,
                    spec.normal_level_ft,
                    spec.max_outflow_cusecs,
                )
            else:
                # RTU sites release near inflow with a mild level bias
                bias = (tank.level_ft - spec.dead_level_ft) / max(
                    1.0, spec.normal_level_ft - spec.dead_level_ft
                )
                tank.outflow_cusecs = max(0.0, tank.inflow_cusecs * (0.85 + 0.2 * min(1.2, bias)))

            tank.discharge_cusecs = tank.outflow_cusecs
            tank.level_ft += (tank.inflow_cusecs - tank.outflow_cusecs) * dt_hours * spec.level_k
            lo = spec.dead_level_ft
            hi = (spec.critical_level_ft or spec.normal_level_ft) * 1.02
            tank.level_ft = max(lo, min(hi, tank.level_ft))

        for up, down, buf in self._routes:
            buf.append(self.tanks[up].discharge_cusecs)

        return {aid: self.as_ai(aid) for aid in self.tanks}

    def as_ai(self, asset_id: int) -> Dict[str, float]:
        tank = self.tanks[asset_id]
        return {
            "level_ft": round(tank.level_ft, 3),
            "inflow_cusecs": round(tank.inflow_cusecs, 1),
            "outflow_cusecs": round(tank.outflow_cusecs, 1),
            "discharge_cusecs": round(tank.discharge_cusecs, 1),
        }

    def is_critical(self, asset_id: int) -> bool:
        spec = DEVICE_BY_ASSET.get(asset_id)
        tank = self.tanks.get(asset_id)
        if not spec or not tank or spec.critical_level_ft is None:
            return False
        return tank.level_ft >= spec.critical_level_ft
