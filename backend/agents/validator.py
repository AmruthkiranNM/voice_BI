"""
Validator Agent

Security and correctness validation for generated SQL queries.
Performs two types of checks:

1. SECURITY: Blocks dangerous SQL operations (injection prevention)
2. SCHEMA: Ensures referenced tables and columns actually exist in the database
"""

import re
import logging
from typing import Any

from config import BLOCKED_SQL_KEYWORDS
from services.database import get_all_table_names, get_table_schema

logger = logging.getLogger(__name__)


def run(
    sql: str,
    retrieved_tables: list[str] | None = None,
    allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    """
    Validate a SQL query for security and schema correctness.

    Args:
        sql: The SQL query to validate.
        retrieved_tables: Tables retrieved by RAG (for contextual validation).
        allowed_tables: When set, the query may reference ONLY these tables
            (the active data source's scope). Referencing any table outside
            this set is rejected, keeping data sources isolated.

    Returns:
        Dictionary with validation status and details.
    """
    logger.info("[Validator Agent] Validating SQL: %s", sql[:120])

    result = {
        "valid": True,
        "security_valid": True,
        "syntax_valid": True,
        "schema_valid": True,
        "semantic_valid": True,
        "errors": [],
        "warnings": [],
        "validated_sql": sql,
    }

    # ── Step 1: Security Validation ──
    _check_security(sql, result)

    # ── Step 2: Ensure it's a SELECT statement ──
    _check_select_only(sql, result)

    # ── Step 3: Schema Validation ──
    if result["security_valid"]:
        _check_schema(sql, retrieved_tables, allowed_tables, result)

    if result["errors"]:
        result["valid"] = False

    logger.info("[Validator Agent] Validation complete. Valid: %s", result["valid"])
    return result


def _check_security(sql: str, result: dict[str, Any]) -> None:
    """
    Check for dangerous SQL keywords that could indicate injection
    or destructive operations.
    """
    sql_upper = sql.upper()

    for keyword in BLOCKED_SQL_KEYWORDS:
        # Use word boundary matching to avoid false positives
        # e.g., "UPDATED_AT" should not trigger "UPDATE"
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, sql_upper):
            result["security_valid"] = False
            result["errors"].append(f"Blocked SQL keyword detected: '{keyword}'. Only SELECT queries are allowed.")

    # Check for multiple statements (semicolon injection)
    # Remove trailing semicolon first, then check for others
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        result["security_valid"] = False
        result["errors"].append("Multiple SQL statements detected. Only single SELECT queries are allowed.")


def _check_select_only(sql: str, result: dict[str, Any]) -> None:
    """Ensure the query is a SELECT statement (or starts with WITH for CTEs)."""
    stripped = sql.strip().upper()
    if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
        result["security_valid"] = False
        result["errors"].append(f"Query must start with SELECT or WITH. Got: '{stripped[:20]}...'")


def _check_schema(
    sql: str,
    retrieved_tables: list[str] | None,
    allowed_tables: list[str] | None,
    result: dict[str, Any]
) -> None:
    """
    Validate that tables and columns referenced in SQL exist in the database
    and (when a scope is given) stay within the active data source.
    """
    db_tables = get_all_table_names()
    db_tables_lower = {t.lower() for t in db_tables}
    allowed_lower = {t.lower() for t in allowed_tables} if allowed_tables else None

    # Extract table names from SQL (basic extraction from FROM and JOIN clauses)
    sql_tables = _extract_tables_from_sql(sql)

    for table in sql_tables:
        if table.lower() not in db_tables_lower:
            result["schema_valid"] = False
            result["errors"].append(f"Table '{table}' does not exist in the database. Available tables: {db_tables}")
        elif allowed_lower is not None and table.lower() not in allowed_lower:
            result["schema_valid"] = False
            result["errors"].append(f"Table '{table}' is outside the selected data source. This query may only use: {allowed_tables}")

    # Validate columns for each known table
    for table in sql_tables:
        if table.lower() in db_tables_lower:
            # Find the correctly-cased table name
            actual_name = next(
                t for t in db_tables if t.lower() == table.lower()
            )
            table_columns = get_table_schema(actual_name)
            column_names = {
                col["column_name"].lower() for col in table_columns
            }

            # Extract columns that might reference this table
            sql_columns = _extract_columns_from_sql(sql)
            for col in sql_columns:
                # Skip SQL functions, aliases, and wildcards
                if col in ("*", "") or "(" in col or col.isdigit():
                    continue
                # If column has table prefix, check if it matches
                if "." in col:
                    parts = col.split(".")
                    tbl, col_name = parts[0], parts[1]
                    if (
                        tbl.lower() == table.lower()
                        and col_name.lower() not in column_names
                    ):
                        result["warnings"].append(
                            f"Column '{col_name}' may not exist in table '{actual_name}'"
                        )


