"""
Shared data-ingestion pipeline.

Any source that produces a pandas DataFrame (CSV upload, a table pulled from
a connected external database, ...) goes through the same steps here: column
sanitization, date normalization, writing to the local SQLite workspace, and
rebuilding the RAG index. Keeping this in one place means every ingestion
path gets the same SQL-reliability fixes for free.
"""

import logging
import re
import sqlite3
from pathlib import Path

import pandas as pd

import config
from config import MAX_UPLOAD_ROWS, MAX_UPLOAD_COLUMNS
from services.database import get_database_path, get_table_row_count, get_table_schema
from services.suggestions import generate_suggestions_for_table
from services import data_quality, query_cache
from services.vector_store import build_index
from models.schema_loader import generate_schema_documents

logger = logging.getLogger(__name__)

SQLITE_RESERVED = {
    "abort", "action", "add", "after", "all", "alter", "analyze", "and", "as", "asc",
    "attach", "autoincrement", "before", "begin", "between", "by", "cascade", "case",
    "cast", "check", "collate", "column", "commit", "conflict", "constraint", "create",
    "cross", "current_date", "current_time", "current_timestamp", "database", "default",
    "deferrable", "deferred", "delete", "desc", "detach", "distinct", "drop", "each",
    "else", "end", "escape", "except", "exclusive", "exists", "explain", "fail", "for",
    "foreign", "from", "full", "glob", "group", "having", "if", "ignore", "immediate",
    "in", "index", "indexed", "initially", "inner", "insert", "instead", "intersect",
    "into", "is", "isnull", "join", "key", "left", "like", "limit", "match", "natural",
    "no", "not", "notnull", "null", "of", "offset", "on", "or", "order", "outer", "plan",
    "pragma", "primary", "query", "raise", "recursive", "references", "regexp", "reindex",
    "release", "rename", "replace", "restrict", "right", "rollback", "row", "savepoint",
    "select", "set", "table", "temp", "temporary", "then", "to", "transaction", "trigger",
    "union", "unique", "update", "using", "vacuum", "values", "view", "virtual", "when",
    "where", "with", "without",
}


def sanitize_table_name(name: str) -> str:
    """Convert a filename or remote table name into a safe SQLite table name."""
    name = Path(name).stem.lower().replace(" ", "_").replace("-", "_")
    name = re.sub(r"[^a-z0-9_]", "", name)
    if not name or name[0].isdigit():
        name = f"data_{name or 'table'}"
    if name in SQLITE_RESERVED:
        name = f"{name}_data"
    return name[:64]


def sanitize_columns(columns) -> list[str]:
    """
    Convert headers to space-free snake_case so generated SQL never needs to
    quote column names — the root cause of most SQL failures on a small
    local model ("Medical Condition" -> medical_condition). The frontend
    renders underscores back as spaces for display.
    """
    out: list[str] = []
    seen: dict[str, int] = {}
    for c in columns:
        s = re.sub(r"[^0-9a-zA-Z]+", "_", str(c)).strip("_").lower() or "col"
        if s[0].isdigit():
            s = f"c_{s}"
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 0
        out.append(s)
    return out


def normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rewrite date-like text columns (e.g. "2/24/2003 0:00", a US-format date
    pandas parses fine) into ISO-8601 strings. SQLite's date functions
    (strftime, date(), BETWEEN date(...)) only understand ISO-8601 and
    silently return NULL on anything else — so without this, every
    date-filtered or date-grouped query on such a column returns no rows.
    Only columns pandas can confidently parse (>90% of non-null values) are
    converted, so ordinary text/ID columns are left untouched.
    """
    for col in df.columns:
        if not pd.api.types.is_string_dtype(df[col]):
            continue
        non_null = df[col].notna().sum()
        if non_null == 0:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().sum() / non_null < 0.9:
            continue
        has_time = (parsed.dt.time != pd.Timestamp("00:00:00").time()).any()
        fmt = "%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d"
        df[col] = parsed.dt.strftime(fmt).where(parsed.notna(), df[col])
    return df


def rebuild_index() -> None:
    """Rebuild the RAG schema index and invalidate the query cache."""
    query_cache.invalidate()
    schema_docs = generate_schema_documents()
    if schema_docs:
        build_index(schema_docs)


def ingest_dataframe(
    df: pd.DataFrame,
    raw_name: str,
    *,
    source_label: str,
    source_id: str = "local_files",
    source_type: str = "csv",
) -> dict:
    """
    Run a DataFrame through the full ingestion pipeline (sanitize, normalize,
    write to SQLite) and return the same response shape regardless of
    whether it came from a CSV upload or an external database table, so the
    frontend's upload-success handling works unchanged for both.

    The table is tagged with its data source (source_id/label/type) so
    queries can be scoped to one source and never mix, e.g., a Postgres
    connection's tables with CSV uploads.

    Does NOT rebuild the RAG index — call rebuild_index() once after
    ingesting all tables in a batch (e.g. all tables from one DB import).
    """
    from services.sources import register_table
    if df.empty:
        raise ValueError(f"'{raw_name}' has no rows.")

    df = df.copy()
    df.columns = sanitize_columns(df.columns)
    df = normalize_date_columns(df)

    if len(df) > MAX_UPLOAD_ROWS:
        raise ValueError(f"'{raw_name}' has too many rows ({len(df):,}). Maximum is {MAX_UPLOAD_ROWS:,}.")

    if len(df.columns) > MAX_UPLOAD_COLUMNS:
        raise ValueError(
            f"'{raw_name}' has too many columns ({len(df.columns)}). Maximum is {MAX_UPLOAD_COLUMNS}."
        )

    table_name = sanitize_table_name(raw_name)

    conn = sqlite3.connect(get_database_path())
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    register_table(table_name, source_id, source_label, source_type)

    row_count = get_table_row_count(table_name)
    columns = [col["column_name"] for col in get_table_schema(table_name)]
    column_types = {col: str(dtype) for col, dtype in df.dtypes.items()}
    preview_rows = df.head(8).fillna("").astype(str).to_dict(orient="records")
    suggestion_bundle = generate_suggestions_for_table(table_name)
    quality_report = data_quality.assess(df)

    logger.info("Ingested %s (%s) as table %s (%d rows)", raw_name, source_label, table_name, row_count)
    return {
        "success": True,
        "table_name": table_name,
        "row_count": row_count,
        "columns": columns,
        "column_types": column_types,
        "preview_rows": preview_rows,
        "domain": suggestion_bundle["domain"],
        "suggestions": suggestion_bundle["suggestions"],
        "data_quality": quality_report,
        "source_id": source_id,
        "source_label": source_label,
        "source_type": source_type,
        "message": (
            f"Imported {row_count:,} rows from '{raw_name}' ({source_label}). "
            f"Detected: {suggestion_bundle['domain']['label']}. "
            "You can now ask questions about your business data."
        ),
    }
