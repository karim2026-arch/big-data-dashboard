"""Response shape of GET /api/kpis/validation: one item per KPI, picked by kpi_id.
Upper-case names are the KPI query's columns, as Snowflake returns them. Units: counts are rows, *_USD is USD."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class KpiValidationBase(BaseModel):
    kpi_id: int
    name: str
    unit: str


class DistanceVarianceValidation(KpiValidationBase):
    """KPI 9, query infrastructure/queries/kpis/distance_variance.sql"""
    kpi_id: Literal[9]
    TRIPS_TOTAL: int
    TRIPS_MATCHED_ROUTE: int
    TRIPS_UNMATCHED_ROUTE: int
    DISTANCE_VARIANCE_PCT: float | None


class MarginProxyValidation(KpiValidationBase):
    """KPI 28, query infrastructure/queries/kpis/margin_proxy.sql"""
    kpi_id: Literal[28]
    TRIPS_TOTAL: int
    TRIPS_USED: int
    TRIPS_WITHOUT_TRUCK_KEY: int
    TRIPS_USED_WITHOUT_FUEL_PURCHASE: int
    FUEL_PURCHASES_UNMATCHED_TRIP: int
    REVENUE_USD: float | None
    FUEL_COST_USD: float | None
    MAINTENANCE_COST_USD: float | None
    FUEL_COST_ALL_PURCHASES_USD: float | None
    MAINTENANCE_COST_ALL_ORDERS_USD: float | None
    MARGIN_PROXY_PER_TRIP_USD: float | None


KpiValidation = Annotated[DistanceVarianceValidation | MarginProxyValidation, Field(discriminator="kpi_id")]
