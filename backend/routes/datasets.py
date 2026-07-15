"""
Dataset API — exposes uploaded business data status to the frontend.
"""

import logging
from fastapi import APIRouter, HTTPException

from services.database import (
    get_all_table_names,
    get_table_schema,
    get_table_row_count,
    drop_all_user_tables,
)
from services.suggestions import generate_suggestions_for_table
from services.domain_detector import analyze_dataset
from services.vector_store import is_index_ready, build_index
from models.schema_loader import generate_schema_documents
from services import query_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Datasets"])


@router.get("/datasets")
def list_datasets():
    """Return uploaded tables, per-table domain, and tailored query suggestions."""
    tables = get_all_table_names()
    datasets = []

    for name in tables:
        schema = get_table_schema(name)
        bundle = generate_suggestions_for_table(name)
        datasets.append({
            "name": name,
            "row_count": get_table_row_count(name),
            "domain": bundle["domain"],
            "suggestions": bundle["suggestions"],
            "columns": [
                {"name": col["column_name"], "type": col["data_type"]}
                for col in schema
            ],
        })

    # Primary dataset = largest table (default selection in UI)
    primary = max(datasets, key=lambda d: d["row_count"]) if datasets else None

    return {
        "has_data": len(datasets) > 0,
        "tables": datasets,
        "total_tables": len(datasets),
        "domain": primary["domain"] if primary else analyze_dataset([]),
        "suggestions": primary["suggestions"] if primary else [],
        "vector_store_ready": is_index_ready(),
    }


@router.delete("/datasets/{table_name}")
def delete_dataset(table_name: str):
    """Remove a single uploaded table from the workspace."""
    from services.database import get_connection

    if table_name not in get_all_table_names():
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")

    conn = get_connection()
    try:
        conn.execute(f"DROP TABLE IF EXISTS [{table_name}];")
        conn.commit()
    finally:
        conn.close()

    _rebuild_index()
    return {"success": True, "removed": table_name, "tables": get_all_table_names()}


@router.delete("/datasets")
def delete_all_datasets():
    """Clear the entire workspace (all uploaded tables)."""
    removed = drop_all_user_tables()
    _rebuild_index()
    return {"success": True, "removed": removed, "tables": get_all_table_names()}


def _rebuild_index():
    query_cache.invalidate()
    schema_docs = generate_schema_documents()
    if schema_docs:
        build_index(schema_docs)
