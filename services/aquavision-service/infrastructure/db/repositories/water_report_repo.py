# infrastructure/db/repositories/water_report_repo.py
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db import models as orm


class WaterReportRepository:
    def __init__(self, session: Session):
        self._db = session

    def list(self, scope: Optional[str] = None) -> List[orm.WaterReport]:
        q = select(orm.WaterReport)
        if scope:
            q = q.where(orm.WaterReport.scope == scope)
        q = q.order_by(orm.WaterReport.week_start_date.desc())
        return list(self._db.execute(q).scalars())

    def create(
        self,
        week_start_date: date,
        title: str,
        scope: str,
        region_id: Optional[int] = None,
        file_path: Optional[str] = None,
        generated_by_user_id: Optional[int] = None,
        status: str = "Success",
    ) -> orm.WaterReport:
        row = orm.WaterReport(
            week_start_date=week_start_date,
            title=title,
            scope=scope,
            region_id=region_id,
            file_path=file_path,
            generated_by_user_id=generated_by_user_id,
            status=status,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row
