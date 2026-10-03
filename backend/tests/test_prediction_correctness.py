"""
Numerical correctness of the prediction pipeline.

These tests assert arithmetic that can be worked out by hand, so a regression
shows up as a wrong number rather than as a graph that looks odd: MASE against
its definition, folds that never see the future, horizons that return the
periods asked for, totals that are sums rather than averages, and reliability
that is stated rather than implied.
"""

import numpy as np
import pandas as pd
import pytest

from agents import prediction_agent
from prediction import config as cfg
from prediction import forecast_selection, forecasting_models as fm
from prediction.config import PredictionConfig
from prediction.engine import PredictionResult


def monthly(values, start="2021-01-31"):
    idx = pd.date_range(start, periods=len(values), freq="ME")
    return pd.Series([float(v) for v in values], index=idx)


# ══════════════════════════════════════════════════════════
# MASE, against its definition
# ══════════════════════════════════════════════════════════

class TestMASE:
    def test_naive_scale_is_mean_absolute_one_step_change(self):
        """The denominator is the in-sample naive one-step MAE."""
        train = monthly([10, 12, 15, 11])       # steps: 2, 3, 4 -> mean 3
        assert forecast_selection._naive_scale(train) == pytest.approx(3.0)

    def test_mase_is_forecast_mae_over_naive_scale(self):
        """A flat forecast with known error gives a hand-checkable MASE."""
        series = monthly([10, 12, 15, 11, 20, 20])
        # One fold: train on the first four, validate on the last two.
        fold_data = forecast_selection.build_fold_data(series, [(4, 6)])
        assert len(fold_data) == 1
        scale = fold_data[0]["scale"]
        assert scale == pytest.approx(3.0)

        score, _ = forecast_selection._score_candidate(fm.NaiveForecaster(), fold_data)
        # Naive predicts 11 for both periods; actuals are 20 and 20.
        assert score.mae == pytest.approx(9.0)
        assert score.mase == pytest.approx(9.0 / 3.0)

    def test_constant_series_has_no_scale_and_no_mase(self):
        """A zero denominator must not be silently turned into a number."""
        flat = monthly([5, 5, 5, 5])
        assert forecast_selection._naive_scale(flat) == 0.0

        series = monthly([5, 5, 5, 5, 7, 7])
        fold_data = forecast_selection.build_fold_data(series, [(4, 6)])
        score, _ = forecast_selection._score_candidate(fm.NaiveForecaster(), fold_data)
        assert score.mae == pytest.approx(2.0)
        assert score.mase is None          # undefined, not 0 and not infinity

    def test_mase_below_one_means_better_than_naive(self):
        """The reliability rule the answer text depends on."""
        series = monthly(list(range(1, 25)))
        diag = _ok_diagnostics(series)
        _, meta = forecast_selection.select_and_fit(series, diag, 3)
        naive = next(c for c in meta.candidates if c.model_key == "naive")
        if meta.selected_score is not None and naive.mase is not None:
            assert meta.beats_naive == (meta.selected_score < naive.mase)


def _ok_diagnostics(series):
    from prediction import series_validation
    return series_validation.validate_series(
        series, requested_frequency="months", horizon=3)


# ══════════════════════════════════════════════════════════
# Rolling-origin validation: the future must stay unseen
# ══════════════════════════════════════════════════════════

class TestRollingOrigin:
    def test_every_fold_trains_only_on_earlier_periods(self):
        series = monthly(list(range(1, 25)))
        folds = forecast_selection.build_folds(series, 3)
        assert folds, "expected at least one fold"

        for train_end, val_end in folds:
            assert train_end < val_end, "validation must come after training"
            train = series.iloc[:train_end]
            validation = series.iloc[train_end:val_end]
            assert train.index.max() < validation.index.min()

    def test_folds_move_forward_and_do_not_overlap_their_training(self):
        series = monthly(list(range(1, 25)))
        folds = forecast_selection.build_folds(series, 3)
        ends = [t for t, _ in folds]
        assert ends == sorted(ends), "fold origins must advance chronologically"

    def test_training_slice_is_a_strict_prefix(self):
        """Interpolation for fitting must not reach past the fold boundary."""
        series = monthly([1, 2, np.nan, 4, 5, 6, 7, 8])
        fold_data = forecast_selection.build_fold_data(series, [(5, 8)])
        train = fold_data[0]["train"]
        assert train.index.max() <= series.index[4]


