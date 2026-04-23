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


class ValidationError(Exception):
    """Raised when SQL validation fails."""

    def __init__(self, reason: str, violation_type: str):
        self.reason = reason
        self.violation_type = violation_type  # "security" or "schema"
        super().__init__(reason)


def run(
    sql: str, retrieved_tables: list[str] | None = None
) -> dict[str, Any]:
    """
    Validate a SQL query for security and schema correctness.

    Args:
        sql: The SQL query to validate.
        retrieved_tables: Tables retrieved by RAG (for contextual validation).

    Returns:
        Dictionary with validation status and details.

    Raises:
        ValidationError: If the SQL fails any check.
    """
    logger.info("[Validator Agent] Validating SQL: %s", sql[:120])

    result = {
        "is_valid": True,
        "security_check": "passed",
        "schema_check": "passed",
        "warnings": [],
        "validated_sql": sql,
    }

    # ── Step 1: Security Validation ──
    _check_security(sql)
    logger.info("[Validator Agent] Security check passed.")

    # ── Step 2: Ensure it's a SELECT statement ──
    _check_select_only(sql)
    logger.info("[Validator Agent] SELECT-only check passed.")

    # ── Step 3: Schema Validation ──
    warnings = _check_schema(sql, retrieved_tables)
    if warnings:
        result["warnings"] = warnings
        logger.warning("[Validator Agent] Schema warnings: %s", warnings)

    logger.info("[Validator Agent] Validation complete — SQL is safe.")
    return result


def _check_security(sql: str) -> None:
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
            raise ValidationError(
                reason=f"Blocked SQL keyword detected: '{keyword}'. "
                       f"Only SELECT queries are allowed.",
                violation_type="security",
            )

    # Check for multiple statements (semicolon injection)
    # Remove trailing semicolon first, then check for others
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValidationError(
            reason="Multiple SQL statements detected. Only single SELECT queries are allowed.",
            violation_type="security",
        )


def _check_select_only(sql: str) -> None:
    """Ensure the query is a SELECT statement."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        raise ValidationError(
            reason=f"Query must start with SELECT. Got: '{stripped[:20]}...'",
            violation_type="security",
        )


def _check_schema(
    sql: str, retrieved_tables: list[str] | None = None
) -> list[str]:
    """
    Validate that tables and columns referenced in SQL exist in the database.

    Returns a list of warning messages (non-fatal).
    """
    warnings = []
    db_tables = get_all_table_names()
    db_tables_lower = {t.lower() for t in db_tables}

    # Extract table names from SQL (basic extraction from FROM and JOIN clauses)
    sql_tables = _extract_tables_from_sql(sql)

    for table in sql_tables:
        if table.lower() not in db_tables_lower:
            raise ValidationError(
                reason=f"Table '{table}' does not exist in the database. "
                       f"Available tables: {db_tables}",
                violation_type="schema",
            )

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
                        warnings.append(
                            f"Column '{col_name}' may not exist in table '{actual_name}'"
                        )

    return warnings


def _extract_tables_from_sql(sql: str) -> list[str]:
    """
    Extract table names referenced in FROM and JOIN clauses.
    Uses regex-based extraction.
    """
    tables = set()

    # Match FROM <table> and JOIN <table>
    patterns = [
        r'\bFROM\s+(\w+)',
        r'\bJOIN\s+(\w+)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, sql, re.IGNORECASE)
        tables.update(matches)

    # Remove SQL keywords that might be falsely matched
    sql_keywords = {
        "select", "where", "and", "or", "not", "in", "on",
        "as", "by", "asc", "desc", "limit", "offset", "group",
        "order", "having", "union", "case", "when", "then",
        "else", "end", "between", "like", "is", "null",
    }
    tables = {t for t in tables if t.lower() not in sql_keywords}

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
