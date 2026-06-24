"""
SQL Generator Agent

Generates SQL queries from natural language using plan + RAG schema context.
Supports error-feedback retries when a previous attempt failed validation or execution.
"""

import logging
from datetime import datetime

from services.llm_service import call_llm

logger = logging.getLogger(__name__)

SQL_GENERATION_PROMPT = """You are an expert SQL Generator helping a business owner query their uploaded business data.

Generate a valid SQLite SELECT query based on:
1. The owner's natural language question
2. A structured analysis plan
3. The actual column names from their uploaded CSV (shown below)

CRITICAL RULES:
- Generate ONLY a SELECT query. Never generate INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use ONLY the tables and columns shown in the schema below. Do NOT invent tables or columns.
- Column names come from the owner's CSV — match them exactly (case may vary).
- COUNT vs SUM — read the question carefully:
  * "how many", "number of", "count of" → COUNT(*) (counting rows/records). "How many sales/orders" means COUNT(*), NOT SUM of an amount.
  * "total", "sum of", "combined", "how much revenue/money" → SUM(<value column>).
  * "average", "mean" → AVG(<value column>). "highest"/"lowest"/"maximum"/"minimum" → MAX/MIN.
- For date filtering, use SQLite date functions like date('now', '-1 month').
- For trends, use strftime('%Y-%m', date_column) when grouping by month.
- When grouping by day of week or month, return the NAME, not the number, so the answer is readable. Day of week:
  CASE strftime('%w', date_column) WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' ELSE 'Saturday' END AS day_of_week
- For COMPARISONS (vs, compare, growth, difference, best vs worst):
  * Use GROUP BY for side-by-side category comparisons.
  * For time comparisons, filter two periods with CASE WHEN or separate subqueries.
  * For growth %, compute: ROUND(100.0 * (new - old) / NULLIF(old, 0), 2) AS growth_pct.
  * For ranking, use ORDER BY ... DESC LIMIT N.
- Today's date is {today}.
- Use proper JOINs when data spans multiple tables.
- Output ONLY the raw SQL query — no markdown, no explanation, no code fences.
{retry_section}
═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

EXECUTION PLAN:
{plan_text}

═══════════════════════════════════════

DATABASE SCHEMA (from RAG retrieval):
{schema_context}

═══════════════════════════════════════

Generate the SQL query now:"""

RETRY_SECTION = """
⚠️ PREVIOUS ATTEMPT FAILED — FIX THE SQL:
Failed SQL: {previous_sql}
Error: {error_message}
Use ONLY valid columns/tables from the schema above. Do not repeat the same mistake.
"""


def run(
    query: str,
    plan: dict,
    rag_context: dict,
    *,
    previous_sql: str | None = None,
    error_message: str | None = None,
) -> str:
    """Generate a SQL query using the LLM with full context and optional error feedback."""
    logger.info("[SQL Agent] Generating SQL for: %s", query[:80])

    plan_text = _format_plan(plan)
    schema_context = rag_context.get("schema_context", "No schema available.")
    pinned = rag_context.get("pinned_table")
    if pinned:
        schema_context = (
            f"IMPORTANT: Query ONLY the table [{pinned}]. "
            f"Do not use any other table.\n\n{schema_context}"
        )
    today = datetime.now().strftime("%Y-%m-%d")

    retry_section = ""
    if previous_sql and error_message:
        retry_section = RETRY_SECTION.format(
            previous_sql=previous_sql,
            error_message=error_message,
        )

    prompt = SQL_GENERATION_PROMPT.format(
        query=query,
        plan_text=plan_text,
        schema_context=schema_context,
        today=today,
        retry_section=retry_section,
    )

    sql = _clean_sql(call_llm(prompt, expect_json=False))
    logger.info("[SQL Agent] Generated SQL: %s", sql[:200])
    return sql


def _format_plan(plan: dict) -> str:
    """Format the plan dict into readable text for the prompt."""
    lines = [
        f"Intent: {plan.get('intent', 'unknown')}",
        f"Metrics: {', '.join(plan.get('metrics', ['unknown']))}",
    ]

    if plan.get("requires_comparison"):
        lines.append("Comparison required: YES — produce side-by-side or period-over-period results")

    compare = plan.get("comparison_type")
    if compare:
        lines.append(f"Comparison type: {compare}")

    filters = plan.get("filters", {})
    for key, value in filters.items():
        if value and value != "null":
            lines.append(f"Filter - {key}: {value}")

    grouping = plan.get("grouping")
    if grouping:
        lines.append(f"Grouping: {grouping}")

    for i, step in enumerate(plan.get("steps", []), 1):
        lines.append(f"  Step {i}: {step}")

    return "\n".join(lines)


def _clean_sql(sql: str) -> str:
    """Clean LLM output to extract just the SQL query."""
    import re

    sql = re.sub(r"```sql\s*", "", sql)
    sql = re.sub(r"```\s*", "", sql)

    sql_lines = []
    for line in sql.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("Here", "This", "The ", "Note:", "Explanation")):
            continue
        sql_lines.append(line)

    sql = "\n".join(sql_lines).strip()
    if sql and not sql.endswith(";"):
        sql += ";"
    return sql