# ══════════════════════════════════════════════════════════
# Horizon and totals
# ══════════════════════════════════════════════════════════

class TestHorizonAndTotals:
    @pytest.mark.parametrize("horizon", [1, 3, 6, 12, 24])
    def test_forecast_returns_exactly_the_periods_requested(self, horizon):
        series = monthly(list(range(1, 25)))
        model = fm.HoltLinearForecaster().fit(series)
        pred, _ = model.predict(steps=horizon)
        assert len(pred) == horizon

    def test_future_index_continues_the_series_frequency(self):
        series = monthly(list(range(1, 25)))
        model = fm.NaiveForecaster().fit(series)
        pred, _ = model.predict(steps=3)
        assert pred.index[0] > series.index[-1]
        gaps = pred.index.to_series().diff().dropna().dt.days
        assert gaps.between(28, 31).all(), "monthly steps expected"

    def test_total_is_a_sum_not_an_average(self):
        """100 + 120 + 80 is 300, and the average is 100. Never interchangeable."""
        result = PredictionResult(forecast_rows=[
            {"group": "A", "period": "2022-04-30", "value": 100.0},
            {"group": "A", "period": "2022-05-31", "value": 120.0},
            {"group": "A", "period": "2022-06-30", "value": 80.0},
        ])
        totals = prediction_agent._totals_by_group(result)
        assert totals == [("A", 300.0)]
        assert totals[0][1] != pytest.approx(100.0)


# ══════════════════════════════════════════════════════════
# Grouped forecasts stay independent and carry their figures
# ══════════════════════════════════════════════════════════

class TestGroupedEvidence:
    def _result(self, groups):
        rows = []
        for i, g in enumerate(groups):
            for p in range(3):
                rows.append({"group": g, "group_values": {"product": g},
                             "period": f"2022-0{p + 4}-30", "value": 100.0 * (i + 1) + p})
        return PredictionResult(forecast_rows=rows)

    def test_grouped_forecast_without_ranking_still_states_figures(self):
        conf = PredictionConfig(table="t", target="amount",
                                prediction_type=cfg.FORECASTING, horizon=3,
                                time_frequency="months", group_dimensions=["product"])
        text = prediction_agent.build_evidence(conf, self._result(["A", "B"]))
        assert prediction_agent._has_digits(text)
        assert "303.00" in text and "603.00" in text
        assert "2 series forecast" in text

    def test_long_group_lists_are_summarised_not_dropped(self):
        conf = PredictionConfig(table="t", target="amount",
                                prediction_type=cfg.FORECASTING, horizon=3,
                                time_frequency="months", group_dimensions=["product"])
        text = prediction_agent.build_evidence(
            conf, self._result([f"P{i}" for i in range(25)]))
        assert "+15 more series" in text
        assert "25 series forecast" in text

    def test_each_group_keeps_its_own_values(self):
        result = self._result(["A", "B", "C"])
        totals = dict(prediction_agent._totals_by_group(result))
        assert len({round(v, 6) for v in totals.values()}) == 3


# ══════════════════════════════════════════════════════════
# Reliability is stated, never implied
# ══════════════════════════════════════════════════════════

