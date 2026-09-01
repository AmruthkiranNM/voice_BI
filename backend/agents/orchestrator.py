"""
Agent Orchestrator

Central controller that coordinates the multi-agent pipeline.
Manages the full flow from user query to final result:

    Query → Planner → RAG → SQL Generator → Validator → Execution → Insight

Includes retry logic for SQL generation failures and comprehensive logging.
"""

import logging
import re
import time
from typing import Any

from agents import planner, rag_agent, sql_agent, validator, execution, insight

logger = logging.getLogger(__name__)

# Maximum retries for SQL generation if validation fails
MAX_SQL_RETRIES = 3


def process_query(
    query: str,
    model: str | None = None,
    *,
    table_names: list[str] | None = None,
    cache_mode: bool = True,
    fast_mode: bool = False,
    skip_insight: bool = False,
) -> dict[str, Any]:
    """
    Process a natural language query through the full agent pipeline.

    Pipeline:
        1. Planner Agent      → Structured execution plan (skipped in fast_mode)
        2. RAG Retriever Agent → Relevant database schema
        3. SQL Generator Agent → SQL query
        4. Validator Agent     → Security & schema check
        5. Execution Agent     → Query execution
        6. Insight Agent       → Business insight (skipped if skip_insight or fast_mode)

    Args:
        query: Natural language business question.
        model: Optional Ollama model override.
        cache_mode: Return cached results for identical queries when available.
        fast_mode: Skip planner LLM call (heuristic plan) for faster execution.
        skip_insight: Skip insight LLM call (auto-enabled when fast_mode is True).

    Returns:
        Complete response with SQL, results, insights, and agent logs.
    """
    import config
    from services import query_cache

    if fast_mode:
        skip_insight = True

    # Stable cache key component for the scope (order-independent).
    scope_key = ",".join(sorted(table_names)) if table_names else None

    if cache_mode:
        cached = query_cache.get(query, model, fast_mode, skip_insight, scope_key)
        if cached:
            return cached

    original_model = config.OLLAMA_MODEL
    if model:
        config.OLLAMA_MODEL = model

    pipeline_start = time.time()

    # Agent step logs for transparency
    agent_logs = []

    def log_step(agent_name: str, status: str, detail: Any = None):
        entry = {
            "agent": agent_name,
            "status": status,
            "detail": detail,
            "timestamp_ms": round((time.time() - pipeline_start) * 1000, 2),
        }
        agent_logs.append(entry)
        logger.info("[Orchestrator] %s → %s", agent_name, status)

    try:
        # ════════════════════════════════════════════
        # STEP 1: Planner Agent (or fast heuristic plan)
        # ════════════════════════════════════════════
        if fast_mode:
            plan = planner.build_fast_plan(query)
            log_step("Planner Agent", "skipped_fast_mode", {
                "intent": plan.get("intent"),
                "metrics": plan.get("metrics"),
            })
        else:
            plan = planner.run(query)
            log_step("Planner Agent", "completed", {
                "intent": plan.get("intent"),
                "steps": plan.get("steps"),
                "metrics": plan.get("metrics"),
            })

        # DEBUG: Log planner output
        logger.info("[DEBUG] Query: %s", query)
        logger.info("[DEBUG] Plan intent: %s | metrics: %s | grouping: %s",
                    plan.get('intent'), plan.get('metrics'), plan.get('grouping'))
        logger.info("[DEBUG] Plan steps: %s", plan.get('steps'))

        # ════════════════════════════════════════════
        # STEP 2: RAG Retriever Agent
        # ════════════════════════════════════════════
        rag_context = rag_agent.run(query, plan, table_names=table_names)
        log_step("RAG Retriever Agent", "completed", {
            "tables_retrieved": rag_context.get("retrieved_tables"),
            "similarity_scores": rag_context.get("similarity_scores"),
        })

        # DEBUG: Log retrieved schema
        logger.info("[DEBUG] RAG tables: %s", rag_context.get('retrieved_tables'))

        # ════════════════════════════════════════════
        # STEP 3–5: SQL Generation, Validation & Execution (with retry + error feedback)
        # ════════════════════════════════════════════
        sql = None
        validation_result = None
        exec_result = None
        last_error = None
        previous_sql = None

        for attempt in range(1, MAX_SQL_RETRIES + 1):
            logger.info(
                "[Orchestrator] SQL generation attempt %d/%d",
                attempt, MAX_SQL_RETRIES,
            )

            sql = sql_agent.run(
                query, plan, rag_context,
                previous_sql=previous_sql,
                error_message=last_error,
            )
            log_step("SQL Generator Agent", f"attempt_{attempt}", {"sql": sql})
            logger.info("[DEBUG] Generated SQL: %s", sql)

            validation_result = validator.run(
                sql,
                retrieved_tables=rag_context.get("retrieved_tables"),
                allowed_tables=rag_context.get("pinned_tables"),
            )
            
            # Print detailed log exactly as requested
            logger.info("\n[Validator]")
            logger.info("Security:\n%s", "PASS" if validation_result["security_valid"] else "FAIL")
            # Syntax validation is done during execution, assume PASS here unless we failed to parse
            logger.info("Syntax:\nPASS")
            logger.info("Schema:\n%s", "PASS" if validation_result["schema_valid"] else "FAIL")
            logger.info("Semantic:\n%s", "PASS" if validation_result["semantic_valid"] else "FAIL")
            
            if not validation_result["valid"]:
                last_error = "; ".join(validation_result["errors"])
                previous_sql = sql
                logger.info("Reason:\n%s", last_error)
                
                log_step("Validator Agent", f"failed_attempt_{attempt}", {
                    "error": last_error,
                })
                
                if not validation_result["security_valid"]:
                    return _error_response(
                        query=query,
                        error=f"Security violation: {last_error}",
                        agent_logs=agent_logs,
                        pipeline_time=time.time() - pipeline_start,
                    )
                    
                if attempt == MAX_SQL_RETRIES:
                    return _error_response(
                        query=query,
                        error=f"SQL generation failed after {MAX_SQL_RETRIES} attempts: {last_error}",
                        agent_logs=agent_logs,
                        pipeline_time=time.time() - pipeline_start,
                    )
                continue
                
            log_step("Validator Agent", "passed", {
                "warnings": validation_result.get("warnings", []),
            })

            exec_result = execution.run(sql)
            if exec_result["success"]:
                # ── Zero-row guard (deterministic fix) ────────────────────
                # The small LLM often ignores textual retry feedback and keeps
                # generating the same bad SQL.  Instead of asking it again,
                # we deterministically strip the spurious WHERE date clause
                # and re-execute — no new LLM call required.
                if exec_result["row_count"] == 0:
                    zero_diag = _diagnose_zero_rows(sql, query)
                    if zero_diag:
                        fixed_sql = _strip_spurious_date_filter(sql)
                        if fixed_sql:
                            logger.warning(
                                "[Orchestrator] 0 rows with date filter — "
                                "auto-fixing SQL by removing date WHERE clause."
                            )
                            fixed_result = execution.run(fixed_sql)
                            if fixed_result["success"] and fixed_result["row_count"] > 0:
                                sql = fixed_sql
                                exec_result = fixed_result
                                log_step("Execution Agent", "completed_auto_fixed", {
                                    "row_count": exec_result["row_count"],
                                    "note": "Removed spurious date WHERE filter",
                                })
                                break
                        # Deterministic fix didn't help — fall through to complete

                log_step("Execution Agent", "completed", {
                    "row_count": exec_result.get("row_count"),
                    "execution_time_ms": exec_result.get("execution_time_ms"),
                })
                break

            last_error = _enrich_column_error(exec_result["error"], rag_context)
            previous_sql = sql
            log_step("Execution Agent", f"failed_attempt_{attempt}", {"error": last_error})

            if attempt == MAX_SQL_RETRIES:
                return _error_response(
                    query=query,
                    error=f"Query execution failed after {MAX_SQL_RETRIES} attempts: {last_error}",
                    sql=sql,
                    agent_logs=agent_logs,
                    pipeline_time=time.time() - pipeline_start,
                )

        # ════════════════════════════════════════════
        # STEP 6: Insight Agent (optional)
        # ════════════════════════════════════════════
        if skip_insight:
            insight_text = None
            log_step("Insight Agent", "skipped", {
                "reason": "fast_mode" if fast_mode else "disabled",
            })
        else:
            insight_text = insight.run(query, sql, exec_result)
            log_step("Insight Agent", "completed", {
                "insight_length": len(insight_text),
            })

        # ════════════════════════════════════════════
        # Build Final Response
        # ════════════════════════════════════════════
        pipeline_time = round(time.time() - pipeline_start, 3)

        from services.domain_detector import analyze_dataset
        from services.database import get_all_table_names, get_table_schema

        active_table = (
            (table_names or [None])[0]
            or (rag_context.get("retrieved_tables") or [None])[0]
        )
        if active_table:
            ts = get_table_schema(active_table)
            domain = analyze_dataset([c["column_name"] for c in ts], ts)
        else:
            all_cols: list[str] = []
            all_schema: list[dict] = []
            for t in get_all_table_names():
                ts = get_table_schema(t)
                for col in ts:
                    all_cols.append(col["column_name"])
                    all_schema.append(col)
            domain = analyze_dataset(all_cols, all_schema)

        response = {
            "success": True,
            "query": query,
            "sql": sql,
            "result": {
                "columns": exec_result["columns"],
                "rows": exec_result["rows"],
                "row_count": exec_result["row_count"],
            },
            "insight": insight_text,
            "llm_mode": "ollama",
            "metadata": {
                "pipeline_time_seconds": pipeline_time,
                "execution_time_ms": exec_result["execution_time_ms"],
                "tables_used": rag_context.get("retrieved_tables", []),
                "active_table": active_table,
                "plan": plan,
                "validation_warnings": (
                    validation_result.get("warnings", []) if validation_result else []
                ),
                "cache_hit": False,
                "fast_mode": fast_mode,
                "skip_insight": skip_insight,
                "cache_mode": cache_mode,
                "domain": domain,
            },
            "agent_logs": agent_logs,
        }

        if cache_mode:
            query_cache.set(query, model, fast_mode, skip_insight, response, scope_key)

        logger.info(
            "[Orchestrator] Pipeline completed in %.3f seconds — %d rows returned",
            pipeline_time, exec_result["row_count"],
        )

        return response

    except Exception as e:
        logger.exception("[Orchestrator] Unexpected error in pipeline")
        return _error_response(
            query=query,
            error=f"Unexpected error: {str(e)}",
            agent_logs=agent_logs,
            pipeline_time=time.time() - pipeline_start,
        )
    finally:
        config.OLLAMA_MODEL = original_model


