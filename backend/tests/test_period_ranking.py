"""
"Which month next year will have the highest sales?"

The bucket comes from the question's bucket word, not from the horizon unit;
the ranked thing is the forecast periods; and the reply is built from the
computed ranking so the wording layer cannot contradict it.
"""
from types import SimpleNamespace

from agents.prediction_agent import _period_label, _period_ranking_evidence, _readable
from prediction import config as cfg
from prediction.config import PredictionConfig
from prediction.config_resolver import _PERIOD_RANK, _LOW_WORDS
from prediction.engine import rank_periods
from prediction.time_resolution import granularity_from_question


# ── bucket vs span ───────────────────────────────────────────

def test_bucket_word_beats_horizon_unit():
    assert granularity_from_question("Which month next year will have the highest sales?") == "months"
    assert granularity_from_question("monthly sales for the next 2 years") == "months"
    assert granularity_from_question("sales per quarter next year") == "quarters"
    assert granularity_from_question("which week will be busiest") == "weeks"


def test_span_alone_names_no_bucket():
    assert granularity_from_question("Forecast sales for next year") is None
    assert granularity_from_question("Forecast sales for the next 6 months") is None


# ── detecting a period ranking ───────────────────────────────

def test_period_rank_detection():
    assert _PERIOD_RANK.search("Which month next year will have the highest sales?")
    assert _PERIOD_RANK.search("what is the busiest quarter going to be")
    assert _PERIOD_RANK.search("peak month for revenue next year")
    assert not _PERIOD_RANK.search("Which product will have the highest sales next year?")
    assert not _PERIOD_RANK.search("Forecast sales for the next 6 months")
    assert _LOW_WORDS.search("which quarter will have the lowest sales")


# ── ranking ──────────────────────────────────────────────────

def _result(rows):
    return SimpleNamespace(forecast_rows=rows)


def test_periods_ranked_with_uncertainty_check():
    rows = [{"period": "2019-10-31", "value": 500.0, "lower": 300.0, "upper": 700.0},
            {"period": "2019-11-30", "value": 900.0, "lower": 850.0, "upper": 950.0},
            {"period": "2019-12-31", "value": 880.0, "lower": 800.0, "upper": 960.0}]
    c = PredictionConfig(time_frequency="months")
    out = rank_periods(_result(rows), c)
    assert [r["period"] for r in out["ranking"]] == ["2019-11-30", "2019-12-31", "2019-10-31"]
    assert out["lead"] == 20.0 and out["lead_within_uncertainty"] is True     # 20 < 50


def test_lowest_direction():
    rows = [{"period": "2019-03-31", "value": 5.0}, {"period": "2019-06-30", "value": 2.0}]
    c = PredictionConfig(time_frequency="quarters", rank_direction="ascending")
    assert rank_periods(_result(rows), c)["ranking"][0]["period"] == "2019-06-30"


def test_grouped_periods_are_summed_without_a_fake_range():
    rows = [{"period": "2019-01-31", "value": 1.0, "lower": 0.5, "upper": 1.5, "group": "A"},
            {"period": "2019-01-31", "value": 2.0, "lower": 1.5, "upper": 2.5, "group": "B"},
            {"period": "2019-02-28", "value": 2.5, "lower": 2.0, "upper": 3.0, "group": "A"}]
    c = PredictionConfig(time_frequency="months", group_dimensions=["g"])
    out = rank_periods(_result(rows), c)
    assert out["ranking"][0] == {"rank": 1, "period": "2019-01-31", "value": 3.0,
                                 "lower": None, "upper": None}


# ── the reply ────────────────────────────────────────────────

def test_reply_leads_with_the_computed_answer():
    pr = {"direction": "highest", "grouped": False, "lead": 20.0, "lead_within_uncertainty": True,
          "ranking": [{"rank": 1, "period": "2019-11-30", "value": 900.0, "lower": 850.0, "upper": 950.0},
                      {"rank": 2, "period": "2019-12-31", "value": 880.0, "lower": 800.0, "upper": 960.0}]}
    c = PredictionConfig(time_frequency="months", target="sales")
    text = _readable("\n".join(_period_ranking_evidence(pr, c)))
    assert text.startswith("**The highest forecast month is November 2019")
    assert "Runner-up: December 2019" in text
    assert "could swap" in text


def test_period_labels():
    assert _period_label("2019-12-31 00:00:00", "months") == "December 2019"
    assert _period_label("2019-12-31", "quarters") == "Q4 2019"
