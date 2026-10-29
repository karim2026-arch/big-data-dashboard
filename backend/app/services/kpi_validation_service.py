"""KPIs calculated on the DBT_MARTS tables over all rows, to validate the model's joins.
Each KPI returns its value together with join checks (rows matched / unmatched), because a broken join
can still give a plausible-looking value. Units are as the marts store them (km, USD).
The SQL is in infrastructure/queries/kpis/<query>.sql."""
from ..domain.repositories import KpiRepository

# (kpi_id, name, unit, query)
KPIS = (
    (9, "Distance Variance", "%", "distance_variance"),
    (28, "Margin Proxy per Trip", "USD", "margin_proxy"),
)


class KpiValidationService:
    def __init__(self, repository: KpiRepository):
        self._repository = repository

    def calculate_all(self) -> list[dict]:
        """One dict per KPI: kpi_id, name, unit, then the query's columns (value + join checks)."""
        return [
            {"kpi_id": kpi_id, "name": name, "unit": unit, **self._repository.fetch_kpi(query)}
            for kpi_id, name, unit, query in KPIS
        ]
