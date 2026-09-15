"""
Regression tests for generic grouped / multidimensional forecasting.

The engine must group a forecast by any categorical column in the schema —
country, region, product, category, team, salesperson — and by any combination
of them, with no special-cased names anywhere. These tests build a synthetic
star schema whose column names deliberately do NOT match the production one, so
a test passing here proves genericity rather than memorisation.

They also lock in the three things that must never happen: a dimension being
silently dropped, a historical attribute being attached to a coarser forecast,
and a combination being invented that does not occur in the data.
"""

import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from prediction import predictor
from prediction.dimensions import (
    DimensionalityError,
    validate_result_dimensions,
)


# ──────────────────────────────────────────────────────────
# Synthetic star schema (deliberately unlike the real one)
# ──────────────────────────────────────────────────────────

FACTS_PER_GROUP = 24


def _fact_table():
    """
    A fact table with two dimension keys and a measure.

    Note the deliberate hole: zone Z2 never sells item I3, so the cross product
    is 2 x 3 = 6 but only 5 combinations actually occur.
    """
    rows = []
    dates = pd.date_range("2021-01-31", periods=FACTS_PER_GROUP, freq="ME")
    combos = [("Z1", "I1"), ("Z1", "I2"), ("Z1", "I3"), ("Z2", "I1"), ("Z2", "I2")]
    for zone, item in combos:
        base = 1000 if zone == "Z1" else 400
        for i, d in enumerate(dates):
            rows.append({
                "zone_key": zone, "item_key": item, "when": d,
                "turnover": float(base + 10 * i + (7 * i) % 23),
            })
    return pd.DataFrame(rows)


def _zone_dim():
    return pd.DataFrame({
        "zone_key": ["Z1", "Z2"],
        "territory": ["North", "South"],
        "cluster": ["Alpha", "Alpha"],
    })


def _item_dim():
    return pd.DataFrame({
        "item_key": ["I1", "I2", "I3"],
        "article": ["Widget", "Gadget", "Doodad"],
        "family": ["Hardware", "Hardware", "Software"],
    })


def _dim(hint, table, column, key, df):
    return {
        "target_table": table, "group_column": column,
        "join_key_base": key, "join_key_target": key,
        "requires_join": True, "semantic_hint": hint, "dim_df": df,
    }


class _Detection:
    date_column = "when"
    target_column = "turnover"


def _forecast(dims, steps=3, ranking_metric="sum", group_filter=None, df=None):
    with patch("prediction.predictor.detector.detect", return_value=_Detection()):
        return predictor.predict_grouped_forecast(
            df if df is not None else _fact_table(),
            dimensions=dims, target_col="turnover", steps=steps,
            frequency="months", table_name="facts",
            ranking_metric=ranking_metric, group_filter=group_filter,
        )


ZONE = lambda: _dim("territory", "zones", "territory", "zone_key", _zone_dim())
ITEM = lambda: _dim("article", "items", "article", "item_key", _item_dim())
FAMILY = lambda: _dim("family", "items", "family", "item_key", _item_dim())
CLUSTER = lambda: _dim("cluster", "zones", "cluster", "zone_key", _zone_dim())


# ══════════════════════════════════════════════════════════
# 1. Single dimension — DIMENSION x PERIOD x MEASURE
# ══════════════════════════════════════════════════════════

class TestSingleDimension:

    def test_one_dimension_produces_dimension_by_period(self):
        result = _forecast([ZONE()], steps=6)

        assert result.dimensions == ["territory"]
        assert len(result.raw_forecast_results) == 2       # North, South
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == {"territory"}
            assert len(entry["forecast"]) == 6             # one row per period
            assert all("date" in f and "value" in f for f in entry["forecast"])

    def test_horizon_is_respected_per_group(self):
        for steps in (3, 6, 12):
            result = _forecast([ZONE()], steps=steps)
            assert result.horizon == steps
            for entry in result.raw_forecast_results:
                assert len(entry["forecast"]) == steps

    def test_any_dimension_column_works_without_special_casing(self):
        """The same code path must serve every dimension in the schema."""
        for spec, expected in [
            (ZONE(), {"North", "South"}),
            (ITEM(), {"Widget", "Gadget", "Doodad"}),
            (FAMILY(), {"Hardware", "Software"}),
            (CLUSTER(), {"Alpha"}),
        ]:
            result = _forecast([spec])
            values = {list(e["group_dict"].values())[0] for e in result.raw_forecast_results}
            assert values == expected


