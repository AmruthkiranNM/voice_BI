"""
SQL Generator Agent

Generates SQL queries from natural language using plan + RAG schema context.
Supports error-feedback retries when a previous attempt failed validation or execution.
"""

import logging
import re
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
- CATEGORICAL FILTERS — the schema lists the exact values that exist for certain text columns (e.g. Category is one of: Bars, Bites, Other). When the question names a term that matches ONE of those values (e.g. "bars"), add WHERE <column> = '<that one matching value>'. Never add an IN(...) list of every possible value for that column — that is not a filter, and matching all values is equivalent to not filtering at all, which is wrong when the question named a specific one.
- Before using AVG/SUM/MAX/MIN on a column, check its type in the schema below. NEVER aggregate a TEXT/VARCHAR column numerically — AVG() or SUM() on text silently returns 0, which is wrong. If the question asks for an "average"/"total" of a column that is actually categorical text (e.g. a size label like Small/Medium/Large, a Yes/No flag, a status), there is no numeric average — instead return a breakdown: SELECT <category_column>, COUNT(*) AS count ... GROUP BY <category_column> (combined with any other requested grouping, e.g. country).
- Only add a date/time WHERE filter when the question names a period (e.g. "last month", "this year"). For general "over time" / "trend" questions, include ALL rows — do NOT filter to recent dates.
- RELATIVE vs NAMED periods — do not confuse them:
  * RELATIVE to today (e.g. "last month", "this year", "past 7 days") → use the literal windows listed under DATA COVERAGE, or anchor on the literal date, e.g. date_column >= date('{today}', '-30 days'). Never date('now', ...).
  * NAMED calendar periods with no year given (e.g. "in April", "the month of May", "in Q1") → these refer to the calendar month/quarter itself, NOT a rolling window from today. Filter with strftime('%m', date_column) = '04' (April = '04', May = '05', etc.), never date('now', ...). The data may be from any year — do not restrict by year unless one is stated.
- For date filtering, anchor SQLite date functions on the literal date, e.g. date('{today}', '-30 days'), and only for RELATIVE periods.
- For trends, use strftime('%Y-%m', date_column) when grouping by month.
- When grouping by day of week or month, return the NAME, not the number, so the answer is readable. Day of week:
  CASE strftime('%w', date_column) WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' ELSE 'Saturday' END AS day_of_week
- For COMPARISONS (vs, compare, growth, difference, best vs worst):
  * Use GROUP BY for side-by-side category comparisons.
  * For time comparisons, filter two periods with CASE WHEN or separate subqueries.
  * For growth %, compute: ROUND(100.0 * (new - old) / NULLIF(old, 0), 2) AS growth_pct.
  * For ranking, use ORDER BY ... DESC LIMIT N.
- Today's date is {today} (the latest date present in this data).
{coverage_block}
- MULTIPLE ANALYTICAL QUESTIONS (COMPOUND QUERIES):
  * You may use multiple CTEs inside one WITH statement to solve multi-step analytical requests.
  * You MUST return exactly one PostgreSQL SELECT/WITH statement.
  * Never return multiple SELECT statements.
  * Never separate statements using semicolons.
  * If the user asks multiple analytical subquestions that can be represented in one relational result, combine them using CTEs and UNION ALL. (e.g. Add a 'result_type' column to distinguish rows from different parts of the question).
  * If they cannot be represented in one result, do your best to combine them, but never output two independent SELECT statements.
- LIMIT RULES:
  * Do not automatically assume plural nouns (like "bars") mean exactly one result with LIMIT 1.
  * If the question asks for "highest selling bar" (singular), LIMIT 1 is appropriate.
  * If the question asks for "highest selling bars" (plural), return the ranked set without a LIMIT, unless an explicit number is given (e.g. "top 3").
