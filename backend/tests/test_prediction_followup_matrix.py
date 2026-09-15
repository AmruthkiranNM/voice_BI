"""
Regression tests for the prediction follow-up chain (test matrix A-F).

These cover the three failures reported from live use:

  1. A future-ranking follow-up answering "the forecast model did not return
     group-level predictions" even though the forecast had just succeeded.
  2. An explanation asserting causes ("driven by rising health-conscious
     consumer demand") that the data cannot support.
  3. A target switch to a continuous measure crashing with a classification
     error ("the least populated class in y has only 1 member").

The schema here is synthetic and deliberately unlike the production one, so
passing proves the fixes are architectural rather than phrase-specific. The
language model is mocked throughout: every number asserted below is produced by
deterministic code.
"""

import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from agents import explanation as explanation_layer
from agents import forecast_comparison as fc
from prediction import service
from prediction.target_resolution import resolve_prediction_type, resolve_target


# ──────────────────────────────────────────────────────────
# Synthetic star schema in a temp database
# ──────────────────────────────────────────────────────────

ZONES = ["North", "South", "East", "West"]
ITEMS = ["Widget", "Gadget", "Doodad"]


@pytest.fixture
def star_db(tmp_path, monkeypatch):
    """
    Facts with two measures (turnover, units) and a binary label, plus two
    dimension tables. 'West' is engineered to overtake 'North' in the forecast
    so a ranking *change* is actually exercised.
    """
    import sqlite3

    db_path = str(tmp_path / "star.db")
    conn = sqlite3.connect(db_path)

    conn.execute("CREATE TABLE zones (zone_key TEXT, territory TEXT, cluster TEXT)")
    conn.executemany("INSERT INTO zones VALUES (?,?,?)", [
        ("Z1", "North", "Alpha"), ("Z2", "South", "Alpha"),
        ("Z3", "East", "Beta"), ("Z4", "West", "Beta"),
    ])
    conn.execute("CREATE TABLE items (item_key TEXT, article TEXT, family TEXT)")
    conn.executemany("INSERT INTO items VALUES (?,?,?)", [
        ("I1", "Widget", "Hardware"), ("I2", "Gadget", "Hardware"), ("I3", "Doodad", "Software"),
    ])

    rng = np.random.default_rng(3)
    dates = pd.date_range("2021-01-31", periods=30, freq="ME")
    rows = []
    # North starts highest but is flat; West starts lower and climbs steeply.
    profile = {
        "Z1": (5000.0, 0.0), "Z2": (3000.0, 20.0),
        "Z3": (2000.0, 10.0), "Z4": (1000.0, 260.0),
    }
    for zone, (base, slope) in profile.items():
        for item_i, item in enumerate(["I1", "I2", "I3"]):
            for i, d in enumerate(dates):
                turnover = base + slope * i + rng.normal(0, 40) - item_i * 200
                rows.append((
                    zone, item, d.strftime("%Y-%m-%d %H:%M:%S"),
                    round(float(max(turnover, 10.0)), 2),
                    int(max(1, round(turnover / 50))),
                    int(i % 2),
                ))
    conn.execute(
        "CREATE TABLE facts (zone_key TEXT, item_key TEXT, when_on TIMESTAMP, "
        "turnover REAL, units INTEGER, flagged INTEGER)"
    )
    conn.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("services.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)
    monkeypatch.setattr("prediction.trainer.MODEL_DIR", tmp_path / "models")
    (tmp_path / "models").mkdir(exist_ok=True)
    return db_path


def _facts(star_db):
    import sqlite3
    return pd.read_sql_query("SELECT * FROM facts", sqlite3.connect(star_db))


# ══════════════════════════════════════════════════════════
# Target type resolution  (requirement 4)
# ══════════════════════════════════════════════════════════

class TestTargetResolution:

    def test_continuous_measures_support_regression_and_forecasting(self, star_db):
        df = _facts(star_db)
        for column in ("turnover", "units"):
            spec = resolve_target(column, df, has_time_axis=True)
            assert spec.semantic_role == "measure"
            assert spec.dtype == "numeric"
            assert set(spec.supported_prediction_types) == {"regression", "forecasting"}
            assert spec.recommended_prediction_type == "forecasting"

    def test_binary_column_is_a_classification_label(self, star_db):
        spec = resolve_target("flagged", _facts(star_db), has_time_axis=True)
        assert spec.semantic_role == "label"
        assert spec.is_binary
        assert spec.supported_prediction_types == ["classification"]

    def test_identifier_is_not_predictable(self, star_db):
        spec = resolve_target("zone_key", _facts(star_db), has_time_axis=True)
        assert spec.supported_prediction_types == []
        assert spec.reason

    def test_measure_without_a_time_axis_falls_back_to_regression(self, star_db):
        spec = resolve_target("turnover", _facts(star_db), has_time_axis=False)
        assert spec.supported_prediction_types == ["regression"]
        assert spec.recommended_prediction_type == "regression"

    def test_classification_request_on_a_measure_is_refused(self, star_db):
        """The root cause of the BOXES crash, at the resolver level."""
        spec = resolve_target("units", _facts(star_db), has_time_axis=True)
        chosen, reason = resolve_prediction_type(
            spec, wants_future=False, requested="classification",
        )
        assert chosen == "forecasting"
        assert "does not support classification" in reason

    def test_future_question_selects_forecasting(self, star_db):
        spec = resolve_target("turnover", _facts(star_db), has_time_axis=True)
        assert resolve_prediction_type(spec, wants_future=True)[0] == "forecasting"


# ══════════════════════════════════════════════════════════
# TEST B — target switching must not reach a classifier
# ══════════════════════════════════════════════════════════

class TestTargetSwitchRouting:

    def test_measure_with_stale_classification_task_is_corrected(self, star_db):
        """
        The exact reported failure: a follow-up inherits task_type
        "classification" from an earlier non-forecast question, then switches
        the target to a continuous measure.
        """
        result = service.predict_rows(
            table_name="facts", target_col="units",
            task_type="classification",          # stale, inherited
            group_hints=["territory"], forecast_steps=3,
        )
        assert result.task_type == "grouped_forecasting"
        assert result.target_column == "units"
        assert result.dimensions == ["territory"]
        assert len(result.raw_forecast_results) == len(ZONES)

    def test_every_measure_routes_to_forecasting(self, star_db):
        for column in ("turnover", "units"):
            result = service.predict_rows(
                table_name="facts", target_col=column,
                task_type="classification", group_hints=["territory"], forecast_steps=3,
            )
            assert result.task_type == "grouped_forecasting", column

    def test_binary_label_still_classifies(self, star_db):
        """The correction must not break genuine classification."""
        result = service.predict_rows(
            table_name="facts", target_col="flagged", task_type="classification",
        )
        assert result.task_type == "classification"
        assert result.row_predictions

    def test_regression_path_does_not_stratify_a_measure(self, star_db):
        """
        Without a time axis a measure is a regression target. The split must
        not stratify on it — that is what raised "the least populated class in
        y has only 1 member" for a continuous column.
        """
        from prediction import detector, preprocessing

        df = _facts(star_db).drop(columns=["when_on"])
        detection = detector.detect(df, "facts", target_hint="turnover")
        assert detection.problem_type == "regression"
        prepared, _ = preprocessing.prepare_training_data(df, detection)
        assert len(prepared.X_train) > 0
        assert len(prepared.X_test) > 0


# ══════════════════════════════════════════════════════════
# TEST A — future ranking comparison
# ══════════════════════════════════════════════════════════

class TestFutureRankingComparison:

    def test_all_groups_are_forecast_then_ranked(self, star_db):
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="grouped_ranking", group_hints=["territory"], forecast_steps=12,
        )
        assert len(result.raw_forecast_results) == len(ZONES)
        assert result.restricted_to == {}

    def test_comparison_is_produced_not_refused(self, star_db):
        """
        Bug 1: this used to return "the forecast model did not return
        group-level predictions" because the guard read a field that does not
        exist on the result.
        """
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="grouped_ranking", group_hints=["territory"], forecast_steps=12,
        )
        future = fc.extract_forecast_ranking(result)
        assert future, "forecast ranking must be readable from the result"

        current = [
            fc.RankedEntry(rank=i, group=g, value=v)
            for i, (g, v) in enumerate(
                [("North", 180000.0), ("South", 130000.0), ("East", 90000.0)], start=1)
        ]
        comparison = fc.compare_rankings(current, future, top_n=3)
        text = fc.format_comparison(comparison, "turnover", "territory", "the next 12 periods")

        assert "did not return" not in text
        assert "CURRENT TOP 3" in text and "FORECAST TOP 3" in text
        for entry in comparison.future_top:
            assert entry.group in text

    def test_a_group_outside_the_current_top_can_enter_it(self, star_db):
        """
        West starts last and grows fastest. It can only appear in the future
        top 3 if every group was forecast before ranking — which is why the
        engine must never forecast just the current leaders.
        """
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="grouped_ranking", group_hints=["territory"], forecast_steps=12,
        )
        future = fc.extract_forecast_ranking(result)
        assert "West" in [e.group for e in future]

        current = [
            fc.RankedEntry(rank=i, group=g, value=v)
            for i, (g, v) in enumerate(
                [("North", 180000.0), ("South", 130000.0), ("East", 90000.0)], start=1)
        ]
        comparison = fc.compare_rankings(current, future, top_n=3)
        assert isinstance(comparison.unchanged_set, bool)
        assert set(comparison.held) | set(comparison.entered) == {
            e.group for e in comparison.future_top
        }

    def test_comparison_reports_membership_changes(self):
        current = [fc.RankedEntry(i, g, v) for i, (g, v) in
                   enumerate([("A", 10.0), ("B", 9.0), ("C", 8.0)], start=1)]
        future = [fc.RankedEntry(i, g, v) for i, (g, v) in
                  enumerate([("D", 12.0), ("A", 11.0), ("B", 7.0), ("C", 6.0)], start=1)]

        comparison = fc.compare_rankings(current, future, top_n=3)
        assert not comparison.unchanged_set
        assert comparison.entered == ["D"]
        assert comparison.left == ["C"]
        assert set(comparison.held) == {"A", "B"}
        assert comparison.rank_changes["A"] == (1, 2)

    def test_unchanged_ranking_is_reported_as_unchanged(self):
        current = [fc.RankedEntry(i, g, 10.0 - i) for i, g in enumerate(["A", "B", "C"], start=1)]
        future = [fc.RankedEntry(i, g, 20.0 - i) for i, g in enumerate(["A", "B", "C"], start=1)]
        comparison = fc.compare_rankings(current, future, top_n=3)
        assert comparison.unchanged_set and comparison.unchanged_order
        assert not comparison.entered and not comparison.left


