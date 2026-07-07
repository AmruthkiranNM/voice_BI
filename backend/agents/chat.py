"""
Chat Agent

Handles conversational follow-up questions about a result the user already
has on screen (e.g. "how can I improve my sales with this data?"). Unlike
the main pipeline, this does NOT generate new SQL — it answers directly
from the result rows and prior insight already returned to the user, so
follow-ups are a single fast LLM call instead of a full re-run of the
Planner -> SQL -> Validator -> Execution pipeline.
"""

import logging
from typing import Any

from services.llm_service import call_llm
from services.database import get_all_table_names, get_table_schema
from services.domain_detector import analyze_dataset

logger = logging.getLogger(__name__)

CHAT_PROMPT_TEMPLATE = """You are a Business Advisor AI in an ongoing conversation with a business owner about their data.

Business type: {domain_label}

Earlier, the owner asked: "{original_query}"
That question returned this data ({row_count} rows):
{results_text}

Your earlier analysis was: "{prior_insight}"
{history_text}
The owner now says: "{message}"

RULES:
1. Speak directly to the owner — use "your business", "your data".
2. If the user asks WHY something happened (e.g. "why are they leaving?"), or asks for data/columns NOT shown above, YOU MUST output exactly this text: [RUN_NEW_QUERY] and nothing else.
3. If you can answer using ONLY the data above, give 2-4 concrete suggestions tied to the data.
4. Do NOT repeat the exact same response you gave previously. If the user repeats their question, acknowledge it and provide a different perspective.
5. Keep it concise. Use **bold** for key terms. Lead with a short sentence before any list.

Write your reply now:"""


def run(
    message: str,
    context: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> str:
    """
    Answer a conversational follow-up about an existing query result.

    Args:
        message: The follow-up question from the user.
        context: {"query", "sql", "result": {"columns","rows","row_count"}, "insight"}
                 from the original query response being followed up on.
        history: Prior turns in this follow-up thread, as
                 [{"role": "user"|"assistant", "content": str}, ...].

    Returns:
        Reply text from the LLM.
    """
    result = context.get("result") or {}
    rows = result.get("rows", [])
    row_count = result.get("row_count", len(rows))

    results_text = _format_results(rows, max_rows=15)
    domain = _get_domain_context()
    history_text = _format_history(history or [])

    prompt = CHAT_PROMPT_TEMPLATE.format(
        domain_label=domain["label"],
        original_query=context.get("query", ""),
        row_count=row_count,
        results_text=results_text,
        prior_insight=context.get("insight") or "(no summary was generated)",
        history_text=history_text,
        message=message,
    )

    logger.info("[Chat Agent] Follow-up: %s", message[:80])
    
    msg_lower = message.lower()
    analytical_keywords = (
        "why", "how many", "count", "total", "average", "avg", 
        "show me", "which ", "compare", "vs ", "versus", "what is"
    )
    needs_new_query = any(kw in msg_lower for kw in analytical_keywords)
    
    reply = ""
    if not needs_new_query:
        reply = call_llm(prompt, expect_json=False).strip()
        if "[RUN_NEW_QUERY]" in reply.upper() or reply.upper() == "[RUN_NEW_QUERY]":
            needs_new_query = True

    if needs_new_query:
        logger.info("[Chat Agent] Follow-up requires new analytics, routing to orchestrator...")
        from agents.orchestrator import process_query
        
        if "why" in msg_lower:
            combined_query = f"Analyze the data to explain the reasons why. Original context: '{context.get('query')}'. Follow-up question: {message}"
        else:
            combined_query = f"Original context: '{context.get('query')}'. Follow-up question: {message}"
            
        try:
            new_result = process_query(combined_query, fast_mode=False, skip_insight=False)
            if new_result["success"] and new_result["insight"]:
                return f"I ran a new analysis to answer your question:\n\n{new_result['insight']}"
            elif new_result["success"]:
                rows = new_result["result"].get("rows", [])
                if rows:
                    return f"I ran a new analysis. Here are the top findings:\n\n" + _format_results(rows, max_rows=5)
                else:
                    return "I ran a new analysis, but found no relevant data to answer this."
            else:
                return f"I tried to run a deeper analysis, but encountered an error: {new_result.get('error')}"
        except Exception as e:
            logger.error(f"Error running follow-up analytics: {e}")
            return "I need more data to answer this, but my analytical query failed. Please try asking as a new search."

    return reply


def _format_results(rows: list[dict], max_rows: int = 15) -> str:
    if not rows:
        return "No results."

    display_rows = rows[:max_rows]
    lines = []
    for i, row in enumerate(display_rows, 1):
        row_str = " | ".join(f"{k}: {v}" for k, v in row.items())
        lines.append(f"Row {i}: {row_str}")

    if len(rows) > max_rows:
        lines.append(f"... and {len(rows) - max_rows} more rows (truncated)")

    return "\n".join(lines)


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return ""

    lines = ["", "Conversation so far:"]
    for turn in history:
        speaker = "Owner" if turn.get("role") == "user" else "You"
        lines.append(f"{speaker}: {turn.get('content', '')}")
    return "\n".join(lines) + "\n"


def _get_domain_context() -> dict:
    columns: list[str] = []
    schema: list[dict] = []
    for table in get_all_table_names():
        table_schema = get_table_schema(table)
        for col in table_schema:
            columns.append(col["column_name"])
            schema.append(col)
    return analyze_dataset(columns, schema)
