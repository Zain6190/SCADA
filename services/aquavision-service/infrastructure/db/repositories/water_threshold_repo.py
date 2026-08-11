# infrastructure/db/repositories/water_threshold_repo.py
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db import models as orm


class WaterThresholdRepository:
    def __init__(self, session: Session):
        self._db = session

    def list(self) -> List[orm.WaterThreshold]:
        return list(self._db.execute(select(orm.WaterThreshold)).scalars())

    def get_by_name(self, threshold_name: str) -> Optional[orm.WaterThreshold]:
        return self._db.execute(
            select(orm.WaterThreshold).where(
                orm.WaterThreshold.threshold_name == threshold_name
            )
        ).scalar_one_or_none()

    def update(self, threshold_name: str, value: float) -> Optional[orm.WaterThreshold]:
        row = self.get_by_name(threshold_name)
        if row is None:
            return None
        row.value = value
        row.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(row)
        return row
