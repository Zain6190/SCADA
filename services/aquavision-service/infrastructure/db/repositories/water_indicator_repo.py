# infrastructure/db/repositories/water_indicator_repo.py
from datetime import date
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.db import models as orm


class WaterIndicatorRepository:
    def __init__(self, session: Session):
        self._db = session

    def get_latest_week(self) -> Optional[date]:
        return self._db.execute(
            select(func.max(orm.WaterIndicator.week_start_date))
        ).scalar()

    def list_by_week(self, week_start_date: date) -> List[orm.WaterIndicator]:
        return list(
            self._db.execute(
                select(orm.WaterIndicator).where(
                    orm.WaterIndicator.week_start_date == week_start_date
                )
            ).scalars()
        )

    def list(
        self,
        region_id: Optional[int] = None,
        severity: Optional[str] = None,
        week_start_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[orm.WaterIndicator]:
        q = select(orm.WaterIndicator)
        if region_id is not None:
            q = q.where(orm.WaterIndicator.region_id == region_id)
        if severity:
            q = q.where(orm.WaterIndicator.severity == severity)
        if week_start_date:
            q = q.where(orm.WaterIndicator.week_start_date == week_start_date)
        q = q.order_by(
            orm.WaterIndicator.week_start_date.desc(), orm.WaterIndicator.region_id.asc()
        ).limit(limit)
        return list(self._db.execute(q).scalars())

    def count(self) -> int:
        return int(
            self._db.execute(select(func.count()).select_from(orm.WaterIndicator)).scalar() or 0
        )

    def upsert(self, region_id: int, week_start_date: date, **fields) -> orm.WaterIndicator:
        row = self._db.execute(
            select(orm.WaterIndicator).where(
                orm.WaterIndicator.region_id == region_id,
                orm.WaterIndicator.week_start_date == week_start_date,
            )
        ).scalar_one_or_none()

        if row is None:
            iso = week_start_date.isocalendar()
            row = orm.WaterIndicator(
                region_id=region_id,
                week_start_date=week_start_date,
                week_number=iso[1],
                year=iso[0],
            )
            self._db.add(row)

        for key, value in fields.items():
            setattr(row, key, value)
        self._db.commit()
        self._db.refresh(row)
        return row
