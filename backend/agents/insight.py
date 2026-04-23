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

logger = logging.getLogger(__name__)

INSIGHT_PROMPT_TEMPLATE = """You are a Business Intelligence Insight Agent.

Given a user's original question and the query results from a database,
generate a clear, concise, and insightful business analysis.

RULES:
1. Be specific — reference actual numbers from the data.
2. Highlight key findings, trends, or notable patterns.
3. If the data allows, mention comparisons or percentage changes.
4. Keep it concise — 2-4 sentences maximum.
5. Use a professional but accessible tone.
6. If the result set is empty, inform the user clearly.

═══════════════════════════════════════
USER QUESTION: {query}
═══════════════════════════════════════

SQL EXECUTED: {sql}

═══════════════════════════════════════

QUERY RESULTS ({row_count} rows):
{results_text}

═══════════════════════════════════════

Generate the business insight now:"""


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
        insight = "No data was found matching your query. This could mean the specified criteria don't match any records in the database."
        logger.info("[Insight Agent] No data — returning empty insight.")
        return insight

    # Format results for the prompt (limit to avoid token overflow)
    results_text = _format_results(rows, max_rows=20)

    prompt = INSIGHT_PROMPT_TEMPLATE.format(
        query=query,
        sql=sql,
        row_count=row_count,
        results_text=results_text,
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
