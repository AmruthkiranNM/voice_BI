"""
Dataset API — exposes uploaded business data status to the frontend.
"""

import logging
from fastapi import APIRouter

from services.database import get_all_table_names, get_table_schema, get_table_row_count
from services.suggestions import generate_suggestions
from services.domain_detector import detect_domain
from services.vector_store import is_index_ready

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Datasets"])


@router.get("/datasets")
def list_datasets():
    """Return uploaded tables, column info, and tailored query suggestions."""
    tables = get_all_table_names()
    datasets = []

    all_columns: list[str] = []
    for name in tables:
        schema = get_table_schema(name)
        cols = [col["column_name"] for col in schema]
        all_columns.extend(cols)
        datasets.append({
            "name": name,
            "row_count": get_table_row_count(name),
            "columns": [
                {"name": col["column_name"], "type": col["data_type"]}
                for col in schema
            ],
        })

    domain = detect_domain(all_columns) if all_columns else detect_domain([])

    return {
        "has_data": len(datasets) > 0,
        "tables": datasets,
        "total_tables": len(datasets),
        "domain": domain,
        "vector_store_ready": is_index_ready(),
        "suggestions": generate_suggestions(domain_id=domain["id"]) if datasets else [],
    }
