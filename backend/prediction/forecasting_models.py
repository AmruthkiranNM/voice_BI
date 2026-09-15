"""
Prediction Package — Forecasting Models

A small library of time-series forecasters behind one interface:

    model.fit(y: pd.Series) -> self
    model.predict(steps: int) -> (forecast: pd.Series, intervals: pd.DataFrame | None)

Every model is deterministic: the same series always produces the same
forecast. No model here calls an LLM, and none of them contain business-domain
knowledge — they only see numbers and a DatetimeIndex.

The library deliberately includes trivial baselines (naive, seasonal naive,
drift). They are not filler: a forecast that cannot beat "next month looks
like last month" has not earned the right to be shown, and the selection
module in ``forecast_selection.py`` measures exactly that.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing
    HAS_STATSMODELS = True
except ImportError:  # pragma: no cover - environment-dependent
    HAS_STATSMODELS = False

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Index helpers
# ──────────────────────────────────────────────────────────

def future_index(index: pd.Index, steps: int) -> pd.Index:
    """
    Build the index of the next ``steps`` periods after ``index``.

    Uses the index's own frequency when it has one; otherwise falls back to
    the median observed spacing, so a series assembled by hand still produces
    sensible future timestamps.
    """
    if steps <= 0:
        return pd.Index([])

    if isinstance(index, pd.DatetimeIndex):
        freq = index.freq or pd.infer_freq(index) if len(index) >= 3 else index.freq
        if freq is not None:
            return pd.date_range(start=index[-1], periods=steps + 1, freq=freq)[1:]
        if len(index) >= 2:
            deltas = np.diff(index.view("int64"))
            step_ns = int(np.median(deltas))
            if step_ns > 0:
                start = index[-1].value + step_ns
                return pd.DatetimeIndex(
                    [pd.Timestamp(start + i * step_ns) for i in range(steps)]
                )
        return pd.DatetimeIndex([index[-1]] * steps)

    # Non-datetime index (rare): continue numerically.
    last = index[-1] if len(index) else 0
    try:
        return pd.Index([last + i + 1 for i in range(steps)])
    except TypeError:
        return pd.RangeIndex(start=0, stop=steps)


# ──────────────────────────────────────────────────────────
# Base
# ──────────────────────────────────────────────────────────

class BaseForecaster:
    """Common interface and interval machinery for every forecaster."""

    model_key = "base"
    model_name = "Base"
    #: Minimum observed points the model needs before it can be fitted at all.
    min_observations = 2
    #: True when the model estimates a seasonal component.
    requires_seasonality = False

    def __init__(self):
        self.history_index: pd.Index | None = None
        self._y: pd.Series | None = None
        self._resid: np.ndarray | None = None

    # -- fitting -------------------------------------------------------
    def fit(self, y: pd.Series) -> "BaseForecaster":
        y = pd.Series(y).astype(float)
        if y.isna().any():
            # Callers are expected to hand over a gap-free training slice.
            # Being defensive here keeps a stray NaN from crashing a whole run.
            y = y.interpolate(limit_direction="both")
        self._y = y
        self.history_index = y.index
        self._fit(y)
        self._resid = self._in_sample_residuals(y)
        return self

    def _fit(self, y: pd.Series) -> None:
        raise NotImplementedError

    # -- prediction ----------------------------------------------------
    def predict(self, steps: int = 12) -> tuple[pd.Series, pd.DataFrame | None]:
        if self._y is None:
            raise ValueError("Model must be fitted before predicting.")
        if steps <= 0:
            return pd.Series(dtype=float), None

        idx = future_index(self._y.index, steps)
        point = np.asarray(self._point_forecast(steps), dtype=float)
        forecast = pd.Series(point, index=idx)
        return forecast, self._intervals(forecast)

    def _point_forecast(self, steps: int) -> np.ndarray:
        raise NotImplementedError

    # -- intervals -----------------------------------------------------
    def _in_sample_residuals(self, y: pd.Series) -> np.ndarray:
        """One-step-ahead in-sample residuals; used only as an interval fallback."""
        if len(y) < 2:
            return np.array([])
        return np.asarray(y.values[1:] - y.values[:-1], dtype=float)

    def set_residual_scale(self, residuals: np.ndarray | None) -> None:
        """
        Override the interval width with out-of-sample validation residuals.

        In-sample residuals systematically understate forecast uncertainty, so
        the selection module hands back the residuals the model actually made
        on held-out data whenever backtesting was possible.
        """
        if residuals is not None and len(residuals):
            self._resid = np.asarray(residuals, dtype=float)

    def _intervals(self, forecast: pd.Series) -> pd.DataFrame | None:
        if self._resid is None or len(self._resid) < 2:
            return None
        sigma = float(np.std(self._resid))
        if not np.isfinite(sigma) or sigma <= 0:
            return None
        h = np.arange(1, len(forecast) + 1)
        spread = 1.96 * sigma * np.sqrt(h)
        return pd.DataFrame(
            {"lower": forecast.values - spread, "upper": forecast.values + spread},
            index=forecast.index,
        )


# ──────────────────────────────────────────────────────────
# Baselines
# ──────────────────────────────────────────────────────────

class NaiveForecaster(BaseForecaster):
    """Every future period equals the last observed value."""

    model_key = "naive"
    model_name = "Naive (last value)"
    min_observations = 1

    def _fit(self, y: pd.Series) -> None:
        self._last = float(y.iloc[-1])

    def _point_forecast(self, steps: int) -> np.ndarray:
        return np.full(steps, self._last)


class SeasonalNaiveForecaster(BaseForecaster):
    """Every future period repeats the value from one full cycle earlier."""

    model_key = "seasonal_naive"
    model_name = "Seasonal Naive"
    requires_seasonality = True

    def __init__(self, seasonal_periods: int = 12):
        super().__init__()
        self.seasonal_periods = int(seasonal_periods)
        self.min_observations = max(2, self.seasonal_periods)

    def _fit(self, y: pd.Series) -> None:
        m = self.seasonal_periods
        self._cycle = np.asarray(y.values[-m:], dtype=float) if len(y) >= m else np.asarray(y.values, dtype=float)

    def _point_forecast(self, steps: int) -> np.ndarray:
        cycle = self._cycle
        if cycle.size == 0:
            return np.zeros(steps)
        return np.array([cycle[i % cycle.size] for i in range(steps)], dtype=float)

    def _in_sample_residuals(self, y: pd.Series) -> np.ndarray:
        m = self.seasonal_periods
        if len(y) <= m:
            return super()._in_sample_residuals(y)
        return np.asarray(y.values[m:] - y.values[:-m], dtype=float)


class DriftForecaster(BaseForecaster):
    """Straight line through the first and last observation."""

    model_key = "drift"
    model_name = "Drift"
    min_observations = 2

    def _fit(self, y: pd.Series) -> None:
        n = len(y)
        self._last = float(y.iloc[-1])
        self._slope = (float(y.iloc[-1]) - float(y.iloc[0])) / (n - 1) if n > 1 else 0.0

    def _point_forecast(self, steps: int) -> np.ndarray:
        return self._last + self._slope * np.arange(1, steps + 1)


class MovingAverageForecaster(BaseForecaster):
    """Flat forecast at the mean of the last ``window`` observations."""

    model_key = "moving_average"
    model_name = "Moving Average"
    min_observations = 2

    def __init__(self, window: int = 3):
        super().__init__()
        self.window = int(window)

    def _fit(self, y: pd.Series) -> None:
        w = min(self.window, len(y))
        self._mean = float(np.mean(y.values[-w:]))

    def _point_forecast(self, steps: int) -> np.ndarray:
        return np.full(steps, self._mean)


# ──────────────────────────────────────────────────────────
# Exponential smoothing family (statsmodels)
# ──────────────────────────────────────────────────────────

class _StatsmodelsForecaster(BaseForecaster):
    """Shared fit/predict plumbing for the statsmodels smoothing models."""

    def _build(self, y: pd.Series):  # pragma: no cover - overridden
        raise NotImplementedError

    def _fit(self, y: pd.Series) -> None:
        if not HAS_STATSMODELS:
            raise ImportError("statsmodels is required for this model.")
        self._fitted = self._build(y).fit()

    def _point_forecast(self, steps: int) -> np.ndarray:
        return np.asarray(self._fitted.forecast(steps), dtype=float)

    def _in_sample_residuals(self, y: pd.Series) -> np.ndarray:
        resid = getattr(self._fitted, "resid", None)
        if resid is None:
            return super()._in_sample_residuals(y)
        arr = np.asarray(resid, dtype=float)
        return arr[np.isfinite(arr)]


class SimpleExpSmoothingForecaster(_StatsmodelsForecaster):
    """Level only — no trend, no seasonality."""

    model_key = "simple_exp_smoothing"
    model_name = "Simple Exponential Smoothing"
    min_observations = 3

    def _build(self, y: pd.Series):
        return SimpleExpSmoothing(y, initialization_method="estimated")


class HoltLinearForecaster(_StatsmodelsForecaster):
    """Holt's linear trend — the model this project used exclusively before."""

    model_key = "holt_linear"
    model_name = "Holt Linear Trend"
    min_observations = 4

    def _build(self, y: pd.Series):
        return ExponentialSmoothing(
            y, trend="add", seasonal=None, initialization_method="estimated"
        )