- OPAQUE COLUMNS: never assume a column with a meaningless name (m1, col3, x, var_2, field7) holds a specific measure the question names (balance, age, salary). If the only candidate is such a column, the measure is not recorded (see next rule).
- MEASURES THE DATA DOES NOT RECORD: if the question asks for a measure that no column records and that cannot be computed by a standard, unambiguous formula from the columns (e.g. churn with no churn/exited/status column, profit or margin with no cost column, ratings with no rating column), do NOT invent a definition from proxy columns (e.g. treating a fall in a customer count as churn) and do NOT fill it with a constant. Instead output exactly: NOT_IN_DATA: <the measure>
- Output ONLY the raw SQL query (or the NOT_IN_DATA line) — no markdown, no explanation, no code fences.
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
    # "Today" means the last date the data knows about. Anchoring relative
    # periods to the wall clock is what makes "last quarter" filter to a window
    # an uploaded extract has never contained, returning nothing. The wall
    # clock is only a fallback for a dataset with no date column at all.
    from services import time_context

    cov = time_context.coverage(pinned_tables or rag_context.get("retrieved_tables"))
    today = cov.anchor or datetime.now().strftime("%Y-%m-%d")
    coverage_block = time_context.prompt_block(cov)

    detected_filters = _detect_categorical_filters(query, rag_context)
    if detected_filters:
        by_col: dict[tuple[str, str], list[str]] = {}
        for t, c, v in detected_filters:
            by_col.setdefault((t, c), []).append(v)
        # Several names in one column ("After Nines and Milk Bars") are
        # alternatives, never conditions that must all hold at once.
        lines = "\n".join(
            f"  - WHERE {t}.{c} = '{vs[0]}'" if len(vs) == 1
            else f"  - WHERE {t}.{c} IN (" + ", ".join(f"'{v}'" for v in vs) + ")"
            for (t, c), vs in by_col.items()
        )
        plan_text += (
            f"\n\nDETECTED FILTERS — the question names these exact category values; "
            f"apply them as WHERE conditions (do not also filter to any of that "
            f"column's other values):\n{lines}"
        )

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
        coverage_block=coverage_block,
        retry_section=retry_section,
    )

    sql = _clean_sql(call_llm(prompt, expect_json=False))
    sql = _repair_columns(sql, rag_context)
    sql = _fix_text_aggregates(sql, rag_context)
    sql = _fix_integer_division(sql)
    sql = _ensure_filter_tables_joined(sql, detected_filters, rag_context)
    logger.info("[SQL Agent] Generated SQL: %s", sql[:200])
    return sql


def _ensure_filter_tables_joined(
    sql: str, detected_filters: list[tuple[str, str, str]], rag_context: dict,
) -> str:
    """
    A detected categorical filter (e.g. products.category = 'Bars') is useless
    if the model referenced that table in WHERE but forgot to JOIN it — SQLite
    then errors with "no such column", and at low temperature the retry loop
    tends to regenerate the same SQL. Deterministically add any missing JOIN
    using the same shared-column heuristic already used for join hints.
    """
    import re
    from services.database import get_table_schema

    if not detected_filters:
        return sql

    from_join_tables = set(re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE))
    needed_tables = {t for t, _, _ in detected_filters}
    missing = needed_tables - from_join_tables
    if not missing:
        return sql

    cols_by_table = {
        t: {c["column_name"] for c in get_table_schema(t)}
        for t in from_join_tables | missing
    }

    insert_point = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
    if not insert_point:
        return sql

    join_clauses = []
    for missing_table in missing:
        for present_table in from_join_tables:
            shared = sorted(cols_by_table.get(missing_table, set()) & cols_by_table.get(present_table, set()))
            shared = [c for c in shared if c.lower() not in ("id", "name")]
            if shared:
                join_clauses.append(
                    f"JOIN {missing_table} ON {present_table}.{shared[0]} = {missing_table}.{shared[0]}\n"
                )
                from_join_tables.add(missing_table)
                break

    if not join_clauses:
        return sql

    idx = insert_point.start()
    return sql[:idx] + "".join(join_clauses) + sql[idx:]


#: Most distinct values a text column may have for its values to be matched
#: as names in a question (beyond that it is free text, not a name column).
_NAME_COLUMN_MAX = 500


