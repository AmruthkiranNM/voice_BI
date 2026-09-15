"""
Prediction Package — Detector

Scans a database table and determines whether it contains a viable
binary classification problem.

Responsibilities:
  - Identify the target column (e.g. 'Exited', 'Churn', 'Sales').
  - Determine if the problem is binary classification or regression.
  - Classify columns as id / target / feature / drop.
  - Validate that the dataset meets minimum requirements.
  - Return a DetectionResult for downstream modules.
"""

import logging
import warnings
from typing import Any

import pandas as pd

from prediction.schemas import ColumnProfile, DetectionResult

logger = logging.getLogger(__name__)

# ── Known target column names, ordered by priority ──
_TARGET_HINTS = [
    "amount", "sales", "revenue", "exited", "churn", "churned", "attrition", "target",
    "label", "is_churned", "defaulted", "cancelled",
]

# ── Patterns that identify ID/drop columns ──
_ID_PATTERNS = [
    "id", "customerid", "customer_id", "userid", "user_id",
    "rownumber", "row_number", "index",
]

_DROP_PATTERNS = [
    "surname", "name", "firstname", "lastname", "first_name",
    "last_name", "email", "phone", "address",
]

# Minimum rows required for a viable model
_MIN_ROWS = 50

# ── Semantic Domain Aliases for Target Resolution ──
_SEMANTIC_ALIASES = {
    "revenue": ["amount", "sales", "revenue", "income", "turnover", "total", "price", "cost", "margin", "profit", "value"],
    "sales": ["amount", "sales", "revenue", "quantity", "sold", "volume", "value"],
    "customers": ["customer", "client", "subscriber", "user", "people", "headcount", "users"],
    "churn": ["exited", "churn", "attrition", "left", "cancelled", "defaulted"],
    "salary": ["salary", "pay", "compensation", "wage", "income"],
    "boxes": ["box", "boxes", "quantity", "units", "items"],
}

def _score_column(col_name: str, hint: str, is_numeric: bool, problem_type_hint: str | None) -> float:
    score = 0.0
    col_lower = col_name.lower().replace("_", "")
    hint_lower = hint.lower()
    
    # Exact match is king
    if hint_lower.replace(" ", "") == col_lower:
        return 100.0
        
    # Split on any non-alphanumeric so a SQL alias ("boxes_sold",
    # "total-revenue") tokenises the same way a column name does. Splitting
    # the column but not the hint meant aliases could never overlap.
    import re as _re
    hint_words = {w for w in _re.split(r"[^a-z0-9]+", hint_lower) if w}
    col_words = {w for w in _re.split(r"[^a-z0-9]+", col_name.lower()) if w}
    
    # Expand hint words with aliases
    expanded_hint = set(hint_words)
    for hw in hint_words:
        for key, aliases in _SEMANTIC_ALIASES.items():
            if hw == key or hw in aliases:
                expanded_hint.update(aliases)
                
    # Check word overlap
    overlap = expanded_hint.intersection(col_words)
    if overlap:
        score += 50.0 * len(overlap)
        
    # Exact word match boost (if the column name itself is in the original hint words)
    if col_lower in hint_words:
        score += 100.0
        
    # Check substring match
    for eh in expanded_hint:
        if len(eh) > 3 and eh in col_lower:
            score += 20.0
            
    # Type preference
    if problem_type_hint in ("regression", "forecasting") and is_numeric:
        score += 10.0
    elif problem_type_hint == "classification" and not is_numeric:
        score += 10.0
        
    return score



