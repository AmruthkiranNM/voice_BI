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

from prediction.forecasting_models import (
    BaseForecaster,
    LevelCombinationForecaster,
    NaiveForecaster,
    PatternRepeatForecaster,
    build_candidates,
)
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


#: Robust z above which an isolated point is treated as a one-off for fitting
#: (Iglewicz & Hoaglin's 3.5 on the modified z-score).
SPIKE_Z = 3.5

#: Switch, so the audit can measure accuracy with and without the adjustment.
ADJUST_SPIKES = True


def adjust_isolated_spikes(train: pd.Series) -> tuple[pd.Series, list[str]]:
    """
    Replace isolated one-period spikes with the mean of their two neighbours,
    for FITTING only.

    A single extreme period (January 2022 in the chocolate data, when every
    product roughly doubled and the next month fell back) otherwise sets the
    level a short-window model carries forward for the whole horizon: a 3-month
    moving average over [spike, normal, normal] forecasts one-third spike for
    six months.

    Only *isolated* points are touched - both neighbours must be ordinary - so
    a genuine level shift (several high periods in a row) is left alone. The
    last observation is never touched: with nothing after it, a new level and
    a spike are indistinguishable. Applied to each training slice separately,
    so no fold sees data it is scored against. Reported history is unchanged.
    """
    s = pd.Series(train).astype(float)
    if len(s) < 5:
        return s, []
    values = s.values
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad <= 0:
        return s, []
    z = 0.6745 * (values - median) / mad
    extreme = np.abs(z) > SPIKE_Z

    adjusted, periods = s.copy(), []
    for i in range(1, len(values) - 1):
        if extreme[i] and not extreme[i - 1] and not extreme[i + 1]:
            adjusted.iloc[i] = (values[i - 1] + values[i + 1]) / 2.0
            periods.append(str(s.index[i]))
    return adjusted, periods


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

    Validation horizon is set to match the actual forecast horizon as closely
    as possible, subject to not starving the training slice. For a 12-month
    forecast, scoring models only 1-step ahead selects level-only models that
    look good short-term but produce uninformative flat forecasts.
    """
    n = len(series)
    if n < MIN_TRAIN_OBSERVATIONS + 1:
        return []

    # Validation window: aim for horizon // 2 steps so the model is tested
    # over a horizon representative of the actual task, while still leaving
    # enough training history for the earliest fold.
    #   - Never more than n // 3 so the training slice stays meaningful.
    #   - At least 1 so we always have some validation.
    target_val = max(1, horizon // 2)
    h_val = max(1, min(target_val, n // 3))

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
        # MASE's scale comes from the data as recorded, so scores stay
        # comparable whether or not a spike was adjusted for fitting.
        scale = _naive_scale(train)
        if ADJUST_SPIKES:
            train, _ = adjust_isolated_spikes(train)
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
            "scale": scale,
        })
    return prepared


def _score_candidate(
    candidate: BaseForecaster,
    fold_data: list[dict],
) -> tuple[CandidateScore, list[float]]:
    """
    Backtest one candidate across every fold.

    Returns its aggregated score and the out-of-sample residuals as
    ``(steps_ahead, error)`` pairs, which the winner later uses to size its
    prediction interval at each horizon from the errors it actually made at
    that horizon.
    """
    score = CandidateScore(
        model_key=candidate.model_key,
        model_label=candidate.model_name,
    )
    residuals: list[float] = []
    maes, rmses, mases = [], [], []
    #: Folds too short for this candidate. Reported separately from a genuine
    #: fitting failure: "not enough history to try" and "tried and failed" are
    #: different answers when defending a model choice.
    skipped_for_length = 0
    longest_train = 0

    for fold in fold_data:
        i = fold["fold"]
        train = fold["train"]
        actual = fold["actual"]
        actual_known = fold["actual_known"]

        if len(train) < candidate.min_observations:
            skipped_for_length += 1
            longest_train = max(longest_train, len(train))
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

        residuals.extend((o + 1, float(e)) for o, e in zip(fold["offsets"], errors))
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
        if skipped_for_length:
            score.reason = (
                f"Needs {candidate.min_observations} observations to fit; the "
                f"longest validation fold had {longest_train}. Not attempted."
            )
        else:
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

# Models that produce inherently flat (level-only) forecasts. When a trending
# series can be better described by a trend model at nearly equal validation
# cost, prefer the trend model even if the level model scored marginally better.
_FLAT_MODEL_KEYS = frozenset({"naive", "moving_average", "simple_exp_smoothing",
                              "level_combination"})


def _series_has_significant_trend(series: pd.Series) -> bool:
    """
    Return True when the observed series carries a detectable linear trend
    relative to its own noise level.

    Uses the ratio of the OLS slope (extrapolated one standard deviation of
    index units) to the residual standard deviation. A value above 0.3 means
    the trend explains more than 30 % of one period's worth of variation —
    strong enough to justify preferring a trend model over a flat one.

    This is purely data-driven: no hard-coded threshold for any domain.
    """
    observed = series.dropna()
    if len(observed) < 4:
        return False
    x = np.arange(len(observed), dtype=float)
    slope, intercept = np.polyfit(x, observed.values.astype(float), 1)
    fitted = slope * x + intercept
    residuals = observed.values.astype(float) - fitted
    std_resid = float(np.std(residuals))
    if std_resid <= 0:
        return abs(slope) > 0
    # |slope| / std_resid > 0.3 means one extra period shifts the fit by >30%
    # of one residual standard deviation — a meaningful trend.
    if abs(slope) / std_resid <= 0.30:
        return False
    # ...and it must be statistically real, not an accident of a few noisy
    # points: the slope's t-test at the 5% level. Six to nine noisy months
    # passed the ratio alone often enough to make trend models win and then
    # extrapolate a slope that did not continue.
    n = len(observed)
    if n < 6:
        return False
    se = float(np.sqrt(np.sum(residuals ** 2) / (n - 2) / np.sum((x - x.mean()) ** 2)))
    if se <= 0:
        return True
    from scipy import stats
    p_value = 2 * stats.t.sf(abs(slope) / se, df=n - 2)
    return p_value < 0.05

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

    if ADJUST_SPIKES and not full.empty:
        full, spikes = adjust_isolated_spikes(full)
        if spikes:
            meta.spikes_adjusted = spikes
            meta.notes.append(
                f"One-off spike(s) at {', '.join(p[:7] for p in spikes)} replaced by the "
                "average of the neighbouring periods for model fitting only, so a single "
                "unusual period does not set the level for the whole forecast. The "
                "history shown keeps the real values.")

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
        _finalise(meta, series, full, diagnostics)
        return model, meta

    if diagnostics.status == "fallback":
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "fallback_no_validation"
        meta.notes.append(diagnostics.reason)
        _finalise(meta, series, full, diagnostics)
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
        _finalise(meta, series, full, diagnostics)
        return model, meta

    # ── Rolling-origin backtest over every eligible candidate ──
    fold_data = build_fold_data(series, folds)
    scores: list[CandidateScore] = []
    residuals_by_key: dict[str, list[tuple[int, float]]] = {}
    order_by_key = {c.model_key: i for i, c in enumerate(candidates)}

    for candidate in candidates:
        score, residuals = _score_candidate(candidate, fold_data)
        scores.append(score)
        if score.eligible:
            residuals_by_key[score.model_key] = residuals

    # The combination is backtested exactly like every other candidate, so its
    # score, its comparison with naive and its interval come from its own
    # held-out errors.
    combo = LevelCombinationForecaster()
    combo_score, combo_resid = _score_candidate(combo, fold_data)
    scores.append(combo_score)
    if combo_score.eligible:
        residuals_by_key[combo_score.model_key] = combo_resid
    candidates.append(combo)

    # Reference only: the "moves like the history" forecast, scored on the
    # same folds so the explanation can quote it. Never eligible to win.
    pattern_score, _ = _score_candidate(PatternRepeatForecaster(), fold_data)
    meta.pattern_reference = pattern_score

    meta.candidates = scores
    meta.n_folds = len(folds)

    eligible = [s for s in scores if s.eligible]
    if not eligible:
        model = NaiveForecaster().fit(full)
        meta.selected_model_key = model.model_key
        meta.selected_model_label = model.model_name
        meta.selection_method = "fallback_no_validation"
        meta.notes.append("No candidate could be validated; falling back to the naive baseline.")
        _finalise(meta, series, full, diagnostics)
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

    # ── Trend-aware tie-breaking ──────────────────────────────────────────
    # Level-only models (Naive, MA, SES) produce flat forecasts by design.
    # When the series carries a statistically significant trend, a flat
    # forecast is misleading even if it scored marginally better on the
    # short validation windows (because short validation disproportionately
    # rewards level accuracy over long-horizon shape accuracy).
    #
    # If the winning model is flat-producing AND the series has a significant
    # trend AND a trend-aware model (Drift, Holt, Damped Holt) is within
    # 10 % of the winner's primary score, promote that trend model instead.
    # The tolerance (10 %) is generous: validation uncertainty on short series
    # easily swamps differences smaller than that, so both models are
    # effectively tied in evidence.
    if winner.model_key in _FLAT_MODEL_KEYS and _series_has_significant_trend(series):
        trend_keys = {"drift", "holt_linear", "damped_holt"}
        trend_eligible = [s for s in eligible if s.model_key in trend_keys]
        if trend_eligible:
            best_trend = trend_eligible[0]           # already sorted by score
            w_score = winner.mase if use_mase else winner.mae
            t_score = best_trend.mase if use_mase else best_trend.mae
            if (w_score is not None and t_score is not None
                    and t_score <= w_score * 1.10):
                logger.info(
                    "[Selection] Trend detected; promoting '%s' (score=%.4f) "
                    "over flat model '%s' (score=%.4f) within 10%% tolerance.",
                    best_trend.model_key, t_score, winner.model_key, w_score,
                )
                meta.notes.append(
                    f"Series shows a significant trend; '{best_trend.model_label}' "
                    f"(score={t_score:.4f}) preferred over flat model "
                    f"'{winner.model_label}' (score={w_score:.4f}) within 10% tolerance."
                )
                winner = best_trend

    # ── The mirror rule: no trend, so do not extrapolate one ─────────────
    # A trend model can edge out a flat one on two or three short folds by
    # chance (Drift 2.163 vs Naive 2.185 on the chocolate data), and then
    # draws a slope the trend test says is not there. When the series has no
    # significant trend and a flat model is within the same 10% tolerance,
    # the simpler model is preferred.
    trend_keys_all = {"drift", "holt_linear", "damped_holt"}
    if winner.model_key in trend_keys_all and not _series_has_significant_trend(series):
        flat_eligible = [s for s in eligible if s.model_key in _FLAT_MODEL_KEYS]
        if flat_eligible:
            best_flat = flat_eligible[0]
            w_score = winner.mase if use_mase else winner.mae
            f_score = best_flat.mase if use_mase else best_flat.mae
            if (w_score is not None and f_score is not None
                    and f_score <= w_score * 1.10):
                meta.notes.append(
                    f"No significant trend in the series; '{best_flat.model_label}' "
                    f"(score={f_score:.4f}) preferred over trend model "
                    f"'{winner.model_label}' (score={w_score:.4f}) within 10% tolerance."
                )
                winner = best_flat

    # ── Combination rule: no trend and no estimable season ──────────────
    # Picking one winner from two or three tiny validation windows mostly
    # picks noise. On this project's data, selecting per series forecast
    # unseen months worse than a plain average at every training length
    # (audit/benchmark_pipeline_designs.py); the equal-weight combination of
    # level models was among the most accurate. So when the series offers no
    # trend and no estimable seasonal pattern - nothing for a more specific
    # model to capture - the combination is used. Series that do trend, or
    # have two full seasonal cycles, keep the backtested selection above.
    use_combination = (
        combo_score.eligible
        and not _series_has_significant_trend(series)
        and not diagnostics.seasonal_estimate_supported
    )
    combination_rule = False
    if use_combination and winner.model_key != combo_score.model_key:
        meta.notes.append(
            "No significant trend and too little history for a seasonal pattern, so "
            "the forecast combines four level models (mean, SES, 3-month average, last "
            "value) instead of trusting whichever single model happened to score best "
            f"on {len(folds)} short validation windows (here {winner.model_label}, "
            f"{(winner.mase if use_mase else winner.mae):.2f} vs the combination's "
            f"{(combo_score.mase if use_mase else combo_score.mae):.2f}). On unseen months, "
            "combining was more accurate than selecting on this kind of data.")
        winner = combo_score
        combination_rule = True
    elif use_combination:
        combination_rule = True

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
        _finalise(meta, series, full, diagnostics)
        return model, meta

    if isinstance(model, LevelCombinationForecaster):
        meta.mean_reversion = {"phi": round(model.phi, 4), "mean": model.mean,
                               "recent": model.recent, "level": model._level}

    try:
        _holdout_check(meta, chosen_cls, kwargs, series, horizon)
    except Exception as exc:  # a display aid must never break a forecast
        logger.debug("[Selection] holdout check skipped: %s", exc)

    # Size the prediction intervals from out-of-sample validation errors.
    oos = residuals_by_key.get(winner.model_key) or []
    if len(oos) >= 2:
        model.set_residual_scale(
            np.asarray([e for _, e in oos], dtype=float),
            steps=np.asarray([s for s, _ in oos], dtype=int),
        )
        meta.interval_source = "validation_residuals"
    else:
        meta.interval_source = "in_sample_residuals"

    meta.selected_model_key = winner.model_key
    meta.selected_model_label = winner.model_label
    meta.selection_method = ("level_combination_rule" if combination_rule
                             else "rolling_origin_backtest")
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

    _finalise(meta, series, full, diagnostics)
    return model, meta


def _holdout_check(meta: ForecastModelMetadata, chosen: BaseForecaster, kwargs: dict,
                   series: pd.Series, horizon: int) -> None:
    """
    Re-fit the chosen method without the last few known periods, predict
    them, and record the predictions next to the actuals.

    Also records what a "pattern" forecast - repeating the ups and downs of
    the periods just before - would have scored on the same periods, which is
    the alternative a reviewer usually has in mind when a forecast is flat.
    """
    observed = series.dropna()
    v = max(2, min(int(horizon), len(observed) // 3))
    if len(observed) - v < max(3, chosen.min_observations):
        return
    train, _ = prepare_fit_slice(observed.iloc[:-v])
    if ADJUST_SPIKES:
        train, _ = adjust_isolated_spikes(train)
    actual = observed.iloc[-v:]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = chosen.__class__(**kwargs).fit(train)
        pred, _ = model.predict(v)
    pred = np.asarray(pred.values, dtype=float)
    pattern = np.resize(train.values[-v:], v)       # replay the previous v periods
    meta.holdout = [{"period": str(p), "actual": float(a), "predicted": float(f)}
                    for p, a, f in zip(actual.index, actual.values, pred)]
    meta.holdout_mae = float(np.mean(np.abs(actual.values - pred)))
    meta.holdout_pattern_mae = float(np.mean(np.abs(actual.values - pattern)))


def _finalise(meta: ForecastModelMetadata, original: pd.Series, fitted_on: pd.Series,
              diagnostics: SeriesDiagnostics | None = None) -> None:
    """Record whether a non-negativity floor applies, and why the forecast has its shape."""
    observed = pd.Series(original).dropna()
    meta.floor_applied = bool(len(observed) and (observed >= 0).all())
    if not meta.interval_source:
        meta.interval_source = "in_sample_residuals"
    try:
        _explain_shape(meta, observed, diagnostics)
    except Exception as exc:  # an explanation must never break a forecast
        logger.debug("[Selection] shape explanation skipped: %s", exc)


_SEASONAL_KEYS = frozenset({"seasonal_naive", "holt_winters_additive"})


def _unit(frequency: str | None) -> str:
    f = (frequency or "period").lower().rstrip("s")
    return {"day": "day", "week": "week", "month": "month", "quarter": "quarter",
            "year": "year"}.get(f, "period")


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def _explain_shape(meta: ForecastModelMetadata, observed: pd.Series,
                   diagnostics: SeriesDiagnostics | None) -> None:
    """
    Why the forecast line is flat, sloped or repeating - in measured numbers.

    A reviewer seeing a moving history and a level forecast asks why the
    forecast does not move too. The answer is a fact about the data, so it
    is computed here from the same quantities the selection used: the size
    of the trend against the period-to-period swing, how much history a
    seasonal pattern needs against how much there is, and how many models
    were tested on held-out periods.
    """
    key = meta.selected_model_key
    meta.shape = ("seasonal" if key in _SEASONAL_KEYS
                  else "flat" if key in _FLAT_MODEL_KEYS else "trend")
    mr = meta.mean_reversion or {}
    if (key == "level_combination" and mr and mr["phi"] >= 0.05
            and abs(mr["recent"] - mr["mean"]) > 0.02 * abs(mr["mean"] or 1)):
        meta.shape = "converging"
    unit = _unit(diagnostics.requested_frequency if diagnostics else None)
    n = int(len(observed))

    facts: dict = {"n_periods": n, "unit": unit, "model": meta.selected_model_label}
    sentences: list[str] = []

    if n >= 3:
        x = np.arange(n, dtype=float)
        slope = float(np.polyfit(x, observed.values.astype(float), 1)[0])
        swing = _naive_scale(observed)
        facts.update(trend_per_period=round(slope, 4), typical_swing=round(swing, 4),
                     # bool(): numpy's bool_ is not JSON-serialisable.
                     trend_significant=bool(_series_has_significant_trend(observed)),
                     level=round(float(observed.mean()), 4))
        if meta.shape == "converging":
            h = max(int(meta.validation_horizon or 1), 1)
            steps = np.arange(1, h + 1)
            path = (mr["level"] + mr["mean"] + mr["phi"] ** steps * (mr["recent"] - mr["mean"])) / 2
            direction = "up" if mr["recent"] < mr["mean"] else "down"
            facts.update(persistence=mr["phi"], recent_level=round(mr["recent"], 4),
                         forecast_first=round(float(path[0]), 4),
                         forecast_last=round(float(path[-1]), 4))
            sentences.append(
                f"The forecast changes month by month: it starts near the recent level "
                f"({_fmt(mr['recent'])}) and moves {direction} toward the long-run average "
                f"({_fmt(mr['mean'])}), from {_fmt(float(path[0]))} to {_fmt(float(path[-1]))}. "
                f"That is how this series has behaved: about {mr['phi'] * 100:.0f}% of a "
                f"{unit}'s distance from its normal level has carried into the next {unit} "
                f"(persistence {mr['phi']:.2f}), so the forecast closes the gap by that "
                f"factor each {unit} - measured from the data, not drawn in.")
        if meta.shape == "flat" and key == "level_combination" and mr:
            sentences.append(
                f"The line is level because this series shows no carry-over from one {unit} "
                f"to the next (persistence {mr['phi']:.2f}): a high or low {unit} has not "
                f"made the following {unit} high or low, so there is no path to project - "
                f"only a level, at "
                f"{_fmt((mr['level'] + mr['mean'] + mr['phi'] * (mr['recent'] - mr['mean'])) / 2)} "
                f"per {unit}.")
        if meta.shape == "flat" and key != "level_combination":
            level_of = {
                # The raw mean would not match the line if a spike in those
                # months was adjusted for fitting, so the figure is then omitted.
                "moving_average": f"the average of the last 3 {unit}s"
                                  + ("" if meta.spikes_adjusted
                                     else f" ({_fmt(float(observed.iloc[-3:].mean()))})"),
                "naive": f"the last {unit}'s value ({_fmt(float(observed.iloc[-1]))})",
                "simple_exp_smoothing": f"a weighted average of all {unit}s, "
                                        f"weighted toward recent ones",
                "level_combination": "the average of four level forecasts (the long-run "
                                     f"mean, SES, the last 3 {unit}s' average and the "
                                     f"last {unit})",
            }.get(key, "a single level")
            sentences.append(
                f"The forecast is a level line at {level_of}, against a long-run "
                f"average of {_fmt(float(observed.mean()))} per {unit}. The chosen "
                f"model ({meta.selected_model_label}) carries that level forward "
                f"rather than a pattern - no pattern in this history held up when "
                f"tested on held-out {unit}s.")
        if meta.shape in ("flat", "converging"):
            trend_scores = [c for c in meta.candidates
                            if c.eligible and c.mase is not None
                            and c.model_key in {"drift", "holt_linear", "damped_holt"}]
            win = next((c for c in meta.candidates if c.model_key == key), None)
            if trend_scores and win is not None and win.mase is not None:
                best_trend = min(trend_scores, key=lambda c: c.mase)
                if best_trend.mase > win.mase:
                    gap = (best_trend.mase / win.mase - 1) * 100
                    verdict = (f"{gap:.0f}% less accurate on {unit}s it had not seen, so "
                               f"continuing the recent rise or fall would have made the "
                               f"forecast worse" if gap >= 10
                               else f"no better on {unit}s it had not seen, so there is no "
                                    f"evidence for extending the recent rise or fall")
                    sentences.append(
                        f"Models that extend a trend were tested too: the best, "
                        f"{best_trend.model_label}, scored {best_trend.mase:.2f} against "
                        f"{win.mase:.2f} (lower is better) - {verdict}.")
        elif meta.shape == "trend":
            sentences.append(
                f"The forecast is a straight trend because the chosen model "
                f"({meta.selected_model_label}) continues the direction the series "
                f"has been moving in.")
        elif meta.shape == "seasonal":
            sentences.append(
                f"The forecast repeats the shape of the last cycle because the "
                f"chosen model ({meta.selected_model_label}) carries the seasonal "
                f"pattern forward.")
        if swing > 0:
            measured = (f"Over the {n} {unit}s of history the values moved by about "
                        f"{_fmt(slope)} per {unit} overall, against a typical swing of "
                        f"{_fmt(swing)} from one {unit} to the next")
            if facts["trend_significant"]:
                tail = " - a real direction to project."
            elif meta.shape == "trend":
                tail = (" - small overall, but the trend model still predicted the "
                        "held-out " + unit + "s more accurately than any level model, "
                        "so the recent direction is carried forward.")
            else:
                tail = (" - the ups and downs are far larger than any direction, so "
                        "there is no reliable trend to project.")
            sentences.append(measured + tail)

    if diagnostics and diagnostics.seasonal_periods and not diagnostics.seasonal_estimate_supported:
        need = 2 * int(diagnostics.seasonal_periods)
        facts.update(seasonal_needed=need, seasonal_available=n)
        sentences.append(
            f"A repeating {diagnostics.seasonal_periods}-{unit} pattern (e.g. a "
            f"yearly cycle) needs at least {need} {unit}s of history to estimate; "
            f"this series has {n}, so no seasonal shape can be learned yet.")

    tested = [c for c in meta.candidates if c.eligible]
    if tested:
        facts["models_tested"] = len(tested)
        scored = [c for c in tested if c.mase is not None] or tested
        best = min(scored, key=lambda c: c.mase if c.mase is not None else (c.mae or float("inf")))
        if best.model_key == key:
            how = f"{meta.selected_model_label} had the lowest error."
        elif key == "level_combination":
            how = (f"{best.model_label} scored best on these few windows, but picking a "
                   f"single winner from so little evidence mostly picks noise; on short, "
                   f"noisy series, averaging level models forecasts unseen {unit}s more "
                   f"accurately, so the combination is used.")
        elif meta.shape == "trend":
            how = (f"{best.model_label} scored marginally better (within 10%), but "
                   f"the series has a significant trend, so "
                   f"{meta.selected_model_label} was preferred.")
        else:
            how = (f"{best.model_label} scored marginally better, but within 10% - "
                   f"well inside the noise of so few held-out {unit}s - so the "
                   f"simpler {meta.selected_model_label} was chosen.")
        sentences.append(f"{len(tested)} models were tested on held-out {unit}s; {how}")

    pattern = meta.pattern_reference
    chosen_score = meta.selected_score
    if (pattern is not None and pattern.eligible and pattern.mase is not None
            and chosen_score is not None and meta.selection_metric == "mase"):
        facts.update(pattern_mase=round(pattern.mase, 4))
        if pattern.mase > chosen_score:
            sentences.append(
                f"A forecast that moves like the history - repeating its recent ups and "
                f"downs - was tested on the same held-out {unit}s: it scored "
                f"{pattern.mase:.2f} against {chosen_score:.2f} for this forecast (lower is "
                f"better), {(pattern.mase / chosen_score - 1) * 100:.0f}% less accurate. "
                f"Past swings do not repeat on schedule, so copying them adds error.")
        else:
            sentences.append(
                f"A forecast repeating the history's recent ups and downs scored "
                f"{pattern.mase:.2f} against {chosen_score:.2f} here - no worse on these "
                f"few windows - but it is not used because swings that are not a "
                f"measured cycle cannot be relied on to recur.")

    if meta.holdout and meta.holdout_mae is not None:
        v = len(meta.holdout)
        above = sum(1 for r in meta.holdout if r["actual"] > r["predicted"])
        below = v - above
        facts.update(holdout_mae=round(meta.holdout_mae, 4), holdout_above=above,
                     holdout_below=below)
        lead = (f"The dotted line shows this method re-fitted without the last {v} known "
                f"{unit}s and asked to predict them; it missed by "
                f"{_fmt(meta.holdout_mae)} per {unit} on average. ")
        if above and below:
            tail = (f"The real {unit}s landed on both sides of it ({above} above, {below} "
                    f"below) - the swings scatter around a level rather than following a path.")
        elif above:
            tail = (f"All {v} real {unit}s came in above it: this series ran higher than its "
                    f"history predicted. Too few {unit}s show it yet for any model to confirm "
                    f"a lasting rise, so the forecast level is set from the evidence and the "
                    f"band's upper half covers a continued rise.")
        else:
            tail = (f"All {v} real {unit}s came in below it: this series ran lower than its "
                    f"history predicted. Too few {unit}s show it yet for any model to confirm "
                    f"a lasting fall, so the forecast level is set from the evidence and the "
                    f"band's lower half covers a continued fall.")
        sentences.append(lead + tail)

    if meta.interval_source == "validation_residuals":
        sentences.append(
            f"The shaded band is where each future {unit} is expected to fall 95% "
            f"of the time, sized from the model's own errors on held-out {unit}s. "
            f"The ups and downs of the history show up there - as uncertainty - "
            f"rather than as invented wiggles in the line.")

    meta.shape_facts = facts
    meta.shape_explanation = sentences


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
