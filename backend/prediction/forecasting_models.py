"""
Prediction Package — Forecasting Models

Wrappers for time-series forecasting models to conform to a standard interface.
"""

import logging
from typing import Any
import pandas as pd
import numpy as np

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

logger = logging.getLogger(__name__)


class ForecastingModelWrapper:
    """Standardized interface for forecasting models."""
    
    def __init__(self, model_name: str = "Exponential Smoothing"):
        self.model_name = model_name
        self.model = None
        self.fitted_model = None
        self.history_index = None

    def fit(self, y: pd.Series):
        self.history_index = y.index
        if HAS_STATSMODELS:
            # Simple heuristic for trend and seasonality
            # For robustness on varying datasets, we'll try trend='add'
            # If there's negative data, 'add' is safer than 'mul'
            try:
                self.model = ExponentialSmoothing(
                    y, 
                    trend="add", 
                    seasonal=None, 
                    initialization_method="estimated"
                )
                self.fitted_model = self.model.fit()
            except Exception as e:
                logger.warning(f"ExponentialSmoothing failed with trend='add': {e}. Trying simplest config.")
                self.model = ExponentialSmoothing(y, initialization_method="estimated")
                self.fitted_model = self.model.fit()
        else:
            raise ImportError("statsmodels is required for forecasting.")
        return self

    def predict(self, steps: int = 12) -> tuple[pd.Series, pd.DataFrame]:
        """
        Returns:
            forecast_mean: Series of point forecasts.
            confidence_intervals: DataFrame with 'lower' and 'upper' bounds (if supported).
        """
        if not self.fitted_model:
            raise ValueError("Model must be fitted before predicting.")

        if HAS_STATSMODELS:
            # Statsmodels ExponentialSmoothing doesn't provide native prediction intervals out of the box easily 
            # without simulating. We will approximate confidence intervals or just return None.
            # forecast() returns point forecasts.
            forecast_mean = self.fitted_model.forecast(steps)
            
            # Approximate standard error of the residuals for a rough confidence interval (e.g. 95%)
            resid = self.fitted_model.resid
            std_err = np.std(resid) if len(resid) > 1 else 0
            
            # Growing uncertainty over time
            z_score = 1.96
            uncertainty = z_score * std_err * np.sqrt(np.arange(1, steps + 1))
            
            lower_bound = forecast_mean - uncertainty
            upper_bound = forecast_mean + uncertainty
            
            # Prevent negative lower bounds if historical data is strictly positive
            # Though this is a heuristic, it is helpful for revenue/sales
            ci_df = pd.DataFrame({
                "lower": lower_bound,
                "upper": upper_bound
            }, index=forecast_mean.index)
            
            return forecast_mean, ci_df
        else:
            raise NotImplementedError()
