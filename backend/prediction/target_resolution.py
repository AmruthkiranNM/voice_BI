"""
Prediction Package — Target Type Resolution

Decides what a target column *is* and therefore what can be predicted from it,
using the column's data rather than its name. `AMOUNT`, `BOXES` and `CUSTOMERS`
are continuous measures because their values are continuous, not because they
appear on a list; `EXITED` is a label because it holds two values, not because
it is called "exited". Point this at a schema it has never seen and it reaches
the same kind of conclusion.

The separation it enforces:

    classification  — a small, fixed set of labels
    regression      — a continuous measure, predicted per row
    forecasting     — a continuous measure, predicted forward in time

A measure supports both regression and forecasting; which one applies is a
property of the *question*, not of the column. ``resolve_prediction_type``
takes that split apart explicitly, so a follow-up that changes the target can
keep asking about the future instead of silently falling back to whatever the
first question happened to be.
"""

from __future__ import annotations

import dataclasses
import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)


# A numeric column with at most this many distinct values is treated as a set
# of codes (a label), not a measure — e.g. a 1-5 rating or a 0/1 flag.
MAX_DISCRETE_CODES = 10

# A categorical target with more classes than this is not something the
# available classifiers can usefully learn from a business dataset.
MAX_TARGET_CLASSES = 20

# A measure needs more distinct values than this before it is worth regressing.
MIN_CONTINUOUS_DISTINCT = 20

_ID_TOKENS = ("id", "key", "code", "uuid", "guid", "index", "rownumber", "no", "num")


@dataclasses.dataclass
class TargetSpec:
    """What a column is, and what it therefore supports predicting."""
    column: str
    dtype: str = "unknown"              # numeric | categorical | boolean | datetime | text
    semantic_role: str = "unknown"      # measure | label | identifier | time
    n_distinct: int = 0
    n_rows: int = 0
    null_count: int = 0
    is_binary: bool = False
    is_continuous: bool = False
    sample_values: list = dataclasses.field(default_factory=list)

    supported_prediction_types: list[str] = dataclasses.field(default_factory=list)
    recommended_prediction_type: str | None = None
    reason: str = ""

    def supports(self, prediction_type: str) -> bool:
        return prediction_type in self.supported_prediction_types


def _looks_like_identifier(
    column: str,
    series: pd.Series,
    n_distinct: int,
    n_rows: int,
) -> bool:
    """
    Whether a column is a key rather than something to predict.

    A name that reads like a key settles it: the column exists to join rows, so
    predicting it is meaningless however few values it holds — a four-value
    foreign key is still a key.

    Near-uniqueness only implicates *non-numeric* columns, such as an email or
    reference string. A numeric measure is near-unique by its nature — every
    transaction has its own amount — so cardinality alone must never turn one
    into an identifier.
    """
    normalised = re.sub(r"[^a-z0-9]", "", column.lower())
    if normalised.endswith(_ID_TOKENS) or normalised in _ID_TOKENS:
        return True

    if pd.api.types.is_numeric_dtype(series):
        return False

    return bool(n_rows > 0 and (n_distinct / n_rows) > 0.95)


