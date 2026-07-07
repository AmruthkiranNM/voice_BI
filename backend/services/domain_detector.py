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
        # Menu-item vocabulary — these mostly appear in DATA VALUES (e.g. a
        # "Product" column containing "Fries", "Beverages"), not column names.
        "fries": 3, "burger": 3, "pizza": 3, "sandwich": 3, "salad": 3,
        "dessert": 3, "appetizer": 3, "beverages": 3, "drinks": 3, "drink": 3,
        "coffee": 3, "tea": 2, "soda": 3, "juice": 2, "fries ": 3, "taco": 3,
        "pasta": 3, "noodle": 3, "soup": 3, "snack": 3, "combo": 3, "wrap": 2,
        "breakfast": 3, "lunch": 3, "dinner": 3, "starter": 3, "entree": 4,
        "wine": 2, "beer": 2, "cocktail": 3, "smoothie": 3, "bakery": 3,
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
    ("Banking & Financial Services", "banking", {
        "balance": 4, "credit": 4, "loan": 4, "mortgage": 4, "deposit": 4,
        "withdrawal": 4, "transaction": 3, "exited": 4, "churn": 4, "tenure": 3,
        "account": 3, "card": 3,
    }),
    ("Software & SaaS", "saas", {
        "subscription": 4, "mrr": 4, "arr": 4, "plan": 3, "tier": 3,
        "renewal": 4, "churn": 3, "usage": 3, "license": 3,
    }),
]

_MIN_THEME_SCORE = 3
_MIN_SCORE_MARGIN = 2

# theme_id -> friendly label, for resolving any theme picked semantically.
_THEME_LABELS: dict[str, str] = {tid: label for label, tid, _ in _THEME_KEYWORDS}

# Natural-language descriptions of each domain. When keyword scoring is
# inconclusive, the dataset's text (columns + sample values) is embedded and
# compared against these via cosine similarity — semantic matching that
# catches datasets whose vocabulary isn't in the keyword lists (e.g. an
# unusual menu, or synonyms the lists don't cover). Reuses the same
# sentence-transformer already loaded for RAG.
_THEME_ANCHORS: dict[str, str] = {
    "restaurant": "Restaurant, cafe, bar or food service data: menu items, dishes, food and drink orders, dining, kitchen and table service.",
    "retail": "Retail and e-commerce data: products, SKUs, stores, shopping carts, merchandise, brands and customer purchases.",
    "sales": "Sales and revenue data: deals, invoices, orders, sales pipeline, commissions and revenue performance.",
    "inventory": "Inventory and supply chain data: warehouse stock levels, suppliers, shipments, reorder points and units on hand.",
    "finance": "Finance and accounting data: expenses, ledgers, accounts payable and receivable, budgets, margins and profit.",
    "hr": "Human resources and workforce data: employees, salaries, payroll, departments, attendance, hiring and headcount.",
    "healthcare": "Healthcare and clinic data: patients, doctors, diagnoses, treatments, prescriptions, hospital and appointments.",
    "hospitality": "Hospitality and travel data: hotels, room bookings, guests, reservations and check-in details.",
    "marketing": "Marketing and customer engagement data: campaigns, conversions, impressions, clicks, leads and subscribers.",
    "banking": "Banking and financial services data: accounts, balances, credit scores, loans, deposits, credit cards, transactions, and customer churn or exited status.",
    "saas": "Software as a service (SaaS) and subscription data: active users, churn rate, monthly recurring revenue (MRR), renewals, plans, and software licenses.",
}

# Lazily-computed cache of anchor embeddings.
_anchor_embeddings = None
_anchor_ids: list[str] = []

# Minimum cosine similarity (and margin over the runner-up) for an
# embedding-based classification to be trusted over the honest fallback.
_EMBED_MIN_SIM = 0.30
_EMBED_MIN_MARGIN = 0.04


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


def _matches_token_set(tokens: set[str], keyword: str) -> bool:
    """Match a keyword against a set of value tokens (exact or long substring)."""
    keyword = keyword.strip()
    if not keyword:
        return False
    if keyword in tokens:
        return True
    if len(keyword) >= 5:
        return any(keyword in tok for tok in tokens)
    return False


def _score_themes(
    column_names: list[str],
    sample_values: list[str] | None = None,
) -> dict[str, int]:
    scores: dict[str, int] = {theme_id: 0 for _, theme_id, _ in _THEME_KEYWORDS}

    for col in column_names:
        for _label, theme_id, keywords in _THEME_KEYWORDS:
            for kw, weight in keywords.items():
                if _keyword_matches_column(col, kw):
                    scores[theme_id] += weight

    # Score against sampled data values too. The strongest industry signal is
    # often in the cells (a generic "Product" column full of "Fries",
    # "Beverages") rather than the column name. Each keyword counts at most
    # once across all values, so variety of vocabulary — not row count — drives
    # the score.
    if sample_values:
        value_tokens: set[str] = set()
        for v in sample_values:
            value_tokens |= _column_tokens(str(v))
        for _label, theme_id, keywords in _THEME_KEYWORDS:
            for kw, weight in keywords.items():
                if _matches_token_set(value_tokens, kw):
                    scores[theme_id] += weight

    return scores