# ══════════════════════════════════════════════════════════
# TEST C / D — hierarchical forecasting and argmax
# ══════════════════════════════════════════════════════════

class TestHierarchicalForecast:

    def test_two_dimensions_are_genuinely_forecast(self, star_db):
        """
        TEST D: the winning combination must come from a forecast of that
        combination — not a zone-level forecast decorated with a historical
        top article.
        """
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="grouped_ranking", group_hints=["territory", "article"],
            forecast_steps=12,
        )
        assert result.dimensions == ["territory", "article"]
        assert len(result.raw_forecast_results) == len(ZONES) * len(ITEMS)

        top = result.raw_forecast_results[0]
        assert set(top["group_dict"]) == {"territory", "article"}
        assert top["forecast"], "the winner must carry its own forecast rows"
        assert len(top["forecast"]) == 12
        # The ranking value is the sum of that combination's own forecast rows.
        expected = sum(r["value"] for r in top["forecast"] if r["value"] is not None)
        assert top["final_value"] == pytest.approx(expected, rel=1e-6)

    def test_argmax_is_deterministic_over_all_combinations(self, star_db):
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="grouped_ranking", group_hints=["territory", "article"],
            forecast_steps=12,
        )
        ranked = fc.extract_forecast_ranking(result)
        best = max(ranked, key=lambda e: e.value)
        assert ranked[0].group == best.group
        assert result.best_group == best.group

    def test_coarse_forecast_is_never_decorated_with_a_finer_attribute(self, star_db):
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="grouped_ranking", group_hints=["territory"], forecast_steps=6,
        )
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == {"territory"}
            for item in ITEMS:
                assert item not in entry["group"]


