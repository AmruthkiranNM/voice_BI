"""
Planner Agent

Analyzes a natural language query and produces a structured execution plan.
The plan guides downstream agents on what steps to take.
"""

import json
import logging
from services.llm_service import call_llm

logger = logging.getLogger(__name__)

PLANNER_PROMPT_TEMPLATE = """You are a Query Planner helping a business owner analyze their uploaded CSV data.

Analyze their natural language question and produce a structured plan for retrieving insights.

IMPORTANT RULES:
1. The owner is NOT technical — focus on business intent (sales, customers, trends, comparisons).
2. Identify metrics, time ranges, filters, and groupings mentioned in the question.
3. Output ONLY valid JSON — no extra text.

Owner's Question: "{query}"

Respond with this exact JSON structure:
{{
    "original_query": "<the user query>",
    "steps": [
        "Step 1 description",
        "Step 2 description"
    ],
    "intent": "<one of: aggregation, comparison, trend, detail, count>",
    "metrics": ["<metric names mentioned, e.g., sales, revenue, orders>"],
    "filters": {{
        "time_range": "<e.g., last month, last year, Q1 2025, or null>",
        "location": "<city/state/region or null>",
        "category": "<product category or null>",
        "other": "<any other filter or null>"
    }},
    "grouping": "<e.g., by city, by month, by product, or null>",
    "requires_aggregation": true/false,
    "requires_comparison": true/false,
    "comparison_type": "<one of: period, category, growth, ranking, null>"
}}
"""


def build_fast_plan(query: str) -> dict:
    """
    Heuristic plan without an LLM call — used in fast mode to skip the planner agent.
    """
    q = query.lower()
    intent = "detail"
    requires_comparison = False
    comparison_type = None

    comparison_words = (
        "compare", "vs", "versus", "difference", "growth", "better", "worse",
        "highest", "lowest", "best", "worst", "rank", "against", "between",
    )
    if any(w in q for w in comparison_words):
        intent = "comparison"
        requires_comparison = True
        if any(w in q for w in ("month", "year", "quarter", "week", "period", "vs last")):
            comparison_type = "period"
        elif any(w in q for w in ("growth", "percent", "%", "increase", "decrease")):
            comparison_type = "growth"
        elif any(w in q for w in ("top", "best", "highest", "worst", "lowest", "rank")):
            comparison_type = "ranking"
        else:
            comparison_type = "category"
    elif any(w in q for w in ("total", "sum", "average", "avg", "count", "how many")):
        intent = "aggregation"
    elif any(w in q for w in ("trend", "monthly", "yearly", "over time")):
        intent = "trend"

    metrics = []
    for word in ("sales", "revenue", "orders", "customers", "profit", "quantity"):
        if word in q:
            metrics.append(word)

    grouping = None
    if " by " in q:
        grouping = q.split(" by ", 1)[1].split()[0]

    return {
        "original_query": query,
        "steps": ["Retrieve data matching the query"],
        "intent": intent,
        "metrics": metrics,
        "filters": {
            "time_range": None,
            "location": None,
            "category": None,
            "other": None,
        },
        "grouping": grouping,
        "requires_aggregation": intent in ("aggregation", "comparison", "trend"),
        "requires_comparison": requires_comparison,
        "comparison_type": comparison_type,
        "fast_mode": True,
    }


def run(query: str) -> dict:
    """
    Analyze the user query and return a structured execution plan.

    Args:
        query: Natural language business query from the user.

    Returns:
        Dictionary containing the execution plan.
    """
    logger.info("[Planner Agent] Processing query: %s", query)

    prompt = PLANNER_PROMPT_TEMPLATE.format(query=query)
    response = call_llm(prompt, expect_json=True)

    try:
        plan = json.loads(response)
        logger.info(
            "[Planner Agent] Plan generated — Intent: %s, Steps: %d",
            plan.get("intent", "unknown"),
            len(plan.get("steps", [])),
        )
        return plan
    except json.JSONDecodeError as e:
        logger.error("[Planner Agent] Failed to parse LLM response: %s", str(e))
        # Return a minimal fallback plan
        return {
            "original_query": query,
            "steps": ["Retrieve relevant data based on the query"],
            "intent": "aggregation",
            "metrics": [],
            "filters": {
                "time_range": None,
                "location": None,
                "category": None,
                "other": None,
            },
            "grouping": None,
            "requires_aggregation": True,
            "requires_comparison": False,
            "parse_error": str(e),
        }
