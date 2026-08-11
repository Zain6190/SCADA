# application/use_cases/get_regions.py
from typing import List, Optional

from application.dtos import RegionResponse
from infrastructure.db.repositories.region_repo import RegionRepository


class GetRegionsUseCase:
    def __init__(self, region_repo: RegionRepository):
        self._regions = region_repo

    def execute(self, region_type: Optional[str] = None) -> List[RegionResponse]:
        rows = self._regions.list(region_type=region_type)
        return [
            RegionResponse(
                id=r.id,
                name=r.name,
                code=r.code,
                type=r.type,
                parent_region_id=r.parent_region_id,
            )
            for r in rows
        ]
