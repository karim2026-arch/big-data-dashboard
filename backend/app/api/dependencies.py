"""Wiring: the only place that chooses which repository each service gets (Snowflake today).
Routes receive services through Depends(), so they never build them or know about Snowflake."""
from ..infrastructure.repositories.snowflake_kpi_repository import SnowflakeKpiRepository
from ..infrastructure.repositories.snowflake_system_repository import SnowflakeSystemRepository
from ..services.kpi_validation_service import KpiValidationService
from ..services.system_service import SystemService


def get_system_service() -> SystemService:
    return SystemService(SnowflakeSystemRepository())


def get_kpi_validation_service() -> KpiValidationService:
    return KpiValidationService(SnowflakeKpiRepository())