def detect(df: pd.DataFrame, table_name: str, target_hint: str | None = None, problem_type_hint: str | None = None) -> DetectionResult:
    """
    Analyze a DataFrame and determine if it contains a viable
    classification, regression, or forecasting problem.
    """
    if df.empty or len(df) < _MIN_ROWS:
        return DetectionResult(
            table_name=table_name,
            is_suitable=False,
            row_count=len(df),
            reason=f"Insufficient data: {len(df)} rows (minimum {_MIN_ROWS}).",
        )

    # ── 1. Identify the date column and target column ──
    date_col = _find_date_column(df)
    target_col = _find_target_column(df, target_hint, problem_type_hint)

    if target_col is None and problem_type_hint in ("forecasting", "regression"):
        # A hint is an override, not a prerequisite. When one is absent — or
        # when it is a SQL alias like "total_revenue" that names no physical
        # column — fall back to the table's own best measure rather than
        # refusing. Requiring a resolvable hint made every follow-up that did
        # not restate the measure fail with "a hint must be provided", even
        # though the table plainly contains forecastable quantities.
        target_col = _best_measure(df, date_col)
        if target_col:
            logger.info(
                "[Detector] Target hint %r did not resolve; using measure '%s'.",
                target_hint, target_col,
            )

    if target_col is None:
        available = _measure_names(df, date_col)
        return DetectionResult(
            table_name=table_name,
            is_suitable=False,
            row_count=len(df),
            reason=(
                "No viable target column found. "
                + (f"Numeric measures available: {', '.join(available)}. "
                   if available else "This table has no numeric measure. ")
                + "For classification a binary column is required."
            ),
        )

    # ── 2. Determine problem type ──
    # The target resolver is the single authority on what a column *is*.
    # Deciding it independently here is how the same column ended up being
    # treated as a measure in one code path and a label in another.
    from prediction.target_resolution import resolve_target

    target_spec = resolve_target(target_col, df, has_time_axis=bool(date_col))
    unique_values = df[target_col].dropna().unique().tolist()
    problem_type = None

    if problem_type_hint == "forecasting":
        if not date_col:
            return DetectionResult(
                table_name=table_name,
                is_suitable=False,
                target_column=target_col,
                row_count=len(df),
                reason="Forecasting requested but no date/time column found in dataset.",
            )
        if not pd.api.types.is_numeric_dtype(df[target_col]):
            # The hint resolved to something unforecastable — usually a SQL
            # alias that collided with a key column. Prefer the table's own
            # measure over refusing the request outright.
            replacement = _best_measure(df, date_col)
            if replacement:
                logger.info(
                    "[Detector] '%s' is not numeric; forecasting '%s' instead.",
                    target_col, replacement,
                )
                target_col = replacement
            else:
                return DetectionResult(
                    table_name=table_name,
                    is_suitable=False,
                    target_column=target_col,
                    row_count=len(df),
                    reason=(
                        f"Target column '{target_col}' is not numeric and this table "
                        "has no numeric measure to forecast instead."
                    ),
                )
        problem_type = "forecasting"
        unique_values = []
    elif target_spec.recommended_prediction_type == "classification":
        problem_type = "classification"
    elif target_spec.semantic_role == "measure":
        # A continuous measure is a regression target here. Whether the caller
        # actually wants it projected over time is decided by the question, via
        # target_resolution.resolve_prediction_type — not by this function.
        problem_type = "regression"
        unique_values = []
    else:
        return DetectionResult(
            table_name=table_name,
            is_suitable=False,
            target_column=target_col,
            row_count=len(df),
            reason=(
                f"Target column '{target_col}' cannot be predicted. {target_spec.reason}"
            ),
        )

    # ── 3. Classify all columns ──
    id_cols = []
    drop_cols = []
    feature_cols = []
    numeric_features = []
    categorical_features = []
    missing_values = {}

    for col in df.columns:
        col_lower = col.lower().replace(" ", "").replace("_", "")
        
        # Track missing values
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            missing_values[col] = null_count
            
        if col == target_col:
            continue
        elif any(pat.replace("_", "") == col_lower for pat in _DROP_PATTERNS):
            drop_cols.append(col)
        elif any(pat.replace("_", "") == col_lower for pat in _ID_PATTERNS):
            id_cols.append(col)
        else:
            feature_cols.append(col)
            # Differentiate numeric vs categorical
            if pd.api.types.is_numeric_dtype(df[col]):
                numeric_features.append(col)
            else:
                categorical_features.append(col)

    # ── 4. Class distribution ──
    class_dist = df[target_col].value_counts().to_dict()
    class_dist_str = {str(k): int(v) for k, v in class_dist.items()}

    logger.info(
        "[Detector] Table '%s': target='%s', features=%d, ids=%d, drop=%d, rows=%d, classes=%s",
        table_name, target_col, len(feature_cols), len(id_cols),
        len(drop_cols), len(df), class_dist_str,
    )

    return DetectionResult(
        table_name=table_name,
        is_suitable=True,
        target_column=target_col,
        target_classes=unique_values,
        problem_type=problem_type,
        feature_columns=feature_cols,
        categorical_features=categorical_features,
        numeric_features=numeric_features,
        id_columns=id_cols,
        drop_columns=drop_cols,
        missing_values=missing_values,
        row_count=len(df),
        class_distribution=class_dist_str,
        date_column=date_col,
    )


def _measure_names(df: pd.DataFrame, date_col: str | None = None) -> list[str]:
    """Columns this table could forecast, judged by their values."""
    from prediction.target_resolution import resolve_target

    names = []
    for column in df.columns:
        if date_col and column == date_col:
            continue
        spec = resolve_target(column, df, has_time_axis=bool(date_col))
        if spec.semantic_role == "measure":
            names.append(column)
    return names


def _best_measure(df: pd.DataFrame, date_col: str | None = None) -> str | None:
    """
    The most plausible default measure for a table.

    Prefers the measure with the widest spread of values, which is the one
    carrying the most information — not the first column alphabetically and
    not a name from a list.
    """
    candidates = _measure_names(df, date_col)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def spread(column: str) -> float:
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        return float(values.nunique()) if not values.empty else 0.0

    return max(candidates, key=spread)


