# Voice BI — AI Business Analysis for Owners

A privacy-first tool that helps **business owners** understand their own data. Upload a CSV from your sales, customers, inventory, or finances, then ask questions by **typing or speaking**. A multi-agent AI pipeline analyzes your data locally and returns charts, tables, and plain-English business insights.

> **No API keys. No cloud. Your data never leaves your machine.**

---

## How It Works

```
1. Upload your business CSV
2. Ask a question (type or voice)
3. AI agents analyze and respond with insights + charts
```

**Agent pipeline:** Planner → RAG Schema Retrieval → SQL Generation → Security Validation → Execution → Business Insight

---

## Key Features

- **CSV upload** — Bring your own business spreadsheet; tables are created automatically
- **Voice input** — Ask questions using your microphone (Web Speech API)
- **Spoken insights** — AI analysis read aloud via text-to-speech
- **Tailored suggestions** — Prompt chips generated from your actual column names
- **Charts & export** — Auto-visualization and CSV export of results
- **Cache & fast mode** — Instant repeat queries and optional speed optimizations
- **100% local** — Powered by [Ollama](https://ollama.com/) on your GPU/CPU

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/) installed and running

### 1. Install Ollama model

```bash
ollama pull qwen2.5-coder:3b
```

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Use the app

1. Open **http://localhost:5173**
2. **Upload your CSV** (Step 1)
3. **Ask a question** by typing or clicking the microphone (Step 2)
4. Review your **analysis, chart, and insights** (Step 3)

---

## API Endpoints

| Method | Endpoint        | Description                    |
|--------|-----------------|--------------------------------|
| POST   | `/api/upload`   | Upload a business CSV          |
| GET    | `/api/datasets` | List uploaded data + suggestions |
| POST   | `/api/query`    | Ask a business question        |
| DELETE | `/api/cache`    | Clear query cache              |
| GET    | `/api/health`   | Health check                   |

---

## Project Structure

```
voice_BI/
├── backend/
│   ├── agents/          # Multi-agent pipeline
│   ├── routes/          # API endpoints
│   ├── services/        # DB, cache, embeddings, LLM
│   └── data/            # SQLite (created at runtime from uploads)
└── frontend/
    └── src/
        ├── components/  # UI panels
        └── hooks/       # Voice input & speech output
```

---

## Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Backend    | Python, FastAPI, SQLite             |
| LLM        | Ollama (local)                      |
| Embeddings | sentence-transformers + FAISS       |
| Frontend   | React, Vite, TailwindCSS, Chart.js  |
| Voice      | Web Speech API + Speech Synthesis   |

---

## Testing

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -q
```

---

## License

Educational and demonstration purposes.
