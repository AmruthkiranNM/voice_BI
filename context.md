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

## Forecasting pipeline redesign (evidence-based)

Benchmarks: `audit/benchmark_forecasters.py`, `audit/benchmark_pipeline_designs.py`
(every method predicts months it has not seen; 26 series x several origins).

- **Finding 1 — "wiggly" forecasts are less accurate.** Repeating the last 6
  months' shape (MASE 1.60), gradient boosting on lags (1.49) and a straight
  trend (1.73) all lost to level forecasts (mean 1.34). In the live backtest,
  the level forecast beats "repeat recent ups and downs" on 24/26 series.
- **Finding 2 — selecting one model per series was the worst design** (1.60):
  with 2–3 tiny validation windows the "winner" is mostly noise.
- **Change:** when a series has no significant trend and too little history
  for seasonality, the forecast is an equal-weight **combination of level
  models** (mean, SES, 3-month average, last value) —
  `LevelCombinationForecaster`. Trending or seasonal series keep backtested
  selection (synthetic trend/season tests still pass).
- **Trend test** now also needs a slope t-test at 5% (6–9 noisy months used
  to pass the ratio alone and trigger false trends).
- Result: pipeline error 1.60 → 1.38 (14% better), best median of all methods.
- **Mean reversion** (`audit/benchmark_mean_reversion.py`): the combination
  is half the flat level, half an AR(1) path that starts at the recent level
  and closes the gap to the long-run mean by the series' measured
  persistence (phi = lag-1 autocorrelation, clipped to [0, 0.95]) each
  month. Slightly more accurate (1.810 → 1.797) and the forecast now changes
  month to month where the data has persistence: APAC 1.293M → 1.318M,
  Americas 816K → 844K, Europe 391K → 416K. Series with persistence 0.00
  (total revenue, Orange Choco) stay level, and the explanation says why.
- **Chart evidence for the guide:** grey dotted "Tested on past months" line —
  the method re-fitted without the last 5 known months, predicting them —
  plus explanation sentences quoting: the trend models' score, the
  "repeat ups and downs" score, and on which side the real months fell.

## "Which month next year will have the highest sales?"

- **Bucket vs span:** `time_resolution.granularity_from_question` reads bucket
  words ("which month", "monthly", "per quarter", "each week") separately
  from the horizon ("next year"). Previously "next year" became the bucket
  and the engine forecast 4 quarters, so "which month" was unanswerable.
- **Ranking periods:** new `OP_RANK_PERIODS` (`engine.rank_periods`) ranks the
  forecast *periods* (summed across groups; no fake summed range), with the
  leader's 95% range, the runner-up, and whether the lead is within the
  forecast uncertainty. Direction from highest/lowest words.
- The reply for period rankings is built only from computed sentences — the
  LLM was seen contradicting the engine ("Q1 2006 lowest" vs computed Q2 2005).
- An ungrouped forecast no longer prints a group ranking ("None: 722,052").
- Frontend: en-US number grouping everywhere; "Tested on past periods".

## Top-N follow-ups ("will the top 5 be the same next 6 months?")

- The follow-up keeps the user's N (inherited from "top 5" in the previous
  question); it used to fall back to top 3.
- Answer = yes/no, current vs forecast top N, a LIKE-FOR-LIKE table (last 6
  months actual vs next 6 forecast — the old answer compared a 15-month total
  with a 6-month total), and one factual reason per product that moved
  (forecast vs usual level, latest months, what its model does with them).
  The reasons are appended by code so the LLM can't drop them.
- **One-off spike adjustment** (`forecast_selection.adjust_isolated_spikes`):
  an isolated extreme month (Jan 2022, robust z > 3.5, both neighbours normal,
  never the last month) is replaced by its neighbours' mean *for fitting
  only*. A 3-month moving average was carrying the spike into 6-month
  forecasts and pushing products into the top 5. Measured on 26 held-out
  series (`audit/audit_spike_adjustment.py`): Moving Average error 61.6% →
  44.9%, no series worse.
- Real finding for the demo: Orange Choco (current #1) fell to 6.6K/5.7K
  boxes in Feb–Mar 2022 vs a 12.8K average, so it drops out; Eclairs has
  been strong for three months, so it rises.
- Chart shows only the relevant series by default (current top N + any
  entering), "Relevant (k)" in the selector, others one click away. Each
  dashed forecast joins its last actual point.

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
  (497 passing). Afterwards run `git checkout -- backend/data/ml_models/` —
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
