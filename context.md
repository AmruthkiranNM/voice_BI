# Project Context — VOICE BI

Running record of what has changed in the system and why. Read this before
changing the backend agents or the prediction engine. Newest changes first.

## Ground rules (apply to every change)

- The LLM never computes numbers. Rankings, differences, percentages and
  forecasts are computed in code; the LLM only words them.
- Missing data is never zero. A missing period/value is reported as "no data".
- No question-specific or dataset-specific logic. Everything must stay generic.
- No artificial fluctuation, noise or fake intervals in forecasts. The chart
  draws backend values exactly.
- Don't weaken tests to make them pass; fix the production code.

---

## Prediction engine and forecast chart

**Why the forecast line is flat (the guide's question at the last demo).**
Measured on the chocolate data (`audit/analyze_monthly_structure.py`):
- Monthly movement is driven by the *number* of sales per month (corr +0.99);
  value per sale varies only 2.9%. Calendar/weekday effects explain nothing
  (corr −0.09).
- Trend: +2,306/month vs a typical month-to-month swing of 620,112 → no trend.
- Seasonality needs 2 full cycles (24 months); the data has 15.
So the swings are irregular and the best point forecast is the typical level.
The uncertainty is shown as the 95% band, not as wiggles in the line.

Changes:
- **Prediction band fixed** (`prediction/forecasting_models.py`). It was 2–5×
  too wide: multi-step validation errors were scaled by √h a second time. Now
  each horizon uses the RMS of the validation errors made at that horizon,
  never narrowing; √h growth only beyond the validated horizon.
- **Parsimony rule** (`prediction/forecast_selection.py`). If the series has no
  significant trend and a flat model scores within 10% of a trend model, the
  flat model wins (mirror of the existing trend-promotion rule).
- **"Why does the forecast look like this?"** Engine computes `shape`,
  `shape_facts`, `shape_explanation` (measured trend vs swing, history needed
  for seasonality, models tested, what the band means). Shown under every
  forecast chart.
- **Chart** (`frontend/src/components/PredictionPanel.jsx`): forecast and band
  start from the last actual point; band is called "95% likely range"
  everywhere; reliability tile uses the backend's four states (Validated /
  Weak / Baseline only / Not validated).
- Forecasts are grouped only when the question asks for a breakdown
  (by / per / each / which / top …); "forecast total revenue" stays a total.
- "Estimate … in 2023" (a year after the data ends) routes to forecasting.
- An unreadable cached model (`.pkl` from another numpy/sklearn version) is
  retrained instead of crashing.
- Names not in the data (e.g. "Germany") are reported instead of silently
  forecasting the overall total (`services/entity_check.py`).

## Descriptive answers (SQL path)

- **Code-computed facts** (`services/result_facts.py`): rankings, period-over-
  period changes, overall change and side-by-side comparisons are computed and
  given to the LLM as authoritative facts. Fixed "Australia is highest" (it was
  New Zealand) and wrong percentages.
- **Follow-ups**: "which one is the lowest/highest" is answered directly from
  the shown rows; years outside the data's range are reported plainly;
  "how reliable is this?" after a forecast is answered from the engine's
  evidence; an empty result is retried once uncached.
- **Name filters** (`agents/sql_agent.py`): product/salesperson names (columns
  with up to 500 values) are detected as exact phrases. Words inside a matched
  name don't also become a category filter ("Milk Bars" ≠ category Bars).
  Several names in one column become `IN (...)`.
- **Honest refusals** (`agents/orchestrator.py`):
  - measure not recorded → "no information on X" (constant columns like
    `0.0 AS churn_rate` and `NOT_IN_DATA` from the LLM are both caught);
  - delete/update/insert requests → read-only message;
  - gibberish (`WHERE 0`) → "couldn't understand".
- SQLite integer division fixed (`SUM(x)/COUNT(*)` → decimal).
- "In March" (no year) means every March, not just the latest.
- "No records" message uses only the selected tables' date range.

## Frontend

- Follow-up chat clears when a new main question is asked (`App.jsx`).
- Descriptive chart tooltips: no overlap with bars, no meaningless "100%"
  share, en-US number grouping, y-axis title not clipped.

---

## Testing

- Backend: `cd backend && venv\Scripts\python.exe -m pytest tests -q`
  (475 passing). Afterwards run `git checkout -- backend/data/ml_models/` —
  tests regenerate those cached `.pkl` files.
- Frontend needs Node ≥ 20 (`npm run dev`); Node 18 cannot run Vite.
- The Groq free tier has a 200k tokens/day limit; long manual test runs can
  exhaust it.
- Restart the backend before manual testing — answers are cached.

## Known open items

- "Which team will sell the most?" asks whether to use revenue or boxes.
- "Which customers will buy X?" should refuse up front (no customer-level
  outcome in the sales data).
- Regression output labels rows by ID (e.g. "SP18").
