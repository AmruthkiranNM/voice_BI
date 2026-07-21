"""
External database connection — Postgres-compatible sources (Supabase, Neon,
RDS Postgres, or any plain Postgres instance).

This is a snapshot importer, not a live query passthrough: selected tables
are pulled into the local SQLite workspace through the same ingestion
pipeline as a CSV upload (services/ingest.py), then every question is
answered locally against that snapshot, same as the rest of the app.
Two things this buys us for free, without extra work: the small local LLM
never has to learn a second SQL dialect, and there's no risk of it ever
writing to the user's real database — the connection is only ever used for
read-only SELECTs.

The connection string is never persisted or logged; it lives only for the
duration of a single test/import request.
"""

import logging

import pandas as pd
import psycopg2

from config import MAX_UPLOAD_ROWS
from services.ingest import ingest_dataframe, rebuild_index
from services.sources import source_id_for_connection

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10


def _connect(connection_string: str):
    if not connection_string.startswith(("postgres://", "postgresql://")):
        raise ValueError(
            "Only Postgres-compatible connection strings are supported right now "
            "(e.g. postgresql://user:password@host:5432/dbname) — this covers "
            "Supabase, Neon, and RDS Postgres."
        )
    try:
        return psycopg2.connect(connection_string, connect_timeout=CONNECT_TIMEOUT_SECONDS)
    except psycopg2.OperationalError as e:
        # psycopg2 error messages don't include the password, safe to surface directly.
        raise ValueError(f"Could not connect: {e}") from e


def list_tables(connection_string: str) -> list[dict]:
    """
    Return public-schema tables with column names and an estimated row count
    (from Postgres's planner statistics, not a full COUNT(*) scan — fast even
    on large tables, at the cost of being approximate).
    """
    conn = _connect(connection_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.relname AS table_name,
                       GREATEST(c.reltuples, 0)::bigint AS est_rows
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r' AND n.nspname = 'public'
                ORDER BY c.relname;
            """)
            tables = [{"name": row[0], "estimated_rows": int(row[1])} for row in cur.fetchall()]

            for t in tables:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position;
                """, (t["name"],))
                t["columns"] = [row[0] for row in cur.fetchall()]

        return tables
    finally:
        conn.close()


def import_tables(connection_string: str, table_names: list[str]) -> dict:
    """
    Pull each selected table (capped at MAX_UPLOAD_ROWS rows) into the local
    workspace. Continues past per-table failures so one bad table doesn't
    block the rest of the batch; failures are reported back per table.
    """
    source_id, source_label = source_id_for_connection(connection_string)
    conn = _connect(connection_string)
    imported = []
    errors = []
    try:
        for name in table_names:
            if '"' in name:
                errors.append({"table": name, "error": "Invalid table name."})
                continue
            try:
                df = pd.read_sql(
                    f'SELECT * FROM "public"."{name}" LIMIT {MAX_UPLOAD_ROWS};',
                    conn,
                )
                result = ingest_dataframe(
                    df, name,
                    source_label=source_label,
                    source_id=source_id,
                    source_type="postgres",
                )
                imported.append(result)
            except Exception as e:
                logger.warning("Failed to import table '%s': %s", name, e)
                errors.append({"table": name, "error": str(e)})
    finally:
        conn.close()

    if imported:
        rebuild_index()

    return {
        "imported": imported,
        "errors": errors,
        "source_id": source_id,
        "source_label": source_label,
    }