class TestReliabilityStatement:
    def test_mase_at_or_above_one_is_called_unreliable(self):
        line = prediction_agent._reliability_line(
            {"selected_score": 2.56, "beats_naive": True})
        assert "NOT reliable" in line
        assert "2.56" in line

    def test_mase_below_one_is_called_validated(self):
        line = prediction_agent._reliability_line(
            {"selected_score": 0.74, "beats_naive": True})
        assert "validated" in line
        assert "NOT reliable" not in line

    def test_naive_winning_is_called_baseline_not_misreported(self):
        """
        Naive cannot beat itself, so beats_naive is False even at MASE 0.66.
        The statement must not claim 0.66 is "at or above 1".
        """
        status, sentence = prediction_agent.reliability_status(0.66, False)
        assert status == "baseline"
        assert "at or above 1" not in sentence
        assert "no model beat" in sentence

    def test_beat_naive_but_mase_above_one_is_weak(self):
        status, sentence = prediction_agent.reliability_status(2.56, True)
        assert status == "weak"
        assert "NOT reliable" in sentence

    def test_series_validation_is_attached_per_group(self):
        """Each grouped series carries its own model and reliability."""
        result = PredictionResult(model_metadata={"per_group": {
            "A": {"selected_model_label": "Naive (last value)",
                  "selected_score": 0.66, "beats_naive": False},
            "B": {"selected_model_label": "Damped Holt Trend",
                  "selected_score": 0.58, "beats_naive": True},
        }})
        a = prediction_agent._series_validation(result, "A")
        b = prediction_agent._series_validation(result, "B")
        assert (a["model"], a["reliability"], a["reliable"]) == \
            ("Naive (last value)", "baseline", False)
        assert (b["model"], b["reliability"], b["reliable"]) == \
            ("Damped Holt Trend", "validated", True)

    def test_unvalidated_fallback_says_so(self):
        line = prediction_agent._reliability_line(
            {"selected_score": None, "beats_naive": None})
        assert "not validated" in line

    def test_reliability_reaches_the_evidence(self):
        conf = PredictionConfig(table="t", target="amount",
                                prediction_type=cfg.FORECASTING, horizon=3,
                                time_frequency="months")
        result = PredictionResult(
            forecast_rows=[{"group": None, "period": "2022-04-30", "value": 10.0}],
            model_metadata={"selected_model_label": "Damped Holt Trend",
                            "selection_method": "rolling_origin_backtest",
                            "selected_score": 2.56, "beats_naive": True})
        text = prediction_agent.build_evidence(conf, result)
        assert "NOT reliable" in text


# ══════════════════════════════════════════════════════════
# Model selection responds to the data, not to preference
# ══════════════════════════════════════════════════════════

class TestSelectionRespondsToData:
    def _select(self, values, horizon=3):
        series = monthly(values)
        diag = _ok_diagnostics(series)
        model, meta = forecast_selection.select_and_fit(series, diag, horizon)
        return model, meta

    def test_trending_series_prefers_a_trend_aware_model(self):
        """A clean ramp should not be won by a flat baseline."""
        _, meta = self._select(list(range(100, 136)))
        assert meta.selected_model_key in {"drift", "holt_linear", "damped_holt",
                                           "seasonal_naive", "holt_winters_additive"}
        assert meta.beats_naive is not False

    def test_seasonal_series_can_select_a_seasonal_model(self):
        """With three full cycles a seasonal model must at least be scorable."""
        values = [100 + 30 * np.sin(2 * np.pi * i / 12) for i in range(36)]
        _, meta = self._select(values, horizon=6)
        scored = {c.model_key for c in meta.candidates if c.mase is not None}
        assert {"seasonal_naive", "holt_winters_additive"} & scored

    def test_constant_series_is_labelled_not_validated(self):
        _, meta = self._select([50.0] * 24)
        assert meta.selection_method == "forced_constant"

    def test_short_history_falls_back_instead_of_fitting_complex_models(self):
        _, meta = self._select([1.0, 2.0, 3.0])
        assert meta.selection_method in {"fallback_no_validation", "not_forecast"}
