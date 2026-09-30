"""
Prediction audit, step 2 — the real pipeline on the real data.

Checks the numbers at each stage rather than the shape of the graph:
aggregation, seasonality gating, horizon, per-period forecast values, per-group
independence, and what the API actually returns.

Run from the backend directory:
    ../venv/Scripts/python.exe ../audit/audit_pipeline.py
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import sqlite3  # noqa: E402

import pandas as pd  # noqa: E402

from services.auth import current_user_id  # noqa: E402

current_user_id.set(1)

from prediction import forecast_selection, preprocessing, series_validation  # noqa: E402

DB = BACKEND / "data" / "business_1.db"


def load(dim=None):
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        "SELECT s.saledate, s.amount, g.geo AS country, p.product, p.category "
        "FROM sales s LEFT JOIN geo g ON s.geoid = g.geoid "
        "LEFT JOIN products p ON s.pid = p.pid", conn)
    conn.close()
    df["saledate"] = pd.to_datetime(df["saledate"])
    return df


def stage_report(df, freq, horizon, label):
    print("=" * 76)
    print(f"{label}: frequency={freq} horizon={horizon}")

    ts, agg = preprocessing.aggregate_time_series(df, "saledate", "amount", frequency=freq)
    print(f"  1. AGGREGATION: {len(ts)} buckets, {ts.notna().sum()} observed, "
          f"{ts.isna().sum()} empty (kept as NaN)")
    print(f"     inferred frequency: {agg.get('inferred_frequency')}, "
          f"duplicates merged: {agg.get('duplicate_timestamps')}")
    print(f"     first 4 values: "
          + ", ".join(f"{i.date()}={v:,.0f}" for i, v in ts.head(4).items()))
    print(f"     variation: min {ts.min():,.0f}  max {ts.max():,.0f}  "
          f"std/mean {ts.std()/ts.mean():.1%}")

    diag = series_validation.validate_series(
        ts, requested_frequency=freq, horizon=horizon,
        inferred_frequency=agg.get("inferred_frequency"),
        duplicate_timestamps=agg.get("duplicate_timestamps", 0),
        n_trimmed_partial=agg.get("n_trimmed_partial", 0))
    print(f"  2. VALIDATION: status={diag.status} "
          f"seasonality_supported={diag.seasonality_supported} "
          f"seasonal_periods={diag.seasonal_periods}")
    if diag.reason:
        print(f"     reason: {diag.reason}")

    model, meta = forecast_selection.select_and_fit(ts, diag, horizon)
    print(f"  3. SELECTION: {meta.selected_model_label} via {meta.selection_method}, "
          f"folds={meta.n_folds}, MASE={meta.selected_score}, "
          f"beats_naive={meta.beats_naive}")
    scored = [c for c in meta.candidates if c.mase is not None]
    if scored:
        print("     candidates: " + "; ".join(
            f"{c.model_label}={c.mase:.3f}" for c in sorted(scored, key=lambda c: c.mase)))
    skipped = [c for c in meta.candidates if c.mase is None]
    if skipped:
        print("     not scored: " + "; ".join(
            f"{c.model_label} ({c.reason[:40]})" for c in skipped))

    if model is None:
        print("  4. FORECAST: refused")
        return
    pred, intervals = model.predict(steps=horizon)
    values = list(pred.astype(float))
    distinct = len(set(round(v, 6) for v in values))
    print(f"  4. FORECAST: {len(values)} periods (asked for {horizon}), "
          f"{distinct} distinct values")
    print("     " + ", ".join(
        f"{str(i)[:10]}={v:,.0f}" for i, v in list(pred.items())[:6]))
    if len(values) != horizon:
        print(f"     *** HORIZON MISMATCH: got {len(values)}, expected {horizon}")
    if distinct == 1:
        print(f"     -> flat, because {meta.selected_model_label} is flat by "
              f"construction (it won the backtest)")


def main() -> None:
    df = load()
    print(f"rows={len(df):,}  span={df.saledate.min().date()} .. {df.saledate.max().date()}")
    print(f"months of history: {df.saledate.dt.to_period('M').nunique()}")
    print()

    for freq, h in (("months", 3), ("months", 6), ("months", 12), ("months", 24),
                    ("weeks", 12), ("days", 30)):
        stage_report(df, freq, h, f"WHOLE SERIES")

    # Per-group independence
    print("=" * 76)
    print("GROUPED: one series, model and forecast per country (monthly, h=6)")
    seen = {}
    for country in sorted(df["country"].dropna().unique()):
        sub = df[df["country"] == country]
        ts, agg = preprocessing.aggregate_time_series(sub, "saledate", "amount",
                                                      frequency="months")
        diag = series_validation.validate_series(
            ts, requested_frequency="months", horizon=6,
            inferred_frequency=agg.get("inferred_frequency"))
        model, meta = forecast_selection.select_and_fit(ts, diag, 6)
        if model is None:
            print(f"  {country:15s} refused ({diag.status})")
            continue
        pred, _ = model.predict(steps=6)
        vals = [round(float(v), 2) for v in pred]
        seen[country] = vals
        print(f"  {country:15s} {meta.selected_model_label:22s} "
              f"first={vals[0]:,.0f} last={vals[-1]:,.0f} "
              f"distinct={len(set(vals))}")
    identical = len({tuple(v) for v in seen.values()})
    print(f"  -> {len(seen)} groups produced {identical} distinct forecast vectors "
          + ("(independent)" if identical == len(seen) else "*** SOME GROUPS SHARE A FORECAST"))


if __name__ == "__main__":
    main()
