"""
Execution Agent

Executes validated SQL queries against the database and returns
structured results. Handles errors gracefully and provides
metadata about the execution.
"""

import logging
import time
from typing import Any

from services.database import execute_query

logger = logging.getLogger(__name__)


def run(sql: str) -> dict[str, Any]:
    """
    Execute a validated SQL query and return structured results.

    Args:
        sql: Validated SQL query string.

    Returns:
        Dictionary with:
            - success: bool
            - columns: list of column names
            - rows: list of row dicts
            - row_count: number of rows returned
            - execution_time_ms: time taken in milliseconds
            - error: error message if failed (None on success)
    """
    logger.info("[Execution Agent] Executing SQL: %s", sql[:150])

    start_time = time.time()

    try:
        result = execute_query(sql)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        output = {
            "success": True,
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "execution_time_ms": elapsed_ms,
            "error": None,
        }

        logger.info(
            "[Execution Agent] Query returned %d rows in %.2f ms",
            output["row_count"],
            elapsed_ms,
        )

        return output

    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        error_msg = str(e)
        logger.error("[Execution Agent] Query failed: %s", error_msg)

        return {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "execution_time_ms": elapsed_ms,
            "error": error_msg,
        }
