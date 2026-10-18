"""
Prediction audit - can a forecast that changes month to month be as accurate?

The level combination is flat by construction. A mean-reverting forecast
(AR(1) around the long-run mean) starts near the recent level and moves a
step closer to the long-run level each month, at a speed estimated from the
series' own month-to-month persistence. It changes every month without any
invented pattern. This compares them on unseen months (26 series, three
training lengths), using the same setup as benchmark_pipeline_designs.py.

Run from the backend directory:
    venv/Scripts/python.exe ../audit/benchmark_mean_reversion.py
"""
import contextlib
import io
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import benchmark_pipeline_designs as b  # noqa: E402

from prediction import forecasting_models as fm  # noqa: E402
from prediction.forecast_selection import adjust_isolated_spikes  # noqa: E402


def phi_of(v):
    """Lag-1 persistence of the de-meaned series, kept in [0, 0.95]."""
    d = v - v.mean()
    if len(d) < 4 or np.dot(d[:-1], d[:-1]) == 0:
        return 0.0
    return float(np.clip(np.dot(d[1:], d[:-1]) / np.dot(d[:-1], d[:-1]), 0.0, 0.95))


def ar1(v, h, start=None):
    mu, phi = v.mean(), phi_of(v)
    s = v[-1] if start is None else start
    return mu + phi ** np.arange(1, h + 1) * (s - mu)


def methods(train, h):
    adj, _ = adjust_isolated_spikes(train)
    v = adj.values.astype(float)
    combo = fm.LevelCombinationForecaster().fit(adj).predict(h)[0].values
    recent = np.mean([v[-1], v[-3:].mean(),
                      float(fm.SimpleExpSmoothingForecaster().fit(adj).predict(1)[0].iloc[0])])
    return {
        "level combination (current)": combo,
        "AR(1) from last value": ar1(v, h),
        "AR(1) from recent level": ar1(v, h, start=recent),
        "avg(combination, AR(1) recent)": (combo + ar1(v, h, start=recent)) / 2,
    }


res = {}
moves = {}
for origin, h in ((6, 6), (9, 6), (12, 3)):
    for name, s in b.SERIES.items():
        train, test = s.iloc[:origin], s.iloc[origin:origin + h].values.astype(float)
        scale = np.mean(np.abs(np.diff(train.values))) or 1.0
        for k, p in methods(train, len(test)).items():
            res.setdefault(k, {}).setdefault(origin, []).append(np.mean(np.abs(test - p)) / scale)
            moves.setdefault(k, []).append(float(np.ptp(p) / max(abs(p.mean()), 1)))

print("Mean MASE on unseen months (lower is better); columns = months of training\n")
print(f"{'design':34s} {'6':>7s} {'9':>7s} {'12':>7s} {'all':>7s} {'month-to-month movement':>25s}")
for k, by in sorted(res.items(), key=lambda kv: np.mean(sum(kv[1].values(), []))):
    allv = sum(by.values(), [])
    print(f"{k:34s} {np.mean(by[6]):>7.3f} {np.mean(by[9]):>7.3f} {np.mean(by[12]):>7.3f} "
          f"{np.mean(allv):>7.3f} {np.mean(moves[k]):>24.1%}")