def _extract_cte_names(sql: str) -> set[str]:
    """
    Extract CTE (Common Table Expression) alias names from WITH clauses.

    For example, given:
        WITH country_rev AS (...), top_countries AS (...)
        SELECT ...

    Returns: {'country_rev', 'top_countries'}

    These are virtual table names defined inline in the query — they do NOT
    need to exist as real database tables, so the schema checker must skip them.
    """
    sql_no_comments = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_comments, flags=re.DOTALL)

    cte_names: set[str] = set()

    # Match the alias name before each AS ( in a WITH block.
    # Pattern: WITH <name> AS (...), <name> AS (...), ...
    # We match both the first CTE after WITH and subsequent ones after commas.
    pattern = r'(?:(?:\bWITH\b|,)\s*)(\w+)\s+AS\s*\('
    for m in re.finditer(pattern, sql_no_comments, re.IGNORECASE):
        cte_names.add(m.group(1).lower())

    return cte_names


def _extract_tables_from_sql(sql: str) -> list[str]:
    """
    Extract table names referenced in FROM and JOIN clauses.
    Uses regex-based extraction.  CTE alias names are excluded because
    they are virtual tables defined within the query itself.
    """
    # Remove SQL comments before extraction to avoid false positives
    # e.g. "-- Assuming the question is asking for conditions from last year"
    sql_no_comments = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_comments, flags=re.DOTALL)
    
    tables = set()

    # Match FROM <table> and JOIN <table>
    patterns = [
        r'\bFROM\s+(\w+)',
        r'\bJOIN\s+(\w+)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, sql_no_comments, re.IGNORECASE)
        tables.update(matches)

    # Remove SQL keywords that might be falsely matched
    sql_keywords = {
        "select", "where", "and", "or", "not", "in", "on",
        "as", "by", "asc", "desc", "limit", "offset", "group",
        "order", "having", "union", "case", "when", "then",
        "else", "end", "between", "like", "is", "null",
    }
    tables = {t for t in tables if t.lower() not in sql_keywords}

    # Exclude CTE alias names — they are virtual, not real database tables
    cte_names = _extract_cte_names(sql)
    tables = {t for t in tables if t.lower() not in cte_names}

    return list(tables)


def _extract_columns_from_sql(sql: str) -> list[str]:
    """
    Extract potential column names from a SQL query.
    Returns a list of column references found.
    """
    # This is a simplified extraction — catches most common patterns
    # Match: table.column, standalone column names in SELECT/WHERE/GROUP BY
    pattern = r'(?:\w+\.)?(\w+)'
    matches = re.findall(pattern, sql)

    # Filter out SQL keywords and common noise
    sql_noise = {
        "select", "from", "where", "and", "or", "not", "in",
        "join", "on", "as", "by", "group", "order", "having",
        "asc", "desc", "limit", "offset", "inner", "left",
        "right", "outer", "cross", "sum", "count", "avg",
        "min", "max", "distinct", "between", "like", "is",
        "null", "case", "when", "then", "else", "end",
        "date", "now", "cast", "coalesce", "ifnull",
        "true", "false", "union", "all", "exists",
    }

    columns = [m for m in matches if m.lower() not in sql_noise]
    return list(set(columns))
