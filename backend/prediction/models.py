"""
Prediction Package — Models

Defines model configurations for binary classification and regression.
"""

import logging

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression

from prediction import forecasting_models
from prediction.forecasting_models import ForecastingModelWrapper


logger = logging.getLogger(__name__)


# ── Model Registry ──
MODEL_REGISTRY: dict[str, dict] = {
    # Classification Models
    "logistic_regression": {
        "label": "Logistic Regression",
        "problem_type": "classification",
        "factory": lambda: LogisticRegression(
            random_state=42,
            max_iter=1000,
            class_weight="balanced",
        ),
    },
    "random_forest_classifier": {
        "label": "Random Forest Classifier",
        "problem_type": "classification",
        "factory": lambda: RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced",
        ),
    },
    "gradient_boosting_classifier": {
        "label": "Gradient Boosting Classifier",
        "problem_type": "classification",
        "factory": lambda: GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=3,
            random_state=42,
        ),
    },

    # Regression Models
    "linear_regression": {
        "label": "Linear Regression",
        "problem_type": "regression",
        "factory": lambda: LinearRegression(),
    },
    "random_forest_regressor": {
        "label": "Random Forest Regressor",
        "problem_type": "regression",
        "factory": lambda: RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1,
        ),
    },
    "gradient_boosting_regressor": {
        "label": "Gradient Boosting Regressor",
        "problem_type": "regression",
        "factory": lambda: GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=3,
            random_state=42,
        ),
    },

    # ── Forecasting Models ──
    # These are candidates, not defaults: forecast_selection.select_and_fit
    # backtests them per series and picks a winner on validation evidence.
    # The trivial baselines are deliberately included — a model that cannot
    # beat "same as last period" has not earned the user's trust.
    "naive": {
        "label": "Naive (last value)",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.NaiveForecaster(),
    },
    "seasonal_naive": {
        "label": "Seasonal Naive",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.SeasonalNaiveForecaster(),
    },
    "drift": {
        "label": "Drift",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.DriftForecaster(),
    },
    "moving_average": {
        "label": "Moving Average",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.MovingAverageForecaster(),
    },
    "simple_exp_smoothing": {
        "label": "Simple Exponential Smoothing",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.SimpleExpSmoothingForecaster(),
    },
    "holt_linear": {
        "label": "Holt Linear Trend",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.HoltLinearForecaster(),
    },
    "damped_holt": {
        "label": "Damped Holt Trend",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.DampedHoltForecaster(),
    },
    "holt_winters_additive": {
        "label": "Holt-Winters (additive seasonal)",
        "problem_type": "forecasting",
        "factory": lambda: forecasting_models.HoltWintersForecaster(),
    },
    "exponential_smoothing": {
        "label": "Exponential Smoothing",
        "problem_type": "forecasting",
        "factory": lambda: ForecastingModelWrapper(),
    },
}


# Keep original keys working if possible, but the original ones were "random_forest"
# We'll map the old names in the registry to avoid breaking classification tests if they hardcode keys
MODEL_REGISTRY["random_forest"] = MODEL_REGISTRY["random_forest_classifier"]
MODEL_REGISTRY["gradient_boosting"] = MODEL_REGISTRY["gradient_boosting_classifier"]

DEFAULT_CLASSIFICATION_KEY = "random_forest_classifier"
DEFAULT_REGRESSION_KEY = "random_forest_regressor"
DEFAULT_FORECASTING_KEY = "exponential_smoothing"

def create_model(key: str | None = None, problem_type: str = "classification"):
    """
    Instantiate a fresh (un-fitted) model from the registry.
    """
    if not key:
        if problem_type == "classification":
            key = DEFAULT_CLASSIFICATION_KEY
        elif problem_type == "regression":
            key = DEFAULT_REGRESSION_KEY
        else:
            key = DEFAULT_FORECASTING_KEY
        
    entry = MODEL_REGISTRY.get(key)
    if entry is None:
        raise ValueError(
            f"Unknown model key '{key}'. Available: {list(MODEL_REGISTRY.keys())}"
        )
    model = entry["factory"]()
    logger.info("[Models] Created model: %s (%s)", entry["label"], key)
    return model


def get_model_label(key: str | None = None, problem_type: str = "classification") -> str:
    """Return the human-readable label for a model key."""
    if not key:
        if problem_type == "classification":
            key = DEFAULT_CLASSIFICATION_KEY
        elif problem_type == "regression":
            key = DEFAULT_REGRESSION_KEY
        else:
            key = DEFAULT_FORECASTING_KEY
    entry = MODEL_REGISTRY.get(key)
    return entry["label"] if entry else key
