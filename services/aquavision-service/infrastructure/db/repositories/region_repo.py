# infrastructure/db/repositories/region_repo.py
# READ-ONLY access to shared.regions and shared.assets.
# This service must NEVER write to these tables.
import json
from typing import Dict, List, Optional

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db import models as orm


class RegionRepository:
    def __init__(self, session: Session):
        self._db = session

    def list(self, region_type: Optional[str] = None) -> List[orm.Region]:
        q = select(orm.Region)
        if region_type:
            q = q.where(orm.Region.type == region_type)
        q = q.order_by(orm.Region.id)
        return list(self._db.execute(q).scalars())

    def get(self, region_id: int) -> Optional[orm.Region]:
        return self._db.get(orm.Region, region_id)

    def geometry_map(self, region_type: Optional[str] = None) -> Dict[int, dict]:
        """region_id -> GeoJSON geometry (SRID 4326)."""
        q = select(orm.Region.id, ST_AsGeoJSON(orm.Region.geom))
        if region_type:
            q = q.where(orm.Region.type == region_type)
        result = {}
        for region_id, geojson in self._db.execute(q):
            result[region_id] = json.loads(geojson)
        return result

    def assets_by_type(self, asset_type: str) -> List[orm.Asset]:
        q = select(orm.Asset).where(
            orm.Asset.asset_type == asset_type, orm.Asset.is_active.is_(True)
        )
        return list(self._db.execute(q).scalars())
