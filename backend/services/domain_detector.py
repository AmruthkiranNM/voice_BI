"""
Detect the business domain of an uploaded dataset from column names.
Used to tailor suggestions, prompts, and insight tone.
"""

from __future__ import annotations

from typing import Any

DOMAIN_PROFILES: dict[str, dict[str, Any]] = {
    "retail_sales": {
        "label": "Retail & Sales",
        "keywords": {
            "sale", "sales", "order", "orders", "product", "sku", "customer",
            "revenue", "quantity", "cart", "store", "retail", "item", "price",
            "discount", "transaction", "invoice",
        },
        "insight_tone": "Focus on revenue drivers, top products, and customer buying patterns.",
    },
    "inventory": {
        "label": "Inventory & Stock",
        "keywords": {
            "stock", "inventory", "warehouse", "sku", "supply", "reorder",
            "on_hand", "units", "batch", "shelf", "supplier",
        },
        "insight_tone": "Focus on stock levels, reorder needs, and supply efficiency.",
    },
    "finance": {
        "label": "Finance & Accounting",
        "keywords": {
            "expense", "income", "budget", "profit", "loss", "payment",
            "invoice", "tax", "ledger", "account", "balance", "cost", "margin",
        },
        "insight_tone": "Focus on cash flow, expenses, profitability, and financial health.",
    },
    "hr": {
        "label": "HR & Workforce",
        "keywords": {
            "employee", "salary", "payroll", "department", "attendance",
            "hire", "staff", "position", "leave", "headcount",
        },
        "insight_tone": "Focus on workforce distribution, attendance, and staffing trends.",
    },
    "healthcare": {
        "label": "Healthcare & Clinic",
        "keywords": {
            "patient", "doctor", "appointment", "diagnosis", "treatment",
            "clinic", "hospital", "prescription", "visit",
        },
        "insight_tone": "Focus on patient volume, service patterns, and operational load.",
    },
    "general": {
        "label": "General Business",
        "keywords": set(),
        "insight_tone": "Focus on key metrics, trends, and actionable business insights.",
    },
}


def detect_domain(column_names: list[str]) -> dict[str, Any]:
    """
    Score each domain profile against column names and return the best match.

    Returns:
        dict with keys: id, label, insight_tone, confidence (0-1)
    """
    if not column_names:
        return {**_domain_payload("general"), "confidence": 0.0}

    normalized = [c.lower().replace(" ", "_") for c in column_names]
    scores: dict[str, int] = {}

    for domain_id, profile in DOMAIN_PROFILES.items():
        if domain_id == "general":
            continue
        score = 0
        for col in normalized:
            for kw in profile["keywords"]:
                if kw in col:
                    score += 1
                    break
        scores[domain_id] = score

    best_id = max(scores, key=scores.get, default="general")
    best_score = scores.get(best_id, 0)

    if best_score == 0:
        best_id = "general"

    max_possible = max(len(normalized), 1)
    confidence = round(min(best_score / max_possible, 1.0), 2)

    return {**_domain_payload(best_id), "confidence": confidence}


def _domain_payload(domain_id: str) -> dict[str, str]:
    profile = DOMAIN_PROFILES.get(domain_id, DOMAIN_PROFILES["general"])
    return {
        "id": domain_id,
        "label": profile["label"],
        "insight_tone": profile["insight_tone"],
    }
