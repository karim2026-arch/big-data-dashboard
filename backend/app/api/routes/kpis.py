from typing import Annotated

from fastapi import APIRouter, Depends

from ...schemas.kpi_validation import KpiValidation
from ...services.kpi_validation_service import KpiValidationService
from ..dependencies import get_kpi_validation_service

router = APIRouter(prefix="/kpis", tags=["kpis"])


@router.get("/validation", response_model=list[KpiValidation])
def kpis_validation(service: Annotated[KpiValidationService, Depends(get_kpi_validation_service)]) -> list[dict]:
    """KPI 9 and KPI 28 over all mart rows, each with its join checks. See app/services/kpi_validation_service.py."""
    return service.calculate_all()
