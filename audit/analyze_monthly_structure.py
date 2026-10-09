"""
Prediction audit - is there month-to-month structure a forecast could learn?

The forecast for the chocolate data is flat while the history moves. That is
only a defect if the movement is predictable. This checks the candidates:

  1. Seasonality  - needs two full cycles (24 months) to estimate; we have 15.
  2. Trend        - OLS slope vs residual noise.
  3. Calendar     - months differ in length and in trading days; a monthly
                    total partly reflects how many selling days the month had.
  4. Weekday mix  - whether selling happens on all days or only some.

Run from the backend directory:
    venv/Scripts/python.exe ../audit/analyze_monthly_structure.py
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
from services.database import get_database_path  # noqa: E402

con = sqlite3.connect(get_database_path())
df = pd.read_sql("SELECT saledate, amount, boxes FROM sales", con, parse_dates=["saledate"])
df["day"] = df.saledate.dt.normalize()

print("rows:", len(df), " days with sales:", df.day.nunique(),
      " span:", df.day.min().date(), "->", df.day.max().date())
print("\nSales rows by weekday (0=Mon):")
print(df.saledate.dt.weekday.value_counts().sort_index().to_string())

daily = df.groupby("day").amount.sum()
full_days = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
print(f"\nCalendar days in span: {len(full_days)}; days with no sales: {len(full_days) - len(daily)}")

m = df.groupby(df.saledate.dt.to_period("M")).agg(
    amount=("amount", "sum"), rows=("amount", "size"),
    selling_days=("day", "nunique"))
m["cal_days"] = [p.days_in_month for p in m.index]
m["weekdays"] = [np.busday_count(p.start_time.date(), (p.end_time + pd.Timedelta(days=1)).date())
                 for p in m.index]
m["per_selling_day"] = (m.amount / m.selling_days).round(0)
m["per_row"] = (m.amount / m.rows).round(0)
print("\nMonthly structure:")
print(m.to_string())

print("\nWhat explains the month-to-month movement in the total?")
for col in ["rows", "selling_days", "cal_days", "weekdays"]:
    r = np.corrcoef(m.amount, m[col])[0, 1]
    print(f"  corr(amount, {col:13s}) = {r:+.2f}")
print(f"  CV of monthly total      = {m.amount.std() / m.amount.mean():.2%}")
print(f"  CV of value per row      = {m.per_row.std() / m.per_row.mean():.2%}")
print(f"  CV of rows per month     = {m.rows.std() / m.rows.mean():.2%}")

x = np.arange(len(m))
slope, icpt = np.polyfit(x, m.amount.values, 1)
resid = m.amount.values - (slope * x + icpt)
print(f"\nTrend: slope {slope:,.0f}/month; residual sd {resid.std():,.0f}; ratio {abs(slope) / resid.std():.2f}"
      " (engine treats > 0.30 as a real trend)")
print(f"Months available: {len(m)}; seasonal estimation needs 24 (two 12-month cycles).")