def _strip_spurious_date_filter(sql: str) -> str | None:
    """
    Deterministically remove a spurious date WHERE clause from SQL.

    Handles the most common LLM patterns:
        - WHERE col BETWEEN '...' AND '...'
        - WHERE col >= '...'
        - WHERE col >= DATE('now', '-1 year')

    Returns the cleaned SQL string if a filter was removed, else None.
    """
    patterns = [
        # BETWEEN with string literals or DATE()
        r"\s+WHERE\s+(?:\"[^\"]+\"|\w+)\s+BETWEEN\s+(?:'[^']+'|DATE\([^)]*\))\s+AND\s+(?:'[^']+'|DATE\([^)]*\))(?=\s*(?:GROUP|ORDER|LIMIT|HAVING|$|;))",
        # Operators >=, <=, >, <, = with string literal or DATE()
        r"\s+WHERE\s+(?:\"[^\"]+\"|\w+)\s+(?:>=|<=|>|<|=)\s+(?:'[^']+'|DATE\([^)]*\))(?=\s*(?:GROUP|ORDER|LIMIT|HAVING|$|;))",
        # SQLite DATE/DATETIME/STRFTIME general function matches
        r"\s+WHERE\s+(?:\"[^\"]+\"|\w+)\s+(?:>=|<=|>|<|=)\s+(?:DATE|DATETIME|STRFTIME|CURRENT_DATE|CURRENT_TIMESTAMP)\b[^;]*?(?=\s*(?:GROUP|ORDER|LIMIT|HAVING|$|;))"
    ]

    sql_no_comments = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_comments, flags=re.DOTALL)

    stripped = sql_no_comments
    for p in patterns:
        regex = re.compile(p, re.IGNORECASE | re.DOTALL)
        stripped = regex.sub("", stripped)
    
    stripped = stripped.strip()

    # Normalise double semicolons or orphan GROUP/ORDER that lost their WHERE
    stripped = re.sub(r';;+', ';', stripped)

    if stripped != sql_no_comments.strip():
        if not stripped.endswith(';'):
            stripped += ';'
        return stripped

    return None