def _detect_categorical_filters(query: str, rag_context: dict) -> list[tuple[str, str, str]]:
    """
    Deterministically match words in the question against known low-cardinality
    column values (e.g. Category: Bars/Bites/Other), so a category or region
    name in the question always becomes an explicit WHERE condition instead of
    depending on a small local model to infer it from prose alone.

    Returns a list of (table, column, value) tuples.
    """
    import re
    from services.database import get_low_cardinality_values, get_table_schema

    q_lower = " ".join(re.findall(r"[a-z0-9&']+", query.lower()))
    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))

    def word_forms(word: str) -> set[str]:
        forms = {word}
        if word.endswith("ies"):
            forms.add(word[:-3] + "y")
        elif word.endswith("es"):
            forms.add(word[:-2])
        if word.endswith("s") and not word.endswith("ss"):
            forms.add(word[:-1])
        return forms

    tables = _scope_tables(rag_context)
    small = {t: get_low_cardinality_values(t, schema=get_table_schema(t)) for t in tables}

    # Pass 1 - larger name columns (products, people: more values than the
    # schema context lists), matched only on the value's full name as an
    # exact phrase, so ordinary words in a question never become a filter.
    name_matches = []
    for table in tables:
        for col, values in get_low_cardinality_values(
            table, schema=get_table_schema(table), max_distinct=_NAME_COLUMN_MAX,
        ).items():
            if col in small[table]:
                continue
            for value in values:
                name = " ".join(re.findall(r"[a-z0-9&']+", value.lower()))
                if len(name) < 4 or not re.search(r"[a-z]", name):
                    continue
                if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", q_lower):
                    name_matches.append((table, col, value, name))
    # A longer name beats one it contains ("Milk Bars" over "Milk").
    name_matches = [m for m in name_matches
                    if not any(o is not m and o[1] == m[1] and m[3] in o[3] and len(o[3]) > len(m[3])
                               for o in name_matches)]

    # Words inside a matched name belong to that name: "bars" in "Milk Bars"
    # is not also a request for the Bars category.
    rest = q_lower
    for *_, name in name_matches:
        rest = re.sub(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", " ", rest)
    query_words = set(re.findall(r"[a-z0-9]+", rest))

    # Pass 2 - small category-like columns, word by word.
    matches = []
    for table in tables:
        for col, values in small[table].items():
            for value in values:
                value_words = re.findall(r"[a-z0-9]+", value.lower())
                if value_words and all(query_words & word_forms(vw) for vw in value_words):
                    matches.append((table, col, value))

    return matches + [(t, c, v) for t, c, v, _ in name_matches]


_AGG_CALL = re.compile(r"\b(SUM|COUNT|TOTAL|MAX|MIN)\s*\(", re.IGNORECASE)


def _fix_integer_division(sql: str) -> str:
    """
    SQLite divides integers as integers: SUM(exited) / COUNT(*) is 0 or 1,
    never 0.2. Any aggregate that is the left side of a division is made
    real (1.0 * SUM(...)) so a rate keeps its fraction. Already-real
    expressions are unchanged in value.
    """
    out, i = [], 0
    for m in _AGG_CALL.finditer(sql):
        if m.start() < i:
            continue
        depth, j = 0, m.end() - 1
        while j < len(sql):
            depth += sql[j] == "("
            depth -= sql[j] == ")"
            if depth == 0:
                break
            j += 1
        after = sql[j + 1:].lstrip()
        before = sql[i:m.start()]
        if after.startswith("/") and not re.search(r"(\d\.\d*|\.\d+)\s*\*\s*$", before):
            out.append(before + "1.0 * " + sql[m.start():j + 1])
        else:
            out.append(before + sql[m.start():j + 1])
        i = j + 1
    out.append(sql[i:])
    return "".join(out)


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

    sql = re.sub(r"<think>.*?</think>", "", sql, flags=re.DOTALL | re.IGNORECASE)
    sql = re.sub(r"```sql\s*", "", sql)
    sql = re.sub(r"```\s*", "", sql)

    sql_lines = []
    for line in sql.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("Here", "This", "The ", "Note:", "Explanation", "Let's", "Let us")):
            continue
        # Reasoning preambles from chatty models: numbered/bulleted prose lines
        # ("1. **Identify the Tables**: ...") before the actual SQL starts.
        if re.match(r"^(\d+\.|[-*])\s", stripped) and not re.match(
            r"^(SELECT|FROM|WHERE|JOIN|GROUP|ORDER|HAVING|LIMIT|AND|OR|ON)\b",
            stripped, re.IGNORECASE,
        ):
            continue
        sql_lines.append(line)

    sql = "\n".join(sql_lines).strip()
    # If a SQL statement starts partway through, drop everything before it.
    match = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
    if match:
        sql = sql[match.start():]
    if sql and not sql.endswith(";"):
        sql += ";"
    return sql
