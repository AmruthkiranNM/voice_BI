"""
Insight Agent

Analyzes query results using LLM to generate human-readable
business insights and summaries. Transforms raw data into
actionable intelligence.
"""

import json
import logging
from typing import Any

from services.llm_service import call_llm
from services.database import get_all_table_names, get_table_schema
from services.domain_detector import analyze_dataset

logger = logging.getLogger(__name__)

INSIGHT_PROMPT_TEMPLATE = """You are a Business Advisor AI helping a business owner understand their data.

Business type: {domain_label}
Advisory focus: {insight_tone}

The owner uploaded their own business CSV and asked a question. Based on the query results,
write a clear, actionable analysis they can use to make better decisions.

RULES:
1. Speak directly to the business owner — use "your business", "your data".
2. Reference specific numbers from the results.
3. Highlight the most important finding first.
4. Suggest one practical next step or business action when possible.
5. Keep it concise — 3-5 sentences maximum.
6. Avoid technical jargon (no SQL, no database terms).
7. If the result set is empty, explain what that means for their business.

═══════════════════════════════════════
OWNER'S QUESTION: {query}
═══════════════════════════════════════

QUERY RESULTS ({row_count} rows):
{results_text}

═══════════════════════════════════════

Write the business analysis now:"""


def run(query: str, sql: str, execution_result: dict[str, Any]) -> str:
    """
    Generate business insights from query results using LLM.

    Args:
        query: Original natural language question.
        sql: The SQL query that was executed.
        execution_result: Results from the Execution Agent.

    Returns:
        Human-readable insight string.
    """
    logger.info("[Insight Agent] Generating insights for: %s", query[:80])

    rows = execution_result.get("rows", [])
    row_count = execution_result.get("row_count", 0)

    # Handle empty results
    if row_count == 0:
        insight = "No matching records were found in your data. Try broadening your question or check that your CSV contains the categories or dates you are asking about."
        logger.info("[Insight Agent] No data — returning empty insight.")
        return insight

    # Format results for the prompt (limit to avoid token overflow)
    results_text = _format_results(rows, max_rows=20)
    domain = _get_domain_context()

    prompt = INSIGHT_PROMPT_TEMPLATE.format(
        query=query,
        row_count=row_count,
        results_text=results_text,
        domain_label=domain["label"],
        insight_tone=domain.get("insight_tone", "Focus on key patterns in the results."),
    )

    insight = call_llm(prompt, expect_json=False)

    logger.info("[Insight Agent] Insight generated: %s", insight[:150])
    return insight.strip()


def _format_results(rows: list[dict], max_rows: int = 20) -> str:
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
        lines.append(f"... and {len(rows) - max_rows} more rows (truncated)")

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
