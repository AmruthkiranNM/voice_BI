"""
Forecast band width, model parsimony, and the "why is it flat" explanation.

These pin down the fixes from the prediction audit on the real chocolate data:
the band was sized twice for horizon (2-5x too wide), a trend model could win
a 1% tie on two folds and draw a slope the trend test rejects, and nothing
explained a level forecast drawn next to a moving history.
"""
import numpy as np
import pandas as pd

from prediction import forecasting_models as fm
from prediction import forecast_selection as fs
from prediction.schemas import SeriesDiagnostics


def monthly(values):
    idx = pd.date_range("2021-01-31", periods=len(values), freq="ME")
    return pd.Series([float(v) for v in values], index=idx)


# ── intervals ────────────────────────────────────────────────

def test_multistep_residuals_are_not_scaled_by_sqrt_h_again():
    m = fm.NaiveForecaster().fit(monthly([10, 12, 11, 13]))
    # Errors measured 1, 2 and 3 steps ahead, each with RMS 2.
    m.set_residual_scale(np.array([2, -2, 2, -2, 2, -2.0]), steps=np.array([1, 1, 2, 2, 3, 3]))
    _, ci = m.predict(3)
    half = (ci["upper"] - ci["lower"]).values / 2
    assert np.allclose(half, 1.96 * 2.0)            # not 1.96 * 2 * sqrt(h)


def test_band_never_narrows_with_horizon():
    m = fm.NaiveForecaster().fit(monthly([10, 12, 11, 13]))
    m.set_residual_scale(np.array([5, -5, 1, -1.0]), steps=np.array([1, 1, 2, 2]))
    _, ci = m.predict(2)
    width = (ci["upper"] - ci["lower"]).values
    assert width[1] >= width[0]


def test_band_grows_only_beyond_validated_horizon():
    m = fm.NaiveForecaster().fit(monthly([10, 12, 11, 13]))
    m.set_residual_scale(np.array([2, -2, 2, -2.0]), steps=np.array([1, 1, 2, 2]))
    _, ci = m.predict(8)
    half = (ci["upper"] - ci["lower"]).values / 2
    assert np.isclose(half[1], 1.96 * 2.0)
    assert np.isclose(half[7], 1.96 * 2.0 * np.sqrt(8 / 2))


def test_rms_keeps_bias_in_width():
    m = fm.NaiveForecaster().fit(monthly([10, 12, 11, 13]))
    # Always 3 too low: std is 0, but the forecast is still 3 off.
    m.set_residual_scale(np.array([3, 3, 3.0]), steps=np.array([1, 1, 1]))
    _, ci = m.predict(1)
    assert np.isclose((ci["upper"] - ci["lower"]).iloc[0] / 2, 1.96 * 3.0)


def test_one_step_residuals_keep_sqrt_h_growth():
    m = fm.NaiveForecaster().fit(monthly([10, 12, 11, 13]))
    m.set_residual_scale(np.array([2, -2, 2, -2.0]))          # no steps: one-step errors
    _, ci = m.predict(4)
    half = (ci["upper"] - ci["lower"]).values / 2
    assert np.allclose(half, 1.96 * 2.0 * np.sqrt(np.arange(1, 5)))


def test_residuals_carry_their_horizon():
    series = monthly([100, 120, 90, 130, 95, 125, 105, 115, 98, 122])
    folds = fs.build_folds(series, horizon=3)
    _, residuals = fs._score_candidate(fm.NaiveForecaster(), fs.build_fold_data(series, folds))
    steps = {s for s, _ in residuals}
    assert steps <= {1, 2, 3} and 1 in steps


# ── parsimony and explanation ────────────────────────────────

NOISY = [2957192, 3036726, 3190775, 2885253, 2794491, 2626162, 2452835, 2985276,
         2361933, 2774107, 2963555, 2940049, 5280919, 2001643, 2310630]   # real monthly totals


def _diag(n, sp=12):
    return SeriesDiagnostics(status="ok", n_periods=n, n_observed=n, seasonal_periods=sp,
                             seasonality_supported=n >= sp, seasonal_estimate_supported=n >= 2 * sp,
                             requested_frequency="months")


def test_no_trend_series_gets_a_flat_model():
    series = monthly(NOISY)
    for h in (6, 12):
        _, meta = fs.select_and_fit(series, _diag(len(series)), h)
        assert meta.selected_model_key in fs._FLAT_MODEL_KEYS, (h, meta.selected_model_key)
        assert meta.shape == "flat"


