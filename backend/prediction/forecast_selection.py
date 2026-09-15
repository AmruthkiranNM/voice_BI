"""
Prediction Package — Forecast Model Selection

Chooses a forecasting model for one series using rolling-origin (chronological)
backtesting, and records exactly how that choice was made.

Why rolling-origin rather than a random split: a random train/test split on a
time series lets the model see the future while predicting the past. Every
split here is a prefix — the model is only ever fitted on data strictly older
than the periods it is scored on.

Three rules drive the whole module:

  1. Nothing is fitted on data it will later be scored against (no leakage).
  2. Gaps are never filled with zero. Internal gaps are linearly interpolated
     for *fitting only*, using values from the training slice alone, and the
     count is reported. Reported history keeps its gaps as nulls.
  3. A model has to beat the naive baseline to be trusted. MASE < 1 means it
     did; MASE >= 1 is recorded honestly so the caller can say so.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

from prediction.forecasting_models import BaseForecaster, NaiveForecaster, build_candidates
from prediction.schemas import (
    CandidateScore,
    ForecastModelMetadata,
    SeriesDiagnostics,
    ValidationFold,
)

logger = logging.getLogger(__name__)


# Maximum rolling-origin folds. More folds means a more stable estimate but
# a shorter first training slice; 3 is the usual compromise for short series.
MAX_FOLDS = 3

# A training slice below this many observed points cannot support any model.
MIN_TRAIN_OBSERVATIONS = 3


# ──────────────────────────────────────────────────────────
# Training-slice preparation
# ──────────────────────────────────────────────────────────

def prepare_fit_slice(series: pd.Series) -> tuple[pd.Series, int]:
    """
    Turn a gappy slice into something a model can be fitted on, without
    inventing data at the edges and without ever writing a zero.

    Leading/trailing gaps are trimmed (not filled — we do not know what
    happened before the first observation). Internal gaps are linearly
    interpolated between the two real observations that bracket them.

    Returns (fittable series, number of interpolated points).
    """
    if series is None or len(series) == 0:
        return pd.Series(dtype=float), 0

    s = pd.Series(series).astype(float)
    first, last = s.first_valid_index(), s.last_valid_index()
    if first is None:
        return pd.Series(dtype=float), 0

    s = s.loc[first:last]
    n_gaps = int(s.isna().sum())
    if n_gaps:
        s = s.interpolate(method="linear")
    return s, n_gaps


def _naive_scale(train: pd.Series) -> float:
    """
    Mean absolute one-step change of the training slice — the denominator of
    MASE. This is the error a naive forecast would make in-sample, so dividing
    by it makes the metric scale-free and comparable across groups of wildly
    different size.
    """
    values = pd.Series(train).dropna().values.astype(float)
    if len(values) < 2:
        return 0.0
    diffs = np.abs(np.diff(values))
    scale = float(np.mean(diffs)) if diffs.size else 0.0
    return scale if np.isfinite(scale) and scale > 0 else 0.0


def build_folds(series: pd.Series, horizon: int) -> list[tuple[int, int]]:
    """
    Build rolling-origin folds as (train_end, val_end) positional boundaries.

    Each fold trains on ``series[:train_end]`` and scores on
    ``series[train_end:val_end]`` — strictly later periods, never overlapping.
    Folds step backwards from the end of the series so the most recent data is
    always used for scoring at least once.
    """
    n = len(series)
    if n < MIN_TRAIN_OBSERVATIONS + 1:
        return []

    # Validation window: as long as the requested horizon, but never so long
    # that it starves the training slice.
    h_val = max(1, min(int(horizon), n // 4 if n >= 8 else 1))

    folds: list[tuple[int, int]] = []
    for i in range(MAX_FOLDS):
        val_end = n - i * h_val
        train_end = val_end - h_val
        if train_end < MIN_TRAIN_OBSERVATIONS:
            break
        if len(series.iloc[:train_end].dropna()) < MIN_TRAIN_OBSERVATIONS:
            break
        folds.append((train_end, val_end))

    return list(reversed(folds))  # chronological order for readable metadata


# ──────────────────────────────────────────────────────────
# Backtesting
# ──────────────────────────────────────────────────────────

def build_fold_data(series: pd.Series, folds: list[tuple[int, int]]) -> list[dict]:
    """
    Materialise each fold's training slice and validation actuals once, so the
    same slicing and interpolation is not repeated for every candidate model.

    The training slice is a strict prefix of the series and is prepared using
    values from that prefix alone — this is where leakage would creep in if
    the whole series were interpolated up front.
    """
    prepared: list[dict] = []
    for i, (train_end, val_end) in enumerate(folds, start=1):
        train, _ = prepare_fit_slice(series.iloc[:train_end])
        actual = series.iloc[train_end:val_end]
        actual_known = actual.dropna()
        if train.empty or actual_known.empty:
            continue
        prepared.append({
            "fold": i,
            "train": train,
            "train_label": str(series.index[train_end - 1]),
            "actual": actual,
            "actual_known": actual_known,
            # Positions of the known actuals inside the forecast horizon.
            "offsets": [actual.index.get_loc(ix) for ix in actual_known.index],
            "scale": _naive_scale(train),
        })
    return prepared


def _score_candidate(
    candidate: BaseForecaster,
    fold_data: list[dict],
) -> tuple[CandidateScore, list[float]]:
    """
    Backtest one candidate across every fold.

    Returns its aggregated score and the flat list of out-of-sample residuals,
    which the winner later uses to size honest prediction intervals.
    """
    score = CandidateScore(
        model_key=candidate.model_key,
        model_label=candidate.model_name,
    )
    residuals: list[float] = []
    maes, rmses, mases = [], [], []

    for fold in fold_data:
        i = fold["fold"]
        train = fold["train"]
        actual = fold["actual"]
        actual_known = fold["actual_known"]

        if len(train) < candidate.min_observations:
            continue

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = candidate.__class__(
                    **({"seasonal_periods": candidate.seasonal_periods}
                       if hasattr(candidate, "seasonal_periods") else {})
                )
                fitted.fit(train)
                pred, _ = fitted.predict(steps=len(actual))
        except Exception as exc:  # a candidate failing to converge is not fatal
            logger.debug("[Selection] %s failed on fold %d: %s", candidate.model_key, i, exc)
            continue

        pred = pred.reset_index(drop=True)
        try:
            pred_known = np.array([float(pred.iloc[o]) for o in fold["offsets"]], dtype=float)
        except (IndexError, ValueError):
            continue

        errors = actual_known.values.astype(float) - pred_known
        if not np.all(np.isfinite(errors)):
            continue

        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        scale = fold["scale"]
        mase = float(mae / scale) if scale > 0 else None

        residuals.extend(errors.tolist())
        maes.append(mae)
        rmses.append(rmse)
        if mase is not None:
            mases.append(mase)

        score.folds.append(ValidationFold(
            fold=i,
            train_end=fold["train_label"],
            n_train=int(len(train)),
            n_validation=int(len(actual_known)),
            mae=round(mae, 6),
            rmse=round(rmse, 6),
            mase=round(mase, 6) if mase is not None else None,
        ))

    if not maes:
        score.eligible = False
        score.reason = "Could not be fitted and scored on any validation fold."
        return score, []

    score.n_folds = len(maes)
    score.mae = round(float(np.mean(maes)), 6)
    score.rmse = round(float(np.mean(rmses)), 6)
    score.mase = round(float(np.mean(mases)), 6) if mases else None
    return score, residuals


# ──────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────

def select_and_fit(
    series: pd.Series,
    diagnostics: SeriesDiagnostics,
    horizon: int,
) -> tuple[BaseForecaster | None, ForecastModelMetadata]:
    """
    Pick the best model for one series and return it fitted on all history.

    Selection is per-series: two countries in the same request can legitimately
    end up with different models, because the evidence for each is different.

    Args:
        series: bucket-indexed series; empty buckets are NaN, never 0.
        diagnostics: the result of ``series_validation.validate_series``.
        horizon: number of future periods requested.

    Returns:
        (fitted model or None, metadata describing the choice).
    """
    meta = ForecastModelMetadata(selection_metric="mase", validation_horizon=int(horizon))

    if diagnostics.status not in ("ok", "fallback"):
        meta.selection_method = "not_forecast"
        meta.notes.append(diagnostics.reason)
        return None, meta

    full, n_imputed = prepare_fit_slice(series)
    meta.n_imputed_for_fit = n_imputed
    if n_imputed:
        meta.notes.append(
            f"{n_imputed} internal gap(s) linearly interpolated for model fitting "
            "only; reported history keeps them as nulls."
        )

    if full.empty:
        meta.selection_method = "not_forecast"
        meta.notes.append("No fittable observations after trimming leading/trailing gaps.")
        return None, meta

    # ── Degenerate and low-evidence cases: use naive, and say so ──
    if diagnostics.is_constant or diagnostics.is_all_zero:
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "forced_constant"
        meta.notes.append(
            "The series is constant, so every model reduces to the same flat "
            "forecast; the naive baseline is used directly."
        )
        _finalise(meta, series, full)
        return model, meta

    if diagnostics.status == "fallback":
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "fallback_no_validation"
        meta.notes.append(diagnostics.reason)
        _finalise(meta, series, full)
        return model, meta

    folds = build_folds(series, horizon)
    candidates = build_candidates(
        seasonal_periods=diagnostics.seasonal_periods,
        include_seasonal=diagnostics.seasonality_supported,
    )

    if not folds:
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "fallback_no_validation"
        meta.notes.append(
            "Not enough history to build a chronological validation fold; the "
            "naive baseline is used rather than an unvalidated model."
        )
        _finalise(meta, series, full)
        return model, meta

    # ── Rolling-origin backtest over every eligible candidate ──
    fold_data = build_fold_data(series, folds)
    scores: list[CandidateScore] = []
    residuals_by_key: dict[str, list[float]] = {}
    order_by_key = {c.model_key: i for i, c in enumerate(candidates)}

    for candidate in candidates:
        score, residuals = _score_candidate(candidate, fold_data)
        scores.append(score)
        if score.eligible:
            residuals_by_key[score.model_key] = residuals

    meta.candidates = scores
    meta.n_folds = len(folds)

    eligible = [s for s in scores if s.eligible]
    if not eligible:
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "fallback_no_validation"
        meta.notes.append("No candidate could be validated; falling back to the naive baseline.")
        _finalise(meta, series, full)
        return model, meta

    # Rank by MASE when available (scale-free, baseline-relative), else by MAE.
    use_mase = any(s.mase is not None for s in eligible)
    meta.selection_metric = "mase" if use_mase else "mae"

    def sort_key(s: CandidateScore):
        primary = (s.mase if use_mase else s.mae)
        # Models without the primary metric sort last; ties break toward the
        # simpler model via registry order.
        return (primary is None, primary if primary is not None else float("inf"),
                order_by_key.get(s.model_key, 99))

    eligible.sort(key=sort_key)
    winner = eligible[0]

    naive_score = next((s for s in eligible if s.model_key == "naive"), None)
    if naive_score is not None:
        if use_mase and winner.mase is not None and naive_score.mase is not None:
            meta.beats_naive = winner.mase < naive_score.mase
        elif winner.mae is not None and naive_score.mae is not None:
            meta.beats_naive = winner.mae < naive_score.mae

    # ── Refit the winner on the complete history ──
    chosen_cls = next(c for c in candidates if c.model_key == winner.model_key)
    kwargs = {"seasonal_periods": chosen_cls.seasonal_periods} if hasattr(chosen_cls, "seasonal_periods") else {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = chosen_cls.__class__(**kwargs).fit(full)
    except Exception as exc:
        logger.warning("[Selection] Winner %s failed on full history (%s); using naive.",
                       winner.model_key, exc)
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "fallback_no_validation"
        meta.notes.append(f"Selected model failed to refit on full history: {exc}")
        _finalise(meta, series, full)
        return model, meta

    # Size the prediction intervals from out-of-sample validation errors.
    oos = residuals_by_key.get(winner.model_key) or []
    if len(oos) >= 2:
        model.set_residual_scale(np.asarray(oos, dtype=float))
        meta.interval_source = "validation_residuals"
    else:
        meta.interval_source = "in_sample_residuals"

    meta.selected_model_key = winner.model_key
    meta.selected_model_label = winner.model_label
    meta.selection_method = "rolling_origin_backtest"
    meta.selected_score = winner.mase if use_mase else winner.mae

    if meta.beats_naive is False:
        meta.notes.append(
            "No candidate beat the naive baseline on validation; the forecast "
            "carries little information beyond the last observed value."
        )
    if use_mase and winner.mase is not None and winner.mase >= 1.0:
        # MASE >= 1 means the selected model's out-of-sample error is larger
        # than a one-step naive forecast's in-sample error. It can still be
        # the best available model while being weak in absolute terms, and
        # the caller deserves to know which of those it is looking at.
        meta.notes.append(
            f"Best-available model, but MASE is {winner.mase:.2f} (>= 1): the series "
            "is noisy relative to its own period-to-period movement, so treat the "
            "point forecast as indicative rather than precise."
        )

    _finalise(meta, series, full)
    return model, meta


def _finalise(meta: ForecastModelMetadata, original: pd.Series, fitted_on: pd.Series) -> None:
    """Record whether a non-negativity floor applies to this series."""
    observed = pd.Series(original).dropna()
    meta.floor_applied = bool(len(observed) and (observed >= 0).all())
    if not meta.interval_source:
        meta.interval_source = "in_sample_residuals"


def apply_non_negative_floor(
    forecast: pd.Series,
    intervals: pd.DataFrame | None,
    apply: bool,
) -> tuple[pd.Series, pd.DataFrame | None]:
    """
    Clip forecasts (and interval bounds) at zero when the observed history was
    entirely non-negative.

    This is data-driven, not a business rule: it triggers because the series
    never went below zero, not because the column happens to be called
    "revenue". A quantity that has historically gone negative keeps its
    negative forecasts.
    """
    if not apply:
        return forecast, intervals

    floored = forecast.clip(lower=0.0)
    if intervals is not None:
        intervals = intervals.copy()
        intervals["lower"] = intervals["lower"].clip(lower=0.0)
        intervals["upper"] = intervals["upper"].clip(lower=0.0)
    return floored, intervals