def _embedding_theme_scores(
    column_names: list[str],
    sample_values: list[str] | None,
) -> dict[str, float]:
    """
    Cosine similarity of the dataset's text against each theme anchor.

    Returns {} if the embedding model can't be loaded (e.g. in a minimal
    test environment), so callers must treat an empty result as "unavailable"
    and fall back to keyword/heuristic classification.
    """
    global _anchor_embeddings, _anchor_ids
    try:
        from services.embeddings import generate_embedding, generate_embeddings_batch
    except Exception:
        return {}

    try:
        if _anchor_embeddings is None:
            _anchor_ids = list(_THEME_ANCHORS.keys())
            _anchor_embeddings = generate_embeddings_batch(
                [_THEME_ANCHORS[tid] for tid in _anchor_ids]
            )

        parts = ["Columns: " + ", ".join(_humanize(c) for c in column_names)]
        if sample_values:
            # de-dup while keeping it small, values carry strong domain signal
            seen: list[str] = []
            for v in sample_values:
                s = str(v).strip()
                if s and s not in seen:
                    seen.append(s)
                if len(seen) >= 60:
                    break
            if seen:
                parts.append("Sample values: " + ", ".join(seen))

        query_emb = generate_embedding(". ".join(parts))
        # anchors and query are L2-normalised, so dot product == cosine sim
        sims = _anchor_embeddings @ query_emb
        return {tid: float(sim) for tid, sim in zip(_anchor_ids, sims)}
    except Exception:
        return {}


def _fallback_business_type(
    grouped: dict[str, list[str]],
    column_names: list[str],
) -> tuple[str, str, float]:
    """Honest label when industry keywords are ambiguous."""
    cols_joined = " ".join(c.lower() for c in column_names)

    hr_strong = any(k in cols_joined for k in ("payroll", "employee", "headcount", "workforce", "hire"))
    has_salary = "salary" in cols_joined
    has_customer_signals = any(k in cols_joined for k in ("estimated", "customer", "balance", "exited", "credit", "churn"))
    
    if hr_strong or (has_salary and not has_customer_signals):
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


def _embedding_business_type(
    column_names: list[str],
    sample_values: list[str] | None,
) -> tuple[str, str, float] | None:
    """Classify semantically; returns None if embeddings are unavailable or weak."""
    sims = _embedding_theme_scores(column_names, sample_values)
    if not sims:
        return None

    ranked = sorted(sims.items(), key=lambda x: x[1], reverse=True)
    best_id, best_sim = ranked[0]
    second_sim = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_sim < _EMBED_MIN_SIM or (best_sim - second_sim) < _EMBED_MIN_MARGIN:
        return None

    # Map cosine sim (~0.3–0.7 typical) onto a sensible confidence band.
    confidence = round(min(max(best_sim, 0.0), 1.0), 2)
    return _THEME_LABELS[best_id], best_id, confidence


def _infer_business_type(
    column_names: list[str],
    grouped: dict[str, list[str]],
    sample_values: list[str] | None = None,
    use_embeddings: bool = False,
) -> tuple[str, str, float]:
    """
    Return (friendly_label, theme_id, confidence).

    Hybrid strategy: keyword scoring decides when it has a clear winner
    (precise, fast, no model needed). When keywords are inconclusive and
    embeddings are enabled, fall back to semantic similarity against theme
    anchors; only if that is also weak do we use the honest heuristic label.
    """
    scores = _score_themes(column_names, sample_values)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    best_id, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    keyword_decisive = (
        best_score >= _MIN_THEME_SCORE
        and (best_score - second_score) >= _MIN_SCORE_MARGIN
    )
    if keyword_decisive:
        # Confidence reflects how dominant the winning theme is, not how many
        # columns exist — a strong value-driven match shouldn't be penalised
        # just because the table is wide.
        confidence = round(min(best_score / (best_score + second_score + 5), 1.0), 2)
        return _THEME_LABELS[best_id], best_id, confidence

    if use_embeddings:
        semantic = _embedding_business_type(column_names, sample_values)
        if semantic is not None:
            return semantic

    return _fallback_business_type(grouped, column_names)


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
    sample_values: list[str] | None = None,
    use_embeddings: bool = False,
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

    business_type, theme_id, confidence = _infer_business_type(
        column_names, grouped, sample_values, use_embeddings
    )
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


def detect_domain(
    column_names: list[str],
    schema: list[dict[str, Any]] | None = None,
    sample_values: list[str] | None = None,
    use_embeddings: bool = False,
) -> dict[str, Any]:
    return analyze_dataset(column_names, schema, sample_values, use_embeddings)


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
