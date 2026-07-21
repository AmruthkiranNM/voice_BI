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
- Column names come from the owner's CSV — match them EXACTLY. Many contain spaces (e.g. "Date of Admission"). Never replace spaces with underscores or rename columns. Wrap any column name containing a space or special character in double quotes, e.g. strftime('%Y-%m', "Date of Admission").
- COUNT vs SUM — read the question carefully:
  * "how many", "number of", "count of" → COUNT(*) (counting rows/records). "How many sales/orders" means COUNT(*), NOT SUM of an amount.
  * "total", "sum of", "combined", "how much revenue/money" → SUM(<value column>).
  * "average", "mean" → AVG(<value column>). "highest"/"lowest"/"maximum"/"minimum" → MAX/MIN.
- Before using AVG/SUM/MAX/MIN on a column, check its type in the schema below. NEVER aggregate a TEXT/VARCHAR column numerically — AVG() or SUM() on text silently returns 0, which is wrong. If the question asks for an "average"/"total" of a column that is actually categorical text (e.g. a size label like Small/Medium/Large, a Yes/No flag, a status), there is no numeric average — instead return a breakdown: SELECT <category_column>, COUNT(*) AS count ... GROUP BY <category_column> (combined with any other requested grouping, e.g. country).
- Only add a date/time WHERE filter when the question names a period (e.g. "last month", "this year"). For general "over time" / "trend" questions, include ALL rows — do NOT filter to recent dates.
- RELATIVE vs NAMED periods — do not confuse them:
  * RELATIVE to today (e.g. "last month", "this year", "past 7 days") → filter with date('now', ...), e.g. date_column >= date('now', '-1 month').
  * NAMED calendar periods with no year given (e.g. "in April", "the month of May", "in Q1") → these refer to the calendar month/quarter itself, NOT a rolling window from today. Filter with strftime('%m', date_column) = '04' (April = '04', May = '05', etc.), never date('now', ...). The data may be from any year — do not restrict by year unless one is stated.
- For date filtering, use SQLite date functions like date('now', '-1 month') only for RELATIVE periods.
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
    pinned_tables = rag_context.get("pinned_tables") or (
        [rag_context["pinned_table"]] if rag_context.get("pinned_table") else None
    )
    if pinned_tables:
        if len(pinned_tables) == 1:
            scope = f"the table [{pinned_tables[0]}]"
        else:
            names = ", ".join(f"[{t}]" for t in pinned_tables)
            scope = f"ONLY these tables: {names} (JOIN across them when the question needs data from more than one)"
        schema_context = (
            f"IMPORTANT: Query {scope}. "
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
    sql = _repair_columns(sql, rag_context)
    sql = _fix_text_aggregates(sql, rag_context)
    logger.info("[SQL Agent] Generated SQL: %s", sql[:200])
    return sql


def _scope_tables(rag_context: dict) -> list[str]:
    """Tables the SQL may reference: the pinned source scope, else retrieved, else all."""
    from services.database import get_all_table_names

    return (
        rag_context.get("pinned_tables")
        or ([rag_context["pinned_table"]] if rag_context.get("pinned_table") else None)
        or rag_context.get("retrieved_tables")
        or get_all_table_names()
    )


def _repair_columns(sql: str, rag_context: dict) -> str:
    """
    Deterministically fix the most common LLM mistake on multi-word columns:
    rewriting "Medical Condition" as Medical_Condition or MedicalCondition.
    Small local models do this even when told not to, so we repair against the
    real schema rather than trusting the prompt. Any identifier (bare, quoted,
    or bracketed) whose normalised form matches a real multi-word column is
    replaced with the correctly-quoted real name.
    """
    import re
    from services.database import get_table_schema, get_all_table_names

    tables = _scope_tables(rag_context)
    cols = [c["column_name"] for t in tables for c in get_table_schema(t)]

    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

    # 1. Quote bare multi-word real names the model left unquoted
    #    (SELECT Medical Condition -> SELECT "Medical Condition").
    for c in cols:
        if " " in c:
            sql = re.sub(r'(?<!["\[\w])' + re.escape(c) + r'(?!["\]\w])', f'"{c}"', sql)

    # 2. Map normalised forms of real columns AND any alias the model declared
    #    (AS "Blood Group"), so self-mangled references resolve back.
    real_by_norm = {norm(c): c for c in cols if " " in c or not c.isalnum()}
    for alias in re.findall(r'\bAS\s+"([^"]+)"', sql, flags=re.IGNORECASE):
        real_by_norm.setdefault(norm(alias), alias)
    if not real_by_norm:
        return sql

    token_re = re.compile(r'(["\[])([^"\]]+)["\]]|\b([A-Za-z_][A-Za-z0-9_]*)\b')

    def repl(m):
        inner = m.group(2) if m.group(2) is not None else m.group(3)
        real = real_by_norm.get(norm(inner))
        return f'"{real}"' if real and real != inner else m.group(0)

    return token_re.sub(repl, sql)


def _fix_text_aggregates(sql: str, rag_context: dict) -> str:
    """
    AVG()/SUM() on a TEXT column (e.g. a Small/Medium/Large size label) never
    errors in SQLite — it silently evaluates to 0, producing a confident but
    fabricated answer. Small local models keep doing this despite prompt
    instructions, so swap the numeric aggregate for GROUP_CONCAT(DISTINCT ...),
    which reports the actual categories instead of a lying zero.
    """
    import re
    from services.database import get_table_schema

    tables = _scope_tables(rag_context)
    text_cols = {
        c["column_name"]
        for t in tables
        for c in get_table_schema(t)
        if (c.get("data_type") or "").upper() in ("TEXT", "VARCHAR", "CHAR", "STRING", "")
    }
    if not text_cols:
        return sql

    def repl(m):
        func, col = m.group(1), m.group(2).strip('"[]')
        if col in text_cols:
            return f'GROUP_CONCAT(DISTINCT {m.group(2)})'
        return m.group(0)

    return re.sub(r'\b(AVG|SUM)\(\s*([\w."\[\]]+)\s*\)', repl, sql, flags=re.IGNORECASE)


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
