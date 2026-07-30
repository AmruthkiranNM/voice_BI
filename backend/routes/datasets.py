"""
Dataset API — exposes uploaded business data status to the frontend.

Tables are grouped into *data sources* (sessions): the local CSV pool and
each connected external database. The frontend switches between sources so a
query is always scoped to one source's tables.
"""

import logging
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from services.auth import require_auth
from services.database import (
    get_all_table_names,
    get_table_schema,
    get_table_row_count,
    get_connection,
    drop_all_user_tables,
)
from services.suggestions import generate_suggestions_for_table
from services.domain_detector import analyze_dataset
from services.vector_store import is_index_ready
from services.ingest import rebuild_index
from services import sources as source_registry
from services import data_quality

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Datasets"], dependencies=[Depends(require_auth)])


def _table_info(name: str) -> dict:
    schema = get_table_schema(name)
    bundle = generate_suggestions_for_table(name)
    return {
        "name": name,
        "row_count": get_table_row_count(name),
        "domain": bundle["domain"],
        "suggestions": bundle["suggestions"],
        "columns": [
            {"name": col["column_name"], "type": col["data_type"]}
            for col in schema
        ],
    }


@router.get("/datasets")
def list_datasets():
    """Return tables grouped by data source, plus per-table domain/suggestions."""
    tables = get_all_table_names()
    info_by_name = {name: _table_info(name) for name in tables}
    datasets = list(info_by_name.values())

    # Group into sources (sessions).
    sources = []
    for src in source_registry.list_sources():
        src_tables = [info_by_name[t] for t in src["tables"] if t in info_by_name]
        if not src_tables:
            continue
        primary = max(src_tables, key=lambda d: d["row_count"])
        sources.append({
            "id": src["id"],
            "label": src["label"],
            "type": src["type"],
            "tables": src_tables,
            "domain": primary["domain"],
            "suggestions": primary["suggestions"],
        })

    primary = max(datasets, key=lambda d: d["row_count"]) if datasets else None

    return {
        "has_data": len(datasets) > 0,
        "tables": datasets,          # flat list (kept for backward compatibility)
        "sources": sources,          # grouped by data source (sessions)
        "total_tables": len(datasets),
        "domain": primary["domain"] if primary else analyze_dataset([]),
        "suggestions": primary["suggestions"] if primary else [],
        "vector_store_ready": is_index_ready(),
    }


@router.get("/datasets/{table_name}/preview")
def get_table_preview(table_name: str):
    """
    Sample rows + a fresh data-quality report for one already-ingested
    table, computed on demand (not just cached from upload time) so the
    Data Source and Data Quality views can show every table in a source,
    not only the one most recently uploaded.
    """
    if table_name not in get_all_table_names():
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")

    conn = get_connection()
    try:
        df = pd.read_sql(f"SELECT * FROM [{table_name}]", conn)
    finally:
        conn.close()

    return {
        "table_name": table_name,
        "row_count": len(df),
        "columns": list(df.columns),
        "column_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "preview_rows": df.head(8).fillna("").astype(str).to_dict(orient="records"),
        "data_quality": data_quality.assess(df),
    }


@router.delete("/datasets/{table_name}")
def delete_dataset(table_name: str):
    """Remove a single table from the workspace."""
    if table_name not in get_all_table_names():
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")

    conn = get_connection()
    try:
        conn.execute(f"DROP TABLE IF EXISTS [{table_name}];")
        conn.commit()
    finally:
        conn.close()

    source_registry.unregister_table(table_name)
    rebuild_index()
    return {"success": True, "removed": table_name, "tables": get_all_table_names()}


@router.delete("/sources/{source_id}")
def delete_source(source_id: str):
    """Remove an entire data source (all its tables) from the workspace."""
    table_names = source_registry.source_table_names(source_id)
    if not table_names:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")

    conn = get_connection()
    try:
        for name in table_names:
            conn.execute(f"DROP TABLE IF EXISTS [{name}];")
        conn.commit()
    finally:
        conn.close()

    for name in table_names:
        source_registry.unregister_table(name)
    rebuild_index()
    return {"success": True, "removed": table_names, "tables": get_all_table_names()}


@router.delete("/datasets")
def delete_all_datasets():
    """Clear the entire workspace (all tables from every source)."""
    removed = drop_all_user_tables()
    for name in removed:
        source_registry.unregister_table(name)
    rebuild_index()
    return {"success": True, "removed": removed, "tables": get_all_table_names()}
