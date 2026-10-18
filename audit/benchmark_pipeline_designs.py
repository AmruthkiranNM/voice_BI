"""
Prediction audit - which pipeline design forecasts unseen months best?

benchmark_forecasters.py showed the per-series model *selection* losing to a
plain average on this data: with 2-3 tiny validation folds the "winner" is
often noise. This compares candidate designs, each predicting months it has
not seen, on 26 series at three origins (train 6/9/12 months).

Run from the backend directory:
    venv/Scripts/python.exe ../audit/benchmark_pipeline_designs.py
"""
import sqlite3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from prediction import forecasting_models as fm  # noqa: E402
from prediction import predictor  # noqa: E402
from prediction.forecast_selection import adjust_isolated_spikes  # noqa: E402
from prediction.preprocessing import aggregate_time_series  # noqa: E402
from services.database import get_database_path  # noqa: E402

con = sqlite3.connect(get_database_path())
df = pd.read_sql("SELECT s.saledate, s.boxes, s.amount, p.product, g.region FROM sales s "
                 "JOIN products p ON s.pid=p.pid JOIN geo g ON s.geoid=g.geoid", con)
SERIES = {}
for name, f in df.groupby("product"):
    SERIES[f"product:{name}"] = aggregate_time_series(f, "saledate", "boxes", frequency="months")[0].dropna()
for name, f in df.groupby("region"):
    SERIES[f"region:{name}"] = aggregate_time_series(f, "saledate", "amount", frequency="months")[0].dropna()
SERIES["total:amount"] = aggregate_time_series(df, "saledate", "amount", frequency="months")[0].dropna()


def level_forecasts(train, h):
    v = train.values.astype(float)
    return {
        "mean": np.full(h, v.mean()),
        "ses": fm.SimpleExpSmoothingForecaster().fit(train).predict(h)[0].values,
        "ma3": np.full(h, v[-3:].mean()),
        "naive": np.full(h, v[-1]),
        "damped": fm.DampedHoltForecaster().fit(train).predict(h)[0].values
        if len(v) >= fm.DampedHoltForecaster.min_observations else np.full(h, v[-1]),
    }


def designs(train, h):
    adj, _ = adjust_isolated_spikes(train)
    f = level_forecasts(train, h)
    fa = level_forecasts(adj, h)
    _, _, fc, _ = predictor.run_series_forecast(train, steps=h, frequency="months")
    return {
        "current pipeline (select one)": fc.values.astype(float),
        "mean": f["mean"],
        "combo: mean+ses+ma3+naive": np.mean([f[k] for k in ("mean", "ses", "ma3", "naive")], axis=0),
        "combo: mean+ses+ma3+naive (spike-adj)": np.mean([fa[k] for k in ("mean", "ses", "ma3", "naive")], axis=0),
        "combo: mean+ses+damped": np.mean([f[k] for k in ("mean", "ses", "damped")], axis=0),
        "combo: mean+ses+damped (spike-adj)": np.mean([fa[k] for k in ("mean", "ses", "damped")], axis=0),
        "median of 5": np.median([f[k] for k in f], axis=0),
    }


results = {}
for origin, h in ((6, 6), (9, 6), (12, 3)):
    for name, s in SERIES.items():
        train, test = s.iloc[:origin], s.iloc[origin:origin + h].values.astype(float)
        scale = np.mean(np.abs(np.diff(train.values))) or 1.0
        for k, p in designs(train, len(test)).items():
            results.setdefault(k, {}).setdefault(origin, []).append(
                np.mean(np.abs(test - p[:len(test)])) / scale)

print("Mean MASE on unseen months (lower is better); columns = months of training\n")
print(f"{'design':42s} {'6':>7s} {'9':>7s} {'12':>7s} {'all':>7s}")
for k, by in sorted(results.items(), key=lambda kv: np.mean(sum(kv[1].values(), []))):
    allv = sum(by.values(), [])
    print(f"{k:42s} {np.mean(by[6]):>7.3f} {np.mean(by[9]):>7.3f} {np.mean(by[12]):>7.3f} {np.mean(allv):>7.3f}")
