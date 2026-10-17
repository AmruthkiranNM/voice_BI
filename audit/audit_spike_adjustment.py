"""
Prediction audit - does adjusting the Jan-2022 spike improve accuracy?

Train every series on data up to Feb 2022 (the spike is then inside the
training slice), forecast Mar 2022, and compare the error with and without
the isolated-spike adjustment, for each level model. 22 products + 3
regions + the total = 26 independent held-out months.

Run from the backend directory:
    venv/Scripts/python.exe ../audit/audit_spike_adjustment.py
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
from prediction.forecast_selection import adjust_isolated_spikes  # noqa: E402
from prediction.preprocessing import aggregate_time_series  # noqa: E402
from services.database import get_database_path  # noqa: E402

con = sqlite3.connect(get_database_path())
df = pd.read_sql("SELECT s.saledate, s.boxes, s.amount, p.product, g.region FROM sales s "
                 "JOIN products p ON s.pid=p.pid JOIN geo g ON s.geoid=g.geoid", con)

series = {}
for name, frame in df.groupby("product"):
    series[f"product:{name}"] = aggregate_time_series(frame, "saledate", "boxes", frequency="months")[0]
for name, frame in df.groupby("region"):
    series[f"region:{name}"] = aggregate_time_series(frame, "saledate", "amount", frequency="months")[0]
series["total:amount"] = aggregate_time_series(df, "saledate", "amount", frequency="months")[0]

MODELS = {"Moving Average": fm.MovingAverageForecaster, "SES": fm.SimpleExpSmoothingForecaster,
          "Naive": fm.NaiveForecaster}
res = {m: {"raw": [], "adj": []} for m in MODELS}
flagged = 0
for name, s in series.items():
    s = s.dropna()
    train, actual = s.iloc[:-1], float(s.iloc[-1])        # train to Feb-22, predict Mar-22
    adj, spikes = adjust_isolated_spikes(train)
    flagged += bool(spikes)
    for m, cls in MODELS.items():
        for kind, data in (("raw", train), ("adj", adj)):
            pred = float(cls().fit(data).predict(1)[0].iloc[0])
            res[m][kind].append(abs(pred - actual) / max(actual, 1))

print(f"{len(series)} series; spike flagged in {flagged} of them (training to Feb 2022)\n")
print(f"{'model':16s} {'mean abs % error raw':>22s} {'adjusted':>10s}  {'series improved':>16s}")
for m in MODELS:
    raw, adj = np.array(res[m]["raw"]), np.array(res[m]["adj"])
    print(f"{m:16s} {raw.mean():>21.1%} {adj.mean():>10.1%}  {int((adj < raw).sum()):>9d} / {len(raw)}")
