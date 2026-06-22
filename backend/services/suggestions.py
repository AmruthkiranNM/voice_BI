"""
Generate business-friendly query suggestions from uploaded dataset columns.
"""

from services.database import get_all_table_names, get_table_schema, get_table_row_count
from services.domain_detector import detect_domain


_NUMERIC_HINTS = {
    "sales", "revenue", "amount", "price", "total", "cost", "profit",
    "quantity", "qty", "income", "expense", "budget", "value",
}

_DATE_HINTS = {"date", "time", "month", "year", "created", "updated", "timestamp"}

_CATEGORY_HINTS = {
    "category", "region", "city", "state", "country", "product",
    "customer", "type", "status", "department", "brand", "name",
}

_COMPARISON_TEMPLATES = [
    "Compare {metric} this month vs last month",
    "Which {category} has the highest {metric}?",
    "What is the growth percentage of {metric} over time?",
    "Show best and worst performing {category} by {metric}",
]


def _classify_column(col_name: str, data_type: str) -> str:
    lower = col_name.lower()
    dtype = (data_type or "").upper()
    if any(h in lower for h in _DATE_HINTS) or "DATE" in dtype:
        return "date"
    if any(h in lower for h in _NUMERIC_HINTS) or dtype in ("INTEGER", "REAL", "NUMERIC", "FLOAT"):
        return "numeric"
    if any(h in lower for h in _CATEGORY_HINTS):
        return "category"
    return "other"


def generate_suggestions(max_suggestions: int = 8, domain_id: str | None = None) -> list[str]:
    """Build natural-language prompts tailored to the owner's uploaded data."""
    tables = get_all_table_names()
    if not tables:
        return []

    table = max(tables, key=get_table_row_count)
    schema = get_table_schema(table)
    row_count = get_table_row_count(table)
    column_names = [c["column_name"] for c in schema]
    domain = detect_domain(column_names)
    domain_id = domain_id or domain["id"]

    suggestions: list[str] = []
    numeric_cols = [c["column_name"] for c in schema if _classify_column(c["column_name"], c["data_type"]) == "numeric"]
    category_cols = [c["column_name"] for c in schema if _classify_column(c["column_name"], c["data_type"]) == "category"]
    date_cols = [c["column_name"] for c in schema if _classify_column(c["column_name"], c["data_type"]) == "date"]

    if numeric_cols:
        col = numeric_cols[0].replace("_", " ")
        suggestions.append(f"What is the total {col}?")
        suggestions.append(f"Show top 10 records by {col}")

    if category_cols and numeric_cols:
        cat = category_cols[0].replace("_", " ")
        num = numeric_cols[0].replace("_", " ")
        suggestions.append(f"Break down total {num} by {cat}")
        suggestions.append(f"Which {cat} has the highest {num}?")
        suggestions.append(f"Compare {num} across different {cat} values")

    if date_cols and numeric_cols:
        num = numeric_cols[0].replace("_", " ")
        suggestions.append(f"Show monthly trend of {num}")
        suggestions.append(f"Compare {num} this month vs last month")

    if domain_id == "retail_sales" and numeric_cols:
        suggestions.append("What are my top selling products by revenue?")
    elif domain_id == "inventory" and numeric_cols:
        suggestions.append("Which items have the lowest stock levels?")
    elif domain_id == "finance" and numeric_cols:
        suggestions.append("What are my total expenses vs income?")
    elif domain_id == "hr":
        suggestions.append("How many employees per department?")

    suggestions.append(f"Give me a summary of my {table.replace('_', ' ')} data")

    seen: set[str] = set()
    unique: list[str] = []
    for s in suggestions:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:max_suggestions]