class DampedHoltForecaster(_StatsmodelsForecaster):
    """
    Holt's trend with damping.

    Damping matters here: an undamped additive trend extrapolated over a long
    horizon runs away linearly and is the direct cause of negative revenue
    forecasts on short or declining series.
    """

    model_key = "damped_holt"
    model_name = "Damped Holt Trend"
    min_observations = 5

    def _build(self, y: pd.Series):
        return ExponentialSmoothing(
            y, trend="add", seasonal=None, damped_trend=True,
            initialization_method="estimated",
        )


class HoltWintersForecaster(_StatsmodelsForecaster):
    """Additive trend plus additive seasonality; needs two full cycles."""

    model_key = "holt_winters_additive"
    model_name = "Holt-Winters (additive seasonal)"
    requires_seasonality = True

    def __init__(self, seasonal_periods: int = 12):
        super().__init__()
        self.seasonal_periods = int(seasonal_periods)
        self.min_observations = 2 * self.seasonal_periods

    def _build(self, y: pd.Series):
        return ExponentialSmoothing(
            y, trend="add", seasonal="add",
            seasonal_periods=self.seasonal_periods,
            initialization_method="estimated",
        )


# ──────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────

#: Non-seasonal candidates, ordered simplest-first. Order is the tie-break
#: rule in model selection: when two models score equally, the simpler wins.
BASE_CANDIDATES: list[tuple[str, type]] = [
    ("naive", NaiveForecaster),
    ("drift", DriftForecaster),
    ("moving_average", MovingAverageForecaster),
    ("simple_exp_smoothing", SimpleExpSmoothingForecaster),
    ("holt_linear", HoltLinearForecaster),
    ("damped_holt", DampedHoltForecaster),
]

