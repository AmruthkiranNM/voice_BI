"""
SQL Generator Agent

Generates SQL queries from natural language using:
  - The original user query
  - The structured plan from the Planner Agent
  - The retrieved schema context from the RAG Agent

Uses LLM to produce accurate, schema-aware SQL.
"""

import logging
from datetime import datetime

from services.llm_service import call_llm

logger = logging.getLogger(__name__)

SQL_GENERATION_PROMPT = """You are an expert SQL Generator Agent for a Business Intelligence system.

Your task is to generate a valid SQLite SQL query based on:
1. The user's natural language question
2. A structured plan
3. The actual database schema (retrieved via RAG)

CRITICAL RULES:
- Generate ONLY a SELECT query. Never generate INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use ONLY the tables and columns shown in the schema below. Do NOT invent tables or columns.
- For date filtering, use SQLite date functions like date('now', '-1 month').
- For monthly/yearly trends, if columns like MONTH_ID and YEAR_ID exist, prioritize grouping by them. If not, use strftime('%Y-%m', date_column) for SQLite.
- Today's date is {today}.
- Use proper JOINs when data spans multiple tables.
- Use aliases for readability.
- Output ONLY the raw SQL query — no markdown, no explanation, no code fences.

═══════════════════════════════════════
USER QUERY: {query}
═══════════════════════════════════════

EXECUTION PLAN:
{plan_text}

═══════════════════════════════════════

DATABASE SCHEMA (from RAG retrieval):
{schema_context}

═══════════════════════════════════════

Generate the SQL query now:"""


def run(query: str, plan: dict, rag_context: dict) -> str:
    """
    Generate a SQL query using the LLM with full context.

    Args:
        query: Original natural language query.
        plan: Structured plan from the Planner Agent.
        rag_context: Schema context from the RAG Agent.

    Returns:
        Generated SQL query string.
    """
    logger.info("[SQL Agent] Generating SQL for: %s", query[:80])

    # Format the plan for the prompt
    plan_text = _format_plan(plan)
    schema_context = rag_context.get("schema_context", "No schema available.")
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = SQL_GENERATION_PROMPT.format(
        query=query,
        plan_text=plan_text,
        schema_context=schema_context,
        today=today,
    )

    # Call LLM
    sql = call_llm(prompt, expect_json=False)

    # Clean the SQL output
    sql = _clean_sql(sql)

    logger.info("[SQL Agent] Generated SQL: %s", sql[:200])
    return sql


def _format_plan(plan: dict) -> str:
    """Format the plan dict into readable text for the prompt."""
    lines = []
    lines.append(f"Intent: {plan.get('intent', 'unknown')}")
    lines.append(f"Metrics: {', '.join(plan.get('metrics', ['unknown']))}")

    filters = plan.get("filters", {})
    for key, value in filters.items():
        if value and value != "null":
            lines.append(f"Filter - {key}: {value}")

    grouping = plan.get("grouping")
    if grouping:
        lines.append(f"Grouping: {grouping}")

    steps = plan.get("steps", [])
    if steps:
        lines.append("Steps:")
        for i, step in enumerate(steps, 1):
            lines.append(f"  {i}. {step}")

    return "\n".join(lines)


def _clean_sql(sql: str) -> str:
    """
    Clean LLM output to extract just the SQL query.
    Removes markdown code fences, explanatory text, and trailing semicolons issues.
    """
    import re

    # Remove markdown code blocks
    sql = re.sub(r"```sql\s*", "", sql)
    sql = re.sub(r"```\s*", "", sql)

    # Remove lines that look like explanatory text (not SQL)
    lines = sql.strip().split("\n")
    sql_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip empty lines and obvious non-SQL explanatory text
        if not stripped:
            continue
        # If it starts with common non-SQL patterns, skip
        if stripped.startswith(("Here", "This", "The ", "Note:", "Explanation")):
            continue
        sql_lines.append(line)

    sql = "\n".join(sql_lines).strip()

    # Ensure it ends with a semicolon
    if sql and not sql.endswith(";"):
        sql += ";"

    return sql
