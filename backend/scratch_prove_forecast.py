import logging
import json
import numpy as np
import pandas as pd
from agents.prediction_agent import run
from prediction import forecasting_models

raw_outputs = {}

original_point_forecast = forecasting_models.BaseForecaster._point_forecast
def hooked_point_forecast(self, steps):
    out = self._real_point_forecast(steps)
    if not hasattr(self, 'group_id'):
        self.group_id = 'unknown'
    raw_outputs[self.group_id] = out.tolist()
    return out

for cls in forecasting_models.BaseForecaster.__subclasses__():
    if not hasattr(cls, '_real_point_forecast'):
        cls._real_point_forecast = cls._point_forecast
        cls._point_forecast = hooked_point_forecast

original_fit = forecasting_models.BaseForecaster._fit
def hooked_fit(self, y):
    self.group_id = y.name if hasattr(y, 'name') and y.name else 'unknown'
    return self._real_fit(y)

for cls in forecasting_models.BaseForecaster.__subclasses__():
    if not hasattr(cls, '_real_fit'):
        cls._real_fit = cls._fit
        cls._fit = hooked_fit

print("\n===============================")
print("QUERY: Forecast revenue by region for the next 12 months.")
print("===============================\n")
raw_outputs.clear()
res = run("Forecast revenue by region for the next 12 months.", table_names=['sales'])
result = res['result']

for r in result['prediction']['model_metadata'].get('per_group', {}):
    if r == 'Americas':
        print(f"REGION: {r}")
        print(f"MODEL: {result['prediction']['model_metadata']['per_group'][r]['selected_model_label']}")
        
        hist = [x for x in result['prediction']['historical_rows'] if x.get('group') == r]
        fc = [x for x in result['prediction']['forecast_rows'] if x.get('group') == r]
        
        print("\nHISTORICAL SERIES (LAST 3):")
        for h in hist[-3:]:
            print(f"{h['period']} -> {h['value']}")
            
        print("\nRAW MODEL OUTPUT (from point_forecast):")
        # Find the group id in raw_outputs (might be named by the region)
        # pandas series name is usually a tuple like ('amount', 'Americas') or just 'Americas'
        for k, v in raw_outputs.items():
            if 'Americas' in str(k):
                for val in v:
                    print(val)
            
        print("\nAPI FORECAST POINTS:")
        for f in fc:
            print(f"{f['period']} -> {f['value']}")
            
        agg = [x for x in result['prediction']['aggregated_rows'] if x.get('group') == r]
        print("\nTOTAL SUM:")
        print(agg[0]['value'] if agg else 'N/A')
        print(f"SUM OF POINTS: {sum(f['value'] for f in fc)}")
