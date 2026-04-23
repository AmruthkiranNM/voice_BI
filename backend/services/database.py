"""
Database Service Module

Handles SQLite database initialization, connection management,
schema introspection, and query execution.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Any

from config import DATABASE_PATH, DATA_DIR, MAX_RESULT_ROWS

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Create and return a new SQLite connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    """
    Initialize the database from the sample SQL file.
    Only runs if the database file does not already exist.
    """
    db_path = Path(DATABASE_PATH)

    if db_path.exists():
        logger.info("Database already exists at %s", DATABASE_PATH)
        return

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    sql_file = DATA_DIR / "sample_db.sql"
    if not sql_file.exists():
        raise FileNotFoundError(f"Sample SQL file not found: {sql_file}")

    logger.info("Initializing database from %s", sql_file)

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        with open(sql_file, "r", encoding="utf-8") as f:
            sql_script = f.read()
        conn.executescript(sql_script)
        conn.commit()
        logger.info("Database initialized successfully.")
    finally:
        conn.close()


def get_all_table_names() -> list[str]:
    """Return a list of all user table names in the database."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        )
        return [row["name"] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_table_schema(table_name: str) -> list[dict[str, Any]]:
    """
    Return column information for a given table.
    Each dict has: cid, name, type, notnull, dflt_value, pk
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
            f"SELECT * FROM {table_name} LIMIT ?;", (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


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
