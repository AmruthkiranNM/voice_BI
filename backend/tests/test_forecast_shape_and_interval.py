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
    assert "level line" in text
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
        assert "within 10%" in text
