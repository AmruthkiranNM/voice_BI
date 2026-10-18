"""
Prediction audit - would any "wiggly" forecast have been more accurate?

The guide's question: the history swings, so why is the forecast a straight
line? This answers it with out-of-sample accuracy. Every method predicts 6
months it has not seen, from two origins (train on 6 months -> predict 7-12,
train on 9 -> predict 10-15), on 26 series (22 products' boxes, 3 regions'
revenue, total revenue).

Methods:
  pipeline         - this project's model selection (rolling-origin MASE)
  naive            - last value
  mean             - average of all training months
  ses / ma3        - level models
  seasonal_naive   - repeat the same months last year (wiggly)
  repeat_last_6    - repeat the last 6 months' shape (wiggly)
  linear_trend     - straight line through the history
  gbm_lags         - gradient boosting on the last 3 values (ML, wiggly)

It also checks the pipeline's 95% band: what share of the held-out actuals
fell inside it.

Run from the backend directory:
    venv/Scripts/python.exe ../audit/benchmark_forecasters.py
"""
import sqlite3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from prediction import forecasting_models as fm  # noqa: E402
from prediction import predictor  # noqa: E402
from prediction.preprocessing import aggregate_time_series  # noqa: E402
from services.database import get_database_path  # noqa: E402

H = 6
con = sqlite3.connect(get_database_path())
df = pd.read_sql("SELECT s.saledate, s.boxes, s.amount, p.product, g.region FROM sales s "
                 "JOIN products p ON s.pid=p.pid JOIN geo g ON s.geoid=g.geoid", con)

SERIES = {}
for name, f in df.groupby("product"):
    SERIES[f"product:{name}"] = aggregate_time_series(f, "saledate", "boxes", frequency="months")[0].dropna()
for name, f in df.groupby("region"):
    SERIES[f"region:{name}"] = aggregate_time_series(f, "saledate", "amount", frequency="months")[0].dropna()
SERIES["total:amount"] = aggregate_time_series(df, "saledate", "amount", frequency="months")[0].dropna()


def gbm_lags(train, h):
    v = train.values.astype(float)
    if len(v) < 5:
        return np.full(h, v[-1])
    X = np.array([v[i - 3:i] for i in range(3, len(v))])
    y = v[3:]
    model = GradientBoostingRegressor(n_estimators=100, max_depth=2, random_state=0).fit(X, y)
    hist, out = list(v), []
    for _ in range(h):                      # recursive multi-step
        p = float(model.predict([hist[-3:]])[0])
        out.append(p)
        hist.append(p)
    return np.array(out)


def methods(train, h):
    v = train.values.astype(float)
    x = np.arange(len(v))
    slope, b = np.polyfit(x, v, 1)
    m = {
        "naive": np.full(h, v[-1]),
        "mean": np.full(h, v.mean()),
        "ma3": np.full(h, v[-3:].mean()),
        "ses": fm.SimpleExpSmoothingForecaster().fit(train).predict(h)[0].values,
        "repeat_last_6": np.resize(v[-6:], h),
        "linear_trend": slope * np.arange(len(v), len(v) + h) + b,
        "gbm_lags": gbm_lags(train, h),
    }
    m["seasonal_naive"] = v[-12:][:h] if len(v) >= 12 else np.full(h, np.nan)
    _, _, fc, ci = predictor.run_series_forecast(train, steps=h, frequency="months")
    m["pipeline"] = fc.values.astype(float)
    return m, ci


errors, inside, total_pts = {}, 0, 0
for name, s in SERIES.items():
    for origin in (6, 9):
        train, test = s.iloc[:origin], s.iloc[origin:origin + H].values.astype(float)
        scale = np.mean(np.abs(np.diff(train.values))) or 1.0       # MASE scale
        preds, ci = methods(train, len(test))
        for k, p in preds.items():
            if np.isnan(p).any():
                continue
            errors.setdefault(k, []).append(np.mean(np.abs(test - p[:len(test)])) / scale)
        if ci is not None:
            lo, hi = ci["lower"].values[:len(test)], ci["upper"].values[:len(test)]
            inside += int(((test >= lo) & (test <= hi)).sum())
            total_pts += len(test)

print(f"{len(SERIES)} series x 2 origins, {H}-month horizon, error = MASE (lower is better)\n")
rows = sorted(((k, np.mean(v), np.median(v), len(v)) for k, v in errors.items()), key=lambda r: r[1])
print(f"{'method':16s} {'mean MASE':>10s} {'median':>8s} {'n':>4s}")
for k, mean, med, n in rows:
    tag = "  <- wiggly" if k in ("seasonal_naive", "repeat_last_6", "gbm_lags") else ""
    print(f"{k:16s} {mean:>10.3f} {med:>8.3f} {n:>4d}{tag}")
pipe = np.array(errors["pipeline"])
for k in ("seasonal_naive", "repeat_last_6", "gbm_lags", "linear_trend", "naive"):
    other = np.array(errors[k])
    if len(other) == len(pipe):
        print(f"pipeline beats {k:15s} on {int((pipe < other).sum())}/{len(pipe)} series-origins")
print(f"\n95% band coverage on held-out months: {inside}/{total_pts} = {inside / total_pts:.1%}")
