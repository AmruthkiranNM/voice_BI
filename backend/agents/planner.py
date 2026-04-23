"""
Planner Agent

Analyzes a natural language query and produces a structured execution plan.
The plan guides downstream agents on what steps to take.
"""

import json
import logging
from services.llm_service import call_llm

logger = logging.getLogger(__name__)

PLANNER_PROMPT_TEMPLATE = """You are a Query Planner Agent in a Business Intelligence system.

Your job is to analyze a natural language business query and produce a structured plan
that downstream agents will use to retrieve data.

IMPORTANT RULES:
1. Break complex queries into logical steps.
2. Identify what type of data operation is needed (aggregation, comparison, filtering, etc.).
3. Identify time ranges, filters, groupings mentioned in the query.
4. Output ONLY valid JSON — no extra text.

User Query: "{query}"

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
    "requires_comparison": true/false
}}
"""


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
