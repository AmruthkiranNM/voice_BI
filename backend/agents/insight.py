"""
Insight Agent

Analyzes query results using LLM to generate human-readable
business insights and summaries. Transforms raw data into
actionable intelligence.

INTENT-AWARE: The response style is governed by the planner's
classified intent so the LLM never silently converts a detail/listing
query into a ranking, recommendation, or aggregation.
"""

import json
import logging
from typing import Any

from services.llm_service import call_llm
from services.database import get_all_table_names, get_table_schema
from services.domain_detector import analyze_dataset

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Intent-specific prompt templates
# ═══════════════════════════════════════════════════════════════════════

DETAIL_PROMPT_TEMPLATE = """You are a Data Presenter AI helping a business owner view their data.

Business type: {domain_label}

The owner asked for a DETAIL / LISTING of specific records. They do NOT want
analysis, ranking, recommendations, or business strategy — only the data they requested.

STRICT RULES — follow every one:
1. Write ONE short introductory sentence (e.g. "Here are the products sold by each salesperson.").
2. Do NOT rank, sort by importance, or identify "top", "best", "worst", "leading", or "lowest" items.
3. Do NOT calculate totals, averages, percentages, or shares unless the owner explicitly asked.
4. Do NOT generate recommendations, next steps, or business advice.
5. Do NOT say things like "X dominates…", "Y leads…", "Z tops…".
6. The first row is merely one example; do NOT claim it defines the entire query scope. Use general, plural terms (e.g., "each salesperson").
7. Use **bold** for key column names when mentioning them in your sentence.
8. Keep it to 1-3 sentences maximum. The table/data is shown separately.

{truncation_note}

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows{truncation_suffix}):
{results_text}

═══════════════════════════════════════

Write your brief data-presentation sentence now:"""


AGGREGATION_PROMPT_TEMPLATE = """You are a Business Advisor AI helping a business owner understand their data.

Business type: {domain_label}
Advisory focus: {insight_tone}

The owner asked for an AGGREGATION (total, sum, average, count). Focus on reporting
the computed numbers clearly.

RULES:
1. Speak directly to the business owner — use "your business", "your data".
2. Reference specific numbers from the results.
3. Highlight the most important finding first.
4. Keep it concise. Start with a one-sentence headline finding.
5. Use **bold** for key terms or numbers. Avoid technical jargon.
6. Only suggest a next step if the owner explicitly asked for recommendations.
7. If the result set is empty, explain what that means for their business.
8. Do NOT invent numbers that aren't in the results.

{truncation_note}

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows{truncation_suffix}):
{results_text}

═══════════════════════════════════════

Write the business analysis now:"""


COMPARISON_PROMPT_TEMPLATE = """You are a Business Advisor AI helping a business owner understand their data.

Business type: {domain_label}
Advisory focus: {insight_tone}

The owner asked for a COMPARISON between entities. Focus on contrasting the items they asked about.

RULES:
1. Speak directly to the business owner — use "your business", "your data".
2. Reference specific numbers from the results for each compared entity.
3. Highlight the key differences and similarities.
4. Keep it concise.
5. Use **bold** for key terms or numbers.
6. Do NOT introduce unrelated metrics or entities not in the results.
7. Only suggest next steps if the owner explicitly asked for recommendations.
8. Do NOT invent numbers that aren't in the results.

{truncation_note}

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows{truncation_suffix}):
{results_text}

═══════════════════════════════════════

Write the comparison analysis now:"""


TREND_PROMPT_TEMPLATE = """You are a Business Advisor AI helping a business owner understand their data.

Business type: {domain_label}
Advisory focus: {insight_tone}

The owner asked about a TREND or change over time. Focus on the time-series pattern.

RULES:
1. Speak directly to the business owner — use "your business", "your data".
2. Reference specific numbers and time periods from the results.
3. Describe the direction and magnitude of the trend.
4. Keep it concise.
5. Use **bold** for key terms or numbers.
6. Do NOT convert this into a ranking unless the owner asked for one.
7. Only suggest next steps if the owner explicitly asked for recommendations.
8. Do NOT invent numbers that aren't in the results.

{truncation_note}

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows{truncation_suffix}):
{results_text}

═══════════════════════════════════════

Write the trend analysis now:"""


COUNT_PROMPT_TEMPLATE = """You are a Data Presenter AI helping a business owner view their data.

Business type: {domain_label}

The owner asked a COUNT question ("how many"). Give a clear, direct numerical answer.

RULES:
1. State the count clearly and directly.
2. Use **bold** for the key number.
3. Keep it to 1-2 sentences.
4. Do NOT generate a large analysis, ranking, or recommendations.
5. Do NOT invent numbers that aren't in the results.

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows):
{results_text}

═══════════════════════════════════════

Write your answer now:"""


# Fallback for unknown intents — still guarded against unsolicited advice.
GENERAL_PROMPT_TEMPLATE = """You are a Business Advisor AI helping a business owner understand their data.

Business type: {domain_label}
Advisory focus: {insight_tone}

The owner uploaded their own business CSV and asked a question. Based on the query results,
write a clear analysis they can use to understand their data.

RULES:
1. Speak directly to the business owner — use "your business", "your data".
2. Reference specific numbers from the results.
3. Highlight the most important finding first.
4. Keep it concise. Start with a one-sentence headline finding.
5. Use **bold** for key terms or numbers. Avoid technical jargon.
6. If the result set is empty, explain what that means for their business.
7. Do NOT invent numbers that aren't in the results.
8. Only suggest recommendations if the owner explicitly asked for them.

{truncation_note}

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows{truncation_suffix}):
{results_text}

═══════════════════════════════════════

Write the business analysis now:"""


