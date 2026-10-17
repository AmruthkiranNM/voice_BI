"""
"Top 5 products" -> "will it be the same in the next 6 months?"

Pins: the follow-up keeps the user's N, the reasons describe the model's
computation truthfully, an isolated spike does not set a 6-month level, and
the chart is told which series the question is about.
"""
import numpy as np
import pandas as pd

from agents.prediction_agent import _comparison_evidence, _section, _why_moved
from prediction.config import PredictionConfig
from prediction.forecast_selection import adjust_isolated_spikes


def monthly(values):
    return pd.Series([float(v) for v in values],
                     index=pd.date_range("2021-01-31", periods=len(values), freq="ME"))


# ── spike adjustment ─────────────────────────────────────────

def test_isolated_spike_is_replaced_for_fitting():
    s = monthly([10, 11, 9, 10, 40, 10, 11])
    adj, spikes = adjust_isolated_spikes(s)
    assert spikes == [str(s.index[4])]
    assert adj.iloc[4] == 10.0                       # mean of neighbours 10 and 10
    assert s.iloc[4] == 40                           # the input is not modified


def test_level_shift_is_not_a_spike():
    s = monthly([10, 11, 9, 10, 40, 41, 39, 40])
    _, spikes = adjust_isolated_spikes(s)
    assert spikes == []


def test_last_point_is_never_adjusted():
    s = monthly([10, 11, 9, 10, 11, 40])
    _, spikes = adjust_isolated_spikes(s)
    assert spikes == []


# ── evidence ─────────────────────────────────────────────────

def _entry(rank, group, value):
    return {"rank": rank, "group": group, "value": value, "group_dict": {}}


def _comparison():
    detail = lambda all_avg, fc_avg, key, label, last: {
        "periods_all": 15, "avg_all": all_avg, "recent_periods": 6, "recent_total": all_avg * 6,
        "avg_recent": all_avg, "forecast_total": fc_avg * 6, "avg_forecast": fc_avg,
        "last_periods": last, "model_key": key, "model": label, "spikes_adjusted": []}
    return {
        "top_n": 2,
        "current_top": [_entry(1, "A", 150), _entry(2, "B", 140)],
        "future_top": [_entry(1, "C", 70), _entry(2, "B", 60)],
        "unchanged_set": False, "unchanged_order": False,
        "held": ["B"], "entered": ["C"], "left": ["A"],
        "details": {
            "A": detail(10, 6, "moving_average", "Moving Average",
                        [("2022-01", 14), ("2022-02", 3), ("2022-03", 2)]),
            "B": detail(9, 9.2, "simple_exp_smoothing", "Simple Exponential Smoothing",
                        [("2022-01", 9), ("2022-02", 9), ("2022-03", 10)]),
            "C": detail(8, 11.7, "naive", "Naive (last value)",
                        [("2022-01", 9), ("2022-02", 10), ("2022-03", 11.7)]),
        },
    }


def test_answer_states_yes_or_no_and_keeps_n():
    cfg = PredictionConfig(horizon=6, time_frequency="months")
    text = "\n".join(_comparison_evidence(_comparison(), cfg))
    assert text.startswith("ANSWER: No - the top 2 changes. Leaving: A. Entering: C.")
    assert "CURRENT TOP 2 (total over all 15 months" in text
    assert "LIKE-FOR-LIKE" in text


def test_why_lines_cover_every_mover_and_skip_unmoved():
    cfg = PredictionConfig(horizon=6, time_frequency="months")
    why = _section("\n".join(_comparison_evidence(_comparison(), cfg)), "WHY IT CHANGES")
    assert any(l.startswith("A (rank 1 -> outside top 2)") for l in why)
    assert any(l.startswith("C (outside top 2 -> rank 1)") for l in why)
    assert not any(l.startswith("B ") for l in why)        # rank 2 -> 2: did not move


def test_why_describes_the_model_not_the_months():
    d = _comparison()["details"]["A"]
    text = _why_moved(d, "month")
    assert "below its usual 10" in text
    assert "average of its last 3 months" in text
    # It lists the months as facts; it never calls a 14 a low month.
    assert "2022-01 14" in text and "latest months were low" not in text


def test_usual_level_mover_is_explained_by_others():
    d = dict(_comparison()["details"]["B"])
    assert "others rose or fell" in _why_moved(d, "month")
