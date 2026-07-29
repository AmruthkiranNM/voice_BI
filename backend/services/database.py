"""
Database Service Module

Handles SQLite connection management, schema introspection, and query execution.
Business data is loaded exclusively via user CSV uploads.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Any

from config import DATA_DIR, DATABASE_PATH, MAX_RESULT_ROWS

logger = logging.getLogger(__name__)


def get_database_path() -> str:
    """
    Resolve the SQLite file for the current request: the logged-in user's
    own database (set via services.auth.require_auth), or the shared
    default path outside a request (tests, scripts, startup).

    Every table a user uploads or connects lives only in their own file, so
    isolation between accounts falls out of this one function instead of
    needing an owner_id column threaded through every table/query.
    """
    from services.auth import current_user_id
    user_id = current_user_id.get()
    if user_id is None:
        return DATABASE_PATH
    return str(DATA_DIR / f"business_{user_id}.db")


def ensure_data_directory() -> None:
    """Create the data directory if it does not exist."""
    Path(get_database_path()).parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Create and return a new SQLite connection with row factory."""
    ensure_data_directory()
    conn = sqlite3.connect(get_database_path())
    conn.row_factory = sqlite3.Row
    return conn


def has_datasets() -> bool:
    """Return True if the user has uploaded at least one table."""
    return len(get_all_table_names()) > 0


def get_all_table_names() -> list[str]:
    """Return a list of all user table names in the database."""
    if not Path(get_database_path()).exists():
        return []
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '\\_vbi\\_%' ESCAPE '\\' ORDER BY name;"
        )
        return [row["name"] for row in cursor.fetchall()]
    finally:
        conn.close()


def drop_all_user_tables(except_table: str | None = None) -> list[str]:
    """
    Drop every user-uploaded table. Used when replacing the workspace with a new CSV.

    Returns names of tables that were removed.
    """
    removed: list[str] = []
    conn = get_connection()
    try:
        for name in get_all_table_names():
            if except_table and name == except_table:
                continue
            conn.execute(f"DROP TABLE IF EXISTS [{name}];")
            removed.append(name)
        conn.commit()
    finally:
        conn.close()

    if removed:
        logger.info("Dropped tables: %s", ", ".join(removed))
    return removed


def get_table_row_count(table_name: str) -> int:
    """Return the number of rows in a table."""
    conn = get_connection()
    try:
        cursor = conn.execute(f"SELECT COUNT(*) AS cnt FROM [{table_name}];")
        return int(cursor.fetchone()["cnt"])
    finally:
        conn.close()


def get_table_schema(table_name: str) -> list[dict[str, Any]]:
    """
    Return column information for a given table.
    Each dict has: column_name, data_type, is_primary_key, is_nullable, default_value
    """
    conn = get_connection()
    try:
        cursor = conn.execute(f"PRAGMA table_info('{table_name}');")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "column_name": row["name"],
                "data_type": row["type"],
                "is_primary_key": bool(row["pk"]),
                "is_nullable": not bool(row["notnull"]),
                "default_value": row["dflt_value"],
            })
        return columns
    finally:
        conn.close()


def get_foreign_keys(table_name: str) -> list[dict[str, str]]:
    """Return foreign key relationships for a given table."""
    conn = get_connection()
    try:
        cursor = conn.execute(f"PRAGMA foreign_key_list('{table_name}');")
        fks = []
        for row in cursor.fetchall():
            fks.append({
                "from_column": row["from"],
                "to_table": row["table"],
                "to_column": row["to"],
            })
        return fks
    finally:
        conn.close()


def get_full_schema() -> dict[str, Any]:
    """
    Return complete database schema as a structured dictionary.
    Includes tables, columns, types, primary keys, and foreign keys.
    """
    tables = get_all_table_names()
    schema = {}

    for table in tables:
        schema[table] = {
            "columns": get_table_schema(table),
            "foreign_keys": get_foreign_keys(table),
        }

    return schema


def get_sample_data(table_name: str, limit: int = 3) -> list[dict]:
    """Return a few sample rows from a table for context."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            f"SELECT * FROM [{table_name}] LIMIT ?;", (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_sample_values(
    table_name: str,
    schema: list[dict[str, Any]] | None = None,
    per_column: int = 40,
) -> list[str]:
    """
    Collect distinct text values from a table's text/category columns, used to
    classify the business domain from cell contents (not just column names).
    """
    schema = schema or get_table_schema(table_name)
    text_cols = [
        c["column_name"]
        for c in schema
        if (c.get("data_type") or "").upper() in ("TEXT", "VARCHAR", "CHAR", "STRING", "")
    ]
    if not text_cols:
        return []

    values: list[str] = []
    conn = get_connection()
    try:
        for col in text_cols:
            try:
                cursor = conn.execute(
                    f"SELECT DISTINCT [{col}] FROM [{table_name}] "
                    f"WHERE [{col}] IS NOT NULL LIMIT ?;",
                    (per_column,),
                )
                values.extend(str(row[0]) for row in cursor.fetchall())
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()
    return values


def get_low_cardinality_values(
    table_name: str,
    schema: list[dict[str, Any]] | None = None,
    max_distinct: int = 12,
) -> dict[str, list[str]]:
    """
    For each text column with few distinct values (e.g. a Category/Region
    column), return its full set of values. Small local LLMs generate a
    filter like WHERE Category = 'Bars' only if the exact valid values are
    spelled out in the schema context — otherwise a question like "highest
    selling bars" silently drops the filter because the model has no way to
    confirm "bars" names a real category value rather than ordinary English.
    """
    schema = schema or get_table_schema(table_name)
    text_cols = [
        c["column_name"]
        for c in schema
        if (c.get("data_type") or "").upper() in ("TEXT", "VARCHAR", "CHAR", "STRING", "")
        # ID/key-like columns are never what a business question names as a
        # filter term ("bars", "australia") — skip them to keep the schema
        # context small enough to fit the model's context window.
        and not c["column_name"].lower().endswith("id")
        and not c.get("is_primary_key")
    ]
    if not text_cols:
        return {}

    result: dict[str, list[str]] = {}
    conn = get_connection()
    try:
        for col in text_cols:
            try:
                cursor = conn.execute(
                    f"SELECT DISTINCT [{col}] FROM [{table_name}] "
                    f"WHERE [{col}] IS NOT NULL LIMIT ?;",
                    (max_distinct + 1,),
                )
                values = [str(row[0]) for row in cursor.fetchall()]
                if 0 < len(values) <= max_distinct:
                    result[col] = values
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()
    return result


def execute_query(sql: str) -> dict[str, Any]:
    """
    Execute a read-only SQL query and return results.

    Returns:
        {
            "columns": [...],
            "rows": [...],
            "row_count": int
        }
    """
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(MAX_RESULT_ROWS)
        result_rows = [dict(zip(columns, row)) for row in rows]

        return {
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
        }
    except Exception as e:
        logger.error("Query execution failed: %s | SQL: %s", str(e), sql)
        raise
    finally:
        conn.close()