# ═══════════════════════════════════════════════════════════════════════
# Template selection map
# ═══════════════════════════════════════════════════════════════════════
_INTENT_TEMPLATES = {
    "detail": DETAIL_PROMPT_TEMPLATE,
    "aggregation": AGGREGATION_PROMPT_TEMPLATE,
    "comparison": COMPARISON_PROMPT_TEMPLATE,
    "trend": TREND_PROMPT_TEMPLATE,
    "count": COUNT_PROMPT_TEMPLATE,
}


def run(
    query: str,
    sql: str,
    execution_result: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> str:
    """
    Generate business insights from query results using LLM.

    The response style is governed by the planner's intent so detail queries
    receive listing-style answers and aggregation queries receive analysis.

    Args:
        query: Original natural language question.
        sql: The SQL query that was executed.
        execution_result: Results from the Execution Agent.
        plan: Structured plan from the Planner Agent (carries intent, metrics,
              grouping, requires_aggregation, requires_comparison).

    Returns:
        Human-readable insight string.
    """
    logger.info("[Insight Agent] Generating insights for: %s", query[:80])

    rows = execution_result.get("rows", [])
    row_count = execution_result.get("row_count", 0)
    is_truncated_by_limit = execution_result.get("is_truncated", False)

    # Handle empty results
    if row_count == 0:
        insight = (
            "No matching records were found in your data. Try broadening "
            "your question or check that your CSV contains the categories "
            "or dates you are asking about."
        )
        logger.info("[Insight Agent] No data — returning empty insight.")
        return insight

    # ── Determine intent ──
    plan = plan or {}
    intent = plan.get("intent", "").lower()
    requires_aggregation = plan.get("requires_aggregation", False)
    requires_comparison = plan.get("requires_comparison", False)

    logger.info(
        "[Insight Agent] Intent=%s | requires_aggregation=%s | requires_comparison=%s | rows=%d | truncated=%s",
        intent, requires_aggregation, requires_comparison, row_count, is_truncated_by_limit,
    )

    # ── Choose how many rows to include in the prompt ──
    # For detail queries we include more rows so the LLM can describe the
    # scope accurately.  For aggregation/comparison the result is usually
    # small so 30 rows is generous.  The LLM context window is the
    # practical limit — we keep it bounded to avoid token overflow.
    if intent == "detail":
        max_prompt_rows = 50
    else:
        max_prompt_rows = 30

    results_text = _format_results(rows, max_rows=max_prompt_rows)

    # ── Truncation note ──
    truncation_parts = []
    prompt_rows_shown = min(len(rows), max_prompt_rows)

    if len(rows) > max_prompt_rows:
        truncation_parts.append(
            f"NOTE: You are seeing {prompt_rows_shown} of {row_count} rows "
            f"for context. The full result has {row_count} rows."
        )
    if is_truncated_by_limit:
        truncation_parts.append(
            f"NOTE: The database safety limit capped results at {row_count} rows. "
            f"The actual matching rows may exceed this number."
        )

    truncation_note = "\n".join(truncation_parts) if truncation_parts else ""
    truncation_suffix = ""
    if is_truncated_by_limit:
        truncation_suffix = ", result capped at safety limit"
    elif len(rows) > max_prompt_rows:
        truncation_suffix = f", showing {prompt_rows_shown} for context"

    # ── Select the prompt template ──
    template = _INTENT_TEMPLATES.get(intent, GENERAL_PROMPT_TEMPLATE)

    # Override: if the intent is aggregation but comparison is required,
    # use the comparison template.
    if requires_comparison:
        template = COMPARISON_PROMPT_TEMPLATE

    domain = _get_domain_context()

    prompt = template.format(
        query=query,
        row_count=row_count,
        results_text=results_text,
        domain_label=domain["label"],
        insight_tone=domain.get("insight_tone", "Focus on key patterns in the results."),
        truncation_note=truncation_note,
        truncation_suffix=truncation_suffix,
    )

    insight = call_llm(prompt, expect_json=False)

    logger.info("[Insight Agent] Insight generated (intent=%s): %s", intent, insight[:150])
    return insight.strip()


def _format_results(rows: list[dict], max_rows: int = 30) -> str:
    """
    Format query result rows into a readable text representation
    for the LLM prompt. Limits rows to avoid token overflow.
    """
    if not rows:
        return "No results."

    display_rows = rows[:max_rows]

    # Create a text table
    lines = []
    for i, row in enumerate(display_rows, 1):
        row_str = " | ".join(f"{k}: {v}" for k, v in row.items())
        lines.append(f"Row {i}: {row_str}")

    if len(rows) > max_rows:
        lines.append(f"... and {len(rows) - max_rows} more rows (not shown here)")

    return "\n".join(lines)


def _get_domain_context() -> dict:
    """Load dynamic data profile from all uploaded columns."""
    columns: list[str] = []
    schema: list[dict] = []
    for table in get_all_table_names():
        table_schema = get_table_schema(table)
        for col in table_schema:
            columns.append(col["column_name"])
            schema.append(col)
    return analyze_dataset(columns, schema)