def resolve_target(
    column: str,
    df: pd.DataFrame,
    *,
    has_time_axis: bool = False,
) -> TargetSpec:
    """
    Describe a target column and the prediction types it supports.

    Args:
        column: the column to profile.
        df: the table it belongs to.
        has_time_axis: whether the table has a usable date column, which is
            what makes forecasting possible at all.

    Returns:
        TargetSpec. ``supported_prediction_types`` is empty when the column
        cannot be predicted, with ``reason`` explaining why.
    """
    spec = TargetSpec(column=column, n_rows=int(len(df)))

    if column not in df.columns:
        spec.reason = f"Column '{column}' is not present in the table."
        return spec

    series = df[column]
    spec.null_count = int(series.isna().sum())
    values = series.dropna()
    spec.n_distinct = int(values.nunique())
    spec.sample_values = [_plain(v) for v in values.unique()[:8]]

    if values.empty:
        spec.reason = f"Column '{column}' has no non-null values."
        return spec

    # ── Time axis ──
    if pd.api.types.is_datetime64_any_dtype(series):
        spec.dtype, spec.semantic_role = "datetime", "time"
        spec.reason = "Datetime columns define the time axis; they are not forecast targets."
        return spec

    # ── Identifier ──
    if _looks_like_identifier(column, series, spec.n_distinct, spec.n_rows):
        spec.dtype = "numeric" if pd.api.types.is_numeric_dtype(series) else "categorical"
        spec.semantic_role = "identifier"
        spec.reason = (
            f"'{column}' looks like an identifier ({spec.n_distinct} distinct values "
            f"across {spec.n_rows} rows); identifiers are not predictable quantities."
        )
        return spec

    numeric = pd.api.types.is_numeric_dtype(series)
    if not numeric:
        # A text column of numerals is still numeric data.
        coerced = pd.to_numeric(values, errors="coerce")
        if coerced.notna().mean() > 0.95:
            numeric = True
            values = coerced.dropna()
            spec.n_distinct = int(values.nunique())

    if numeric:
        unique_values = set(values.unique().tolist())
        spec.is_binary = spec.n_distinct == 2

        # Two values (classically 0/1) is a label wearing a number's clothes.
        if spec.is_binary:
            spec.dtype = "boolean" if unique_values <= {0, 1, 0.0, 1.0} else "categorical"
            spec.semantic_role = "label"
            spec.supported_prediction_types = ["classification"]
            spec.recommended_prediction_type = "classification"
            spec.reason = (
                f"'{column}' takes exactly two values {sorted(spec.sample_values)[:2]}, "
                "so it is a binary label rather than a quantity."
            )
            return spec

        # A handful of whole-number codes is a category, not a measure.
        all_integral = bool((values == values.round()).all())
        if all_integral and spec.n_distinct <= MAX_DISCRETE_CODES:
            spec.dtype = "categorical"
            spec.semantic_role = "label"
            if spec.n_distinct <= MAX_TARGET_CLASSES:
                spec.supported_prediction_types = ["classification"]
                spec.recommended_prediction_type = "classification"
            spec.reason = (
                f"'{column}' holds only {spec.n_distinct} distinct whole numbers, "
                "which reads as a set of codes rather than a continuous measure."
            )
            return spec

        # Otherwise it is a continuous measure: regressable, and forecastable
        # whenever the table has a time axis to project along.
        spec.dtype = "numeric"
        spec.semantic_role = "measure"
        spec.is_continuous = spec.n_distinct >= MIN_CONTINUOUS_DISTINCT
        spec.supported_prediction_types = ["regression"]
        if has_time_axis:
            spec.supported_prediction_types.append("forecasting")
        # Forecasting is the better default for a measure over time: a business
        # asking about a quantity almost always wants it projected forward.
        spec.recommended_prediction_type = "forecasting" if has_time_axis else "regression"
        spec.reason = (
            f"'{column}' is a continuous numeric measure ({spec.n_distinct} distinct "
            f"values). It supports regression"
            + (" and time-series forecasting." if has_time_axis else
               " (no date column, so forecasting is unavailable).")
        )
        return spec

    # ── Non-numeric ──
    spec.dtype = "categorical" if spec.n_distinct <= MAX_TARGET_CLASSES else "text"
    spec.semantic_role = "label" if spec.dtype == "categorical" else "text"
    spec.is_binary = spec.n_distinct == 2

    if spec.dtype == "categorical":
        spec.supported_prediction_types = ["classification"]
        spec.recommended_prediction_type = "classification"
        spec.reason = (
            f"'{column}' is categorical with {spec.n_distinct} classes, so it is a "
            "classification target."
        )
    else:
        spec.reason = (
            f"'{column}' has {spec.n_distinct} distinct free-text values; there is no "
            "quantity to predict and too many classes to learn."
        )
    return spec


def resolve_prediction_type(
    spec: TargetSpec,
    *,
    wants_future: bool,
    requested: str | None = None,
) -> tuple[str | None, str]:
    """
    Choose classification / regression / forecasting for one target.

    The column decides what is *possible*; the question decides what is *wanted*.
    Keeping those apart is what stops a follow-up that changes the measure from
    inheriting the previous question's prediction type — the failure that sent a
    continuous quantity into a classifier.

    Args:
        spec: the resolved target.
        wants_future: the question is about future periods.
        requested: an explicitly requested type, honoured when supported.

    Returns:
        (prediction_type or None, reason)
    """
    if not spec.supported_prediction_types:
        return None, spec.reason or f"'{spec.column}' cannot be predicted."

    if requested and spec.supports(requested):
        return requested, f"'{requested}' was requested and '{spec.column}' supports it."

    if requested and not spec.supports(requested):
        fallback = spec.recommended_prediction_type
        return fallback, (
            f"'{spec.column}' does not support {requested} ({spec.reason}) — "
            f"using {fallback} instead."
        )

    if wants_future:
        if spec.supports("forecasting"):
            return "forecasting", (
                f"The question asks about future periods and '{spec.column}' is a "
                "continuous measure with a time axis."
            )
        if spec.semantic_role == "measure":
            return "regression", (
                f"'{spec.column}' is a measure but the table has no usable date "
                "column, so it can only be predicted per row, not over time."
            )

    return spec.recommended_prediction_type, spec.reason


def _plain(value):
    """Make a numpy/pandas scalar JSON-friendly."""
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value
