"""
Natural-language question suggestions tailored to each uploaded dataset.

Questions are written the way a business owner would ask — no SQL jargon
or raw column names exposed in the UI.
"""

from __future__ import annotations

from typing import Any

from services.database import get_all_table_names, get_table_schema, get_table_row_count
from services.domain_detector import analyze_dataset


def _dedupe(suggestions: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in suggestions:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _build_natural_questions(
    profile: dict[str, Any],
    row_count: int,
    max_suggestions: int,
) -> list[str]:
    """Generate conversational questions from business type and column roles."""
    suggestions: list[str] = []
    business_type = profile.get("business_type", "your business")
    roles: dict[str, str | None] = profile.get("roles") or {}

    has_money = bool(roles.get("money") or profile.get("numeric_columns"))
    has_product = bool(roles.get("product"))
    has_customer = bool(roles.get("customer"))
    has_location = bool(roles.get("location"))
    has_category = bool(roles.get("category"))
    has_time = bool(roles.get("time"))
    theme = profile.get("id", "general")
    confidence = profile.get("confidence", 0)

    # Theme-specific openers only when detection is confident
    if theme == "restaurant" and confidence >= 0.25:
        suggestions.extend([
            "How much revenue did my restaurant make in total?",
            "What were my most popular menu items?",
            "Which days of the week are busiest?",
        ])
    elif theme == "retail" and confidence >= 0.25:
        suggestions.extend([
            "What were my total sales?",
            "Which products sold the best?",
            "Which store or region performed strongest?",
        ])
    elif theme == "hr" and confidence >= 0.25:
        suggestions.extend([
            "What is the average salary across my team?",
            "How is headcount spread across departments?",
            "Who are the highest paid employees?",
        ])
    elif theme == "finance" and confidence >= 0.25:
        suggestions.extend([
            "What are my total expenses?",
            "Where am I spending the most money?",
            "How does income compare to expenses?",
        ])
    elif theme == "healthcare" and confidence >= 0.25:
        suggestions.extend([
            "How many patient visits did we have?",
            "Which services are most common?",
            "What does appointment volume look like over time?",
        ])
    elif theme == "inventory" and confidence >= 0.25:
        suggestions.extend([
            "Which items are running low on stock?",
            "What is my total inventory value?",
            "Which suppliers provide the most products?",
        ])

    # --- Role-based questions (natural language) ---
    if has_money:
        suggestions.extend([
            "How much money did I make in total?",
            "What was my average transaction value?",
            "What were my top 10 best performers?",
        ])

    if has_product and has_money:
        suggestions.extend([
            "Which products brought in the most revenue?",
            "What is my best selling item?",
        ])

    if has_location and has_money:
        suggestions.extend([
            "Which location performed the best?",
            "How do sales compare across regions?",
        ])
    elif has_category and has_money:
        suggestions.extend([
            "Which category performed the best?",
            "How do results break down by category?",
        ])

    if has_customer:
        suggestions.append("Who are my top customers?")

    if has_time and has_money:
        suggestions.extend([
            "How have my sales changed over time?",
            "What did I earn this month compared to last month?",
            "Show me a monthly sales trend.",
        ])

    if not has_money and has_category:
        suggestions.append("How many records do I have in each group?")

    # --- Universal summaries ---
    suggestions.extend([
        f"Give me an overview of my {business_type.lower()}.",
        f"What are the most important insights from my {row_count:,} records?",
    ])

    return _dedupe(suggestions)[:max_suggestions]


def generate_suggestions_for_table(
    table_name: str,
    max_suggestions: int = 6,
) -> dict[str, Any]:
    schema = get_table_schema(table_name)
    if not schema:
        empty = analyze_dataset([])
        return {"table_name": table_name, "domain": empty, "suggestions": []}

    column_names = [c["column_name"] for c in schema]
    profile = analyze_dataset(column_names, schema)
    row_count = get_table_row_count(table_name)

    suggestions = _build_natural_questions(profile, row_count, max_suggestions)

    return {
        "table_name": table_name,
        "domain": profile,
        "suggestions": suggestions,
    }


def generate_suggestions(
    max_suggestions: int = 6,
    table_name: str | None = None,
    domain_id: str | None = None,
) -> list[str]:
    tables = get_all_table_names()
    if not tables:
        return []
    target = table_name if table_name and table_name in tables else max(tables, key=get_table_row_count)
    return generate_suggestions_for_table(target, max_suggestions)["suggestions"]


def generate_all_dataset_suggestions(max_suggestions: int = 6) -> list[dict[str, Any]]:
    return [generate_suggestions_for_table(name, max_suggestions) for name in get_all_table_names()]
