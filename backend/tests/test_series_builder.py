"""
Breakdowns no direct join reaches ("revenue by genre" over invoices).

They must never be dropped silently, and when built through SQL the series
keep the engine's rules: gaps stay empty, part-covered edge periods are left
out.
"""
from types import SimpleNamespace

import numpy as np

from agents.series_builder import _classify, series_by_group
from prediction.config_resolver import _asked_breakdowns


def test_asked_breakdowns_found_and_time_words_ignored():
    assert _asked_breakdowns("Forecast revenue by genre for the next 6 months") == ["genre"]
    assert _asked_breakdowns("sales per store next year") == ["store"]
    assert _asked_breakdowns("forecast revenue by month") == []
    assert _asked_breakdowns("Forecast total revenue for the next 6 months") == []


def test_classify_period_group_value():
    rows = [{"month": "2021-01", "genre": "Rock", "revenue": 10.5},
            {"month": "2021-02", "genre": "Jazz", "revenue": 3.0}]
    assert _classify(rows) == ("month", "genre", "revenue")


def test_classify_rejects_a_table_without_periods():
    rows = [{"genre": "Rock", "revenue": 10.5}, {"genre": "Jazz", "revenue": 3.0}]
    assert _classify(rows)[0] is None


def _source(rows):
    return {"rows": rows, "period_col": "month", "group_col": "genre", "value_col": "revenue"}


def test_series_keep_gaps_as_missing_not_zero():
    rows = [{"month": "2021-01", "genre": "Rock", "revenue": 10.0},
            {"month": "2021-03", "genre": "Rock", "revenue": 12.0},
            {"month": "2021-02", "genre": "Jazz", "revenue": 4.0}]
    series, _ = series_by_group(_source(rows), "months")
    rock = series["Rock"]
    assert len(rock) == 3 and np.isnan(rock.iloc[1])          # Feb is unknown, not 0
    assert str(rock.index[0].date()) == "2021-01-31"           # indexed by period end


def test_part_covered_last_period_is_left_out():
    rows = [{"month": f"2021-{m:02d}", "genre": "Rock", "revenue": 10.0} for m in range(1, 7)]
    series, notes = series_by_group(_source(rows), "months",
                                    history_start="2021-01-01", history_end="2021-06-22")
    assert str(series["Rock"].index[-1].date()) == "2021-05-31"
    assert any("partly covered" in n for n in notes)


def test_unresolved_breakdown_is_refused_not_turned_into_a_total(monkeypatch):
    from agents import prediction_agent
    from prediction import config as cfg
    from prediction.config import PredictionConfig

    c = PredictionConfig(prediction_type=cfg.FORECASTING, table="invoice", target="total",
                         time_column="invoice_date", horizon=6)
    c.unresolved_dimensions = ["genre"]
    monkeypatch.setattr(prediction_agent, "resolve_config", lambda *a, **k: c)
    monkeypatch.setattr("agents.series_builder.build_series_through_sql", lambda *a, **k: None)
    called = SimpleNamespace(n=0)
    monkeypatch.setattr(prediction_agent.engine, "execute",
                        lambda *a, **k: setattr(called, "n", called.n + 1))
    out = prediction_agent.run("Forecast revenue by genre")
    assert called.n == 0                                       # no total was forecast
    assert "can't forecast it by genre" in out["insight"]
