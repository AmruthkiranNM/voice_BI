"""
Investigator Agent

Autonomous multi-hop root-cause drill-down. Given a question that already
has an answer (one SQL query, one result), this decides — on its own,
without the user prompting each step — what follow-up question would
explain *why* that result looks the way it does, runs it through the same
pipeline as a normal query, and repeats up to a hop limit. The chain is
then synthesized into a single narrative.

This is the thing that makes the system reason instead of just answer:
a normal query is one hop (question -> SQL -> result). This is several
hops chained by the model's own judgment of what to check next.
"""

import json
import logging
import re
from typing import Any

from agents.orchestrator import process_query
from services.llm_service import call_llm

logger = logging.getLogger(__name__)

MAX_HOPS = 3

NEXT_QUESTION_PROMPT = """You are a business analyst investigating why a result looks the way it does.
You already know the following:

ORIGINAL QUESTION: {original_query}

WHAT'S BEEN FOUND SO FAR:
{chain_summary}

AVAILABLE DATA TABLES AND COLUMNS:
{schema_text}

Decide ONE follow-up question that would help explain *why* the most recent
finding looks the way it does — something that can be answered by querying
the tables above (e.g. break it down by a category, region, time period, or
compare it against something).

Rules:
- Ask about something that can be answered with a SQL query over the tables listed above.
- Don't repeat a question already asked.
- If you've already found a clear root cause, or three follow-ups is enough, respond with exactly: DONE
- Otherwise respond with ONLY the follow-up question, one sentence, no preamble, no quotes.
"""

SYNTHESIS_PROMPT = """You are a business analyst. You investigated a question by asking a chain of
follow-up questions and found the following, in order:

{chain_summary}

Write a short, plain-English explanation (3-5 sentences) that connects these
findings into a single root-cause story — start with the headline finding,
then explain what's actually driving it, using the specific numbers found.
Speak directly to the business owner ("your revenue", "your data"). Use
**bold** for key numbers. Do not repeat the raw questions — tell the story."""


def investigate(
    original_query: str,
    original_sql: str,
    original_result: dict[str, Any],
    *,
    model: str | None = None,
    table_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run an autonomous multi-hop drill-down starting from an already-answered
    query. Returns the hop chain and a synthesized narrative.
    """
    chain: list[dict[str, Any]] = [{
        "question": original_query,
        "sql": original_sql,
        "summary_text": _summary_text(original_result),
        "finding": _structured_finding(original_result),
    }]

    schema_text = _schema_text(table_names)

    for hop in range(1, MAX_HOPS + 1):
        next_question = _pick_next_question(original_query, chain, schema_text, model)
        if not next_question or next_question.strip().upper() == "DONE":
            break

        logger.info("[Investigator] Hop %d question: %s", hop, next_question)
        hop_result = process_query(
            next_question,
            model=model,
            table_names=table_names,
            cache_mode=True,
            fast_mode=True,   # heuristic planner — this is a supporting lookup, not the headline query
            skip_insight=True,
        )

        if not hop_result.get("success"):
            logger.info("[Investigator] Hop %d failed, stopping: %s", hop, hop_result.get("error"))
            break

        result = hop_result.get("result", {})
        chain.append({
            "question": next_question,
            "sql": hop_result.get("sql"),
            "summary_text": _summary_text(result),
            "finding": _structured_finding(result),
        })

    narrative = _synthesize(chain, model) if len(chain) > 1 else None

    return {
        "chain": [{"question": c["question"], "sql": c["sql"], "finding": c["finding"]} for c in chain],
        "narrative": narrative,
        "hops": len(chain) - 1,
    }


def _pick_next_question(
    original_query: str,
    chain: list[dict[str, Any]],
    schema_text: str,
    model: str | None,
) -> str | None:
    chain_summary = "\n".join(
        f"{i + 1}. Q: {c['question']}\n   Found: {c['summary_text']}" for i, c in enumerate(chain)
    )
    prompt = NEXT_QUESTION_PROMPT.format(
        original_query=original_query,
        chain_summary=chain_summary,
        schema_text=schema_text,
    )
    try:
        response = call_llm(prompt, expect_json=False)
    except Exception as e:
        logger.warning("[Investigator] Failed to get next question: %s", e)
        return None
    return _clean_question(response)


def _clean_question(text: str) -> str:
    text = text.strip().strip('"').strip("'")
    # Strip a leading "Q:" / numbering the model sometimes adds despite instructions.
    text = re.sub(r"^(Q:|Question:|\d+[.)])\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _synthesize(chain: list[dict[str, Any]], model: str | None) -> str | None:
    chain_summary = "\n".join(
        f"{i + 1}. {c['question']}\n   -> {c['summary_text']}" for i, c in enumerate(chain)
    )
    prompt = SYNTHESIS_PROMPT.format(chain_summary=chain_summary)
    try:
        return call_llm(prompt, expect_json=False).strip()
    except Exception as e:
        logger.warning("[Investigator] Failed to synthesize narrative: %s", e)
        return None


def _summary_text(result: dict[str, Any]) -> str:
    """Compact text summary of a query result for feeding back into a prompt."""
    rows = result.get("rows", [])
    row_count = result.get("row_count", len(rows))
    if not rows:
        return "No matching rows."
    display = rows[:5]
    lines = [" | ".join(f"{k}: {v}" for k, v in row.items()) for row in display]
    suffix = f" (+{row_count - 5} more rows)" if row_count > 5 else ""
    return "; ".join(lines) + suffix


def _structured_finding(result: dict[str, Any]) -> dict[str, Any]:
    """Structured (not flattened-string) version of a hop's result, so the
    frontend can render it as an actual table instead of a text dump."""
    rows = result.get("rows", [])
    row_count = result.get("row_count", len(rows))
    display = rows[:5]
    return {
        "row_count": row_count,
        "columns": list(display[0].keys()) if display else [],
        "rows": display,
        "truncated": row_count > len(display),
    }


def _schema_text(table_names: list[str] | None) -> str:
    from services.database import get_all_table_names, get_table_schema

    names = table_names or get_all_table_names()
    lines = []
    for t in names:
        cols = [c["column_name"] for c in get_table_schema(t)]
        lines.append(f"{t}: {', '.join(cols)}")
    return "\n".join(lines) if lines else "(no tables)"
