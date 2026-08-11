# infrastructure/db/repositories/water_prediction_repo.py
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db import models as orm


class WaterPredictionRepository:
    def __init__(self, session: Session):
        self._db = session

    def list(self, region_id: Optional[int] = None) -> List[orm.WaterPrediction]:
        q = select(orm.WaterPrediction)
        if region_id is not None:
            q = q.where(orm.WaterPrediction.region_id == region_id)
        q = q.order_by(orm.WaterPrediction.target_week_start_date.desc())
        return list(self._db.execute(q).scalars())

    def upsert(
        self,
        region_id: int,
        target_week_start_date,
        model_version: str,
        **fields,
    ) -> orm.WaterPrediction:
        row = self._db.execute(
            select(orm.WaterPrediction).where(
                orm.WaterPrediction.region_id == region_id,
                orm.WaterPrediction.target_week_start_date == target_week_start_date,
                orm.WaterPrediction.model_version == model_version,
            )
        ).scalar_one_or_none()

        if row is None:
            row = orm.WaterPrediction(
                region_id=region_id,
                target_week_start_date=target_week_start_date,
                model_version=model_version,
            )
            self._db.add(row)

        for key, value in fields.items():
            setattr(row, key, value)
        self._db.commit()
        self._db.refresh(row)
        return row
