"""
Prediction audit - why does the top-5 by boxes change in the forecast?

For every product: all-history average per month, last-6-month average,
the selected model and its 6-month forecast average. Shows whether the
forecast follows the recent level, the long-run level, or neither.

Run from the backend directory:
    venv/Scripts/python.exe ../audit/audit_topn_change.py
"""
import sqlite3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pandas as pd  # noqa: E402

from prediction import predictor  # noqa: E402
from prediction.preprocessing import aggregate_time_series  # noqa: E402
from services.database import get_database_path  # noqa: E402

H = 6
con = sqlite3.connect(get_database_path())
df = pd.read_sql("SELECT s.saledate, s.boxes, p.product FROM sales s JOIN products p ON s.pid=p.pid", con)

rows = []
for product, frame in df.groupby("product"):
    s, info = aggregate_time_series(frame, "saledate", "boxes", frequency="months")
    _, meta, fc, _ = predictor.run_series_forecast(s, steps=H, frequency="months",
                                                   inferred_frequency=info.get("inferred_frequency"))
    obs = s.dropna()
    rows.append({"product": product, "total_all": obs.sum(), "avg_all": obs.mean(),
                 "avg_last6": obs.iloc[-H:].mean(), "avg_last6_excl_jan22": obs.iloc[-H:].drop(
                     [i for i in obs.index[-H:] if str(i).startswith("2022-01")]).mean(),
                 "fc_avg": fc.mean(), "fc_total": fc.sum(), "model": meta.selected_model_label})

t = pd.DataFrame(rows)
t["rank_all"] = t.total_all.rank(ascending=False).astype(int)
t["rank_fc"] = t.fc_total.rank(ascending=False, method="first").astype(int)
t = t.sort_values("rank_fc")
pd.set_option("display.width", 220)
print(t.round(0).to_string(index=False))
near = lambda a, b: abs(a - b) / max(abs(b), 1)
t["closer_to"] = ["recent" if near(r.fc_avg, r.avg_last6) < near(r.fc_avg, r.avg_all) else "all-history"
                  for r in t.itertuples()]
print("\nForecast average is closer to:", t.closer_to.value_counts().to_dict())
