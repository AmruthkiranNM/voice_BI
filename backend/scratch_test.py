import sqlite3, pandas as pd
from prediction.predictor import predict_grouped_forecast
import logging

logging.basicConfig(level=logging.ERROR)

conn = sqlite3.connect('data/business_1.db')
df = pd.read_sql('SELECT saledate, sales.pid, amount, product, category FROM sales JOIN products ON sales.pid = products.pid', conn)

res = predict_grouped_forecast(
    df, 
    dimensions=[{'group_column': 'product', 'semantic_hint': 'product', 'requires_join': False}], 
    target_col='amount', 
    steps=12, 
    frequency='months'
)

for r in res.raw_forecast_results:
    if r['status'] == 'ok' and r['group'] == 'Drinking Coco':
        print(f"Product: {r['group']}")
        meta = r['model']
        print(f"Selected: {meta['selected_model_key']}")
        for c in meta['candidates']:
            print(f"  Candidate: {c['model_key']} Eligible: {c['eligible']} MASE: {c['mase']} (Folds: {c['n_folds']})")


for r in res.raw_forecast_results:
    if r['status'] == 'ok' and r['forecast']:
        print(f"Product: {r['group']}")
        print(f"Model: {r['model'].get('selected_model_label')} (Method: {r['model'].get('selection_method')})")
        print(f"Beats naive: {r['model'].get('beats_naive')}, MASE: {r['model'].get('selected_score')}")
        fcst = [f['value'] for f in r['forecast']]
        print(f"Forecast length: {len(fcst)}")
        print(f"Forecast: {fcst}")
        print('-'*40)
