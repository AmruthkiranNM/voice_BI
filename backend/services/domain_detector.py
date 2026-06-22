"""
Infer business data type and column roles from uploaded CSV columns.

Uses token-based keyword scoring with confidence thresholds so generic
columns like order_id or orderdate do not misclassify data as restaurant.
"""

from __future__ import annotations

import re
from typing import Any

_DATE_HINTS = ("date", "time", "month", "year", "created", "updated", "timestamp", "day", "period")
_NUMERIC_HINTS = (
    "amount", "count", "total", "sum", "price", "cost", "revenue", "sales",
    "quantity", "qty", "value", "rate", "percent", "score", "age", "salary",
    "budget", "profit", "fee", "balance", "stock", "units", "tip", "tax",
)
_CATEGORY_HINTS = (
    "name", "type", "category", "status", "region", "city", "state", "country",
    "department", "team", "product", "customer", "brand", "vendor", "sku",
    "item", "group", "class", "menu", "dish", "store", "employee", "patient",
)

# keyword → weight (higher = more distinctive for that industry)
_THEME_KEYWORDS: list[tuple[str, str, dict[str, int]]] = [
    ("Restaurant & Food Service", "restaurant", {
        "menu": 4, "dish": 4, "cuisine": 4, "restaurant": 5, "kitchen": 4,
        "meal": 4, "tip": 4, "server": 3, "dine": 4, "beverage": 3, "food": 3,
        "waiter": 4, "chef": 4,
    }),
    ("Retail & E-Commerce", "retail", {
        "product": 3, "sku": 4, "store": 3, "retail": 5, "merchandise": 4,
        "cart": 3, "shop": 3, "customer": 2, "brand": 2, "inventory": 3,
    }),
    ("Sales & Revenue", "sales", {
        "revenue": 4, "sales": 4, "invoice": 3, "deal": 3, "pipeline": 3,
        "commission": 3, "ordernumber": 2, "orderline": 2,
    }),
    ("Inventory & Supply Chain", "inventory", {
        "warehouse": 4, "supplier": 4, "shipment": 4, "reorder": 4,
        "onhand": 3, "stock": 2,
    }),
    ("Finance & Accounting", "finance", {
        "expense": 4, "ledger": 4, "payable": 4, "receivable": 4,
        "accounting": 5, "margin": 3, "budget": 3, "profit": 3,
    }),
    ("HR & Workforce", "hr", {
        "employee": 4, "salary": 4, "payroll": 5, "attendance": 4,
        "headcount": 4, "workforce": 4, "hire": 3, "position": 2,
    }),
    ("Healthcare & Clinic", "healthcare", {
        "patient": 5, "doctor": 4, "diagnosis": 4, "treatment": 4,
        "clinic": 4, "hospital": 4, "prescription": 4,
    }),
    ("Hospitality & Travel", "hospitality", {
        "hotel": 5, "booking": 3, "guest": 3, "reservation": 4, "checkin": 4,
    }),
    ("Marketing & Customers", "marketing", {
        "campaign": 4, "conversion": 4, "impression": 4, "subscriber": 4,
        "click": 2, "lead": 2,
    }),
]

_MIN_THEME_SCORE = 3
_MIN_SCORE_MARGIN = 2


def _humanize(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("_", " ").replace("-", " ")).strip()


def _column_tokens(col: str) -> set[str]:
    """Split a column name into lowercase tokens."""
    col = col.lower().strip()
    # Insert boundaries for camelCase / glued caps: ORDERDATE -> order, date
    spaced = re.sub(r"([a-z])([A-Z])", r"\1_\2", col)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", spaced)
    parts = re.split(r"[_\-\s]+", spaced.lower())
    tokens = {p for p in parts if len(p) >= 2}
    if col:
        tokens.add(col)
    return tokens


def _keyword_matches_column(col: str, keyword: str) -> bool:
    """Match keywords on tokens; allow substring only for distinctive long terms."""
    col_l = col.lower()
    tokens = _column_tokens(col_l)

    if keyword in tokens:
        return True

    # Glued names: productline, customername, ordernumber
    if len(keyword) >= 5 and keyword in col_l:
        return True

    return False


def classify_column(col_name: str, data_type: str = "") -> str:
    lower = col_name.lower()
    dtype = (data_type or "").upper()

    if any(h in lower for h in _DATE_HINTS) or "DATE" in dtype or "TIME" in dtype:
        return "date"
    if dtype in ("INTEGER", "REAL", "NUMERIC", "FLOAT", "INT", "DOUBLE"):
        return "numeric"
    if any(h in lower for h in _NUMERIC_HINTS):
        return "numeric"
    if any(h in lower for h in _CATEGORY_HINTS):
        return "category"
    if dtype in ("TEXT", "VARCHAR", "CHAR", "STRING", ""):
        return "category"
    return "other"


def _score_themes(column_names: list[str]) -> dict[str, int]:
    scores: dict[str, int] = {theme_id: 0 for _, theme_id, _ in _THEME_KEYWORDS}

    for col in column_names:
        for _label, theme_id, keywords in _THEME_KEYWORDS:
            for kw, weight in keywords.items():
                if _keyword_matches_column(col, kw):
                    scores[theme_id] += weight

    return scores


