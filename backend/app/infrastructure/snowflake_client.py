"""The only module that talks to Snowflake. Repositories call fetch_all() and never touch the connection."""
import snowflake.connector
from snowflake.connector import DictCursor, SnowflakeConnection

from ..core.config import settings

_connection: SnowflakeConnection | None = None


def get_connection() -> SnowflakeConnection:
    """Shared connection: opened on first use, reopened if Snowflake closed it (session timeout)."""
    global _connection
    if _connection is None or _connection.is_closed():
        _connection = snowflake.connector.connect(
            account=settings.snowflake_api_account,
            user=settings.snowflake_api_user,
            password=settings.snowflake_api_password,
            database=settings.snowflake_api_database,
            role=settings.snowflake_api_role,
            warehouse=settings.snowflake_api_warehouse,
            schema=settings.snowflake_api_schema,
            client_session_keep_alive=True,
            enable_server_session_keep_alive_auto_detection=False,  # no async queries: plain logout on close
        )
    return _connection


def fetch_all(sql: str, params: dict | tuple | None = None) -> list[dict]:
    """Runs one query and returns the rows as dicts keyed by column name (upper case, as Snowflake returns them)."""
    with get_connection().cursor(DictCursor) as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def close_connection() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
