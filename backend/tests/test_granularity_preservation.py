"""
Granularity must survive a follow-up.

A conversation that ranks countries and then asks "will this be the same next
year?" must answer about countries. The failure these tests guard against is
subtle because every individual number stays correct — only the level changes,
because the interpreter reads the previous rows and proposes grouping by
whatever columns it finds in them.
"""

import pytest

from prediction import engine
from prediction.config import PredictionConfig
from prediction.config_resolver import (
    _mentions_dimension,
    _resolve_dimension_change,
)


def country_config(**kw) -> PredictionConfig:
    return PredictionConfig(
        table="sales", target="amount", group_dimensions=["country"], **kw
    )


class TestGranularityContract:
    def test_granularity_names_the_level(self):
        assert country_config().result_granularity == "country"
        assert PredictionConfig(
            table="t", target="a", group_dimensions=["country", "product"]
        ).result_granularity == "country_product"

    def test_ungrouped_is_total(self):
        assert PredictionConfig(table="t", target="a").result_granularity == "total"

    def test_granularity_is_exported(self):
        assert country_config().to_dict()["result_granularity"] == "country"


class TestDimensionChangeGate:
    """A dimension enters a follow-up only when the question asks for it."""

    @pytest.mark.parametrize("question", [
        "will this be same next year",
        "will it remain the same next year",
        "what about next year",
        "is that going to hold",
        "will New Zealand remain the leader",
    ])
    def test_unrequested_dimension_is_refused(self, question):
        # The interpreter proposes `product` because products were in the rows.
        dims, origin, note = _resolve_dimension_change(
            question, ["product"], country_config(), {},
        )
        assert dims == ["country"], f"granularity drifted on: {question}"
        assert origin == "inherited"
        assert "did not ask for" in note

    def test_unrequested_dimension_refused_even_when_interpreter_flags_it(self):
        # `keeps_previous_dimensions` used to be the only gate; the question
        # itself now has to agree.
        dims, origin, _ = _resolve_dimension_change(
            "will this be same next year", ["product"], country_config(),
            {"keeps_previous_dimensions": True},
        )
        assert dims == ["country"]
        assert origin == "inherited"

    @pytest.mark.parametrize("question,expected", [
        ("break it down by product", ["product"]),
        ("group by region instead", ["region"]),
        ("show me that by category", ["category"]),
        ("which product will lead next year", ["product"]),
    ])
    def test_explicit_regrouping_is_honoured(self, question, expected):
        dims, origin, _ = _resolve_dimension_change(
            question, expected, country_config(), {},
        )
        assert dims == expected
        assert origin == "replaced"

    @pytest.mark.parametrize("question", [
        "show me their top products",
        "what are their products",
        "break that down within each one by product",
    ])
    def test_drilldown_keeps_the_outer_level(self, question):
        dims, origin, _ = _resolve_dimension_change(
            question, ["product"], country_config(), {},
        )
        assert dims == ["country", "product"], "drill-down collapsed the outer level"
        assert origin == "drilldown"

    def test_silence_inherits(self):
        dims, origin, _ = _resolve_dimension_change(
            "and next year?", [], country_config(), {},
        )
        assert dims == ["country"]
        assert origin == "inherited"

    def test_gate_is_not_column_specific(self):
        """No dimension name is privileged — the rules hold for any column."""
        prev = PredictionConfig(table="t", target="a", group_dimensions=["salesperson"])
        assert _resolve_dimension_change("will that hold", ["team"], prev, {})[0] == ["salesperson"]
        assert _resolve_dimension_change("by team please", ["team"], prev, {})[0] == ["team"]


class TestMentionDetection:
    @pytest.mark.parametrize("question,dim,expected", [
        ("show me products", "product", True),
        ("show me product lines", "product", True),
        ("by categories", "category", True),
        ("will this be same next year", "product", False),
        ("which country leads", "geo.country", True),
        ("revenue by nation", "country", False),
    ])
    def test_stem_matching(self, question, dim, expected):
        assert _mentions_dimension(question, dim) is expected


class TestGranularityEnforcement:
    """The engine must not return rows finer than the config asked for."""

    def _result(self, rows_dims):
        result = engine.PredictionResult()
        for i, values in enumerate(rows_dims):
            label = " - ".join(values.values())
            result.forecast_rows.append({
                "group": label, "group_values": values,
                "period": "2025-01", "value": 100.0 + i,
                "lower": 90.0, "upper": 110.0,
            })
            result.ranking_rows.append({
                "group": label, "group_values": values,
                "value": 100.0 + i, "rank": i + 1,
            })
        return result

    def test_finer_rows_are_rolled_up(self):
        result = self._result([
            {"country": "NZ", "product": "A"},
            {"country": "NZ", "product": "B"},
            {"country": "AU", "product": "A"},
        ])
        engine._enforce_granularity(country_config(), result)

        assert result.result_granularity == "country"
        assert {r["group"] for r in result.forecast_rows} == {"NZ", "AU"}
        nz = next(r for r in result.forecast_rows if r["group"] == "NZ")
        assert nz["value"] == pytest.approx(201.0)  # 100 + 101, not either alone
        assert nz["upper"] == pytest.approx(220.0)  # bounds summed with the value
        assert any("did not ask to break it down" in w for w in result.warnings)

    def test_rollup_reranks(self):
        result = self._result([
            {"country": "AU", "product": "A"},
            {"country": "AU", "product": "B"},
            {"country": "NZ", "product": "A"},
        ])
        engine._enforce_granularity(country_config(), result)
        ranks = [(r["group"], r["rank"]) for r in result.ranking_rows]
        assert ranks == [("AU", 1), ("NZ", 2)], "ranking not recomputed after roll-up"

    def test_matching_granularity_is_untouched(self):
        result = self._result([{"country": "NZ"}, {"country": "AU"}])
        engine._enforce_granularity(country_config(), result)
        assert result.warnings == []
        assert len(result.forecast_rows) == 2

    def test_missing_level_is_an_error_not_a_rollup(self):
        result = self._result([{"product": "A"}])
        engine._enforce_granularity(country_config(), result)
        assert not result.ok
        assert any("missing the requested grouping" in e for e in result.errors)


class TestComparisonAnswer:
    def _format(self, current, future, **kw):
        from agents.forecast_comparison import (
            RankedEntry, RankingComparison, format_comparison,
        )
        comparison = RankingComparison(
            current_top=[RankedEntry(i, g, v) for i, (g, v) in enumerate(current, 1)],
            future_top=[RankedEntry(i, g, v) for i, (g, v) in enumerate(future, 1)],
            top_n=len(current), n_ranked=5, **kw
        )
        return format_comparison(comparison, "amount", "country", "next year")

    def test_leader_retention_is_stated_explicitly(self):
        text = self._format(
            [("New Zealand", 900.0), ("Australia", 700.0)],
            [("New Zealand", 950.0), ("Australia", 720.0)],
            unchanged_order=True, unchanged_set=True,
        )
        assert "ANSWER: Yes" in text
        assert "CURRENT LEADER: New Zealand" in text
        assert "FORECAST LEADER: New Zealand" in text
        assert "REPORTED AT: country level" in text

    def test_leader_change_is_stated_explicitly(self):
        text = self._format([("New Zealand", 900.0)], [("Australia", 980.0)])
        assert "ANSWER: No" in text
        assert "change from New Zealand to Australia" in text
