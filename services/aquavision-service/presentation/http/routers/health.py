# presentation/http/routers/health.py
from fastapi import APIRouter

router = APIRouter(tags=["Service"])


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "aquavision-service"}
