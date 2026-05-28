import logging
import time
import re
import pyodbc
from app.config import settings
from app.observability.logger import AgentLogger
from app.constants.app_constants import AgentName, EventName, AppConfig
from app.constants.messages import (
    QUERY_EXECUTION_STARTED,
    QUERY_EXECUTION_COMPLETED,
    QUERY_EXECUTION_FAILED,
    TOP_CLAUSE_ENFORCED,
)

logger = logging.getLogger(__name__)


def get_ecommerce_connection() -> pyodbc.Connection:
    if settings.mssql_use_windows_auth:
        connection_string = (
            f"DRIVER={{{settings.mssql_driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
    else:
        connection_string = (
            f"DRIVER={{{settings.mssql_driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"UID={settings.mssql_username};"
            f"PWD={settings.mssql_password};"
            f"TrustServerCertificate=yes;"
        )
    return pyodbc.connect(connection_string)


def enforce_top_clause(sql: str, max_rows: int = AppConfig.MAX_ROWS) -> tuple[str, bool]:
    """
    Ensures the query contains a TOP clause.
    Returns the (possibly modified) SQL and a bool indicating if TOP was injected.
    """
    # Check if TOP clause already exists (case insensitive)
    top_pattern = re.compile(r'\bSELECT\s+TOP\s*\(\s*\d+\s*\)\s*|\bSELECT\s+TOP\s+\d+\s+', re.IGNORECASE)

    if top_pattern.search(sql):
        # Replace any existing TOP value with our hard cap
        enforced = re.sub(
            r'(SELECT\s+TOP\s*\(?\s*)\d+(\s*\)?)',
            lambda m: f"SELECT TOP {max_rows} ",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
        return enforced, False

    # Inject TOP clause after SELECT keyword
    enforced = re.sub(
        r'\bSELECT\b',
        f"SELECT TOP {max_rows}",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    return enforced, True


def execute_query(sql: str, session_id: str) -> list[dict]:
    agent_logger = AgentLogger(
        agent_name=AgentName.DB_QUERY_TOOL,
        session_id=session_id,
    )

    agent_logger.info(
        QUERY_EXECUTION_STARTED,
        event=EventName.QUERY_EXECUTION_STARTED,
        payload={"original_sql": sql},
    )

    # Enforce TOP clause
    enforced_sql, was_injected = enforce_top_clause(sql)

    if was_injected:
        agent_logger.info(
            TOP_CLAUSE_ENFORCED.format(max_rows=AppConfig.MAX_ROWS),
            event=EventName.QUERY_EXECUTION_STARTED,
            payload={"enforced_sql": enforced_sql},
        )

    start_time = time.monotonic()

    try:
        conn = get_ecommerce_connection()
        cursor = conn.cursor()
        cursor.execute(enforced_sql)

        columns = [column[0] for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, row)))

        cursor.close()
        conn.close()

        latency_ms = int((time.monotonic() - start_time) * 1000)

        agent_logger.info(
            QUERY_EXECUTION_COMPLETED.format(row_count=len(rows)),
            event=EventName.QUERY_EXECUTION_COMPLETED,
            payload={
                "row_count": len(rows),
                "latency_ms": latency_ms,
                "enforced_sql": enforced_sql,
            },
        )

        return rows

    except pyodbc.Error as e:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        agent_logger.error(
            QUERY_EXECUTION_FAILED.format(error=str(e)),
            event=EventName.QUERY_EXECUTION_FAILED,
            payload={
                "error": str(e),
                "latency_ms": latency_ms,
                "sql": enforced_sql,
            },
            exc_info=True,
        )
        raise