"""
Data-source registry.

Each queryable table belongs to exactly one *data source* (a "session"):
either the local CSV pool, or one specific external database connection.
This registry records that mapping so queries can be scoped to a single
source — the tables of one Postgres connection are never mixed with CSV
uploads or a different database when answering a question.

The registry is a small SQLite table (_vbi_source_registry) that lives
alongside the user tables and survives restarts. get_all_table_names()
excludes it, so it never shows up as user data.
"""

import hashlib
import logging
from urllib.parse import urlparse

from services.database import get_connection, get_all_table_names

logger = logging.getLogger(__name__)

REGISTRY_TABLE = "_vbi_source_registry"

# The default source for CSV uploads and any pre-existing / unregistered table.
LOCAL_SOURCE_ID = "local_files"
LOCAL_SOURCE_LABEL = "Uploaded files"
LOCAL_SOURCE_TYPE = "csv"


def ensure_registry() -> None:
    conn = get_connection()
    try:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} ("
            "table_name TEXT PRIMARY KEY, "
            "source_id TEXT NOT NULL, "
            "source_label TEXT NOT NULL, "
            "source_type TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def register_table(table_name: str, source_id: str, source_label: str, source_type: str) -> None:
    ensure_registry()
    conn = get_connection()
    try:
        conn.execute(
            f"INSERT INTO {REGISTRY_TABLE} (table_name, source_id, source_label, source_type) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(table_name) DO UPDATE SET "
            "source_id=excluded.source_id, source_label=excluded.source_label, "
            "source_type=excluded.source_type",
            (table_name, source_id, source_label, source_type),
        )
        conn.commit()
    finally:
        conn.close()


def unregister_table(table_name: str) -> None:
    ensure_registry()
    conn = get_connection()
    try:
        conn.execute(f"DELETE FROM {REGISTRY_TABLE} WHERE table_name = ?", (table_name,))
        conn.commit()
    finally:
        conn.close()


def _registry_rows() -> dict[str, dict]:
    """table_name -> {source_id, source_label, source_type}."""
    ensure_registry()
    conn = get_connection()
    try:
        cursor = conn.execute(
            f"SELECT table_name, source_id, source_label, source_type FROM {REGISTRY_TABLE}"
        )
        return {
            row["table_name"]: {
                "source_id": row["source_id"],
                "source_label": row["source_label"],
                "source_type": row["source_type"],
            }
            for row in cursor.fetchall()
        }
    finally:
        conn.close()


def get_table_source(table_name: str) -> dict:
    """Return the source for a table, defaulting unregistered tables to local."""
    row = _registry_rows().get(table_name)
    if row:
        return row
    return {
        "source_id": LOCAL_SOURCE_ID,
        "source_label": LOCAL_SOURCE_LABEL,
        "source_type": LOCAL_SOURCE_TYPE,
    }


def list_sources() -> list[dict]:
    """
    Group every existing user table under its source. Tables with no registry
    entry (e.g. uploaded before this feature existed) fall into the local
    CSV source so nothing is ever hidden from the user.
    """
    rows = _registry_rows()
    grouped: dict[str, dict] = {}
    for table in get_all_table_names():
        src = rows.get(table) or {
            "source_id": LOCAL_SOURCE_ID,
            "source_label": LOCAL_SOURCE_LABEL,
            "source_type": LOCAL_SOURCE_TYPE,
        }
        sid = src["source_id"]
        if sid not in grouped:
            grouped[sid] = {
                "id": sid,
                "label": src["source_label"],
                "type": src["source_type"],
                "tables": [],
            }
        grouped[sid]["tables"].append(table)

    # Local source first, then the rest alphabetically by label.
    return sorted(
        grouped.values(),
        key=lambda s: (s["id"] != LOCAL_SOURCE_ID, s["label"].lower()),
    )


def source_table_names(source_id: str) -> list[str]:
    return [t for s in list_sources() if s["id"] == source_id for t in s["tables"]]


def source_id_for_connection(connection_string: str) -> tuple[str, str]:
    """
    Derive a stable source id + friendly label from a Postgres connection
    string. Reconnecting the same database maps to the same source, so a
    re-import replaces that source's tables instead of creating a duplicate.
    """
    parsed = urlparse(connection_string)
    host = (parsed.hostname or "db").lower()
    dbname = (parsed.path or "/postgres").lstrip("/") or "postgres"

    digest = hashlib.sha1(f"{host}/{dbname}".encode()).hexdigest()[:8]
    source_id = f"pg_{digest}"

    if "supabase" in host:
        provider = "Supabase"
    elif "neon" in host:
        provider = "Neon"
    elif "rds.amazonaws" in host:
        provider = "AWS RDS"
    else:
        provider = host

    label = f"{provider} · {dbname}"
    return source_id, label
