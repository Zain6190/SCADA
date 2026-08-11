# packages/backend/app/api/v1/api.py
from fastapi import APIRouter
from .endpoints import auth, geovision, flood, soil, water

api_router = APIRouter()


@api_router.get("/health", tags=["System"])
async def health():
    return {"status": "healthy"}


api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(geovision.router, prefix="/geovision", tags=["GeoVision"])
api_router.include_router(flood.router, prefix="/flood", tags=["Flood SCADA"])
api_router.include_router(soil.router, prefix="/soil", tags=["Soil Monitoring"])
api_router.include_router(water.router, prefix="/water", tags=["AquaVision"])