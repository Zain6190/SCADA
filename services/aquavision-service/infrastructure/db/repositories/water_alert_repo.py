# infrastructure/db/repositories/water_alert_repo.py
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.db import models as orm


class WaterAlertRepository:
    def __init__(self, session: Session):
        self._db = session

    def list(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        region_id: Optional[int] = None,
    ) -> List[orm.WaterAlert]:
        q = select(orm.WaterAlert)
        if status:
            q = q.where(orm.WaterAlert.status == status)
        if severity:
            q = q.where(orm.WaterAlert.severity == severity)
        if region_id is not None:
            q = q.where(orm.WaterAlert.region_id == region_id)
        q = q.order_by(orm.WaterAlert.created_at.desc())
        return list(self._db.execute(q).scalars())

    def get(self, alert_id: int) -> Optional[orm.WaterAlert]:
        return self._db.get(orm.WaterAlert, alert_id)

    def count_by_status(self, status: str) -> int:
        return int(
            self._db.execute(
                select(func.count())
                .select_from(orm.WaterAlert)
                .where(orm.WaterAlert.status == status)
            ).scalar() or 0
        )

    def persist_status(self, alert: orm.WaterAlert, new_status: str) -> orm.WaterAlert:
        alert.status = new_status
        now = datetime.now(timezone.utc)
        if new_status == "Acknowledged":
            alert.acknowledged_at = alert.acknowledged_at or now
        elif new_status == "Resolved":
            alert.resolved_at = alert.resolved_at or now
        self._db.commit()
        self._db.refresh(alert)
        return alert

