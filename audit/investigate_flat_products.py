"""
Why are the per-product forecasts flat when the history swings so much?

Checks, with numbers:
  A. Is the Jan-2022 spike real data or a date-preparation artefact?
  B. Per product: winning model, MASE, whether it beat naive, and whether the
     forecast values really are constant or only look it.
  C. Are prediction intervals computed for these series at all?

Run from the backend directory:
    ../venv/Scripts/python.exe ../audit/investigate_flat_products.py
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

from services.auth import current_user_id  # noqa: E402

current_user_id.set(1)
from prediction import forecast_selection, preprocessing, series_validation  # noqa: E402

DB = BACKEND / "data" / "business_1.db"
conn = sqlite3.connect(DB)

# ── A. The spike ─────────────────────────────────────────────
print("A. ROWS AND REVENUE PER MONTH (raw table)")
monthly = pd.read_sql_query(
    "SELECT strftime('%Y-%m', saledate) m, COUNT(*) n, SUM(amount) amt, "
    "AVG(amount) avg_amt, COUNT(DISTINCT strftime('%d', saledate)) days "
    "FROM sales GROUP BY m ORDER BY m", conn)
for _, r in monthly.iterrows():
    bar = "#" * int(r.n / 40)
    print(f"  {r.m}  rows={r.n:4d}  days={r.days:2d}  avg/row={r.avg_amt:7,.0f}  "
          f"total={r.amt:12,.0f}  {bar}")

print("\n   Jan-2022 rows by day-of-month (a parse artefact would cluster on days 1-12):")
days = pd.read_sql_query(
    "SELECT CAST(strftime('%d', saledate) AS INT) d, COUNT(*) n FROM sales "
    "WHERE saledate >= '2022-01-01' AND saledate < '2022-02-01' GROUP BY d", conn)
print("   " + " ".join(f"{int(d)}:{int(n)}" for d, n in zip(days.d, days.n)))
print(f"   days 1-12: {days[days.d <= 12].n.sum()}  |  days 13-31: {days[days.d > 12].n.sum()}")

# ── B + C. Per product ───────────────────────────────────────
df = pd.read_sql_query(
    "SELECT s.saledate, s.amount, p.product FROM sales s "
    "JOIN products p ON s.pid = p.pid", conn)
df["saledate"] = pd.to_datetime(df["saledate"])
conn.close()

print("\nB/C. PER-PRODUCT MODEL CHOICE (monthly, horizon 12)")
print(f"  {'product':22s} {'model':24s} {'MASE':>6s} {'naive':>6s} beats "
      f"{'last hist':>10s} {'fc first':>9s} {'fc last':>9s} distinct interval-width")
rows = []
for product in sorted(df["product"].unique()):
    sub = df[df["product"] == product]
    ts, agg = preprocessing.aggregate_time_series(sub, "saledate", "amount", frequency="months")
    diag = series_validation.validate_series(
        ts, requested_frequency="months", horizon=12,
        inferred_frequency=agg.get("inferred_frequency"))
    model, meta = forecast_selection.select_and_fit(ts, diag, 12)
    if model is None:
        print(f"  {product:22s} refused: {diag.status}")
        continue
    pred, intervals = model.predict(steps=12)
    vals = np.asarray(pred, dtype=float)
    naive = next((c.mase for c in meta.candidates
                  if c.model_key == "naive" and c.mase is not None), None)
    width = "-"
    if intervals is not None and len(intervals):
        w = (intervals.iloc[:, 1] - intervals.iloc[:, 0]).astype(float)
        width = f"{w.iloc[0]:,.0f}..{w.iloc[-1]:,.0f}"
    rows.append((product, meta.selected_model_label, meta.selected_score, naive,
                 meta.beats_naive, ts.dropna().iloc[-1], vals[0], vals[-1],
                 len(np.unique(np.round(vals, 2))), width))

for r in sorted(rows, key=lambda r: -r[6])[:22]:
    p, m, s, n, b, last, f0, f1, d, w = r
    print(f"  {p[:22]:22s} {m[:24]:24s} {s if s is None else round(s,2)!s:>6s} "
          f"{n if n is None else round(n,2)!s:>6s} {str(b):5s} "
          f"{last:10,.0f} {f0:9,.0f} {f1:9,.0f} {d:8d} {w}")

flat = sum(1 for r in rows if r[8] == 1)
reliable = sum(1 for r in rows if r[2] is not None and r[2] < 1)
print(f"\n  {len(rows)} products: {flat} strictly flat forecasts, "
      f"{reliable} with MASE < 1 (reliable), "
      f"{sum(1 for r in rows if r[9] != '-')} with prediction intervals computed")
