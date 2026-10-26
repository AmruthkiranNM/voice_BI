"""
Series builder — per-group time series for breakdowns no direct join reaches.

"Forecast revenue by genre" over Chinook needs invoice -> invoice_line ->
track -> genre, and revenue there is unit_price x quantity on invoice_line.
The prediction engine's dimension resolver joins one step from the fact
table, so it cannot reach genre; before this module it silently forecast the
overall total instead, which read as a genre forecast.

The SQL pipeline already handles multi-table joins and derived measures, so
it is asked for "<measure> by <breakdown> per <period>". The database
computes every value; the language model only writes the query, and the
result is checked for the expected shape before anything is forecast.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_PERIOD = re.compile(r"^\d{4}(-\d{1,2}(-\d{1,2})?|-?Q[1-4]|-W\d{1,2}|/\d{1,2}(/\d{1,2})?)?"
                     r"( \d{2}:\d{2}:\d{2})?$")

#: Minimum distinct periods for the built series to be worth forecasting.
MIN_PERIODS = 6


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _classify(rows: list[dict]) -> tuple[str | None, str | None, str | None]:
    """(period column, group column, value column) of a result, judged on its values."""
    if not rows:
        return None, None, None
    cols = list(rows[0].keys())
    numeric = [c for c in cols if all(r.get(c) is None or _is_number(r.get(c)) for r in rows)
               and any(r.get(c) is not None for r in rows)]
    period = next((c for c in cols if c not in numeric
                   and all(_PERIOD.match(str(r.get(c) or "")) for r in rows)), None)
    labels = [c for c in cols if c not in numeric and c != period]
    value = numeric[0] if numeric else None
    return period, (labels[0] if labels else None), value


def build_series_through_sql(config, question: str, table_names: list[str] | None) -> dict[str, Any] | None:
    """
    Ask the SQL pipeline for the measure by the unresolved breakdown per
    period. Returns the series source for the engine, or None when the result
    is not a usable (period, group, value) table.
    """
    from agents.orchestrator import process_query

    unit = (config.time_frequency or "months").rstrip("s")
    measure = config.target_request or config.target or "value"
    dims = " and ".join(config.unresolved_dimensions)
    filters = "; ".join(f"only {f.column} = {', '.join(map(str, f.values))}" for f in config.filters)
    request = (f"Total {measure} by {dims} for every {unit} in the data "
               f"(one row per {dims} per {unit}, with the {unit} as a date or YYYY-MM)"
               + (f", {filters}" if filters else ""))

    logger.info("[SeriesBuilder] %s", request)
    try:
        response = process_query(request, table_names=table_names, skip_insight=True,
                                 cache_mode=False)
    except Exception as exc:
        logger.warning("[SeriesBuilder] SQL pipeline failed: %s", exc)
        return None
    if not response.get("success"):
        logger.warning("[SeriesBuilder] SQL pipeline error: %s", response.get("error"))
        return None

    rows = (response.get("result") or {}).get("rows") or []
    period_col, group_col, value_col = _classify(rows)
    if not (period_col and group_col and value_col):
        logger.warning("[SeriesBuilder] Result is not (period, group, value): %s",
                       list(rows[0]) if rows else [])
        return None
    if len({str(r[period_col]) for r in rows}) < MIN_PERIODS:
        logger.warning("[SeriesBuilder] Too few periods in the built series.")
        return None

    return {"sql": response.get("sql"), "request": request, "period_col": period_col,
            "group_col": group_col, "value_col": value_col, "rows": rows}


def _period_end(value: str, freq: str) -> pd.Timestamp | None:
    text = str(value).strip().replace("/", "-")
    try:
        if re.match(r"^\d{4}-?Q[1-4]$", text):
            ts = pd.Period(text.replace("-", ""), freq="Q").start_time
        else:
            ts = pd.Timestamp(text)
    except Exception:
        return None
    return pd.Period(ts, freq=freq).end_time.normalize()


_PANDAS_FREQ = {"days": "D", "weeks": "W", "months": "M", "quarters": "Q", "years": "Y"}


def series_by_group(source: dict, frequency: str, history_start=None,
                    history_end=None) -> tuple[dict[str, pd.Series], list[str]]:
    """
    Turn the built rows into one gap-aware series per group, indexed by period
    end. Missing periods stay NaN (never 0). A first or last period that the
    raw data only partly covers is dropped, as the engine does for the base
    table, so a part-month is never forecast from.
    """
    freq = _PANDAS_FREQ.get(frequency, "M")
    df = pd.DataFrame(source["rows"])
    df["_end"] = df[source["period_col"]].map(lambda v: _period_end(v, freq))
    df["_v"] = pd.to_numeric(df[source["value_col"]], errors="coerce")
    df = df.dropna(subset=["_end", "_v"])
    if df.empty:
        return {}, []

    periods = sorted(df["_end"].unique())
    first, last = pd.Timestamp(periods[0]), pd.Timestamp(periods[-1])
    index = pd.period_range(first, last, freq=freq).to_timestamp(how="end").normalize()

    notes = []
    drop = set()
    if history_end is not None and pd.Timestamp(history_end).normalize() < last:
        drop.add(last)
        notes.append(f"The last {frequency.rstrip('s')} ({last.date()}) is only partly covered "
                     f"by the data and was left out of the series.")
    if history_start is not None:
        start_period = pd.Period(first, freq=freq).start_time.normalize()
        if pd.Timestamp(history_start).normalize() > start_period:
            drop.add(first)
            notes.append(f"The first {frequency.rstrip('s')} ({first.date()}) is only partly "
                         f"covered and was left out.")
    index = index[~index.isin(list(drop))]

    out: dict[str, pd.Series] = {}
    for group, part in df.groupby(source["group_col"]):
        s = part.groupby("_end")["_v"].sum(min_count=1)
        out[str(group)] = s.reindex(index)
    return out, notes
