"""
Prediction Package — Time-Series Validation

Deterministic health checks that run on a time series *before* any model is
fitted. Nothing in this module calls an LLM, and nothing here is specific to
any business domain: every rule is expressed in terms of observation counts,
spacing, and robust statistics, so it behaves identically for a country, a
product, a team, or a dataset this project has never seen.

The contract is deliberately conservative:

  * A missing period is NEVER a zero. Gaps stay NaN and are counted.
  * A series that cannot support a forecast is refused with a stated reason
    rather than being forecast badly.
  * Outliers are reported, not silently removed — model selection is what
    decides whether an outlier-sensitive model deserves to win.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from prediction.schemas import SeriesDiagnostics

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Thresholds (all deterministic, all overridable by callers)
# ──────────────────────────────────────────────────────────

# Absolute floor. Below this a series cannot be split chronologically into a
# train slice and a validation slice at all, so no model can be justified.
MIN_OBSERVATIONS = 4

# Between MIN_FALLBACK_OBSERVATIONS and MIN_OBSERVATIONS we may still emit a
# forecast, but only via an explicitly-labelled naive fallback.
MIN_FALLBACK_OBSERVATIONS = 2

# Above this share of empty buckets the series is too sparse to model; the
# gaps would dominate whatever the model learns.
MAX_MISSING_RATIO = 0.60

# Robust outlier rule: |x - median| > k * 1.4826 * MAD. 5.0 is intentionally
# permissive — it flags genuine shocks, not ordinary business variation.
OUTLIER_MAD_K = 5.0

# Canonical bucket lengths in days, used to infer frequency from raw spacing.
_FREQ_BY_DAYS = [
    (1.0, "days"),
    (7.0, "weeks"),
    (30.44, "months"),
    (91.31, "quarters"),
    (365.25, "years"),
]

# Pandas offset alias per supported frequency. "ME"/"QE"/"YE" are the
# non-deprecated period-end aliases.
FREQ_TO_RULE = {
    "days": "D", "day": "D",
    "weeks": "W", "week": "W",
    "months": "ME", "month": "ME",
    "quarters": "QE", "quarter": "QE",
    "years": "YE", "year": "YE",
    "periods": "ME", "period": "ME",
}

# Number of buckets in one seasonal cycle, per frequency.
SEASONAL_PERIODS = {
    "days": 7,
    "weeks": 52,
    "months": 12,
    "quarters": 4,
    "years": 0,      # no meaningful sub-cycle
}

# How fine each frequency is, for detecting "asked for days, data is monthly".
_FREQ_ORDER = ["days", "weeks", "months", "quarters", "years"]


def normalize_frequency(frequency: str | None) -> str:
    """Map any accepted spelling of a frequency onto its canonical plural form."""
    if not frequency:
        return "months"
    f = str(frequency).strip().lower()
    aliases = {
        "day": "days", "daily": "days",
        "week": "weeks", "weekly": "weeks",
        "month": "months", "monthly": "months",
        "quarter": "quarters", "quarterly": "quarters",
        "year": "years", "yearly": "years", "annual": "years", "annually": "years",
        "period": "months", "periods": "months",
    }
    f = aliases.get(f, f)
    return f if f in _FREQ_ORDER else "months"


def frequency_rule(frequency: str | None) -> str:
    """Return the pandas resample rule for a frequency name."""
    return FREQ_TO_RULE.get(normalize_frequency(frequency), "ME")


def median_step_days(timestamps: pd.Series | pd.DatetimeIndex) -> float:
    """
    Median gap in days between consecutive distinct timestamps.

    Used to size the tolerance for "is this edge bucket incomplete?": data that
    arrives daily can be a few days short of a month boundary and still
    represent a complete month, whereas data three months short of a year
    boundary plainly does not represent a complete year.
    """
    idx = pd.DatetimeIndex(pd.Series(timestamps).dropna().unique()).sort_values()
    if len(idx) < 2:
        return 0.0
    gaps = np.diff(idx.view("int64")) / 8.64e13
    gaps = gaps[gaps > 0]
    return float(np.median(gaps)) if gaps.size else 0.0


def infer_frequency(timestamps: pd.Series | pd.DatetimeIndex) -> str:
    """
    Infer the natural frequency of raw (pre-aggregation) timestamps from the
    median gap between consecutive distinct dates.

    Returns the canonical frequency whose bucket length is closest to that
    median gap on a log scale, so "roughly monthly" data with irregular
    spacing still resolves to "months".
    """
    idx = pd.DatetimeIndex(pd.Series(timestamps).dropna().unique()).sort_values()
    if len(idx) < 2:
        return "months"

    gaps_days = np.diff(idx.view("int64")) / 8.64e13  # ns → days
    gaps_days = gaps_days[gaps_days > 0]
    if gaps_days.size == 0:
        return "months"

    median_gap = float(np.median(gaps_days))
    # Compare on a log scale so "closest" is proportional, not absolute.
    best = min(_FREQ_BY_DAYS, key=lambda kv: abs(np.log(kv[0]) - np.log(max(median_gap, 1e-9))))
    return best[1]


def _is_finer(a: str, b: str) -> bool:
    """True when frequency ``a`` is finer-grained than ``b`` (days < months)."""
    try:
        return _FREQ_ORDER.index(a) < _FREQ_ORDER.index(b)
    except ValueError:
        return False


def detect_outliers(series: pd.Series) -> tuple[int, list[str]]:
    """
    Flag extreme values using the median absolute deviation, which (unlike a
    standard-deviation rule) is not itself dragged around by the outliers it
    is trying to find.

    Returns (count, period labels). Values are reported, never removed.
    """
    values = series.dropna()
    if len(values) < 4:
        return 0, []

    median = float(values.median())
    deviations = (values - median).abs()
    mad = float(deviations.median())

    if mad > 0:
        threshold = OUTLIER_MAD_K * 1.4826 * mad
        flagged = values[deviations > threshold]
        return len(flagged), [str(d) for d in flagged.index]

    # MAD of zero means more than half the periods are identical. The rule
    # above would then flag nothing at all — including a single enormous
    # spike, which is exactly the case worth catching. Treat any departure
    # from that dominant value as extreme, provided the departures really are
    # a small minority (otherwise the series is bimodal, not anomalous).
    differing = values[deviations > 0]
    if differing.empty or len(differing) > 0.25 * len(values):
        return 0, []
    return len(differing), [str(d) for d in differing.index]


def validate_series(
    series: pd.Series,
    *,
    requested_frequency: str,
    horizon: int,
    inferred_frequency: str | None = None,
    duplicate_timestamps: int = 0,
    n_trimmed_partial: int = 0,
    min_observations: int = MIN_OBSERVATIONS,
    max_missing_ratio: float = MAX_MISSING_RATIO,
) -> SeriesDiagnostics:
    """
    Produce a full health report for one aggregated series.

    Args:
        series: bucket-indexed series where empty buckets are NaN (not 0).
        requested_frequency: the frequency the question asked for.
        horizon: how many future buckets are being requested.
        inferred_frequency: frequency the raw timestamps actually support.
        duplicate_timestamps: exact-duplicate raw timestamps seen pre-aggregation.
        n_trimmed_partial: incomplete leading/trailing buckets already dropped.

    Returns:
        SeriesDiagnostics whose ``status`` decides whether a forecast is allowed:
        "ok" (model selection), "fallback" (naive only, clearly labelled), or a
        refusal status with a stated reason.
    """
    requested = normalize_frequency(requested_frequency)
    inferred = normalize_frequency(inferred_frequency) if inferred_frequency else requested

    diag = SeriesDiagnostics(
        requested_frequency=requested,
        inferred_frequency=inferred,
        frequency_mismatch=_is_finer(requested, inferred),
        horizon=int(horizon),
        duplicate_timestamps=int(duplicate_timestamps),
        n_trimmed_partial=int(n_trimmed_partial),
    )

    if series is None or len(series) == 0:
        diag.status = "no_data"
        diag.reason = "The series contains no periods after aggregation."
        return diag

    observed = series.dropna()
    diag.n_periods = int(len(series))
    diag.n_observed = int(len(observed))
    diag.n_missing = int(diag.n_periods - diag.n_observed)
    diag.missing_ratio = round(diag.n_missing / diag.n_periods, 4) if diag.n_periods else 0.0
    diag.first_period = str(series.index[0])
    diag.last_period = str(series.index[-1])

    seasonal_m = SEASONAL_PERIODS.get(requested, 0)
    diag.seasonal_periods = seasonal_m or None
    diag.seasonality_supported = bool(seasonal_m) and diag.n_observed >= 2 * seasonal_m

    diag.history_to_horizon_ratio = (
        round(diag.n_observed / horizon, 3) if horizon > 0 else 0.0
    )
    diag.horizon_exceeds_history = horizon > 0 and diag.n_observed < horizon

    if diag.n_observed > 0:
        diag.is_all_zero = bool((observed == 0).all())
        diag.is_constant = bool(observed.nunique() <= 1)
        diag.n_outliers, diag.outlier_periods = detect_outliers(series)

    # ── Warnings: conditions worth disclosing that do not block a forecast ──
    if diag.frequency_mismatch:
        diag.warnings.append(
            f"Requested '{requested}' granularity but the timestamps only support "
            f"'{inferred}'; buckets will be mostly empty."
        )
    if diag.n_trimmed_partial:
        diag.warnings.append(
            f"Dropped {diag.n_trimmed_partial} incomplete period(s) at the series edges "
            "so partial periods are not compared against full ones."
        )
    if diag.horizon_exceeds_history:
        diag.warnings.append(
            f"Forecast horizon ({horizon}) exceeds the observed history "
            f"({diag.n_observed} periods); the forecast is an extrapolation well "
            "beyond the evidence."
        )
    elif 0 < diag.history_to_horizon_ratio < 2.0:
        diag.warnings.append(
            f"Only {diag.n_observed} periods of history for a {horizon}-period horizon "
            "(less than 2x); treat the later periods as indicative only."
        )
    if seasonal_m and not diag.seasonality_supported:
        diag.warnings.append(
            f"Fewer than two full seasonal cycles ({2 * seasonal_m} periods); "
            "seasonality cannot be estimated and seasonal models are excluded."
        )
    if diag.n_missing:
        diag.warnings.append(
            f"{diag.n_missing} of {diag.n_periods} periods have no data. They are "
            "treated as unknown, not as zero."
        )
    if diag.n_outliers:
        diag.warnings.append(
            f"{diag.n_outliers} extreme value(s) detected; they are retained, and "
            "model selection favours whichever model handles them best."
        )
    if diag.is_all_zero:
        diag.warnings.append("Every observed period is zero.")
    elif diag.is_constant:
        diag.warnings.append("The series is constant across all observed periods.")

    # ── Blocking conditions, most specific first ──
    if diag.n_observed == 0:
        diag.status = "no_data"
        diag.reason = "No period in the requested range has any data."
        return diag

    if diag.n_observed < MIN_FALLBACK_OBSERVATIONS:
        diag.status = "insufficient_history"
        diag.reason = (
            f"Only {diag.n_observed} observed period(s); at least "
            f"{MIN_FALLBACK_OBSERVATIONS} are required for any forecast."
        )
        return diag

    if diag.n_observed < min_observations:
        diag.status = "fallback"
        diag.reason = (
            f"Only {diag.n_observed} observed period(s) — below the {min_observations} "
            "needed to validate a model. A naive (last-value) fallback is used and "
            "labelled as such."
        )
        return diag

    if diag.missing_ratio > max_missing_ratio:
        diag.status = "too_sparse"
        diag.reason = (
            f"{diag.missing_ratio:.0%} of periods have no data (limit "
            f"{max_missing_ratio:.0%}); the history is too intermittent to forecast "
            "at this granularity."
        )
        return diag

    diag.status = "ok"
    return diag
