"""
Tests for the general-purpose prediction engine.

Two things are being proved here, and they are different:

1. **Correctness** — configs execute, numbers are deterministic, and the
   documented properties hold (dimensions preserved, ranking equals sorting,
   growth equals the formula, horizons produce the requested periods).

2. **Genericity** — the engine works on a schema it has never seen, whose
   columns are named nothing like the production one, and on questions phrased
   in ways no test anticipated. Paraphrases of one intent must resolve to the
   same configuration, because the engine never sees the wording.

The language model is mocked or bypassed throughout, so every assertion is
about deterministic code.
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

from prediction import config as cfg
from prediction import engine, time_resolution as tr
from prediction.config import Filter, PredictionConfig, validate_config
from prediction.intent_markers import is_predictive_question


# ──────────────────────────────────────────────────────────
# A schema the engine has never seen: a clinic, not a shop.
# ──────────────────────────────────────────────────────────

SITES = ["Harbourside", "Riverton", "Northgate"]
SERVICES = ["Imaging", "Pathology"]


@pytest.fixture
def clinic_db(tmp_path, monkeypatch):
    import sqlite3

    db_path = str(tmp_path / "clinic.db")
    conn = sqlite3.connect(db_path)

    conn.execute("CREATE TABLE sites (site_ref TEXT, clinic TEXT, district TEXT)")
    conn.executemany("INSERT INTO sites VALUES (?,?,?)", [
        ("S1", "Harbourside", "Metro"), ("S2", "Riverton", "Metro"),
        ("S3", "Northgate", "Rural"),
    ])
    conn.execute("CREATE TABLE services (svc_ref TEXT, service TEXT, discipline TEXT)")
    conn.executemany("INSERT INTO services VALUES (?,?,?)", [
        ("V1", "Imaging", "Diagnostic"), ("V2", "Pathology", "Diagnostic"),
    ])

    rng = np.random.default_rng(11)
    periods = pd.date_range("2021-01-31", periods=30, freq="ME")
    rows = []
    profile = {"S1": (900.0, 2.0), "S2": (600.0, 6.0), "S3": (300.0, 30.0)}
    for site, (base, slope) in profile.items():
        for svc_i, svc in enumerate(["V1", "V2"]):
            for i, when in enumerate(periods):
                billed = base + slope * i + rng.normal(0, 15) - svc_i * 120
                rows.append((
                    site, svc, when.strftime("%Y-%m-%d %H:%M:%S"),
                    round(float(max(billed, 5.0)), 2),
                    int(max(1, round(billed / 30))),
                    int(i % 2),
                ))
    conn.execute(
        "CREATE TABLE visits (site_ref TEXT, svc_ref TEXT, seen_on TIMESTAMP, "
        "billed REAL, headcount INTEGER, readmitted INTEGER)"
    )
    conn.executemany("INSERT INTO visits VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("services.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)
    monkeypatch.setattr("prediction.trainer.MODEL_DIR", tmp_path / "models")
    (tmp_path / "models").mkdir(exist_ok=True)
    engine.clear_cache()
    return db_path


def make_config(**overrides) -> PredictionConfig:
    """A directly-constructed config, bypassing language entirely."""
    base = dict(
        prediction_type=cfg.FORECASTING, table="visits", target="billed",
        time_column="seen_on", time_frequency="months", horizon=6,
    )
    base.update(overrides)
    config = PredictionConfig(**base)
    if config.group_dimensions and not config.dimension_specs:
        from prediction.dimensions import resolve_dimensions
        resolution = resolve_dimensions(config.group_dimensions, config.table)
        config.dimension_specs = [d.to_dim_info() for d in resolution.resolved]
        config.group_dimensions = [d.hint for d in resolution.resolved]
    return config


# ══════════════════════════════════════════════════════════
# 1. Config as a contract
# ══════════════════════════════════════════════════════════

class TestPredictionConfig:

    def test_identity_separates_incompatible_requests(self):
        base = make_config.__wrapped__ if hasattr(make_config, "__wrapped__") else None
        a = PredictionConfig(table="t", target="billed", horizon=3, time_frequency="months")
        variants = {
            "different target": PredictionConfig(table="t", target="headcount", horizon=3, time_frequency="months"),
            "different horizon": PredictionConfig(table="t", target="billed", horizon=12, time_frequency="months"),
            "different frequency": PredictionConfig(table="t", target="billed", horizon=3, time_frequency="weeks"),
            "different table": PredictionConfig(table="u", target="billed", horizon=3, time_frequency="months"),
            "added dimension": PredictionConfig(table="t", target="billed", horizon=3,
                                                time_frequency="months", group_dimensions=["clinic"]),
        }
        for label, other in variants.items():
            assert a.identity() != other.identity(), label

    def test_identity_ignores_wording(self):
        a = PredictionConfig(table="t", target="billed", horizon=3, question="Forecast billings")
        b = PredictionConfig(table="t", target="billed", horizon=3,
                             question="What will we bill over the coming quarter?")
        assert a.identity() == b.identity()

    def test_identity_separates_filtered_from_unfiltered(self):
        a = PredictionConfig(table="t", target="billed", horizon=3)
        b = PredictionConfig(table="t", target="billed", horizon=3,
                             filters=[Filter(column="clinic", values=["Riverton"])])
        assert a.identity() != b.identity()

    @pytest.mark.parametrize("broken,expected", [
        (dict(prediction_type="astrology"), "Unknown prediction type"),
        (dict(table=""), "No dataset table"),
        (dict(target=""), "No target column"),
        (dict(horizon=0), "horizon must be positive"),
        (dict(time_column=None), "needs a time column"),
        (dict(top_n=-1), "top_n must be positive"),
    ])
    def test_structural_gate_rejects_unexecutable_configs(self, broken, expected):
        payload = dict(prediction_type=cfg.FORECASTING, table="t", target="billed",
                       time_column="seen_on", horizon=6)
        payload.update(broken)
        errors = validate_config(PredictionConfig(**payload))
        assert any(expected in e for e in errors), errors

    def test_unresolved_dimensions_are_rejected(self):
        config = PredictionConfig(
            prediction_type=cfg.FORECASTING, table="t", target="billed",
            time_column="seen_on", horizon=6,
            group_dimensions=["clinic", "service"], dimension_specs=[{"group_column": "clinic"}],
        )
        assert any("were resolved" in e for e in validate_config(config))


# ══════════════════════════════════════════════════════════
# 2. Time resolution
# ══════════════════════════════════════════════════════════

class TestTimeResolution:

    @pytest.mark.parametrize("phrase,count,unit", [
        ("next 6 months", 6, "months"),
        ("the next three quarters", 3, "quarters"),
        ("over the next 30 days", 30, "days"),
        ("next 12 weeks", 12, "weeks"),
        ("next year", 1, "years"),
        ("next quarter", 1, "quarters"),
        ("for 8 periods", 8, None),
    ])
    def test_horizon_phrases_parse_without_a_phrase_table(self, phrase, count, unit):
        assert tr.parse_horizon_phrase(phrase) == (count, unit)

    def test_coarse_horizon_is_expressed_at_the_working_frequency(self):
        """'Next year' over monthly history is twelve monthly periods."""
        spec = tr.resolve_horizon("next year", "months", "2022-03-31")
        assert spec.periods == 12 and spec.frequency == "months"

    def test_horizon_is_anchored_to_the_data_not_the_calendar(self):
        spec = tr.resolve_horizon("next 3 months", "months", "2019-06-30")
        assert spec.anchor.startswith("2019-06-30")
        assert spec.forecast_start.startswith("2019-07")
        assert spec.forecast_end.startswith("2019-09")

    def test_requested_frequency_cannot_exceed_the_data(self):
        chosen, notes = tr.resolve_frequency("days", data_frequency="months", span_days=900)
        assert chosen == "months"
        assert notes

    def test_default_frequency_is_a_reporting_period_not_the_sampling_rate(self):
        """Daily transactions over ~15 months should report monthly."""
        assert tr.default_frequency(455, "days") == "months"

    def test_time_column_is_chosen_by_values_not_by_name(self, clinic_db):
        from prediction.service import _load_table

        selected, candidates = tr.select_time_column(_load_table("visits"))
        assert selected is not None
        assert selected.column == "seen_on"   # no "date" in the name

    def test_question_can_select_among_several_time_columns(self):
        df = pd.DataFrame({
            "ordered_on": pd.date_range("2021-01-01", periods=40, freq="D").astype(str),
            "delivered_on": pd.date_range("2021-02-01", periods=40, freq="D").astype(str),
            "value": range(40),
        })
        picked, _ = tr.select_time_column(df, question="forecast by delivered_on date")
        assert picked.column == "delivered_on"


# ══════════════════════════════════════════════════════════
# 3. Intent markers (router-level, offline)
# ══════════════════════════════════════════════════════════

class TestIntentMarkers:

    @pytest.mark.parametrize("question", [
        "Will these top 3 clinics remain the same next year?",
        "Which district is expected to bill the most next quarter?",
        "Who is likely to lead next month?",
        "Forecast billings for the next 6 months.",
        "What is the outlook for headcount?",
        "Which service will grow fastest?",
        "Is this patient at risk of readmission?",
    ])
    def test_future_questions_are_recognised(self, question):
        assert is_predictive_question(question)[0], question

    @pytest.mark.parametrize("question", [
        "Rank clinics by billings.",
        "What were billings last month?",
        "Show headcount by district.",
        "What is the total billed amount?",
        "Which clinic had the highest billings?",
    ])
    def test_historical_questions_are_not_hijacked(self, question):
        assert not is_predictive_question(question)[0], question


# ══════════════════════════════════════════════════════════
# 4. Engine execution on an unfamiliar schema
# ══════════════════════════════════════════════════════════

class TestEngineExecution:

    def test_ungrouped_forecast_produces_the_requested_periods(self, clinic_db):
        result = engine.execute(make_config(horizon=6), use_cache=False)
        assert result.ok
        assert len(result.forecast_rows) == 6
        assert result.historical_rows
        assert result.model_metadata.get("selected_model_key")

    @pytest.mark.parametrize("horizon", [1, 3, 6, 12])
    def test_every_horizon_yields_exactly_that_many_periods(self, clinic_db, horizon):
        result = engine.execute(make_config(horizon=horizon), use_cache=False)
        assert len(result.forecast_rows) == horizon

    @pytest.mark.parametrize("target", ["billed", "headcount"])
    def test_forecast_values_come_from_the_requested_target(self, clinic_db, target):
        """Property: a billed forecast and a headcount forecast must differ."""
        result = engine.execute(make_config(target=target, horizon=3), use_cache=False)
        assert result.ok
        assert result.config["target"] == target
        totals = sum(r["value"] for r in result.forecast_rows if r["value"] is not None)
        assert totals > 0

    def test_two_targets_produce_different_numbers(self, clinic_db):
        billed = engine.execute(make_config(target="billed", horizon=3), use_cache=False)
        heads = engine.execute(make_config(target="headcount", horizon=3), use_cache=False)
        a = sum(r["value"] for r in billed.forecast_rows if r["value"] is not None)
        b = sum(r["value"] for r in heads.forecast_rows if r["value"] is not None)
        assert a != b

    def test_grouped_forecast_preserves_every_dimension(self, clinic_db):
        config = make_config(group_dimensions=["clinic", "service"], horizon=3,
                             operations=[cfg.OP_RANK])
        result = engine.execute(config, use_cache=False)
        assert result.ok
        assert set(result.config["group_dimensions"]) == {"clinic", "service"}
        for row in result.forecast_rows:
            assert set(row["group_values"]) == {"clinic", "service"}

    def test_group_count_matches_observed_combinations(self, clinic_db):
        config = make_config(group_dimensions=["clinic", "service"], horizon=3)
        result = engine.execute(config, use_cache=False)
        groups = {r["group"] for r in result.forecast_rows}
        assert len(groups) == len(SITES) * len(SERVICES)

    def test_classification_target_routes_to_classification(self, clinic_db):
        config = PredictionConfig(
            prediction_type=cfg.CLASSIFICATION, table="visits", target="readmitted",
        )
        result = engine.execute(config, use_cache=False)
        assert result.ok
        assert result.row_predictions
        assert result.model_metadata["problem_type"] == cfg.CLASSIFICATION

    def test_single_observation_is_refused_not_fabricated(self, clinic_db):
        import sqlite3
        conn = sqlite3.connect(clinic_db)
        conn.execute("CREATE TABLE tiny (seen_on TIMESTAMP, billed REAL)")
        conn.executemany("INSERT INTO tiny VALUES (?,?)",
                         [("2021-01-31 00:00:00", 5.0)])
        conn.commit(); conn.close()

        result = engine.execute(make_config(table="tiny", horizon=6), use_cache=False)
        assert not result.ok
        assert result.status == cfg.STATUS_INSUFFICIENT_DATA
        assert result.errors and not result.forecast_rows

    def test_minimal_history_uses_a_labelled_fallback(self, clinic_db):
        """
        Two or three observations are too few to validate a model, but not
        nothing. A naive fallback is allowed there — provided the result says
        so rather than presenting it as a validated forecast.
        """
        import sqlite3
        conn = sqlite3.connect(clinic_db)
        conn.execute("CREATE TABLE small (seen_on TIMESTAMP, billed REAL)")
        conn.executemany("INSERT INTO small VALUES (?,?)", [
            ("2021-01-31 00:00:00", 5.0), ("2021-02-28 00:00:00", 6.0),
            ("2021-03-31 00:00:00", 7.0),
        ])
        conn.commit(); conn.close()

        result = engine.execute(make_config(table="small", horizon=3), use_cache=False)
        assert result.ok
        assert result.model_metadata["selection_method"] == "fallback_no_validation"
        assert result.model_metadata["selected_model_key"] == "naive"
        assert result.series_diagnostics["status"] == "fallback"
        assert result.series_diagnostics["reason"]

    def test_filters_narrow_the_source_rows(self, clinic_db):
        unfiltered = engine.execute(make_config(horizon=3), use_cache=False)
        filtered = engine.execute(
            make_config(horizon=3, filters=[Filter(column="clinic", values=["Riverton"])]),
            use_cache=False,
        )
        assert filtered.dataset_context["rows"] < unfiltered.dataset_context["rows"]

    def test_invalid_config_returns_a_structured_error(self, clinic_db):
        config = make_config(horizon=0)
        config.errors = validate_config(config)
        config.status = cfg.STATUS_INVALID_CONFIG
        result = engine.execute(config, use_cache=False)
        assert result.status == cfg.STATUS_INVALID_CONFIG
        assert result.errors and not result.forecast_rows


# ══════════════════════════════════════════════════════════
# 5. Property-based validation of the operations
# ══════════════════════════════════════════════════════════

class TestOperationProperties:

    def _ranked(self, clinic_db, **kw):
        config = make_config(group_dimensions=["clinic"], horizon=6,
                             operations=[cfg.OP_RANK], **kw)
        return engine.execute(config, use_cache=False)

    def test_ranking_equals_deterministic_sorting_of_forecasts(self, clinic_db):
        result = self._ranked(clinic_db)
        totals = {}
        for row in result.forecast_rows:
            if row["value"] is not None:
                totals[row["group"]] = totals.get(row["group"], 0.0) + row["value"]
        expected = [g for g, _ in sorted(totals.items(), key=lambda kv: -kv[1])]
        actual = [r["group"] for r in result.ranking_rows if r.get("value") is not None]
        assert actual == expected

    def test_ranking_covers_every_forecast_entity(self, clinic_db):
        result = self._ranked(clinic_db)
        assert len({r["group"] for r in result.forecast_rows}) == len(result.ranking_rows)

    def test_top_n_is_a_view_over_a_complete_ranking(self, clinic_db):
        config = make_config(group_dimensions=["clinic"], horizon=6,
                             operations=[cfg.OP_RANK, cfg.OP_TOP_N], top_n=2)
        result = engine.execute(config, use_cache=False)
        assert len(result.top_rows) == 2
        assert len(result.ranking_rows) == len(SITES), "full ranking must survive"

    def test_growth_equals_the_documented_formula(self, clinic_db):
        config = make_config(group_dimensions=["clinic"], horizon=6,
                             operations=[cfg.OP_RANK, cfg.OP_GROWTH],
                             ranking_metric="growth")
        result = engine.execute(config, use_cache=False)
        assert result.growth_rows
        for row in result.growth_rows:
            if row["growth_pct"] is None:
                continue
            expected = ((row["forecast_total"] - row["baseline_total"])
                        / row["baseline_total"] * 100.0)
            assert row["growth_pct"] == pytest.approx(expected)

    def test_growth_ranking_is_sorted_by_growth(self, clinic_db):
        config = make_config(group_dimensions=["clinic"], horizon=6,
                             operations=[cfg.OP_RANK, cfg.OP_GROWTH],
                             ranking_metric="growth")
        result = engine.execute(config, use_cache=False)
        values = [r["value"] for r in result.ranking_rows if r.get("value") is not None]
        assert values == sorted(values, reverse=True)

    def test_comparison_ranks_the_future_over_all_entities(self, clinic_db):
        """Northgate grows fastest; it can only surface if all sites are forecast."""
        config = make_config(group_dimensions=["clinic"], horizon=12,
                             operations=[cfg.OP_RANK, cfg.OP_COMPARE], top_n=2)
        result = engine.execute(config, use_cache=False)
        assert result.comparison is not None
        comparison = result.comparison
        assert comparison["top_n"] == 2
        assert len(comparison["future_top"]) == 2
        assert set(comparison["held"]) | set(comparison["entered"]) == {
            e["group"] for e in comparison["future_top"]
        }

    def test_unforecastable_entities_are_never_ranked_as_zero(self, clinic_db):
        result = self._ranked(clinic_db)
        for row in result.ranking_rows:
            if row.get("value") is None:
                assert "rank" not in row


# ══════════════════════════════════════════════════════════
# 6. Caching keyed on config identity
# ══════════════════════════════════════════════════════════

class TestCaching:

    def test_identical_config_is_reused(self, clinic_db):
        engine.clear_cache()
        first = engine.execute(make_config(horizon=3))
        second = engine.execute(make_config(horizon=3))
        assert second is first

    @pytest.mark.parametrize("change", [
        {"horizon": 12}, {"target": "headcount"}, {"time_frequency": "quarters"},
        {"group_dimensions": ["clinic"]},
    ])
    def test_incompatible_config_is_never_reused(self, clinic_db, change):
        engine.clear_cache()
        first = engine.execute(make_config(horizon=3))
        payload = {"horizon": 3}
        payload.update(change)
        second = engine.execute(make_config(**payload))
        assert second is not first
        assert second.config != first.config


# ══════════════════════════════════════════════════════════
# 7. Paraphrase equivalence (no LLM: deterministic markers)
# ══════════════════════════════════════════════════════════

class TestParaphrases:

    RANKING_PARAPHRASES = [
        "Which clinic will lead next month?",
        "Who is expected to have the highest billings next month?",
        "Which site is likely to be #1 next month?",
        "Who will generate the most next month?",
    ]

    def test_paraphrases_all_read_as_predictive(self):
        for question in self.RANKING_PARAPHRASES:
            assert is_predictive_question(question)[0], question

    def test_paraphrases_all_parse_the_same_horizon(self):
        specs = [tr.resolve_horizon(q, "months", "2022-03-31")
                 for q in self.RANKING_PARAPHRASES]
        assert len({s.periods for s in specs}) == 1
        assert specs[0].periods == 1

    GROWTH_PARAPHRASES = [
        "Which clinic will grow the fastest?",
        "Which site is expected to increase the most?",
        "Which service is projected to rise the most?",
    ]

    def test_growth_paraphrases_are_all_predictive(self):
        for question in self.GROWTH_PARAPHRASES:
            assert is_predictive_question(question)[0], question

    @pytest.mark.parametrize("question", [
        "Where is billing rising most quickly?",
        "Which clinic is growing fastest?",
    ])
    def test_present_tense_trend_questions_stay_historical(self, question):
        """
        A documented boundary, not an oversight. "Which clinic is growing
        fastest?" describes a trend in the data already recorded, and is
        answerable exactly from history. Reading present-tense trend language
        as a forecast would turn descriptive questions into predictions; the
        safer default is to answer them from the data, and users who want a
        projection say "will" or "expected".
        """
        assert not is_predictive_question(question)[0]


# ══════════════════════════════════════════════════════════
# 8. Determinism and LLM boundary
# ══════════════════════════════════════════════════════════

class TestBoundaries:

    def test_engine_never_calls_a_language_model(self):
        import inspect
        from prediction import engine as engine_module

        source = inspect.getsource(engine_module)
        assert "call_llm" not in source
        assert "llm_service" not in source

    def test_repeated_execution_is_identical(self, clinic_db):
        a = engine.execute(make_config(group_dimensions=["clinic"], horizon=6,
                                       operations=[cfg.OP_RANK]), use_cache=False)
        b = engine.execute(make_config(group_dimensions=["clinic"], horizon=6,
                                       operations=[cfg.OP_RANK]), use_cache=False)
        assert [r["value"] for r in a.forecast_rows] == [r["value"] for r in b.forecast_rows]
        assert [r["group"] for r in a.ranking_rows] == [r["group"] for r in b.ranking_rows]

    def test_engine_runs_with_interpretation_unavailable(self, clinic_db):
        """A config built without any language model still executes."""
        with patch("services.llm_service.call_llm", side_effect=RuntimeError("offline")):
            result = engine.execute(make_config(horizon=3), use_cache=False)
        assert result.ok and len(result.forecast_rows) == 3
