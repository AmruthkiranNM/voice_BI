"""
Schema Loader Module

Converts the database schema into rich, descriptive text documents
suitable for embedding and RAG retrieval. Each document describes
a single table with its columns, types, relationships, and sample data.
"""

import logging
from typing import Any

from services.database import get_full_schema, get_sample_data

logger = logging.getLogger(__name__)


def _format_column(col: dict[str, Any]) -> str:
    """Format a single column into a readable description."""
    parts = [f"{col['column_name']} ({col['data_type']})"]
    if col["is_primary_key"]:
        parts.append("PRIMARY KEY")
    if not col["is_nullable"]:
        parts.append("NOT NULL")
    if col["default_value"] is not None:
        parts.append(f"DEFAULT {col['default_value']}")
    return " | ".join(parts)


def _format_foreign_keys(fks: list[dict[str, str]]) -> str:
    """Format foreign key relationships into readable text."""
    if not fks:
        return "No foreign keys."
    lines = []
    for fk in fks:
        lines.append(
            f"  - {fk['from_column']} → {fk['to_table']}.{fk['to_column']}"
        )
    return "Foreign Keys:\n" + "\n".join(lines)


def _format_sample_rows(table_name: str) -> str:
    """Get sample rows and format them as text."""
    try:
        samples = get_sample_data(table_name, limit=3)
        if not samples:
            return "No sample data available."
        lines = ["Sample Data:"]
        for i, row in enumerate(samples, 1):
            row_str = ", ".join(f"{k}={v}" for k, v in row.items())
            lines.append(f"  Row {i}: {row_str}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Could not fetch sample data for %s: %s", table_name, e)
        return "Sample data unavailable."


def generate_schema_documents() -> list[dict[str, str]]:
    """
    Generate rich text documents from the database schema.

    Each document contains:
        - Table name and description
        - Column details (name, type, constraints)
        - Foreign key relationships
        - Sample data rows

    Returns:
        List of dicts with keys: "table_name", "document"
    """
    schema = get_full_schema()
    documents = []

    for table_name, table_info in schema.items():
        lines = [
            f"Table: {table_name}",
            f"Description: This table stores {table_name} data.",
            "",
            "Columns:",
        ]

        for col in table_info["columns"]:
            lines.append(f"  - {_format_column(col)}")

        lines.append("")
        lines.append(_format_foreign_keys(table_info["foreign_keys"]))
        lines.append("")
        lines.append(_format_sample_rows(table_name))

        document = "\n".join(lines)
        documents.append({
            "table_name": table_name,
            "document": document,
        })

    logger.info("Generated %d schema documents.", len(documents))
    return documents
