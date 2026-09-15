"""
Regression tests for semantic task routing.

These lock in the separation that was missing: an analytical question about
data already recorded must never reach a model, and a genuine prediction
request must never be answered with a computation the dataset cannot support.

Three properties:

1. **Descriptive priority.** "What is the churn rate by country?" is an
   aggregation over a column named churn — not a churn model. A dataset
   containing a predictable target is not an instruction to predict.
2. **Capability gating.** A forecast needs a real time axis. Without one the
   request is refused and explained, never reshaped into something else.
3. **Context is a tiebreak, not a latch.** Once a prediction has run, ordinary
   analytical follow-ups must still route to BI.

Two synthetic schemas are used, neither named like production, so passing
proves the routing reads signals and data rather than particular words.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from agents import task_router as tr
from agents.task_router import (
    ENGINE_BI, ENGINE_CLASSIFICATION, ENGINE_FORECAST,
    DatasetCapabilities, classify_task, inspect_capabilities,
)


# ──────────────────────────────────────────────────────────
# Two datasets: one with a time axis, one without.
# ──────────────────────────────────────────────────────────

@pytest.fixture
def two_datasets(tmp_path, monkeypatch):
    import sqlite3

    db_path = str(tmp_path / "mixed.db")
    conn = sqlite3.connect(db_path)

    # No temporal column: a per-record table with a binary outcome.
    rng = np.random.default_rng(2)
    conn.execute(
        "CREATE TABLE members (member_ref INTEGER, tier TEXT, segment TEXT, "
        "score REAL, tenure INTEGER, holdings REAL, lapsed INTEGER)"
    )
    conn.executemany("INSERT INTO members VALUES (?,?,?,?,?,?,?)", [
        (i, rng.choice(["Bronze", "Silver", "Gold"]), rng.choice(["Retail", "Corporate"]),
         float(rng.normal(600, 80)), int(rng.integers(0, 11)),
         float(rng.normal(70000, 25000)), int(rng.integers(0, 2)))
        for i in range(400)
    ])

    # With a temporal column: a transactional table.
    periods = pd.date_range("2021-01-31", periods=30, freq="ME")
    conn.execute(
        "CREATE TABLE ledger (branch TEXT, booked_on TIMESTAMP, takings REAL, footfall INTEGER)"
    )
    conn.executemany("INSERT INTO ledger VALUES (?,?,?,?)", [
        (branch, when.strftime("%Y-%m-%d %H:%M:%S"),
         float(500 + 10 * i + rng.normal(0, 20)), int(50 + i))
        for branch in ("Northside", "Southside")
        for i, when in enumerate(periods)
    ])
    conn.commit()
    conn.close()

    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("services.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)
    return db_path


# ══════════════════════════════════════════════════════════
# 1. Capability discovery
# ══════════════════════════════════════════════════════════

class TestCapabilityDiscovery:

    def test_a_table_without_dates_cannot_forecast(self, two_datasets):
        capabilities = inspect_capabilities("members")
        assert not capabilities.has_temporal_column
        assert not capabilities.supports_forecast
        assert capabilities.supports_classification

    def test_a_table_with_dates_can_forecast(self, two_datasets):
        capabilities = inspect_capabilities("ledger")
        assert capabilities.has_temporal_column
        assert "booked_on" in capabilities.temporal_columns
        assert capabilities.supports_forecast

    def test_capabilities_are_read_from_data_not_names(self, two_datasets):
        """Nothing here is called date, churn or revenue."""
        capabilities = inspect_capabilities("members")
        assert "lapsed" in capabilities.classification_targets
        assert {"score", "holdings"} <= set(capabilities.measures)


# ══════════════════════════════════════════════════════════
# 2. Descriptive priority — the core fix
# ══════════════════════════════════════════════════════════

WITH_TARGETS = DatasetCapabilities(
    table="members", has_temporal_column=False,
    measures=["score", "holdings", "tenure"],
    classification_targets=["lapsed", "tier"], dimensions=["tier", "segment"],
)


class TestDescriptivePriority:

    @pytest.mark.parametrize("question", [
        "What is the average holdings by tier?",
        "What is the lapse rate by tier?",
        "Which tier has the highest lapse rate?",
        "What is the average holdings of members who lapsed?",
        "How many members lapsed?",
        "What percentage of corporate members lapsed?",
        "What is the lapse rate by tier and segment?",
        "Show holdings per segment",
        "Compare tenure across tiers",
        "What is the distribution of scores?",
    ])
    def test_analytical_questions_never_reach_a_model(self, question):
        decision = classify_task(question, capabilities=WITH_TARGETS)
        assert decision.engine == ENGINE_BI, f"{question} -> {decision.describe()}"

    def test_a_predictable_column_is_not_a_request_to_predict(self):
        """
        The dataset has a binary outcome, so a classifier *could* be trained.
        That is not what an aggregation question asked for.
        """
        decision = classify_task(
            "What is the lapse rate by tier?", capabilities=WITH_TARGETS)
        assert decision.engine == ENGINE_BI
        assert decision.task == tr.HISTORICAL_AGGREGATION

    def test_ranking_is_recognised_as_such(self):
        decision = classify_task(
            "Which tier has the highest lapse rate?", capabilities=WITH_TARGETS)
        assert decision.task == tr.HISTORICAL_RANKING

    def test_distribution_is_recognised_as_such(self):
        decision = classify_task(
            "What is the distribution of holdings?", capabilities=WITH_TARGETS)
        assert decision.task == tr.HISTORICAL_DISTRIBUTION

    def test_correlation_is_recognised_as_such(self):
        decision = classify_task(
            "Is there a relationship between tenure and holdings?",
            capabilities=WITH_TARGETS)
        assert decision.task == tr.CORRELATION


# ══════════════════════════════════════════════════════════
# 3. Genuine prediction still routes to a model
# ══════════════════════════════════════════════════════════

class TestPredictiveRouting:

    @pytest.mark.parametrize("question", [
        "Can you predict whether a member will lapse?",
        "Which members are most likely to lapse?",
        "What is the probability this member lapses?",
        "Which members are at high risk?",
        "Are corporate members more likely to lapse?",
    ])
    def test_propensity_questions_route_to_classification(self, question):
        decision = classify_task(question, capabilities=WITH_TARGETS)
        assert decision.engine == ENGINE_CLASSIFICATION, question

    WITH_TIME = DatasetCapabilities(
        table="ledger", has_temporal_column=True, temporal_columns=["booked_on"],
        measures=["takings", "footfall"], dimensions=["branch"],
    )

    @pytest.mark.parametrize("question", [
        "Forecast takings for the next 6 months",
        "What will takings be next quarter?",
        "Which branch is expected to lead next month?",
        "Project footfall going forward",
    ])
    def test_future_questions_route_to_forecast(self, question):
        decision = classify_task(question, capabilities=self.WITH_TIME)
        assert decision.engine == ENGINE_FORECAST, question

    def test_future_ranking_growth_and_comparison_are_distinguished(self):
        assert classify_task("Which branch will earn most next month?",
                             capabilities=self.WITH_TIME).task == tr.FUTURE_RANKING
        assert classify_task("Which branch will grow the most next year?",
                             capabilities=self.WITH_TIME).task == tr.FUTURE_GROWTH
        assert classify_task("Will it remain the leader next year?",
                             capabilities=self.WITH_TIME).task == tr.FUTURE_COMPARISON


# ══════════════════════════════════════════════════════════
# 4. Capability gates
# ══════════════════════════════════════════════════════════

class TestCapabilityGates:

    def test_forecast_is_refused_without_a_time_axis(self, two_datasets):
        decision = tr.route("Can you forecast lapses next year?", table="members")
        assert decision.engine == ENGINE_FORECAST
        assert decision.blocked, "must be refused, not silently reshaped"
        assert "no date or time column" in decision.blocked[0].lower()

    def test_the_refusal_offers_what_the_data_can_do(self, two_datasets):
        decision = tr.route("Can you forecast lapses next year?", table="members")
        assert decision.alternatives
        assert any("classification" in a.lower() for a in decision.alternatives)

    def test_the_same_question_is_allowed_where_time_exists(self, two_datasets):
        decision = tr.route("Can you forecast takings next year?", table="ledger")
        assert decision.engine == ENGINE_FORECAST
        assert not decision.blocked

    def test_classification_is_refused_without_a_categorical_target(self):
        measures_only = DatasetCapabilities(
            table="t", has_temporal_column=True, temporal_columns=["d"],
            measures=["takings"], classification_targets=[],
        )
        decision = classify_task("Predict whether this will lapse",
                                 capabilities=measures_only)
        assert decision.blocked
        assert any("categorical" in b.lower() for b in decision.blocked)

    def test_a_blocked_decision_is_never_silently_downgraded(self, two_datasets):
        """The engine stays as asked; only `blocked` marks it unrunnable."""
        decision = tr.route("Forecast lapses next year", table="members")
        assert decision.engine == ENGINE_FORECAST
        assert decision.blocked


# ══════════════════════════════════════════════════════════
# 5. Context is a tiebreak, not a latch
# ══════════════════════════════════════════════════════════

class TestContextInheritance:

    @pytest.mark.parametrize("question", [
        "What is the average holdings by tier?",
        "How many members lapsed?",
        "What is the lapse rate by segment?",
        "Which tier has the highest holdings?",
    ])
    def test_analytical_followups_escape_a_predictive_conversation(self, question):
        """
        The failure this fixes: once a prediction had run, every later question
        was pushed through the prediction engine regardless of what it asked.
        """
        decision = classify_task(
            question, capabilities=WITH_TARGETS,
            previous_task="classification", previous_engine=ENGINE_CLASSIFICATION,
        )
        assert decision.engine == ENGINE_BI, question
        assert not decision.inherited_from_context

    def test_a_bare_modifier_does_inherit(self):
        """"What about X?" carries no task of its own and continues the thread."""
        decision = classify_task(
            "What about Gold members?", capabilities=WITH_TARGETS,
            previous_task="historical_ranking", previous_engine=ENGINE_BI,
        )
        assert decision.engine == ENGINE_BI
        assert decision.inherited_from_context

    def test_a_bare_modifier_after_a_forecast_stays_a_forecast(self):
        with_time = DatasetCapabilities(
            table="ledger", has_temporal_column=True, temporal_columns=["booked_on"],
            measures=["takings", "footfall"], dimensions=["branch"],
        )
        decision = classify_task(
            "What about footfall?", capabilities=with_time,
            previous_task="future_ranking", previous_engine=ENGINE_FORECAST,
        )
        assert decision.engine == ENGINE_FORECAST
        assert decision.inherited_from_context

    def test_a_ranking_followup_after_bi_ranks(self):
        decision = classify_task(
            "Which one is highest?", capabilities=WITH_TARGETS,
            previous_task="historical_aggregation", previous_engine=ENGINE_BI,
        )
        assert decision.engine == ENGINE_BI
        assert decision.task == tr.HISTORICAL_RANKING

    def test_an_explicit_prediction_overrides_a_bi_conversation(self):
        decision = classify_task(
            "Which members are most likely to lapse?", capabilities=WITH_TARGETS,
            previous_task="historical_aggregation", previous_engine=ENGINE_BI,
        )
        assert decision.engine == ENGINE_CLASSIFICATION
        assert not decision.inherited_from_context


# ══════════════════════════════════════════════════════════
# 6. Boundaries and observability
# ══════════════════════════════════════════════════════════

class TestRouterBoundaries:

    def test_every_decision_explains_itself(self):
        decision = classify_task("What is the lapse rate by tier?",
                                 capabilities=WITH_TARGETS)
        assert decision.reasons
        assert decision.confidence > 0
        assert "task=" in decision.describe()

    def test_signals_are_reported_for_debugging(self):
        decision = classify_task("Which tier will grow most next year?",
                                 capabilities=WITH_TARGETS)
        assert decision.signals["future_time"]
        assert decision.signals["growth"]

    def test_the_router_calls_no_language_model(self):
        import inspect
        source = inspect.getsource(tr)
        assert "call_llm" not in source
        assert "llm_service" not in source

    def test_past_tense_is_never_predictive(self):
        for question in ["What were takings last month?",
                         "How many members lapsed last year?",
                         "What was the highest tier historically?"]:
            assert classify_task(question, capabilities=WITH_TARGETS).engine == ENGINE_BI
