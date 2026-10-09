"""
Prediction audit - the engine on the real chocolate data, no LLM involved.

For each series and horizon: every candidate's rolling-origin score, the
winner, the forecast it produces, and the interval around it. Then an
honest check of the winner against the alternatives a reviewer would
suggest ("why not a model that moves like the history?").

Run from the backend directory:
    venv/Scripts/python.exe ../audit/audit_real_forecasts.py
"""
import sqlite3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from prediction import predictor  # noqa: E402
from prediction.preprocessing import aggregate_time_series  # noqa: E402
from services.database import get_database_path  # noqa: E402

con = sqlite3.connect(get_database_path())
df = pd.read_sql(
    "SELECT s.saledate, s.amount, s.boxes, g.region, g.geo FROM sales s "
    "JOIN geo g ON s.geoid = g.geoid", con)


def run(label, frame, target, horizon):
    series, info = aggregate_time_series(frame, "saledate", target, frequency="months")
    diag, meta, fc, ci = predictor.run_series_forecast(
        series, steps=horizon, frequency="months",
        inferred_frequency=info.get("inferred_frequency"),
        duplicate_timestamps=info.get("duplicate_timestamps", 0),
        n_trimmed_partial=info.get("n_trimmed_partial", 0))
    print(f"\n=== {label} | {target} | h={horizon} | {len(series)} months "
          f"({series.index[0].date()} .. {series.index[-1].date()})")
    print(f"  seasonality_supported={diag.seasonality_supported} "
          f"seasonal_estimate_supported={getattr(diag, 'seasonal_estimate_supported', None)} "
          f"folds={meta.n_folds} val_horizon={meta.validation_horizon}")
    for c in sorted(meta.candidates, key=lambda c: (c.mase is None, c.mase or 9e9)):
        mark = "*" if c.model_key == meta.selected_model_key else " "
        print(f"  {mark} {c.model_label:32s} MASE={c.mase!s:10.10s} MAE={c.mae!s:12.12s} "
              f"folds={c.n_folds} {'' if c.eligible else '[' + (c.reason or '') + ']'}")
    print(f"  selected: {meta.selected_model_label} (score {meta.selected_score}) "
          f"beats_naive={meta.beats_naive} interval_source={meta.interval_source}")
    vals = [float(v) for v in fc.values]
    spread = (max(vals) - min(vals)) / (abs(np.mean(vals)) or 1)
    print(f"  history mean {series.mean():,.0f}  last {series.iloc[-1]:,.0f}  "
          f"sd {series.std():,.0f}")
    print(f"  forecast: first {vals[0]:,.0f} last {vals[-1]:,.0f} "
          f"(max-min spread {spread:.2%} of mean)")
    if ci is not None:
        w0 = ci.iloc[0].upper - ci.iloc[0].lower
        w1 = ci.iloc[-1].upper - ci.iloc[-1].lower
        print(f"  interval width: first {w0:,.0f}  last {w1:,.0f}  "
              f"(history sd x2 = {2 * series.std():,.0f})")
        inside = ((series >= ci.lower.min()) & (series <= ci.upper.max())).mean()
        print(f"  share of HISTORICAL months inside the widest band: {inside:.0%}")
    for note in meta.notes:
        print("  note:", note)
    print("  shape:", meta.shape)
    for s in meta.shape_explanation:
        print("   >", s)


for h in (6, 12):
    run("ALL", df, "amount", h)
run("ALL", df, "boxes", 6)
for region in sorted(df.region.unique()):
    run(f"region={region}", df[df.region == region], "amount", 6)
