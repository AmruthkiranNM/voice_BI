"""
Direct-monthly forecasting vs daily-then-aggregate ("bottom-up"), judged on the
same held-out months.

The question is not which one looks less flat but which one is more accurate
on months the models never saw. Both approaches are scored by MAE on monthly
totals at several chronological cut-offs, alongside the naive "same as last
month" reference.

Run from the backend directory:
    ../venv/Scripts/python.exe ../audit/compare_bottom_up.py
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

from prediction import forecast_selection, preprocessing, series_validation  # noqa: E402

DB = BACKEND / "data" / "business_1.db"
HORIZON_MONTHS = 3


def load(where="", params=()):
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        "SELECT s.saledate, s.amount, p.product FROM sales s "
        "JOIN products p ON s.pid = p.pid " + where, conn, params=params)
    conn.close()
    df["saledate"] = pd.to_datetime(df["saledate"])
    return df


def fit_predict(df, freq, horizon):
    ts, agg = preprocessing.aggregate_time_series(df, "saledate", "amount", frequency=freq)
    diag = series_validation.validate_series(
        ts, requested_frequency=freq, horizon=horizon,
        inferred_frequency=agg.get("inferred_frequency"))
    model, meta = forecast_selection.select_and_fit(ts, diag, horizon)
    if model is None:
        return None, meta, ts
    pred, _ = model.predict(steps=horizon)
    return pred, meta, ts


def monthly_actuals(df):
    return df.set_index("saledate")["amount"].resample("ME").sum()


def evaluate(df, label):
    actual_m = monthly_actuals(df)
    cutoffs = actual_m.index[-(HORIZON_MONTHS + 4):-HORIZON_MONTHS]
    rows = []
    for cut in cutoffs:
        train = df[df["saledate"] <= cut]
        future = actual_m[(actual_m.index > cut)][:HORIZON_MONTHS]
        if len(future) < HORIZON_MONTHS:
            continue

        # (a) direct monthly
        pm, mm, _ = fit_predict(train, "months", HORIZON_MONTHS)
        # (b) daily, summed into calendar months
        days = (future.index[-1] - cut).days
        pd_, md, _ = fit_predict(train, "days", days)
        bottom_up = None
        if pd_ is not None:
            daily = pd.Series(np.asarray(pd_, dtype=float),
                              index=pd.date_range(cut + pd.Timedelta(days=1),
                                                  periods=days, freq="D"))
            bottom_up = daily.resample("ME").sum().reindex(future.index)
        naive = pd.Series(monthly_actuals(train).iloc[-1], index=future.index)

        def mae(x):
            return None if x is None else float(np.mean(np.abs(np.asarray(x) - future.values)))

        rows.append({
            "cut": cut.date(), "direct": mae(pm), "bottom_up": mae(bottom_up),
            "naive": mae(naive),
            "direct_model": mm.selected_model_label,
            "daily_model": md.selected_model_label,
        })

    print(f"\n{label}: held-out {HORIZON_MONTHS}-month windows")
    print(f"  {'cut-off':10s} {'direct MAE':>12s} {'bottom-up MAE':>14s} {'naive MAE':>11s}"
          f"  direct model / daily model")
    for r in rows:
        f = lambda v: f"{v:12,.0f}" if v is not None else f"{'-':>12s}"
        print(f"  {str(r['cut']):10s} {f(r['direct'])} {f(r['bottom_up']):>14s} "
              f"{f(r['naive']):>11s}  {r['direct_model']} / {r['daily_model']}")
    ok = [r for r in rows if r["direct"] is not None and r["bottom_up"] is not None]
    if ok:
        d = np.mean([r["direct"] for r in ok])
        b = np.mean([r["bottom_up"] for r in ok])
        n = np.mean([r["naive"] for r in ok])
        wins = sum(1 for r in ok if r["bottom_up"] < r["direct"])
        print(f"  MEAN       {d:12,.0f} {b:14,.0f} {n:11,.0f}  "
              f"bottom-up better in {wins}/{len(ok)} windows")
    return rows


def show_next_year(df, label):
    pm, mm, _ = fit_predict(df, "months", 12)
    last = df["saledate"].max()
    days = (pd.Timestamp(last) + pd.offsets.MonthEnd(12) - last).days
    pdly, md, _ = fit_predict(df, "days", days)
    daily = pd.Series(np.asarray(pdly, dtype=float),
                      index=pd.date_range(last + pd.Timedelta(days=1), periods=days, freq="D"))
    bu = daily.resample("ME").sum()[:12]
    print(f"\n{label}: next 12 months")
    print(f"  direct monthly ({mm.selected_model_label}): "
          + ", ".join(f"{v/1000:,.0f}k" for v in np.asarray(pm, dtype=float)))
    print(f"  bottom-up     ({md.selected_model_label}, MASE {md.selected_score}): "
          + ", ".join(f"{v/1000:,.0f}k" for v in bu.values))


if __name__ == "__main__":
    all_sales = load()
    evaluate(all_sales, "ALL PRODUCTS")
    show_next_year(all_sales, "ALL PRODUCTS")
    one = load("WHERE p.product = ?", ("After Nines",))
    evaluate(one, "ONE PRODUCT (After Nines)")