#: Seasonal candidates, only offered when >= 2 full cycles are observed.
SEASONAL_CANDIDATES: list[tuple[str, type]] = [
    ("seasonal_naive", SeasonalNaiveForecaster),
    ("holt_winters_additive", HoltWintersForecaster),
]


def build_candidates(
    seasonal_periods: int | None = None,
    include_seasonal: bool = False,
) -> list[BaseForecaster]:
    """
    Instantiate the candidate set for one series.

    Seasonal models are included only when the caller has confirmed that the
    series actually has enough history to estimate a seasonal component —
    fitting a 12-period seasonal model to 15 points is how you get a forecast
    that memorises noise.
    """
    candidates: list[BaseForecaster] = [cls() for _, cls in BASE_CANDIDATES]

    if include_seasonal and seasonal_periods and seasonal_periods > 1:
        for _, cls in SEASONAL_CANDIDATES:
            candidates.append(cls(seasonal_periods=seasonal_periods))

    if not HAS_STATSMODELS:
        candidates = [c for c in candidates if not isinstance(c, _StatsmodelsForecaster)]

    return candidates


# ──────────────────────────────────────────────────────────
# Backwards compatibility
# ──────────────────────────────────────────────────────────

class ForecastingModelWrapper(HoltLinearForecaster):
    """
    Legacy name kept so previously pickled artifacts still unpickle and so
    ``models.MODEL_REGISTRY["exponential_smoothing"]`` keeps working.

    New code should go through ``forecast_selection.select_and_fit``, which
    picks a model on validation evidence instead of assuming this one.
    """

    model_key = "exponential_smoothing"
    model_name = "Exponential Smoothing"

    def __init__(self, model_name: str = "Exponential Smoothing"):
        super().__init__()
        self.model_name = model_name
