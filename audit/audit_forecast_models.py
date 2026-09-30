"""
Prediction audit, step 1 — what each model actually produces.

Synthetic series with known behaviour, so a flat forecast can be judged rather
than guessed at: a trend series must extrapolate, a seasonal series must
oscillate, and a model that repeats one number must be doing so by definition
(Naive, Moving Average) rather than by accident.

Run from the backend directory:
    ../venv/Scripts/python.exe ../audit/audit_forecast_models.py
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from prediction import forecasting_models as fm  # noqa: E402

H = 12


def monthly(values):
    idx = pd.date_range("2021-01-31", periods=len(values), freq="ME")
    return pd.Series([float(v) for v in values], index=idx)


SERIES = {
    "pure trend (100..340, +10/mo)": monthly(range(100, 340, 10)),
    "seasonal (level 100, +-30, period 12, 3 cycles)": monthly([
        100 + 30 * np.sin(2 * np.pi * i / 12) for i in range(36)
    ]),
    "trend + season (3 cycles)": monthly([
        100 + 2 * i + 30 * np.sin(2 * np.pi * i / 12) for i in range(36)
    ]),
    "noisy, no trend": monthly([
        150000, 90000, 180000, 110000, 170000, 95000,
        160000, 105000, 175000, 100000, 165000, 120000,
    ]),
    "flat/constant": monthly([100] * 24),
    "short (5 points, trend)": monthly([100, 110, 120, 130, 140]),
}

CANDIDATES = [
    ("Naive", fm.NaiveForecaster, {}),
    ("Seasonal Naive", fm.SeasonalNaiveForecaster, {"seasonal_periods": 12}),
    ("Drift", fm.DriftForecaster, {}),
    ("Moving Average", fm.MovingAverageForecaster, {}),
    ("SES", fm.SimpleExpSmoothingForecaster, {}),
    ("Holt", fm.HoltLinearForecaster, {}),
    ("Damped Holt", fm.DampedHoltForecaster, {}),
    ("Holt-Winters", fm.HoltWintersForecaster, {"seasonal_periods": 12}),
]


def describe(values: np.ndarray) -> str:
    """How much the forecast actually moves across the horizon."""
    if len(values) == 0:
        return "EMPTY"
    distinct = len(np.unique(np.round(values, 6)))
    if distinct == 1:
        return "FLAT (one repeated value)"
    spread = (values.max() - values.min())
    rel = spread / abs(values.mean()) if values.mean() else 0.0
    direction = ("rising" if values[-1] > values[0] + 1e-9
                 else "falling" if values[-1] < values[0] - 1e-9 else "oscillating")
    return f"{distinct} distinct, {direction}, spread {spread:,.1f} ({rel:.1%} of mean)"


def main() -> None:
    for name, series in SERIES.items():
        print("=" * 78)
        print(f"SERIES: {name}   n={len(series)}  "
              f"last={series.iloc[-1]:,.1f}  mean={series.mean():,.1f}")
        print("-" * 78)
        for label, cls, kwargs in CANDIDATES:
            try:
                model = cls(**kwargs)
                if len(series) < getattr(model, "min_observations", 1):
                    print(f"  {label:16s} SKIPPED (needs "
                          f"{model.min_observations} obs, has {len(series)})")
                    continue
                model.fit(series)
                pred, intervals = model.predict(steps=H)
                values = np.asarray(pred, dtype=float)
                head = ", ".join(f"{v:,.1f}" for v in values[:4])
                print(f"  {label:16s} n={len(values):2d}  [{head}, ...]")
                print(f"  {'':16s} {describe(values)}"
                      + (f"  | intervals: {'yes' if intervals is not None else 'no'}"))
            except Exception as exc:
                print(f"  {label:16s} FAILED: {type(exc).__name__}: {exc}")
        print()


if __name__ == "__main__":
    main()
