"""
Regression tests for the forecasting engine.

These lock in the statistical guarantees the engine is supposed to provide:
gaps are never zeros, partial periods never masquerade as full ones, models
are chosen on chronological validation rather than assumption, dimensions
survive grouping, and a series that cannot support a forecast is refused with
a stated reason instead of being forecast badly.

Everything here is deterministic and offline — no LLM, no database, no network.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from prediction import forecast_selection, predictor, preprocessing, series_validation
from prediction.forecasting_models import (
    DriftForecaster,
    NaiveForecaster,
    SeasonalNaiveForecaster,
    build_candidates,
)


# ──────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────

def _monthly(values, start="2021-01-31"):
    """Build a month-end indexed series; None entries stay NaN."""
    idx = pd.date_range(start, periods=len(values), freq="ME")
    return pd.Series(values, index=idx, dtype=float)


def _transactions(dates, values, **extra):
    frame = {"d": pd.to_datetime(dates), "v": values}
    frame.update(extra)
    return pd.DataFrame(frame)


# ══════════════════════════════════════════════════════════
# 1. Aggregation — missing is never zero
# ══════════════════════════════════════════════════════════

class TestAggregation:

    def test_missing_periods_become_nan_not_zero(self):
        """A month with no rows must be unknown, not a fabricated 0.0."""
        df = _transactions(
            ["2021-01-05", "2021-01-20", "2021-06-10"],
            [10.0, 5.0, 7.0],
        )
        series, info = preprocessing.aggregate_time_series(df, "d", "v", frequency="months")

        assert series.isna().sum() == 4, "Feb-May have no data and must be NaN"
        assert not (series.fillna(-1) == 0).any(), "no empty bucket may become 0.0"
        assert series.iloc[0] == 15.0, "real values still aggregate by sum"
        assert series.dropna().shape[0] == 2

    def test_genuine_zero_is_preserved(self):
        """A period whose rows really do sum to zero stays 0.0, not NaN."""
        df = _transactions(
            ["2021-01-05", "2021-02-10", "2021-03-10"],
            [10.0, 0.0, 7.0],
        )
        series, _ = preprocessing.aggregate_time_series(df, "d", "v", frequency="months")
        assert series.iloc[1] == 0.0
        assert not pd.isna(series.iloc[1])

    def test_partial_trailing_period_is_trimmed(self):
        """A quarter of data must not be summed into an annual bucket."""
        dates = pd.date_range("2021-01-15", "2022-03-31", freq="7D")
        df = _transactions(dates, [100.0] * len(dates))

        series, info = preprocessing.aggregate_time_series(df, "d", "v", frequency="years")
        assert info["n_trimmed_partial"] >= 1, "incomplete 2022 must be dropped"
        assert all(ts.year != 2022 for ts in series.index)

    def test_complete_edges_are_not_trimmed(self):
        """Full months at both ends must survive untouched."""
        dates = pd.date_range("2021-01-01", "2021-03-31", freq="D")
        df = _transactions(dates, [1.0] * len(dates))
        series, info = preprocessing.aggregate_time_series(df, "d", "v", frequency="months")
        assert info["n_trimmed_partial"] == 0
        assert len(series) == 3

    def test_requested_frequency_is_honoured(self):
        """Asking for months returns month buckets, whatever the raw spacing."""
        dates = pd.date_range("2021-01-01", "2021-12-31", freq="D")
        df = _transactions(dates, [1.0] * len(dates))

        monthly, _ = preprocessing.aggregate_time_series(df, "d", "v", frequency="months")
        daily, _ = preprocessing.aggregate_time_series(df, "d", "v", frequency="days")

        assert len(monthly) == 12
        assert len(daily) == 365
        assert monthly.index.freqstr.startswith("M")


class TestFrequencyInference:

    @pytest.mark.parametrize("freq,expected", [
        ("D", "days"), ("W", "weeks"), ("ME", "months"), ("QE", "quarters"), ("YE", "years"),
    ])
    def test_infers_frequency_from_spacing(self, freq, expected):
        idx = pd.date_range("2020-01-01", periods=12, freq=freq)
        assert series_validation.infer_frequency(pd.Series(idx)) == expected

    def test_finer_request_than_data_is_flagged(self):
        """Asking for days when the data is monthly is a mismatch worth stating."""
        series = _monthly([1.0] * 12)
        diag = series_validation.validate_series(
            series, requested_frequency="days", horizon=7, inferred_frequency="months",
        )
        assert diag.frequency_mismatch is True
        assert any("granularity" in w for w in diag.warnings)


# ══════════════════════════════════════════════════════════
# 2. Historical data validation
# ══════════════════════════════════════════════════════════

class TestSeriesValidation:

    def test_empty_series_is_refused(self):
        diag = series_validation.validate_series(
            pd.Series(dtype=float), requested_frequency="months", horizon=6,
        )
        assert diag.status == "no_data"

    def test_single_observation_is_refused(self):
        series = _monthly([100.0, None, None, None])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        assert diag.status == "insufficient_history"
        assert diag.reason
        assert diag.n_observed == 1

    def test_short_history_falls_back_explicitly(self):
        """2-3 points: forecast allowed, but only as a labelled naive fallback."""
        series = _monthly([100.0, 110.0, 120.0])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        assert diag.status == "fallback"
        assert "naive" in diag.reason.lower()

    def test_too_sparse_series_is_refused(self):
        """The sparse group that used to produce a negative revenue forecast."""
        series = _monthly([5000, None, None, None, 8000, None, None,
                           None, None, 3000, None, None, None, None, 6000])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=12)
        assert diag.status == "too_sparse"
        assert diag.missing_ratio > 0.6

    def test_counts_and_range_are_reported(self):
        series = _monthly([10.0, None, 30.0, 40.0, 50.0, 60.0])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=3)
        assert diag.n_periods == 6
        assert diag.n_observed == 5
        assert diag.n_missing == 1
        assert diag.first_period and diag.last_period
        assert any("not as zero" in w for w in diag.warnings)

    def test_constant_and_all_zero_series_are_flagged(self):
        const = series_validation.validate_series(
            _monthly([7.0] * 10), requested_frequency="months", horizon=3)
        assert const.is_constant and not const.is_all_zero

        zeros = series_validation.validate_series(
            _monthly([0.0] * 10), requested_frequency="months", horizon=3)
        assert zeros.is_all_zero and zeros.is_constant

    def test_extreme_outliers_are_detected_not_removed(self):
        values = [100.0] * 11 + [50000.0]
        series = _monthly(values)
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=3)
        assert diag.n_outliers >= 1
        assert diag.outlier_periods
        # Reported, never silently dropped: the observation count is unchanged.
        assert diag.n_observed == 12

    def test_duplicate_rows_are_counted(self):
        df = _transactions(
            ["2021-01-05", "2021-01-05", "2021-02-05", "2021-03-05", "2021-04-05"],
            [10.0, 10.0, 20.0, 30.0, 40.0],
        )
        _, info = preprocessing.aggregate_time_series(df, "d", "v", frequency="months")
        assert info["duplicate_timestamps"] == 1

    def test_horizon_longer_than_history_is_warned(self):
        series = _monthly([float(i) for i in range(1, 9)])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=24)
        assert diag.horizon_exceeds_history is True
        assert any("exceeds the observed history" in w for w in diag.warnings)

    def test_seasonality_requires_two_full_cycles(self):
        short = series_validation.validate_series(
            _monthly([1.0] * 15), requested_frequency="months", horizon=6)
        assert short.seasonal_periods == 12
        assert short.seasonality_supported is False

        long = series_validation.validate_series(
            _monthly([float(i % 12) for i in range(30)]), requested_frequency="months", horizon=6)
        assert long.seasonality_supported is True


# ══════════════════════════════════════════════════════════
# 3. Chronological splitting & leakage prevention
# ══════════════════════════════════════════════════════════

class TestChronologicalValidation:

    def test_folds_are_strictly_chronological_and_disjoint(self):
        series = _monthly([float(i) for i in range(1, 25)])
        folds = forecast_selection.build_folds(series, horizon=3)

        assert folds, "24 points must support at least one fold"
        for train_end, val_end in folds:
            assert train_end < val_end, "validation must come after training"
            assert train_end >= forecast_selection.MIN_TRAIN_OBSERVATIONS
            assert val_end <= len(series), "validation cannot run past the series"

    def test_training_slice_never_sees_future_values(self):
        """
        Two series identical except for their final value must yield byte-identical
        training slices for the first fold — proof the model cannot peek ahead.
        """
        base = [float(i) for i in range(1, 25)]
        a = _monthly(base)
        b = _monthly(base[:-1] + [999999.0])

        fold_a = forecast_selection.build_folds(a, horizon=3)[0]
        fold_b = forecast_selection.build_folds(b, horizon=3)[0]
        assert fold_a == fold_b

        train_a, _ = forecast_selection.prepare_fit_slice(a.iloc[:fold_a[0]])
        train_b, _ = forecast_selection.prepare_fit_slice(b.iloc[:fold_b[0]])
        pd.testing.assert_series_equal(train_a, train_b)

    def test_too_short_series_yields_no_folds(self):
        assert forecast_selection.build_folds(_monthly([1.0, 2.0, 3.0]), horizon=3) == []

    def test_fit_slice_interpolates_gaps_without_writing_zeros(self):
        series = _monthly([10.0, None, None, 40.0, 50.0])
        fitted, n_imputed = forecast_selection.prepare_fit_slice(series)

        assert n_imputed == 2
        assert not fitted.isna().any()
        assert (fitted > 0).all(), "interpolation must never introduce a zero"
        assert fitted.iloc[1] == pytest.approx(20.0)
        assert fitted.iloc[2] == pytest.approx(30.0)

    def test_fit_slice_trims_edges_rather_than_inventing_them(self):
        """Leading/trailing gaps are dropped — we do not know what happened there."""
        series = _monthly([None, None, 30.0, 40.0, None])
        fitted, n_imputed = forecast_selection.prepare_fit_slice(series)
        assert len(fitted) == 2
        assert n_imputed == 0

    def test_original_series_is_not_mutated(self):
        series = _monthly([10.0, None, 30.0])
        before = series.copy()
        forecast_selection.prepare_fit_slice(series)
        pd.testing.assert_series_equal(series, before)


# ══════════════════════════════════════════════════════════
# 4. Baselines and candidate models
# ══════════════════════════════════════════════════════════

class TestBaselineModels:

    def test_naive_repeats_last_value(self):
        model = NaiveForecaster().fit(_monthly([1.0, 2.0, 5.0]))
        fc, _ = model.predict(steps=3)
        assert list(fc.values) == [5.0, 5.0, 5.0]

    def test_seasonal_naive_repeats_the_cycle(self):
        values = [float(i % 4) for i in range(16)]
        model = SeasonalNaiveForecaster(seasonal_periods=4).fit(_monthly(values))
        fc, _ = model.predict(steps=4)
        assert list(fc.values) == [0.0, 1.0, 2.0, 3.0]

    def test_drift_extends_the_straight_line(self):
        model = DriftForecaster().fit(_monthly([10.0, 20.0, 30.0]))
        fc, _ = model.predict(steps=2)
        assert list(fc.values) == pytest.approx([40.0, 50.0])

    def test_forecast_index_continues_the_history(self):
        series = _monthly([1.0] * 6, start="2021-01-31")
        fc, _ = NaiveForecaster().fit(series).predict(steps=3)
        assert list(fc.index) == list(pd.date_range("2021-07-31", periods=3, freq="ME"))

    def test_seasonal_candidates_excluded_without_two_cycles(self):
        without = {c.model_key for c in build_candidates(12, include_seasonal=False)}
        with_seasonal = {c.model_key for c in build_candidates(12, include_seasonal=True)}
        assert "seasonal_naive" not in without
        assert "seasonal_naive" in with_seasonal

    def test_baselines_are_always_candidates(self):
        keys = {c.model_key for c in build_candidates(12, include_seasonal=False)}
        assert {"naive", "drift", "moving_average"} <= keys


# ══════════════════════════════════════════════════════════
# 5. Model selection on validation performance
# ══════════════════════════════════════════════════════════

class TestModelSelection:

    def test_trending_series_selects_a_trend_model_and_beats_naive(self):
        series = _monthly([float(100 + 10 * i) for i in range(24)])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        model, meta = forecast_selection.select_and_fit(series, diag, horizon=6)

        assert meta.selection_method == "rolling_origin_backtest"
        assert meta.beats_naive is True
        assert meta.selected_model_key in ("drift", "holt_linear", "damped_holt")
        assert meta.n_folds >= 1
        assert meta.selected_score is not None

    def test_seasonal_series_selects_a_seasonal_model(self):
        rng = np.random.default_rng(0)
        season = [50.0, 40, 45, 60, 80, 120, 140, 130, 90, 70, 60, 100]
        values = [season[i % 12] + rng.normal(0, 1.0) for i in range(48)]
        series = _monthly(values)

        diag = series_validation.validate_series(series, requested_frequency="months", horizon=12)
        assert diag.seasonality_supported is True

        model, meta = forecast_selection.select_and_fit(series, diag, horizon=12)
        assert meta.selected_model_key in ("seasonal_naive", "holt_winters_additive")
        assert meta.beats_naive is True

    def test_every_candidate_is_scored_and_recorded(self):
        series = _monthly([float(100 + 10 * i) for i in range(24)])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        _, meta = forecast_selection.select_and_fit(series, diag, horizon=6)

        assert len(meta.candidates) >= 5
        scored = [c for c in meta.candidates if c.eligible]
        assert scored, "at least one candidate must be scored"
        for c in scored:
            assert c.n_folds >= 1
            assert c.mae is not None
            assert c.folds, "per-fold detail must be retained for auditability"

    def test_constant_series_is_forced_to_naive(self):
        series = _monthly([42.0] * 20)
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        model, meta = forecast_selection.select_and_fit(series, diag, horizon=6)

        assert meta.selection_method == "forced_constant"
        assert meta.selected_model_key == "naive"
        fc, _ = model.predict(steps=3)
        assert list(fc.values) == [42.0, 42.0, 42.0]

    def test_fallback_series_uses_labelled_naive(self):
        series = _monthly([100.0, 110.0, 130.0])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        model, meta = forecast_selection.select_and_fit(series, diag, horizon=6)

        assert meta.selection_method == "fallback_no_validation"
        assert meta.selected_model_key == "naive"
        assert meta.notes

    def test_refused_series_returns_no_model(self):
        series = _monthly([100.0, None, None, None])
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)
        model, meta = forecast_selection.select_and_fit(series, diag, horizon=6)

        assert model is None
        assert meta.selection_method == "not_forecast"
        assert meta.notes

    def test_selection_is_deterministic(self):
        rng = np.random.default_rng(7)
        values = [float(100 + 5 * i + rng.normal(0, 3)) for i in range(30)]
        series = _monthly(values)
        diag = series_validation.validate_series(series, requested_frequency="months", horizon=6)

        _, first = forecast_selection.select_and_fit(series, diag, horizon=6)
        _, second = forecast_selection.select_and_fit(series, diag, horizon=6)

        assert first.selected_model_key == second.selected_model_key
        assert first.selected_score == second.selected_score


# ══════════════════════════════════════════════════════════
# 6. Forecast output guarantees
# ══════════════════════════════════════════════════════════

class TestForecastOutput:

    def test_non_negative_history_never_forecasts_negative(self):
        """The declining short series that used to produce negative revenue."""
        series = _monthly([9000.0, 7000, 6000, 4500, 3000, 2000, 1500, 1000, 800, 600, 400, 300])
        diag, meta, fc, ci = predictor.run_series_forecast(series, steps=12, frequency="months")

        assert meta.floor_applied is True
        assert (fc.values >= 0).all(), "a non-negative series cannot forecast below zero"
        if ci is not None:
            assert (ci["lower"].values >= 0).all()

    def test_series_with_negative_history_keeps_negative_forecasts(self):
        """The floor is data-driven, not a business rule about revenue."""
        series = _monthly([5.0, -2.0, 3.0, -4.0, 2.0, -6.0, 1.0, -8.0, 0.0, -10.0, -1.0, -12.0])
        _, meta, fc, _ = predictor.run_series_forecast(series, steps=6, frequency="months")
        assert meta.floor_applied is False

    def test_every_forecast_carries_model_and_validation_metadata(self):
        series = _monthly([float(100 + 10 * i) for i in range(24)])
        diag, meta, fc, _ = predictor.run_series_forecast(series, steps=6, frequency="months")

        assert diag.status == "ok"
        assert diag.n_observed == 24
        assert meta.selected_model_key
        assert meta.selection_method == "rolling_origin_backtest"
        assert meta.selection_metric in ("mase", "mae")
        assert meta.interval_source in ("validation_residuals", "in_sample_residuals")
        assert len(fc) == 6

    def test_refused_series_produces_no_numbers(self):
        series = _monthly([100.0, None, None, None])
        diag, meta, fc, ci = predictor.run_series_forecast(series, steps=6, frequency="months")

        assert fc.empty, "a refused series must not emit a forecast"
        assert ci is None
        assert diag.status == "insufficient_history"
        assert diag.reason


# ══════════════════════════════════════════════════════════
# 7. Grouped forecasting — dimensions, ranking, growth
# ══════════════════════════════════════════════════════════

def _grouped_frame():
    """
    Two countries x two products. One combination (UK/B) has only a single
    observation and must therefore be refused rather than forecast.
    """
    rng = np.random.default_rng(11)
    rows = []
    dates = pd.date_range("2021-01-15", periods=24, freq="ME")
    for i, d in enumerate(dates):
        # Seeded noise keeps the fixture deterministic while making the series
        # realistically imperfect — a noiseless series has zero residuals and
        # therefore no prediction interval to assert on.
        rows.append({"d": d, "country": "US", "product": "A", "v": 1000.0 + 20 * i + rng.normal(0, 40)})
        rows.append({"d": d, "country": "US", "product": "B", "v": 500.0 + 5 * i + rng.normal(0, 20)})
        rows.append({"d": d, "country": "UK", "product": "A", "v": 300.0 + 2 * i + rng.normal(0, 10)})
    rows.append({"d": dates[0], "country": "UK", "product": "B", "v": 42.0})
    return pd.DataFrame(rows)


class TestGroupedForecasting:

    def test_group_keys_preserve_every_dimension(self):
        df = _grouped_frame()
        series_by_group = preprocessing.prepare_grouped_forecasting_data(
            df, "d", "v", ["country", "product"], frequency="months",
        )
        assert ("US", "A") in series_by_group
        assert all(isinstance(k, tuple) and len(k) == 2 for k in series_by_group)

    def _run(self, ranking_metric="sum", steps=6):
        df = _grouped_frame()
        dims = [
            {"dim_df": pd.DataFrame({"country": ["US", "UK"]}),
             "join_key_base": "country", "join_key_target": "country",
             "group_column": "country", "semantic_hint": "country"},
            {"dim_df": pd.DataFrame({"product": ["A", "B"]}),
             "join_key_base": "product", "join_key_target": "product",
             "group_column": "product", "semantic_hint": "product"},
        ]

        class _Detection:
            date_column = "d"
            target_column = "v"

        from unittest.mock import patch
        with patch("prediction.predictor.detector.detect", return_value=_Detection()):
            return predictor.predict_grouped_forecast(
                df, dimensions=dims, target_col="v", steps=steps,
                frequency="months", table_name="t", ranking_metric=ranking_metric,
            )

    def test_country_and_product_remain_addressable(self):
        result = self._run()
        assert result.dimensions == ["country", "product"]
        for entry in result.raw_forecast_results:
            assert set(entry["group_dict"]) == {"country", "product"}

    def test_insufficient_group_is_refused_with_a_reason(self):
        result = self._run()
        uk_b = next(p for p in result.raw_forecast_results
                    if p["group_dict"] == {"country": "UK", "product": "B"})

        assert uk_b["final_value"] is None, "must not be ranked as zero"
        assert uk_b["forecast"] == []
        assert uk_b["status"] != "ok"
        assert uk_b["reason"]
        assert any(e["group_dict"] == uk_b["group_dict"] for e in result.excluded_groups)

    def test_ranking_excludes_unforecastable_groups(self):
        result = self._run()
        values = [p["final_value"] for p in result.raw_forecast_results]
        ranked = [v for v in values if v is not None]

        assert ranked == sorted(ranked, reverse=True), "ranked groups sort descending"
        assert values[-1] is None, "unforecastable groups sort last, not as zero"
        assert result.best_group is not None
        assert result.count == len(ranked)

    def test_each_group_gets_its_own_model_metadata(self):
        result = self._run()
        forecast_entries = [p for p in result.raw_forecast_results if p["forecast"]]
        assert forecast_entries
        for entry in forecast_entries:
            assert entry["model"]["selected_model_key"]
            assert entry["diagnostics"]["n_observed"] >= 1

    def test_forecast_rows_keep_confidence_intervals(self):
        result = self._run()
        entry = next(p for p in result.raw_forecast_results if p["forecast"])
        assert "lower" in entry["forecast"][0] and "upper" in entry["forecast"][0]

    def test_growth_is_none_when_baseline_is_unusable(self):
        """Undefined growth is reported as undefined, never as 0 or infinity."""
        assert predictor._ranking_value(
            [{"date": "x", "value": 0.0}], [{"date": "y", "value": 10.0}], 1, "growth",
        ) is None
        assert predictor._ranking_value(
            [{"date": "x", "value": None}], [{"date": "y", "value": 10.0}], 1, "growth",
        ) is None

    def test_growth_uses_a_like_for_like_baseline(self):
        hist = [{"date": f"h{i}", "value": 100.0} for i in range(6)]
        fc = [{"date": f"f{i}", "value": 150.0} for i in range(3)]
        # baseline = last 3 observed periods = 300; forecast = 450 → +50%
        assert predictor._ranking_value(hist, fc, 3, "growth") == pytest.approx(50.0)

    def test_sum_counts_real_zeros_and_skips_missing(self):
        rows = [{"value": 10.0}, {"value": 0.0}, {"value": None}, {"value": 5.0}]
        assert predictor._sum_values(rows) == 15.0
        assert predictor._sum_values([{"value": None}]) is None


# ══════════════════════════════════════════════════════════
# 8. Boundaries: deterministic, offline, no LLM
# ══════════════════════════════════════════════════════════

class TestEngineBoundaries:

    def test_forecasting_engine_does_not_import_the_llm_service(self):
        """Numbers must come from the models, never from a language model."""
        import inspect

        for module in (forecast_selection, series_validation, preprocessing, predictor):
            source = inspect.getsource(module)
            assert "llm_service" not in source
            assert "call_llm" not in source

    def test_identical_input_yields_identical_forecast(self):
        series = _monthly([float(100 + 7 * i) for i in range(24)])
        _, _, first, _ = predictor.run_series_forecast(series, steps=6, frequency="months")
        _, _, second, _ = predictor.run_series_forecast(series, steps=6, frequency="months")
        pd.testing.assert_series_equal(first, second)
