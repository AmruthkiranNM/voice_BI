# Voice BI — Project Overview & Team Presentation Script

## 1. What it is (one-liner)

**Voice BI** is a privacy-first business intelligence tool: upload a CSV (sales, HR, inventory, finance — anything tabular), then ask questions about it in plain English — by typing *or* speaking — and get back charts, tables, and a written answer, with the option to keep asking follow-ups conversationally.

The pitch to a non-technical business owner: *"You don't need a data analyst or SQL — just ask your spreadsheet a question out loud."*

---

## 2. How it works

1. **Upload** — a CSV is dropped into a per-user SQLite database. A data-quality report (missing values, duplicates, inconsistent types) is generated instantly from the data itself — no AI involved, so it's always accurate and free.
2. **Ask** — the user types or speaks a question ("what were our top 5 products last quarter?").
3. **Multi-agent pipeline** turns that question into a validated SQL query, runs it, and generates a plain-English insight:
   - **Planner** — figures out intent (ranking, trend, comparison, aggregation, etc.)
   - **RAG Retriever** — pulls the relevant table/column context from a FAISS vector index of the schema, so the LLM isn't guessing at column names
   - **SQL Generator** — writes the actual SQL query
   - **Validator** — checks the SQL for correctness/safety before it ever touches the database, retries on failure
   - **Execution** — runs the query against SQLite
   - **Insight** — turns the raw result rows into a written explanation
4. **Result** — the frontend renders the answer as a chart (auto-picks the best chart type for the data shape), a sortable/filterable table, and the written insight — plus a **pipeline trace** showing exactly which agent did what.
5. **Follow-ups** — the user can keep asking about the same result ("why did that spike?") without re-running the full SQL pipeline — a lighter-weight chat agent handles that conversationally, including a hands-free voice loop (speak → hear the answer → mic reopens automatically).

Everything runs against the user's own data in a locally-scoped SQLite file; the only outbound calls are to the LLM (local via Ollama, or optionally a cloud provider like Groq).

---

## 3. Tech stack

| Layer | Technology |
|---|---|
| **Backend** | Python, FastAPI, SQLite |
| **Multi-agent pipeline** | Hand-rolled orchestrator (no LangChain) — Planner, RAG Retriever, SQL Generator, Validator, Execution, Insight, Chat agents |
| **LLM** | Ollama (local, default) or Groq (cloud API) — plain `urllib` HTTP calls, no SDK |
| **Retrieval / embeddings** | `sentence-transformers` + FAISS (CPU-only, so GPU VRAM stays free for the LLM) |
| **Auth / data isolation** | Per-user SQLite DB files, bcrypt password hashing, request-scoped context for DB routing |
| **Frontend** | React + Vite |
| **Styling** | Tailwind CSS v4 (custom "Editorial Analyst" warm-paper design system, light/dark theme) |
| **Charts** | ECharts |
| **Voice** | Web Speech API (speech-to-text) + Speech Synthesis (text-to-speech) — all in-browser, no external voice API |
| **Testing** | pytest (unit/integration, agents mocked) + a hand-labeled SQL-accuracy benchmark harness |
| **Deployment** | Docker Compose (frontend + backend containers, Ollama runs natively on the host) |

---

## 4. Individual contribution script — 4-person team

Use this to divide (or present) the work as four clearly-scoped ownership areas. Each section is written so that person can explain their part standalone in a viva/demo.

### Person 1 — Backend Pipeline & Agents
**Owns:** `backend/agents/`, `backend/routes/query.py`, `backend/routes/chat.py`

- Designed and implemented the six-stage agent pipeline (Planner → RAG Retriever → SQL Generator → Validator → Execution → Insight)
- Built the SQL validation + self-correction retry loop (catches bad SQL before execution, retries with the error fed back to the LLM)
- Implemented the follow-up chat agent for conversational, lightweight queries that don't re-run the full pipeline
- Instrumented every agent step with timing so the frontend can render a live pipeline trace

**Talking point:** *"I built the reasoning core — the part that turns 'what were our best sellers?' into safe, correct SQL, with a self-correction loop so a bad first attempt doesn't just fail."*

### Person 2 — Data, Retrieval & LLM Integration
**Owns:** `backend/services/embeddings.py`, `vector_store.py`, `domain_detector.py`, `llm_service.py`, `data_quality.py`, `db_import.py`

- Built the schema-aware RAG retrieval system (sentence-transformer embeddings + FAISS index) so the SQL generator gets only relevant table/column context
- Implemented hybrid domain detection (keyword scoring + semantic classifier) to identify business type (retail, HR, restaurant, etc.) from the uploaded data
- Wrote the CSV ingestion pipeline and the instant, LLM-free data-quality report (missing values, duplicates, inconsistent types)
- Built the provider-agnostic LLM client (Ollama local / Groq cloud) with timeout handling and error surfacing

**Talking point:** *"I made sure the AI is grounded in the real schema instead of hallucinating column names, and built the domain detection that lets the app adapt its suggestions to whatever kind of business data you upload."*

### Person 3 — Frontend Application & Visualization
**Owns:** `frontend/src/components/`, `frontend/src/utils/echartsBuilder.js`, `chartRecommender.js`, `resultAnalytics.js`

- Built the results dashboard: auto-recommended chart types, sortable/filterable data table, KPI cards, business insights panel
- Implemented client-side result analytics (period-over-period change, outlier detection, correlation callouts) computed directly from result rows — no LLM calls, no hallucination risk
- Built the forecasting feature (least-squares trend projection drawn as a dashed line extension)
- Built the light/dark theme system and the "Editorial Analyst" design system (Tailwind CSS v4 tokens, warm-paper palette)

**Talking point:** *"I own everything the user actually sees and clicks — from picking the right chart type automatically, to computing insight callouts client-side so they're always accurate to the data, never invented."*

### Person 4 — Voice, Auth & Platform
**Owns:** `frontend/src/hooks/useVoice.js`, `backend/services/auth.py`, `routes/auth.py`, `routes/upload.py`, Docker/deployment

- Implemented voice input/output using the Web Speech API — live transcript while speaking, answers read back via speech synthesis, and the hands-free conversation loop (speak → answer → mic reopens)
- Built multi-user authentication with per-user SQLite database isolation (bcrypt hashing, request-scoped DB routing so users can never see each other's data)
- Built the CSV upload flow and query/response caching (instant repeat queries) and fast-mode optimization for slower hardware
- Set up Docker Compose deployment (frontend + backend containers, Ollama on host via `host.docker.internal`)

**Talking point:** *"I built the parts that make this usable by real, non-technical users and safe for multiple people to use — the voice interface, login/data isolation, and the one-command Docker setup."*

---

## 5. Suggested demo flow (for all 4 to run together)

1. **Person 4** logs in, uploads a sales CSV — shows the instant data-quality report.
2. **Person 2** explains what happened behind the scenes (schema embedding, domain detection identifying it as "retail").
3. **Person 1** asks a question by typing, narrates the pipeline trace as each agent lights up (Planner → ... → Insight).
4. **Person 3** shows the resulting chart/table/insight, then asks a follow-up question, and points out the forecast trendline and light/dark toggle.
5. **Person 4** closes with a live voice question ("hey, what's our top product?") to show the hands-free loop end-to-end.