# ══════════════════════════════════════════════════════════
# TEST E — growth
# ══════════════════════════════════════════════════════════

class TestGrowth:

    def test_growth_is_computed_from_baseline_and_forecast(self):
        historical = [{"value": 100.0} for _ in range(6)]
        forecast = [{"value": 150.0} for _ in range(3)]
        growth = fc.compute_growth(historical, forecast, horizon=3)

        assert growth["baseline_total"] == 300.0
        assert growth["forecast_total"] == 450.0
        assert growth["absolute_change"] == 150.0
        assert growth["growth_pct"] == pytest.approx(50.0)

    def test_growth_matches_the_stated_formula(self):
        historical = [{"value": 80.0}, {"value": 120.0}]
        forecast = [{"value": 260.0}, {"value": 240.0}]
        growth = fc.compute_growth(historical, forecast, horizon=2)
        expected = (500.0 - 200.0) / 200.0 * 100.0
        assert growth["growth_pct"] == pytest.approx(expected)

    def test_zero_baseline_yields_no_percentage(self):
        growth = fc.compute_growth([{"value": 0.0}], [{"value": 10.0}], horizon=1)
        assert growth["growth_pct"] is None
        assert "undefined" in growth["reason"]
        assert growth["absolute_change"] == 10.0

    def test_missing_history_yields_no_percentage(self):
        growth = fc.compute_growth([{"value": None}], [{"value": 10.0}], horizon=1)
        assert growth["growth_pct"] is None

    def test_growth_ranking_runs_over_all_combinations(self, star_db):
        result = service.predict_rows(
            table_name="facts", target_col="turnover",
            task_type="growth_analysis", group_hints=["territory", "article"],
            forecast_steps=12,
        )
        assert result.ranking_metric == "growth"
        values = [e["final_value"] for e in result.raw_forecast_results
                  if e["final_value"] is not None]
        assert values == sorted(values, reverse=True)
        assert len(result.raw_forecast_results) == len(ZONES) * len(ITEMS)


