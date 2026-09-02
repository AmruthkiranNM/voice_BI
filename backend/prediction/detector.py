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
        
    hint_words = set(hint_lower.split())
    col_words = set(col_name.lower().replace("_", " ").split())
    
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
    if target_col is None:
        return DetectionResult(
            table_name=table_name,
            is_suitable=False,
            row_count=len(df),
            reason="No viable target column found. For classification, need a binary column. For regression/forecasting, a hint must be provided.",
        )

    # ── 2. Determine problem type ──
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
            return DetectionResult(
                table_name=table_name,
                is_suitable=False,
                target_column=target_col,
                row_count=len(df),
                reason=f"Target column '{target_col}' must be numeric for forecasting.",
            )
        problem_type = "forecasting"
        unique_values = []
    elif len(unique_values) == 2:
        problem_type = "classification"
    elif pd.api.types.is_numeric_dtype(df[target_col]) and len(unique_values) > 2:
        problem_type = "regression"
        # For regression, target classes don't make sense
        unique_values = []
    else:
        return DetectionResult(
            table_name=table_name,
            is_suitable=False,
            target_column=target_col,
            row_count=len(df),
            reason=f"Target column '{target_col}' is neither binary nor continuous numerical.",
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


def _find_date_column(df: pd.DataFrame) -> str | None:
    """Find the first column that appears to be a date/datetime."""
    # Check explicitly typed datetime columns first
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
            
    # Heuristics for string columns that might be dates
    date_hints = ["date", "time", "month", "year", "timestamp"]
    for col in df.columns:
        col_lower = col.lower()
        if any(h in col_lower for h in date_hints):
            # Try parsing a sample
            sample = df[col].dropna().head(10)
            if not sample.empty:
                try:
                    pd.to_datetime(sample, errors="coerce")
                    return col
                except (ValueError, TypeError):
                    pass
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


def detect_group_dimension(group_hint: str, base_table: str) -> dict[str, str] | None:
    """
    Find the table, column, and join key for a grouped forecasting hint.
    
    Returns:
        A dict with:
          - target_table: e.g. "geo"
          - group_column: e.g. "geo"
          - join_key_base: e.g. "geoid"
          - join_key_target: e.g. "geoid"
        Or None if no matching dimension found.
    """
    from services.database import get_all_table_names, get_table_schema

    hint_lower = group_hint.lower().replace(" ", "")
    tables = get_all_table_names()
    
    best_score = 0.0
    best_match = None
    
    # Semantic mapping for common dimension names
    dim_aliases = {
        "country": ["geo", "region", "country", "nation"],
        "region": ["geo", "region"],
        "product": ["product", "item"],
        "category": ["category", "type", "class", "productcategory"],
        "team": ["team", "salesteam", "group"],
        "salesperson": ["salesperson", "rep", "agent"],
    }
    
    expanded_hint = set([hint_lower])
    for key, aliases in dim_aliases.items():
        if hint_lower in aliases or hint_lower == key:
            expanded_hint.update(aliases)

    base_schema = get_table_schema(base_table)
    base_columns = [c["column_name"].lower() for c in base_schema]

    for table in tables:
        if table == base_table:
            continue
            
        schema = get_table_schema(table)
        target_columns = [c["column_name"].lower() for c in schema]
        
        for col in target_columns:
            score = 0.0
            
            # Exact match
            if col in expanded_hint:
                score += 100.0
                
            # Substring match
            for eh in expanded_hint:
                if len(eh) >= 3 and (eh in col or col in eh):
                    score += 20.0
                    
            if score > best_score:
                # To be a valid dimension, we need a join key.
                # Look for a common ID column.
                # E.g., 'geoid' in both tables, or 'pid' in both tables, or table+'id'
                possible_keys = [table + "id", table[0] + "id"]
                join_key = None
                
                # Check for direct ID match in base table
                for bc in base_columns:
                    if bc in possible_keys or bc == table + "id":
                        join_key = bc
                        break
                        
                # Check for identical column names ending in 'id'
                if not join_key:
                    for tc in target_columns:
                        if tc.endswith("id") and tc in base_columns:
                            join_key = tc
                            break
                            
                if join_key:
                    best_score = score
                    best_match = {
                        "target_table": table,
                        "group_column": col,
                        "join_key_base": join_key,
                        "join_key_target": join_key,
                    }
                    
    return best_match
