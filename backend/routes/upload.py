import logging
import re
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import sqlite3

import config
from config import MAX_UPLOAD_ROWS, MAX_UPLOAD_COLUMNS, MAX_UPLOAD_MB
from services.vector_store import build_index
from models.schema_loader import generate_schema_documents
from services.database import get_all_table_names, get_table_row_count, get_table_schema, drop_all_user_tables
from services import query_cache
from services.suggestions import generate_suggestions_for_table
from services import data_quality

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Upload"])

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


def _sanitize_table_name(filename: str) -> str:
    """Convert a CSV filename into a safe SQLite table name."""
    name = Path(filename).stem.lower().replace(" ", "_").replace("-", "_")
    name = re.sub(r"[^a-z0-9_]", "", name)
    if not name or name[0].isdigit():
        name = f"data_{name or 'table'}"
    if name in SQLITE_RESERVED:
        name = f"{name}_data"
    return name[:64]


def _sanitize_columns(columns) -> list[str]:
    """
    Convert CSV headers to space-free snake_case so generated SQL never needs
    to quote column names — the root cause of most SQL failures on a small
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


def _normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
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


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a business CSV, create a queryable table, and rebuild the RAG index."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {MAX_UPLOAD_MB} MB.",
        )

    try:
        from io import BytesIO
        buffer = BytesIO(content)
        try:
            df = pd.read_csv(buffer)
        except UnicodeDecodeError:
            buffer.seek(0)
            try:
                df = pd.read_csv(buffer, encoding="ISO-8859-1")
            except UnicodeDecodeError:
                buffer.seek(0)
                df = pd.read_csv(buffer, encoding="cp1252")

        if df.empty:
            raise HTTPException(status_code=400, detail="CSV file is empty.")

        df.columns = _sanitize_columns(df.columns)
        df = _normalize_date_columns(df)

        if len(df) > MAX_UPLOAD_ROWS:
            raise HTTPException(
                status_code=400,
                detail=f"Too many rows ({len(df):,}). Maximum is {MAX_UPLOAD_ROWS:,}.",
            )

        if len(df.columns) > MAX_UPLOAD_COLUMNS:
            raise HTTPException(
                status_code=400,
                detail=f"Too many columns ({len(df.columns)}). Maximum is {MAX_UPLOAD_COLUMNS}.",
            )

        table_name = _sanitize_table_name(file.filename)

        # Replace workspace: only the newly uploaded file should be queryable.
        drop_all_user_tables()

        conn = sqlite3.connect(config.DATABASE_PATH)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()

        schema_docs = generate_schema_documents()
        if schema_docs:
            build_index(schema_docs)

        query_cache.invalidate()

        row_count = get_table_row_count(table_name)
        columns = [col["column_name"] for col in get_table_schema(table_name)]
        column_types = {col: str(dtype) for col, dtype in df.dtypes.items()}
        preview_rows = df.head(8).fillna("").astype(str).to_dict(orient="records")
        schema = get_table_schema(table_name)
        suggestion_bundle = generate_suggestions_for_table(table_name)
        tables = get_all_table_names()
        quality_report = data_quality.assess(df)

        logger.info("Uploaded %s as table %s (%d rows)", file.filename, table_name, row_count)
        return {
            "success": True,
            "table_name": table_name,
            "row_count": row_count,
            "columns": columns,
            "column_types": column_types,
            "preview_rows": preview_rows,
            "domain": suggestion_bundle["domain"],
            "total_tables": len(tables),
            "suggestions": suggestion_bundle["suggestions"],
            "data_quality": quality_report,
            "message": (
                f"Imported {row_count:,} rows from '{file.filename}'. "
                f"Detected: {suggestion_bundle['domain']['label']}. "
                "You can now ask questions about your business data."
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))