# ══════════════════════════════════════════════════════════
# 2. Multiple dimensions — no collapsing
# ══════════════════════════════════════════════════════════

class TestMultipleDimensions:

    def test_two_dimensions_stay_separately_addressable(self):
        result = _forecast([ZONE(), ITEM()], steps=3)

        assert result.dimensions == ["territory", "article"]
        for entry in result.raw_forecast_results:
            gd = entry["group_dict"]
            assert set(gd) == {"territory", "article"}
            assert gd["territory"] in {"North", "South"}
            assert gd["article"] in {"Widget", "Gadget", "Doodad"}
            # Neither field may hold the other's value.
            assert " - " not in gd["territory"]
            assert " - " not in gd["article"]

    def test_three_dimensions_are_all_preserved(self):
        result = _forecast([ZONE(), ITEM(), FAMILY()], steps=3)
        assert result.dimensions == ["territory", "article", "family"]
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == {"territory", "article", "family"}

    def test_two_dimensions_from_one_table_do_not_collide(self):
        """
        'article' and 'family' both live in the items table. Joining that table
        twice produced article_x/article_y and then a KeyError.
        """
        result = _forecast([ITEM(), FAMILY()], steps=3)
        assert result.dimensions == ["article", "family"]
        assert len(result.raw_forecast_results) == 3
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == {"article", "family"}

    def test_dimension_order_is_preserved(self):
        assert _forecast([ZONE(), ITEM()]).dimensions == ["territory", "article"]
        assert _forecast([ITEM(), ZONE()]).dimensions == ["article", "territory"]

    def test_group_label_lists_every_dimension_value(self):
        result = _forecast([ZONE(), ITEM()])
        for entry in result.raw_forecast_results:
            for value in entry["group_dict"].values():
                assert value in entry["group"]

    def test_period_granularity_survives_multiple_dimensions(self):
        """ZONE x ITEM x MONTH x MEASURE — the horizon is per combination."""
        result = _forecast([ZONE(), ITEM()], steps=3)
        for entry in result.raw_forecast_results:
            dates = [f["date"] for f in entry["forecast"]]
            assert len(dates) == 3
            assert len(set(dates)) == 3, "each forecast row is a distinct period"


# ══════════════════════════════════════════════════════════
# 3. No fabricated combinations
# ══════════════════════════════════════════════════════════

class TestNoFabrication:

    def test_only_observed_combinations_are_forecast(self):
        """2 zones x 3 items = 6, but Z2/I3 never occurs — so 5, not 6."""
        result = _forecast([ZONE(), ITEM()])

        combos = {(e["group_dict"]["territory"], e["group_dict"]["article"])
                  for e in result.raw_forecast_results}
        assert len(combos) == 5
        assert ("South", "Doodad") not in combos

    def test_missing_combination_is_absent_not_zero(self):
        """An unobserved combination must not appear with a zero forecast."""
        result = _forecast([ZONE(), ITEM()])
        for entry in result.raw_forecast_results:
            gd = entry["group_dict"]
            assert not (gd["territory"] == "South" and gd["article"] == "Doodad")

    def test_coarse_forecast_carries_no_finer_attribute(self):
        """
        A forecast grouped by zone alone must not have a product attached to
        it. Decorating a country-level forecast with its historical top product
        is how a past fact gets presented as a prediction.
        """
        result = _forecast([ZONE()])
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == {"territory"}
            assert "article" not in entry["group_dict"]
            assert "family" not in entry["group_dict"]
            assert "Widget" not in entry["group"]


# ══════════════════════════════════════════════════════════
# 4. Forecast all eligible groups before ranking
# ══════════════════════════════════════════════════════════