def _find_date_column(df: pd.DataFrame) -> str | None:
    """
    Find the column that carries the time axis.

    Three passes, most reliable first: a real datetime dtype, then a
    name that advertises itself as a date and whose values parse, then —
    only if neither found anything — any text column whose values actually
    parse as dates.

    The third pass matters for genericity: a timestamp column called
    ``when_on`` or ``period`` carries no naming hint, and without it such a
    dataset simply reports "no date column" and cannot be forecast at all.
    """
    # 1. Explicitly typed datetime columns
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col

    def _parses_as_dates(col: str, threshold: float) -> bool:
        sample = df[col].dropna().head(50)
        if sample.empty:
            return False
        # Plain numbers parse as epochs; that is not evidence of a date column.
        if pd.api.types.is_numeric_dtype(sample):
            return False
        try:
            with warnings.catch_warnings():
                # Mixed/unknown formats fall back to dateutil and warn; that is
                # expected here, since probing is the whole point.
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(sample, errors="coerce")
        except (ValueError, TypeError):
            return False
        return bool(parsed.notna().mean() >= threshold)

    # 2. Name advertises a date, and the values agree
    date_hints = ["date", "time", "month", "year", "timestamp"]
    for col in df.columns:
        if any(h in col.lower() for h in date_hints) and _parses_as_dates(col, 0.5):
            return col

    # 3. No hint in any name — fall back to what the values actually are
    for col in df.columns:
        if _parses_as_dates(col, 0.9):
            logger.info(
                "[Detector] '%s' has no date-like name but its values parse as dates; "
                "using it as the time axis.", col,
            )
            return col

    return None


def _find_target_column(df: pd.DataFrame, hint: str | None = None, problem_type_hint: str | None = None) -> str | None:
    """
    Find the target column for classification, regression, or forecasting.
    Uses semantic scoring if a hint is provided.
    """
    cols_lower = {c.lower(): c for c in df.columns}

    # Helper to check if a column shouldn't be a target
    def is_invalid_target(c: str) -> bool:
        c_low = c.lower().replace("_", "")
        return any(p.replace("_", "") in c_low for p in _ID_PATTERNS + _DROP_PATTERNS)

    # 1. Semantic Hint Match
    if hint:
        best_col = None
        best_score = 0.0
        for col in df.columns:
            if is_invalid_target(col):
                continue
            is_num = pd.api.types.is_numeric_dtype(df[col])
            score = _score_column(col, hint, is_num, problem_type_hint)
            if score > best_score:
                best_score = score
                best_col = col
                
        if best_col and best_score >= 20.0:
            logger.info("[Detector] Resolved target hint '%s' to column '%s' (score: %.1f)", hint, best_col, best_score)
            return best_col

    # Steps 2 and 3 below look for a *binary* column — they are classification
    # heuristics. Running them for a forecasting request picked whatever 0/1
    # flag the table happened to contain (an "delayed"/"exited" column) and
    # forecast that instead of a measure. When a quantity is wanted, the
    # caller falls back to the table's best measure rather than to a label.
    if problem_type_hint in ("forecasting", "regression"):
        return None

    # 2. Known names (Fallback for no-hint classification)
    for name in _TARGET_HINTS:
        if name in cols_lower:
            col = cols_lower[name]
            if not is_invalid_target(col):
                unique_vals = df[col].dropna().unique()
                if len(unique_vals) == 2:
                    return col

    # 3. Heuristic: binary column (prioritize end of dataframe)
    for col in reversed(df.columns):
        if is_invalid_target(col):
            continue
        try:
            unique_vals = df[col].dropna().unique()
            if len(unique_vals) == 2:
                numeric_vals = pd.to_numeric(pd.Series(unique_vals), errors="coerce")
                if numeric_vals.notna().all() and set(numeric_vals.astype(int)) == {0, 1}:
                    return col
        except (TypeError, ValueError):
            continue

    return None


def detect_group_dimensions(
    group_hints: list[str],
    base_table: str,
    exclude_columns: set[str] | None = None,
) -> list[dict[str, str]]:
    """
    Resolve grouping hints to concrete (table, column, join key) triples.

    Delegates to :mod:`prediction.dimensions`, which resolves against the live
    schema and its values rather than a hardcoded alias table. The old
    implementation mapped "country" and "region" onto the same candidate list
    and guessed join keys from table names, so "by region" silently returned
    countries and "by team" joined on the product key.

    Returns the dict shape the predictor consumes. Hints that cannot be
    resolved are reported by raising, never by falling back to a default
    dimension — answering a different question than the one asked is worse
    than failing.
    """
    from prediction.dimensions import resolve_dimensions

    resolution = resolve_dimensions(
        group_hints, base_table, exclude_columns=exclude_columns,
    )
    if not resolution.ok:
        raise ValueError(resolution.error_message())

    return [d.to_dim_info() for d in resolution.resolved]
