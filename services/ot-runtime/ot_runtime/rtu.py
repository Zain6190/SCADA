# Soft RTU — unmanned telemetry, 15-minute cadence, store-and-forward.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ot_runtime.catalog import DeviceSpec

STALE_AFTER_HOURS = 6.0
OFFICIAL_STALE_HOURS = 36.0


@dataclass
class RtuPacket:
    asset_id: int
    device_code: str
    observed_at: datetime
    water_level_ft: Optional[float]
    inflow_cusecs: Optional[float]
    outflow_cusecs: Optional[float]
    discharge_cusecs: Optional[float]
    quality: str
    comms_ok: bool
    power_ok: bool
    notes: str = ""


@dataclass
class SoftRTU:
    spec: DeviceSpec
    comms_down: bool = False
    sensor_stuck: bool = False
    power_fail: bool = False
    stuck_ai: Optional[Dict[str, float]] = None
    buffer: List[RtuPacket] = field(default_factory=list)

    def _quality(
        self,
        observed_at: datetime,
        now: datetime,
        official_at: Optional[datetime] = None,
    ) -> str:
        if self.sensor_stuck:
            return "SUSPECT"
        if official_at is not None:
            official = official_at if official_at.tzinfo else official_at.replace(tzinfo=timezone.utc)
            current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            official_age_h = (current - official).total_seconds() / 3600.0
            if official_age_h >= OFFICIAL_STALE_HOURS:
                return "STALE"
        age_h = (now - observed_at).total_seconds() / 3600.0
        if age_h >= STALE_AFTER_HOURS:
            return "STALE"
        return "VALID"

    def _capture(
        self,
        ai: Dict[str, float],
        now: datetime,
        official_at: Optional[datetime] = None,
    ) -> RtuPacket:
        if self.sensor_stuck:
            if self.stuck_ai is None:
                self.stuck_ai = dict(ai)
            src = self.stuck_ai
        else:
            self.stuck_ai = None
            src = ai
        return RtuPacket(
            asset_id=self.spec.asset_id,
            device_code=self.spec.device_code,
            observed_at=now,
            water_level_ft=src.get("level_ft"),
            inflow_cusecs=src.get("inflow_cusecs"),
            outflow_cusecs=src.get("outflow_cusecs"),
            discharge_cusecs=src.get("discharge_cusecs"),
            quality=self._quality(now, now, official_at),
            comms_ok=not self.comms_down,
            power_ok=not self.power_fail,
            notes=f"rtu={self.spec.device_code}",
        )

    def scan(
        self,
        ai: Dict[str, float],
        now: Optional[datetime] = None,
        official_at: Optional[datetime] = None,
    ) -> List[RtuPacket]:
        """Sample plant AI. Buffer while comms are down; flush on restore."""
        now = now or datetime.now(timezone.utc)
        packet = self._capture(ai, now, official_at)
        if self.comms_down:
            packet.comms_ok = False
            packet.quality = self._quality(packet.observed_at, now, official_at)
            self.buffer.append(packet)
            # Age already-buffered packets
            for old in self.buffer:
                old.quality = self._quality(old.observed_at, now, official_at)
            return []
        flushed = []
        for old in self.buffer:
            old.quality = self._quality(old.observed_at, now, official_at)
            old.comms_ok = True
            flushed.append(old)
        self.buffer.clear()
        flushed.append(packet)
        return flushed

    def inject_fault(self, kind: str) -> None:
        if kind == "comms_down":
            self.comms_down = True
        elif kind == "sensor_stuck":
            self.sensor_stuck = True
        elif kind == "power_fail":
            self.power_fail = True
        else:
            raise ValueError(f"Unknown RTU fault '{kind}'")

    def clear_faults(self) -> None:
        self.comms_down = False
        self.sensor_stuck = False
        self.power_fail = False
        self.stuck_ai = None
