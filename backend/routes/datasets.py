"""
Dataset API — exposes uploaded business data status to the frontend.
"""

import logging
from fastapi import APIRouter

from services.database import get_all_table_names, get_table_schema, get_table_row_count
from services.suggestions import generate_suggestions_for_table
from services.domain_detector import analyze_dataset
from services.vector_store import is_index_ready

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
