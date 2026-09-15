"""
Regression tests for prediction target/context resolution.

These lock in the fix for a whole class of failure: predictive follow-ups that
name no measure ("Will it remain the leader next year?") used to die with
"No viable target column found ... a hint must be provided", because the target
was reconstructed from the previous SQL answer's column aliases — names like
`total_revenue` and `GEO` that no table actually has.

Three properties are asserted:

1. A target hint is an *override*, never a prerequisite.
2. A SQL alias maps back to the real schema column it came from.
3. A follow-up inherits target, dimension, entities and leader from whatever
   the previous turn was — a forecast or an ordinary BI answer.

The schema is synthetic and unlike production, so passing proves the resolution
is schema-driven rather than tuned to one dataset.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from agents import conversation_state
from prediction import detector, engine
from prediction.config import OP_FINAL_PERIOD, PredictionConfig


@pytest.fixture
def depot_db(tmp_path, monkeypatch):
    """A logistics schema: nothing here is named like the sales database."""
    import sqlite3

    db_path = str(tmp_path / "depot.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE hubs (hub_ref TEXT, depot TEXT, zone TEXT)")
    conn.executemany("INSERT INTO hubs VALUES (?,?,?)", [
        ("H1", "Eastport", "Coastal"), ("H2", "Fairvale", "Inland"),
        ("H3", "Kingsmill", "Inland"),
    ])
    conn.execute("CREATE TABLE lanes (lane_ref TEXT, lane TEXT, mode TEXT)")
    conn.executemany("INSERT INTO lanes VALUES (?,?,?)", [
        ("L1", "Express", "Air"), ("L2", "Standard", "Road"),
    ])

    rng = np.random.default_rng(5)
    periods = pd.date_range("2021-01-31", periods=30, freq="ME")
    rows = []
    for hub, (base, slope) in {"H1": (800.0, 1.0), "H2": (500.0, 5.0),
                               "H3": (200.0, 25.0)}.items():
        for lane_i, lane in enumerate(["L1", "L2"]):
            for i, when in enumerate(periods):
                freight = base + slope * i + rng.normal(0, 12) - lane_i * 90
                rows.append((hub, lane, when.strftime("%Y-%m-%d %H:%M:%S"),
                             round(float(max(freight, 5.0)), 2),
                             int(max(1, round(freight / 25))), int(i % 2)))
    conn.execute(
        "CREATE TABLE shipments (hub_ref TEXT, lane_ref TEXT, dispatched TIMESTAMP, "
        "freight_cost REAL, parcels INTEGER, delayed INTEGER)"
    )
    conn.executemany("INSERT INTO shipments VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("services.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)
    monkeypatch.setattr("prediction.trainer.MODEL_DIR", tmp_path / "models")
    (tmp_path / "models").mkdir(exist_ok=True)
    engine.clear_cache()
    return db_path


def _shipments():
    from prediction.service import _load_table
    return _load_table("shipments")


# ══════════════════════════════════════════════════════════
# 1. A hint is an override, not a prerequisite
# ══════════════════════════════════════════════════════════

class TestTargetHintIsOptional:

    def test_forecasting_resolves_a_target_with_no_hint(self, depot_db):
        result = detector.detect(_shipments(), "shipments",
                                 target_hint=None, problem_type_hint="forecasting")
        assert result.is_suitable
        assert result.target_column in ("freight_cost", "parcels")

    @pytest.mark.parametrize("alias", [
        "total_freight_cost", "sum_parcels", "highest_freight", "HUB_REF",
        "grand_total", "whatever_alias",
    ])
    def test_an_unmatchable_hint_no_longer_fails(self, depot_db, alias):
        """
        The failure mode: a SQL alias that names no column made the whole
        request fail rather than falling back to the table's own measure.
        """
        result = detector.detect(_shipments(), "shipments",
                                 target_hint=alias, problem_type_hint="forecasting")
        assert result.is_suitable, result.reason
        assert result.target_column

    @pytest.mark.parametrize("alias,expected", [
        ("total_parcels", "parcels"),
        ("parcels_shipped", "parcels"),
        ("sum_freight_cost", "freight_cost"),
        ("freight-cost", "freight_cost"),
    ])
    def test_aliases_tokenise_back_to_their_column(self, depot_db, alias, expected):
        result = detector.detect(_shipments(), "shipments",
                                 target_hint=alias, problem_type_hint="forecasting")
        assert result.target_column == expected

    def test_a_table_with_no_measure_still_reports_why(self, depot_db):
        import sqlite3
        conn = sqlite3.connect(depot_db)
        conn.execute("CREATE TABLE labels_only (dispatched TIMESTAMP, note TEXT)")
        conn.executemany("INSERT INTO labels_only VALUES (?,?)",
                         [(f"2021-0{i%9+1}-01 00:00:00", f"n{i}") for i in range(60)])
        conn.commit(); conn.close()

        from prediction.service import _load_table
        result = detector.detect(_load_table("labels_only"), "labels_only",
                                 problem_type_hint="forecasting")
        assert not result.is_suitable
        assert "no numeric measure" in result.reason.lower()


# ══════════════════════════════════════════════════════════
# 2. Conversation state from a previous BI answer
# ══════════════════════════════════════════════════════════

BI_RESULT = {
    "columns": ["depot", "total_freight_cost"],
    "rows": [
        {"depot": "Eastport", "total_freight_cost": 91000},
        {"depot": "Fairvale", "total_freight_cost": 72000},
        {"depot": "Kingsmill", "total_freight_cost": 51000},
    ],
    "row_count": 3,
}


class TestConversationSeed:

    def _seed(self, question="Which depot had the highest freight cost?"):
        return conversation_state.seed_from_bi_result(BI_RESULT, "shipments", question)

    def test_measure_alias_maps_to_the_real_column(self, depot_db):
        assert self._seed().target == "freight_cost"

    def test_dimension_alias_maps_to_a_real_dimension(self, depot_db):
        seed = self._seed()
        assert seed.group_dimensions, "the grouping must survive the alias"

    def test_entities_and_leader_are_captured(self, depot_db):
        seed = self._seed()
        assert seed.source_leader == "Eastport"
        assert "Fairvale" in seed.source_entities

    def test_seed_is_built_from_a_full_chat_context(self, depot_db):
        seed = conversation_state.build_seed({
            "query": "Which depot had the highest freight cost?",
            "sql": "SELECT h.depot, SUM(s.freight_cost) AS total_freight_cost "
                   "FROM shipments s JOIN hubs h ON s.hub_ref=h.hub_ref GROUP BY h.depot",
            "result": BI_RESULT,
            "table_names": ["shipments", "hubs", "lanes"],
        })
        assert seed is not None
        assert seed.table == "shipments"
        assert seed.target == "freight_cost"

    def test_fact_table_is_recovered_from_sql(self, depot_db):
        """The fact table is the largest one the query touched, not the first."""
        assert conversation_state._table_from_sql(
            "SELECT * FROM hubs h JOIN shipments s ON h.hub_ref = s.hub_ref"
        ) == "shipments"

    def test_a_previous_prediction_is_inherited_whole(self, depot_db):
        original = PredictionConfig(
            table="shipments", target="parcels", group_dimensions=["depot"],
            horizon=9, time_frequency="months", time_column="dispatched",
        )
        seed = conversation_state.build_seed({"result": {"config": original.to_dict()}})
        assert seed.target == "parcels"
        assert seed.group_dimensions == ["depot"]
        assert seed.horizon == 9

    def test_an_empty_previous_turn_yields_no_seed(self, depot_db):
        assert conversation_state.build_seed({"result": {}}) is None


# ══════════════════════════════════════════════════════════
# 3. Dimension inference from question text
# ══════════════════════════════════════════════════════════

class TestDimensionInference:

    def _infer(self, question, exclude_words=None):
        from prediction.dimensions import infer_dimensions
        return [d.column for d in infer_dimensions(
            question, "shipments",
            exclude_columns={"freight_cost", "dispatched"},
            exclude_words=exclude_words or set(),
        )]

    def test_a_named_dimension_is_found(self, depot_db):
        assert "depot" in self._infer("Forecast by depot for the next 6 months")

    def test_a_dimension_value_implies_its_column(self, depot_db):
        """Naming a value ("Express") should find the column holding it."""
        assert "lane" in self._infer("What is the outlook for Express shipments?")

    def test_an_ungrouped_question_infers_nothing(self, depot_db):
        assert self._infer("Forecast freight cost for the next 6 months",
                           exclude_words={"freight", "cost"}) == []

    def test_measure_words_are_not_treated_as_dimensions(self, depot_db):
        inferred = self._infer("Which depot will have the highest freight cost?",
                               exclude_words={"freight", "cost"})
        assert "depot" in inferred
        assert all(c not in ("freight_cost", "parcels") for c in inferred)


# ══════════════════════════════════════════════════════════
# 4. Final-period ranking is a distinct operation
# ══════════════════════════════════════════════════════════

class TestFinalPeriodOperation:

    def _config(self, operations):
        from prediction.dimensions import resolve_dimensions
        resolution = resolve_dimensions(["depot"], "shipments")
        return PredictionConfig(
            table="shipments", target="freight_cost", time_column="dispatched",
            time_frequency="months", horizon=6,
            group_dimensions=[d.hint for d in resolution.resolved],
            dimension_specs=[d.to_dim_info() for d in resolution.resolved],
            operations=operations,
        )

    def test_final_period_ranks_only_the_last_period(self, depot_db):
        from prediction import config as cfg

        result = engine.execute(
            self._config([cfg.OP_RANK, OP_FINAL_PERIOD]), use_cache=False)
        assert result.ok
        periods = {r["period"] for r in result.ranking_rows}
        assert len(periods) == 1, "only the closing period may be ranked"

        last = max(str(r["period"]) for r in result.forecast_rows)
        assert str(periods.pop()) == last

    def test_final_period_differs_from_the_horizon_total(self, depot_db):
        from prediction import config as cfg

        total = engine.execute(self._config([cfg.OP_RANK]), use_cache=False)
        final = engine.execute(
            self._config([cfg.OP_RANK, OP_FINAL_PERIOD]), use_cache=False)

        total_top = total.ranking_rows[0]["value"]
        final_top = final.ranking_rows[0]["value"]
        assert total_top != final_top, "a period is not the sum of the horizon"

    def test_the_full_timeline_survives_a_final_period_ranking(self, depot_db):
        from prediction import config as cfg

        result = engine.execute(
            self._config([cfg.OP_RANK, OP_FINAL_PERIOD]), use_cache=False)
        periods = {r["period"] for r in result.forecast_rows}
        assert len(periods) == 6, "ranking on one period must not discard the rest"

    def test_final_period_changes_the_cache_identity(self, depot_db):
        from prediction import config as cfg

        plain = self._config([cfg.OP_RANK])
        final = self._config([cfg.OP_RANK, OP_FINAL_PERIOD])
        assert plain.identity() != final.identity()
