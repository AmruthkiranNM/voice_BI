# Voice BI — Ask Your Business Data Questions, by Voice or Text

Voice BI lets a business owner **ask questions about their own data in plain English** — typed or spoken — and get back charts, tables and a clear answer. It answers two kinds of question:

| Kind | Example | What you get |
|---|---|---|
| **Descriptive** — what happened | "What is the total revenue by country?" | SQL is generated, run on your data, and explained |
| **Predictive** — what will happen | "Forecast revenue by region for the next 6 months" | A validated forecast with a 95% range and an explanation of its shape |

You can keep the conversation going with **follow-ups** ("which one is the lowest?", "will it be the same next 6 months?").

> **Ground rules the system follows:** the AI never calculates numbers (all figures are computed in code), missing data is never treated as zero, and nothing is hard-coded to a particular dataset or question.

For a full history of changes and the reasons behind them, see **[context.md](context.md)**.

---

## Contents
1. [Quick start](#quick-start)
2. [Using the app](#using-the-app)
3. [Example questions](#example-questions)
4. [How predictions work](#how-predictions-work)
5. [Testing](#testing)
6. [Troubleshooting](#troubleshooting)
7. [Project structure](#project-structure)
8. [API endpoints](#api-endpoints)
9. [Tech stack](#tech-stack)

---

## Quick start

### Requirements
- **Python 3.10+**
- **Node.js 20 or newer** (Vite does not run on Node 18)
- An AI provider — either:
  - **Groq** (free cloud API, fastest to set up) — get a key at [console.groq.com](https://console.groq.com), or
  - **Ollama** (fully local) — install from [ollama.com](https://ollama.com) and run `ollama pull qwen2.5-coder:3b`

### 1. Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000 
```

Create a file **`backend/.env`** with your settings:
```env
# Choose ONE provider
LLM_PROVIDER=groq                # or: ollama
GROQ_API_KEY=your-groq-key       # only for groq
# OLLAMA_MODEL=qwen2.5-coder:3b  # only for ollama

# Required for login tokens — use any long random string
JWT_SECRET=change-me-to-a-long-random-string
```
> Never commit `.env` — it holds your keys.

Start the server:
```bash
uvicorn main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**.

### Optional: Docker
`docker compose up --build` starts both parts (app on :5173, API on :8000). It expects a local Ollama on the host — see [docker-compose.yml](docker-compose.yml).

---

## Using the app

1. **Sign up / log in.**
2. **Connect data** — either:
   - **Upload a CSV** (you get an instant data-quality report: missing values, duplicates, mixed types), or
   - **Connect a PostgreSQL database** (e.g. Supabase) by pasting its connection URL:
     ```
     postgresql://USER:PASSWORD@HOST:PORT/DATABASE
     ```
     In Supabase: **Connect → URI → Transaction pooler**. Encode special characters in the password (`@` → `%40`, `#` → `%23`).
3. **Pick the tables** to ask about (or leave on *Auto*).
4. **Ask a question** — type it or press the mic.
5. **Read the result** — chart, table, written answer. Change chart type, go fullscreen, export.
6. **Ask follow-ups** in the chat panel under the result. Asking a new main question clears the follow-up chat.

---

## Example questions

### Descriptive
| Question | Follow-up |
|---|---|
| What is the total revenue by country? | which one is the lowest |
| Show monthly revenue for 2022 | Now compare it with 2021 |
| Top 5 products by boxes shipped | What about by revenue? |
| Revenue for After Nines by month | Only for India |
| Share of revenue by category | — |

### Predictive
| Question | Follow-up |
|---|---|
| Forecast total revenue for the next 6 months | How reliable is this? |
| Forecast revenue by region for the next 6 months | Will APAC remain the highest? |
| Top 5 products by boxes shipped | will it be same in the next 6 months |
| Which month next year will have the highest sales? | — |
| Predict boxes for each sale | which factors matter most |
| Which customers are likely to leave? *(churn dataset)* | What drives churn the most? |

### The system should refuse or explain (not invent)
| Question | Expected |
|---|---|
| Revenue in 2030 | "No data for that period", with the data's date range |
| Predict revenue for Germany | "Germany doesn't appear in the data" |
| Churn rate by country *(sales data with no churn column)* | "No information on churn" — never a made-up 0 |
| Delete all sales from India | Refused — the app only reads data |

> **Tip:** forecasting needs history. With ~15 months the system can't learn a yearly pattern (needs 24+). Use a dataset with 2–4 years (e.g. Superstore) to see seasonal forecasts.

---

## How predictions work

```
Question → Task router (descriptive or predictive?)
         → Config resolver (what to forecast, by what, how far, at what bucket size)
         → Prediction engine (per series):
              1. Aggregate to the bucket (month/quarter/...) — gaps stay empty, never 0
              2. Check the series (length, gaps, one-off spikes, trend, seasonality)
              3. Backtest candidate models on months they haven't seen
              4. Choose the method, fit it, build the 95% range from its real errors
         → Evidence (all numbers computed) → short written answer
```

**Which method is used — and why** (measured in `audit/benchmark_*.py`, all on months the models had not seen):

| Situation in the data | Method | Forecast shape |
|---|---|---|
| Real trend (passes a 5% significance test) | Best trend model from backtesting | Straight / flattening slope |
| 2+ full seasonal cycles (e.g. 24+ months) | Best seasonal model (e.g. Holt-Winters, Seasonal Naive) | Repeats the yearly ups and downs |
| Neither (short, noisy data) | **Combination** of mean, SES, 3-month average, last value, **with mean reversion** | Curves from the recent level back toward normal, at the rate the data shows; level if the data shows no carry-over |

**Why is a forecast sometimes a flat line?** Because the past ups and downs were random. On this project's data, forecasts that copied the history's ups and downs were less accurate on 24 of 26 series. The swings are shown as the **shaded 95% range** instead. Every forecast chart has a **"Why does the forecast look like this?"** box with the measured reasons, and a grey dotted **"Tested on past periods"** line showing the method predicting real past months it never saw.

**Reliability labels** (same everywhere — chart and text):
- **Validated** — MASE below 1 and beats the naive baseline
- **Weak (indicative)** — beats naive, but MASE ≥ 1
- **Baseline only** — nothing beat "same as last period"
- **Not validated** — too little history to test

---

## Testing

### Automated tests (no AI calls needed)
```bash
cd backend
venv\Scripts\python.exe -m pytest tests -q
```
Expect about **500 passing**. The tests regenerate some cached model files — restore them afterwards:
```bash
git checkout -- data/ml_models/
```

### Forecast audits (real data, no AI calls)
Run from `backend/`:
```bash
venv\Scripts\python.exe ..\audit\benchmark_forecasters.py
```
Other audits in `audit/`: `benchmark_pipeline_designs.py`, `benchmark_mean_reversion.py`, `audit_real_forecasts.py`, `audit_spike_adjustment.py`, `analyze_monthly_structure.py`.

### Manual testing
Restart the backend first (answers are cached), then work through [Example questions](#example-questions) in one chat.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `npm run dev` fails / Vite error | Upgrade to **Node 20+** |
| An old answer keeps coming back | Restart the backend (results are cached), or call `DELETE /api/cache` |
| "The AI service's daily usage limit has been reached" | Groq free tier ≈ 200k tokens/day — wait, or switch `LLM_PROVIDER=ollama` |
| Postgres import: `date/time field value out of range: "16/06/2017"` | Dates are day/month/year — import the column as text, then `ALTER TABLE t ALTER COLUMN "Order Date" TYPE date USING to_date("Order Date", 'DD/MM/YYYY');` |
| Postgres import: `duplicate key value violates unique constraint` | The chosen primary key repeats (e.g. one order has many rows) — use a unique column like `Row ID` |
| Connection URL rejected | Encode special characters in the password (`@` → `%40`) |
| Forecast says "needs 24 months… this series has 15" | Expected — the dataset is too short for seasonality |

---

## Project structure

```
voice_BI/
├── README.md, context.md        # this guide; detailed change log
├── audit/                       # forecast benchmarks and audits (real data)
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── config.py                # settings (read from .env)
│   ├── agents/                  # orchestrator, planner, SQL agent, validator, insight,
│   │                            # task router, prediction agent, follow-ups
│   ├── prediction/              # forecasting engine: models, selection, intervals,
│   │                            # time resolution, config resolver
│   ├── services/                # database, cache, LLM client, time coverage,
│   │                            # computed result facts, entity checks
│   ├── routes/                  # API endpoints
│   └── tests/                   # pytest suite
└── frontend/
    └── src/
        ├── components/          # results dashboard, charts, prediction panel, chat
        ├── hooks/               # voice input / speech output
        └── utils/               # chart builders, palette
```

---

## API endpoints

All endpoints except `/api/auth/*` require a login token.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | Create account / log in |
| GET | `/api/auth/me` | Current user |
| POST | `/api/upload` | Upload a CSV (returns a data-quality report) |
| POST | `/api/connections/test`, `/api/connections/import` | Test / import a PostgreSQL database |
| GET | `/api/datasets` | List data sources and tables |
| GET | `/api/datasets/{table}/preview` | Preview a table |
| DELETE | `/api/datasets/{table}`, `/api/sources/{id}` | Remove a table / source |
| POST | `/api/query` | Ask a question (descriptive or predictive) |
| POST | `/api/chat` | Ask a follow-up about a result |
| POST | `/api/investigate` | Dig deeper into an answered question (multi-step root-cause drill-down) |
| DELETE | `/api/cache` | Clear cached answers |
| GET | `/api/health`, `/api/models` | Health check / available models |

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, SQLite (+ PostgreSQL import) |
| AI | Groq (cloud) or Ollama (local) — wording and SQL only, never numbers |
| Forecasting | statsmodels, scikit-learn, NumPy/pandas |
| Schema search | sentence-transformers + FAISS (CPU) |
| Frontend | React, Vite, Tailwind CSS, ECharts |
| Voice | Web Speech API + Speech Synthesis |

---

## License
Educational and demonstration purposes (major project).