def _fallback_business_type(
    grouped: dict[str, list[str]],
    column_names: list[str],
) -> tuple[str, str, float]:
    """Honest label when industry keywords are ambiguous."""
    cols_joined = " ".join(c.lower() for c in column_names)

    if any(k in cols_joined for k in ("salary", "payroll", "employee")):
        return "HR & Workforce", "hr", 0.3
    if any(k in cols_joined for k in ("patient", "doctor", "clinic")):
        return "Healthcare & Clinic", "healthcare", 0.3
    if grouped["numeric"] and any(
        k in cols_joined for k in ("sales", "revenue", "price", "amount")
    ):
        if any(k in cols_joined for k in ("product", "sku", "customer")):
            return "Sales & Product Data", "sales", 0.3
        return "Sales & Revenue Data", "sales", 0.3
    if grouped["numeric"] and grouped["category"]:
        return "Business Metrics Data", "general", 0.2

    return "General Business Data", "general", 0.0


def _infer_business_type(
    column_names: list[str],
    grouped: dict[str, list[str]],
) -> tuple[str, str, float]:
    """Return (friendly_label, theme_id, confidence) from column keywords."""
    scores = _score_themes(column_names)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    best_id, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score < _MIN_THEME_SCORE or (best_score - second_score) < _MIN_SCORE_MARGIN:
        return _fallback_business_type(grouped, column_names)

    label = next(label for label, tid, _ in _THEME_KEYWORDS if tid == best_id)
    confidence = round(min(best_score / max(len(column_names) * 3, 1), 1.0), 2)
    return label, best_id, confidence


def _pick_role(columns: list[str], keywords: tuple[str, ...]) -> str | None:
    for kw in keywords:
        for col in columns:
            if _keyword_matches_column(col, kw):
                return col
    return columns[0] if columns else None


def infer_column_roles(grouped: dict[str, list[str]]) -> dict[str, str | None]:
    numeric = grouped["numeric"]
    category = grouped["category"]
    dates = grouped["date"]

    return {
        "money": _pick_role(numeric, (
            "revenue", "sales", "amount", "total", "price", "profit", "income",
            "cost", "salary", "fee", "payment", "balance",
        )),
        "quantity": _pick_role(numeric, ("quantity", "qty", "units", "count", "stock")),
        "product": _pick_role(category, (
            "product", "item", "sku", "menu", "dish", "brand", "service",
        )),
        "customer": _pick_role(category, (
            "customer", "client", "guest", "patient", "employee", "buyer", "user",
        )),
        "location": _pick_role(category, (
            "region", "city", "state", "country", "store", "branch", "location", "area",
            "territory",
        )),
        "category": _pick_role(category, (
            "category", "type", "department", "segment", "class", "group", "status",
            "productline",
        )),
        "time": dates[0] if dates else None,
    }


def analyze_dataset(
    column_names: list[str],
    schema: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not column_names:
        return _empty_profile()

    type_map: dict[str, str] = {}
    if schema:
        for col in schema:
            type_map[col["column_name"]] = col.get("data_type", "")

    grouped: dict[str, list[str]] = {
        "numeric": [], "date": [], "category": [], "other": [],
    }
    for name in column_names:
        grouped[classify_column(name, type_map.get(name, ""))].append(name)

    business_type, theme_id, confidence = _infer_business_type(column_names, grouped)
    roles = infer_column_roles(grouped)

    return {
        "id": theme_id,
        "label": business_type,
        "business_type": business_type,
        "insight_tone": _build_insight_tone(business_type, grouped, roles, confidence),
        "confidence": confidence,
        "numeric_columns": grouped["numeric"],
        "category_columns": grouped["category"],
        "date_columns": grouped["date"],
        "other_columns": grouped["other"],
        "column_names": column_names,
        "roles": roles,
    }


def detect_domain(column_names: list[str], schema: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return analyze_dataset(column_names, schema)


def _empty_profile() -> dict[str, Any]:
    return {
        "id": "general",
        "label": "No data uploaded",
        "business_type": "No data uploaded",
        "insight_tone": "Summarize the key patterns in plain language for a business owner.",
        "confidence": 0.0,
        "numeric_columns": [],
        "category_columns": [],
        "date_columns": [],
        "other_columns": [],
        "column_names": [],
        "roles": {},
    }


def _build_insight_tone(
    business_type: str,
    grouped: dict[str, list[str]],
    roles: dict[str, str | None],
    confidence: float,
) -> str:
    if confidence >= 0.25:
        hints = [f"this appears to be {business_type.lower()} data"]
    else:
        hints = ["describe patterns in the uploaded spreadsheet without assuming a specific industry"]
    if roles.get("money"):
        hints.append("highlight totals and comparisons using the main financial figures")
    if roles.get("location") or roles.get("category"):
        hints.append("compare performance across groups when relevant")
    if roles.get("time"):
        hints.append("note trends over time when dates are involved")
    return "Speak to a business owner — " + "; ".join(hints) + "."
