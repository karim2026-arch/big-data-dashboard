"""Fleet Dashboard API: FastAPI in front of Snowflake. Run from backend/: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from snowflake.connector.errors import Error as SnowflakeError

from . import kpi_validation, snowflake_client
from .config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    snowflake_client.close_connection()


app = FastAPI(title="Fleet Dashboard API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(SnowflakeError)
async def snowflake_error_handler(_: Request, exc: SnowflakeError) -> JSONResponse:
    """Any Snowflake failure (login, SQL, timeout) becomes a 503 with the Snowflake message, not a stack trace."""
    return JSONResponse(status_code=503, content={"detail": f"Snowflake error: {exc.msg}"})


@app.get("/health")
def health() -> dict:
    """Proves the login works and shows which user, role, warehouse, database and schema the API is using."""
    row = snowflake_client.fetch_all(
        "SELECT CURRENT_USER() AS login_user, CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse, "
        "CURRENT_DATABASE() AS database, CURRENT_SCHEMA() AS schema"
    )[0]
    return {"status": "ok", **{column.lower(): value for column, value in row.items()}}


@app.get("/api/tables")
def tables() -> list[dict]:
    """Every table and view the API user can see in the configured database, with its row count."""
    return snowflake_client.fetch_all(
        "SELECT table_schema, table_name, table_type, row_count "
        "FROM information_schema.tables "
        "WHERE table_schema <> 'INFORMATION_SCHEMA' "
        "ORDER BY table_schema, table_name"
    )


@app.get("/api/kpis/validation")
def kpis_validation() -> list[dict]:
    """KPI 9 and KPI 28 over all mart rows, each with its join checks. See app/kpi_validation.py."""
    return kpi_validation.calculate_all()
