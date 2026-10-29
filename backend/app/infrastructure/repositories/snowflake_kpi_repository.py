"""KpiRepository on Snowflake: runs a KPI query from queries/kpis/ and returns its single row."""
from .. import snowflake_client
from ..sql_loader import load_sql


class SnowflakeKpiRepository:
    def fetch_kpi(self, query: str) -> dict:
        return snowflake_client.fetch_all(load_sql(f"kpis/{query}"))[0]