class TestRankingScope:

    def test_all_groups_are_forecast_before_ranking(self):
        result = _forecast([ZONE(), ITEM()])
        assert result.count == 5, "every eligible combination must be ranked"
        assert result.restricted_to == {}, "no restriction unless asked for"

    def test_ranking_is_descending_over_the_full_set(self):
        result = _forecast([ZONE(), ITEM()])
        values = [e["final_value"] for e in result.raw_forecast_results
                  if e["final_value"] is not None]
        assert values == sorted(values, reverse=True)
        assert result.best_group == result.raw_forecast_results[0]["group"]

    def test_explicit_restriction_is_applied_and_recorded(self):
        result = _forecast([ZONE(), ITEM()], group_filter={"territory": ["North"]})

        assert result.restricted_to == {"territory": ["North"]}
        territories = {e["group_dict"]["territory"] for e in result.raw_forecast_results}
        assert territories == {"North"}

    def test_restriction_on_an_unknown_dimension_is_ignored(self):
        result = _forecast([ZONE()], group_filter={"not_a_dimension": ["x"]})
        assert result.restricted_to == {}
        assert len(result.raw_forecast_results) == 2


# ══════════════════════════════════════════════════════════
# 5. Hard dimensionality validation
# ══════════════════════════════════════════════════════════

class TestDimensionalityValidation:

    def test_valid_result_passes(self):
        result = _forecast([ZONE(), ITEM()])
        assert validate_result_dimensions(result, ["territory", "article"]) == []

    def test_wrong_dimension_list_is_rejected(self):
        result = _forecast([ZONE()])
        with pytest.raises(DimensionalityError):
            validate_result_dimensions(result, ["territory", "article"])

    def test_collapsed_dimension_is_detected(self):
        """The old '{country: "India - Bars"}' shape must be caught."""
        broken = {
            "dimensions": ["territory", "article"],
            "raw_forecast_results": [
                {"group": "North - Widget", "group_dict": {"territory": "North - Widget"}},
            ],
        }
        issues = validate_result_dimensions(broken, ["territory", "article"], strict=False)
        assert any("collapsed" in i for i in issues)
        with pytest.raises(DimensionalityError):
            validate_result_dimensions(broken, ["territory", "article"])

    def test_missing_group_dict_is_detected(self):
        broken = {
            "dimensions": ["territory"],
            "raw_forecast_results": [{"group": "North"}],
        }
        issues = validate_result_dimensions(broken, ["territory"], strict=False)
        assert any("no group_dict" in i for i in issues)

    def test_dimension_order_mismatch_is_rejected(self):
        result = _forecast([ZONE(), ITEM()])
        with pytest.raises(DimensionalityError):
            validate_result_dimensions(result, ["article", "territory"])

    def test_grouped_forecast_self_validates(self):
        """predict_grouped_forecast runs the check itself before returning."""
        result = _forecast([ZONE(), ITEM()])
        assert result.dimensions == ["territory", "article"]
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == set(result.dimensions)


# ══════════════════════════════════════════════════════════
# 6. Resolution provenance and join failures
# ══════════════════════════════════════════════════════════

class TestResolutionProvenance:

    def test_result_records_how_each_dimension_was_resolved(self):
        result = _forecast([ZONE(), ITEM()])
        assert len(result.dimension_specs) == 2
        for spec in result.dimension_specs:
            assert spec["semantic_hint"] in result.dimensions
            assert spec["group_column"]
            assert spec["target_table"]
            assert "dim_df" not in spec, "raw frames must not leak into the result"

    def test_join_key_missing_from_dimension_table_fails_loudly(self):
        bad = _dim("territory", "zones", "territory", "no_such_key", _zone_dim())
        with pytest.raises(ValueError, match="no_such_key"):
            _forecast([bad])

    def test_join_key_missing_from_fact_table_fails_loudly(self):
        """The failure mode behind the old team dimension: a key the fact table lacks."""
        bad = dict(_dim("territory", "zones", "territory", "zone_key", _zone_dim()))
        bad["join_key_base"] = "not_in_facts"
        with pytest.raises(ValueError, match="no join key"):
            _forecast([bad])

    def test_missing_group_column_fails_loudly(self):
        bad = _dim("ghost", "zones", "no_such_column", "zone_key", _zone_dim())
        with pytest.raises(ValueError, match="missing column"):
            _forecast([bad])

    def test_base_table_dimension_needs_no_join(self):
        """A denormalised single table groups exactly like a star schema."""
        spec = {
            "target_table": "facts", "group_column": "zone_key",
            "join_key_base": None, "join_key_target": None,
            "requires_join": False, "semantic_hint": "zone",
        }
        result = _forecast([spec])
        assert result.dimensions == ["zone"]
        assert {e["group_dict"]["zone"] for e in result.raw_forecast_results} == {"Z1", "Z2"}