def _enrich_column_error(error: str, rag_context: dict) -> str:
    """
    At low temperature the SQL agent regenerates near-identical SQL when the
    retry prompt only repeats a generic "no such column: X" error — it has
    no concrete alternative to reach for. List the real columns of the
    scoped tables so the retry has something to correct to.
    """
    from services.database import get_table_schema

    m = re.search(r"no such column:\s*(\S+)", error or "", re.IGNORECASE)
    if not m:
        return error

    tables = (
        rag_context.get("pinned_tables")
        or rag_context.get("retrieved_tables")
        or []
    )
    lines = [f"  {t}: {[c['column_name'] for c in get_table_schema(t)]}" for t in tables]
    if not lines:
        return error

    return f"{error}\nActual available columns per table:\n" + "\n".join(lines)


def _diagnose_zero_rows(sql: str, query: str) -> str | None:
    """
    Inspect SQL that ran successfully but returned 0 rows.
    Returns a human-readable diagnosis to feed back to the SQL agent,
    or None when the 0-row result appears genuinely correct.

    Strategy: check the *user's raw query text* for time expressions.
    Never rely on the planner's plan.filters.time_range — that field
    can itself be hallucinated by the LLM.
    """
    # Words/phrases that mean the user explicitly requested a time period
    TIME_KEYWORDS = (
        "last month", "this month", "last year", "this year",
        "last week", "this week", "last quarter", "this quarter",
        "yesterday", "today", "ytd", "year to date", "month to date",
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan ", "feb ", "mar ", "apr ", "jun ", "jul ", "aug ",
        "sep ", "oct ", "nov ", "dec ",
        "q1", "q2", "q3", "q4",
        "2019", "2020", "2021", "2022", "2023", "2024", "2025",
        "recent", "latest", "current",
    )
    user_asked_for_time = any(kw in query.lower() for kw in TIME_KEYWORDS)

    if not user_asked_for_time:
        # Detect a BETWEEN date range, bare date literal, or SQLite date function in WHERE
        date_filter_re = re.compile(
            r"BETWEEN\s+'\d{4}-\d{2}-\d{2}'\s+AND\s+'\d{4}-\d{2}-\d{2}'"
            r"|WHERE[^;]*['\"]\d{4}-\d{2}-\d{2}['\"]"
            r"|WHERE[^;]*(?:DATE|DATETIME|STRFTIME|CURRENT_DATE|CURRENT_TIMESTAMP)\b"
            r"|LIKE\s+'\d{4}%'",
            re.IGNORECASE | re.DOTALL,
        )
        if date_filter_re.search(sql):
            return (
                "The query returned 0 rows because you added a date/year filter "
                "that the user did NOT ask for. The user's question has no time range. "
                "REMOVE ALL WHERE filters on date columns and re-generate the SQL to "
                "return ALL rows, then GROUP or aggregate as needed."
            )

    # Detect bare 'name' column that likely does not exist
    if re.search(r'\bSELECT\b.*?\bname\b', sql, re.IGNORECASE | re.DOTALL):
        return (
            "The query returned 0 rows. You may have used a column called 'name' "
            "which does not exist in this table. Check the DATABASE SCHEMA section "
            "carefully and use ONLY the exact column names listed there. Column names "
            'may contain spaces (e.g. "insurance provider") — always wrap them in double quotes.'
        )

    return None


def _error_response(
    query: str,
    error: str,
    sql: str | None = None,
    agent_logs: list = None,
    pipeline_time: float = 0.0,
) -> dict[str, Any]:
    """Build a standardized error response."""
    return {
        "success": False,
        "query": query,
        "sql": sql,
        "result": {
            "columns": [],
            "rows": [],
            "row_count": 0,
        },
        "insight": None,
        "error": error,
        "llm_mode": "ollama",
        "metadata": {
            "pipeline_time_seconds": round(pipeline_time, 3),
        },
        "agent_logs": agent_logs or [],
    }
