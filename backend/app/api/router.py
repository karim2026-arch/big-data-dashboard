"""All routes in one router. /health stays at the root; data endpoints live under /api."""
from fastapi import APIRouter

from .routes import health, kpis, tables

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tables.router, prefix="/api")
api_router.include_router(kpis.router, prefix="/api")