def test_trending_series_keeps_a_trend_model():
    series = monthly([100 + 10 * i + (3 if i % 2 else -3) for i in range(18)])
    _, meta = fs.select_and_fit(series, _diag(len(series)), 6)
    assert meta.shape == "trend"


def test_explanation_states_measured_reasons():
    series = monthly(NOISY)
    _, meta = fs.select_and_fit(series, _diag(len(series)), 6)
    text = " ".join(meta.shape_explanation)
    assert "line is level because" in text and "persistence 0.00" in text
    assert "24 months" in text and "has 15" in text            # seasonality needs 2 cycles
    assert "620,112" in text                                     # the measured typical swing
    assert "95%" in text
    assert meta.shape_facts["trend_significant"] is False


def test_explanation_never_claims_lowest_error_for_a_tie_break():
    series = monthly(NOISY)
    _, meta = fs.select_and_fit(series, _diag(len(series)), 6)
    best = min((c for c in meta.candidates if c.eligible and c.mase is not None), key=lambda c: c.mase)
    text = " ".join(meta.shape_explanation)
    if best.model_key != meta.selected_model_key:
        assert "had the lowest error" not in text
        if meta.selected_model_key == "level_combination":
            assert "averaging level models forecasts unseen months more accurately" in text
        else:
            assert "within 10%" in text


def test_noisy_series_without_trend_uses_the_combination():
    series = monthly(NOISY)
    _, meta = fs.select_and_fit(series, _diag(len(series)), 6)
    assert meta.selected_model_key == "level_combination"
    assert meta.selection_method == "level_combination_rule"
    assert meta.interval_source == "validation_residuals"     # band from its own backtest


def test_holdout_check_and_pattern_reference_are_recorded():
    series = monthly(NOISY)
    _, meta = fs.select_and_fit(series, _diag(len(series)), 6)
    assert len(meta.holdout) == 5                               # min(h, n // 3)
    assert {"period", "actual", "predicted"} <= set(meta.holdout[0])
    assert meta.holdout[-1]["actual"] == NOISY[-1]              # real values, not adjusted
    assert meta.pattern_reference is not None
    assert meta.pattern_reference.model_key == "pattern_repeat"
    assert all(c.model_key != "pattern_repeat" for c in meta.candidates)   # never selectable


def test_holdout_sentence_reports_which_side_actuals_fell():
    rising = monthly([10, 11, 9, 10, 12, 11, 10, 9, 11, 10, 18, 19, 21, 20, 22])
    _, meta = fs.select_and_fit(rising, _diag(len(rising)), 6)
    text = " ".join(meta.shape_explanation)
    if all(r["actual"] > r["predicted"] for r in meta.holdout):
        assert "came in above it" in text
        assert "middle" not in text


def test_persistent_series_forecast_moves_back_toward_its_mean():
    # A series whose dips carry over (APAC-like): recent months below normal.
    persistent = monthly([100, 104, 108, 110, 107, 103, 99, 96, 95, 97, 101, 104, 100, 92, 88])
    model = fm.LevelCombinationForecaster().fit(persistent)
    fc = model.predict(6)[0].values
    assert model.phi > 0.05
    assert np.all(np.diff(fc) > 0)                       # changes every month, upward
    assert fc[-1] < persistent.mean()                    # approaches, never overshoots, the mean


def test_no_persistence_means_no_invented_path():
    alternating = monthly([100, 140, 95, 150, 90, 145, 100, 150, 95, 140])
    model = fm.LevelCombinationForecaster().fit(alternating)
    assert model.phi == 0.0                               # negative carry-over is clipped to 0
    assert np.ptp(model.predict(6)[0].values) == 0        # level, not a made-up wiggle


def test_converging_explanation_quotes_the_path():
    persistent = monthly([100, 104, 108, 110, 107, 103, 99, 96, 95, 97, 101, 104, 100, 92, 88])
    _, meta = fs.select_and_fit(persistent, _diag(len(persistent)), 6)
    if meta.selected_model_key == "level_combination" and meta.shape == "converging":
        text = " ".join(meta.shape_explanation)
        assert "changes month by month" in text and "persistence" in text


def test_trend_test_rejects_a_few_noisy_points():
    # Ratio passes, but 6 noisy points are not a statistically real slope.
    assert not fs._series_has_significant_trend(monthly([10, 30, 12, 34, 15, 33]))
    assert fs._series_has_significant_trend(monthly([10, 12, 14, 16, 18, 20, 22, 24]))