# ══════════════════════════════════════════════════════════
# TEST F — explanation must stay within the evidence
# ══════════════════════════════════════════════════════════

EVIDENCE = """FORECAST: turnover by territory and article, horizon 12 periods.
RANKED GROWTH:
  1. West - Widget: 152.63% growth
  2. South - Gadget: 98.10% growth
(12 territory and article combinations were forecast and ranked.)"""


class TestExplanationGrounding:

    def test_causal_claim_is_rejected(self):
        text = (
            "West - Widget is expected to grow the most at 152.63%. This growth is "
            "driven by rising consumer demand and expanding market penetration."
        )
        ok, problems = explanation_layer.verify(text, EVIDENCE)
        assert not ok
        assert any("causal" in p for p in problems)

    @pytest.mark.parametrize("phrase", [
        "because of stronger demand", "due to better marketing",
        "thanks to seasonal uplift", "as a result of pricing changes",
        "caused by supply improvements", "reflects growing interest",
    ])
    def test_causal_phrasings_are_caught_generically(self, phrase):
        ok, _ = explanation_layer.verify(f"West - Widget grows 152.63%, {phrase}.", EVIDENCE)
        assert not ok

    def test_invented_number_is_rejected(self):
        text = "West - Widget grows 152.63%, making up 47.2% of the forecast total."
        ok, problems = explanation_layer.verify(text, EVIDENCE)
        assert not ok
        assert any("not present in the evidence" in p for p in problems)

    def test_grounded_explanation_is_accepted(self):
        text = (
            "The model projects **West - Widget** to grow the most over the next 12 "
            "periods, at **152.63%** against its historical baseline. South - Gadget "
            "follows at 98.10%. All 12 combinations were forecast and ranked."
        )
        ok, problems = explanation_layer.verify(text, EVIDENCE)
        assert ok, problems

    def test_falls_back_to_deterministic_text_when_generation_cannot_be_verified(self):
        """A plainer true answer is preferred over a fluent invented one."""
        with patch("agents.explanation.call_llm", return_value=(
            "Growth is driven by rising health-conscious consumer demand."
        )):
            out = explanation_layer.explain("Why?", EVIDENCE, fallback=EVIDENCE)
        assert out == EVIDENCE

    def test_verified_generation_is_returned(self):
        good = "The model projects West - Widget to grow 152.63% over 12 periods."
        with patch("agents.explanation.call_llm", return_value=good):
            assert explanation_layer.explain("Why?", EVIDENCE, fallback=EVIDENCE) == good

    def test_llm_failure_falls_back_rather_than_erroring(self):
        with patch("agents.explanation.call_llm", side_effect=RuntimeError("offline")):
            assert explanation_layer.explain("Why?", EVIDENCE, fallback="FALLBACK") == "FALLBACK"

    def test_why_questions_have_an_honest_standard_answer(self):
        note = explanation_layer.no_cause_available_note("turnover")
        assert "does not contain the information needed to establish" in note
        ok, _ = explanation_layer.verify(note, EVIDENCE)
        assert ok, "the standard answer must itself pass verification"