# ══════════════════════════════════════════════════════════
# 7. Generic resolution against a live schema
# ══════════════════════════════════════════════════════════

class TestSchemaDrivenResolution:
    """
    Exercises resolve_dimensions against a temporary database, proving the
    resolver reads the schema rather than recognising particular words.
    """

    @pytest.fixture
    def star_db(self, tmp_path, monkeypatch):
        import sqlite3
        db_path = str(tmp_path / "star.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE zones (zone_key TEXT, territory TEXT, cluster TEXT)")
        conn.executemany("INSERT INTO zones VALUES (?,?,?)",
                         [("Z1", "North", "Alpha"), ("Z2", "South", "Beta")])
        conn.execute("CREATE TABLE items (item_key TEXT, article TEXT, family TEXT)")
        conn.executemany("INSERT INTO items VALUES (?,?,?)",
                         [("I1", "Widget", "Hardware"), ("I2", "Gadget", "Software")])
        conn.execute("CREATE TABLE facts (zone_key TEXT, item_key TEXT, when_on TEXT, turnover REAL)")
        conn.executemany("INSERT INTO facts VALUES (?,?,?,?)",
                         [("Z1", "I1", "2021-01-01", 10.0), ("Z2", "I2", "2021-02-01", 20.0)])
        conn.commit()
        conn.close()
        monkeypatch.setattr("config.DATABASE_PATH", db_path)
        monkeypatch.setattr("services.database.DATABASE_PATH", db_path)
        return db_path

    def test_exact_column_names_resolve_with_full_confidence(self, star_db):
        from prediction.dimensions import resolve_dimensions

        res = resolve_dimensions(["territory", "article", "family"], "facts")
        assert res.ok
        assert [d.column for d in res.resolved] == ["territory", "article", "family"]
        assert all(d.method == "exact_name" and d.confidence == 1.0 for d in res.resolved)

    def test_join_keys_are_discovered_and_verified(self, star_db):
        from prediction.dimensions import resolve_dimensions

        res = resolve_dimensions(["territory", "article"], "facts")
        by_hint = {d.hint: d for d in res.resolved}
        assert by_hint["territory"].join_key_base == "zone_key"
        assert by_hint["article"].join_key_base == "item_key"

    def test_unknown_term_is_refused_with_suggestions(self, star_db):
        from prediction.dimensions import resolve_dimensions

        res = resolve_dimensions(["nonexistent_thing_xyz"], "facts")
        assert not res.ok
        assert res.unresolved[0]["closest"], "should suggest what is available"

    def test_measure_and_date_columns_are_not_offered_as_dimensions(self, star_db):
        from prediction.dimensions import build_dimension_catalog

        catalog = build_dimension_catalog("facts", exclude_columns={"turnover", "when_on"})
        columns = {c.column for c in catalog}
        assert "turnover" not in columns
        assert "when_on" not in columns

    def test_key_columns_are_not_offered_as_dimensions(self, star_db):
        from prediction.dimensions import build_dimension_catalog

        catalog = build_dimension_catalog("facts")
        assert not any(c.column.endswith("_key") for c in catalog)

    def test_unreachable_tables_are_excluded(self, star_db, monkeypatch):
        """A table with no verified join path cannot supply a dimension."""
        import sqlite3
        from prediction.dimensions import joinable_tables

        conn = sqlite3.connect(star_db)
        conn.execute("CREATE TABLE unrelated (thing TEXT, territory TEXT)")
        conn.executemany("INSERT INTO unrelated VALUES (?,?)", [("a", "Mars"), ("b", "Venus")])
        conn.commit()
        conn.close()

        reachable = joinable_tables("facts")
        assert "unrelated" not in reachable
        assert set(reachable) == {"facts", "zones", "items"}
