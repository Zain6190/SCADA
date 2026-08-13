# packages/backend/app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn

from app.core.config import settings

settings.validate_security()

# Rate limiter — in-memory, keyed by client IP.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(
    title="IBCP-SCADA API",
    description="Indus Basin Cyber-Physical SCADA System",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS allowlist from environment (comma-separated CORS_ORIGINS).
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "IBCP-SCADA API",
        "version": "1.0.0",
        "status": "operational"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Import and include routers
from app.api.v1.api import api_router
app.include_router(api_router, prefix="/api/v1")

# Seed sample water data into PostgreSQL if empty (idempotent)
from app.services.water_service import seed_if_empty
seed_if_empty()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)