"""Fleet Dashboard API: FastAPI in front of Snowflake. Run from backend/: uvicorn app.main:app --reload
Only builds the app: CORS, error handler, routes, and closing the Snowflake connection on shutdown."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from snowflake.connector.errors import Error as SnowflakeError

from .api.router import api_router
from .core.config import settings
from .core.errors import snowflake_error_handler
from .infrastructure import snowflake_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    snowflake_client.close_connection()


app = FastAPI(title="Fleet Dashboard API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"], allow_headers=["*"])
app.add_exception_handler(SnowflakeError, snowflake_error_handler)
app.include_router(api_router)
