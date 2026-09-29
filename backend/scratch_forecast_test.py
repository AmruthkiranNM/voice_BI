import pandas as pd
import numpy as np
from prediction.forecasting_models import MovingAverageForecaster, DriftForecaster
from prediction.engine import PredictionConfig, PredictionResult

print("=== DIRECT MODEL OUTPUT ===")
y = pd.Series([100, 120, 90, 150, 110, 180, 130, 200, 170, 250, 210, 280], 
              index=pd.date_range("2023-01-01", periods=12, freq="M"))
model = DriftForecaster()
model._fit(y)
fc = model._point_forecast(4)
print("Forecast points:", fc.tolist())
print("Total:", sum(fc))
print("Total / 4:", sum(fc)/4)

print("\n=== ENGINE AGGREGATION ===")
res = PredictionResult()
res.forecast_rows = [
    {"period": "A", "value": 100},
    {"period": "B", "value": 120},
    {"period": "C", "value": 140},
    {"period": "D", "value": 160},
]
from prediction.engine import _sum
total = _sum([r["value"] for r in res.forecast_rows])
print("Sum derived from rows:", total)
