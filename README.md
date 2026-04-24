# 🧠 Voice BI — Agentic AI Business Intelligence (100% Local)

A privacy-first Business Intelligence system that converts **natural language questions** into SQL queries, executes them, and generates AI-powered insights — all running **100% locally** on your machine using [Ollama](https://ollama.com/).

> **No API keys. No cloud. No data ever leaves your machine.**

---

## ✨ Key Features

- **🦙 Powered by Ollama** — Uses `qwen2.5-coder:3b` running locally on your GPU/CPU
- **📊 Dynamic CSV Upload** — Upload any CSV file; the system auto-creates database tables and indexes them for AI querying
- **🔍 RAG-Powered Schema Retrieval** — FAISS vector store with sentence-transformer embeddings ensures the AI always references the correct tables and columns
- **🛡️ Zero-Trust SQL Security** — Blocks all destructive operations (DROP, DELETE, UPDATE, INSERT); only SELECT queries are allowed
- **🎨 Modern Dashboard UI** — Glassmorphism design with real-time pipeline visualization

---

## 🏗️ Architecture

```
User (Natural Language Query)
       ↓
  ┌──────────────────────────────────┐
  │         FastAPI Backend          │
  │     Agent Orchestrator           │
  │                                  │
  │  1. Planner Agent                │ → Breaks query into intent + steps
  │  2. RAG Retriever Agent          │ → Searches FAISS for relevant schema
  │  3. SQL Generator Agent          │ → Ollama generates SQL from schema
  │  4. Validator Agent              │ → Blocks dangerous SQL (security)
  │  5. Execution Agent              │ → Runs SQL on SQLite database
  │  6. Insight Agent                │ → Ollama summarizes results in English
  └──────────────────────────────────┘
       ↓
  Structured Response (SQL + Data + Charts + Insights)
```

---

## 📁 Project Structure

```
voice_BI/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Central configuration (Ollama settings)
│   ├── requirements.txt           # Python dependencies
│   │
│   ├── routes/
│   │   ├── query.py               # POST /api/query — NL query pipeline
│   │   └── upload.py              # POST /api/upload — CSV dataset upload
│   │
│   ├── agents/
│   │   ├── orchestrator.py        # Pipeline coordinator
│   │   ├── planner.py             # Query planning & intent extraction
│   │   ├── rag_agent.py           # RAG-based schema retrieval
│   │   ├── sql_agent.py           # SQL generation via Ollama
│   │   ├── validator.py           # Security & schema validation
│   │   ├── execution.py           # Database query execution
│   │   └── insight.py             # AI insight generation via Ollama
│   │
│   ├── services/
│   │   ├── database.py            # SQLite database management
│   │   ├── embeddings.py          # Sentence-transformer embeddings
│   │   ├── vector_store.py        # FAISS vector index management
│   │   └── llm_service.py        # Ollama LLM client
│   │
│   ├── models/
│   │   └── schema_loader.py       # Schema-to-document converter
│   │
│   └── data/                      # Auto-created SQLite database directory
│
└── frontend/
    ├── src/
    │   ├── App.jsx                # Main application
    │   ├── components/            # UI components (Header, Upload, Charts, etc.)
    │   └── services/api.js        # Backend API client
    └── package.json
```

---

## 🚀 Setup & Run

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **[Ollama](https://ollama.com/)** installed and running

### 1. Install Ollama & Download the Model

```bash
# Install Ollama from https://ollama.com/
# Then pull the model:
ollama pull qwen2.5-coder:3b
```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\Activate    # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
cd backend
pip install -r requirements.txt
pip install pandas python-multipart

# Start the server
uvicorn main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the App

1. Ensure **Ollama is running** (check: http://localhost:11434)
2. Open **http://localhost:5173** in your browser
3. **Upload a CSV** file using the "Provide Your Data" section
4. **Ask questions** in natural language!

---

## 📡 API Endpoints

| Method | Endpoint       | Description                              |
|--------|----------------|------------------------------------------|
| POST   | `/api/query`   | Process a natural language query         |
| POST   | `/api/upload`  | Upload a CSV dataset                     |
| GET    | `/api/health`  | Health check + vector store status       |
| GET    | `/docs`        | Interactive Swagger API documentation    |

### Example: Upload a CSV

```bash
curl -X POST -F "file=@sales_data.csv" http://localhost:8000/api/upload
```

### Example: Ask a Question

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show total sales by category"}'
```

### Example Response

```json
{
  "success": true,
  "query": "Show total sales by category",
  "sql": "SELECT category, SUM(total_price) AS total_sales FROM sales GROUP BY category;",
  "result": {
    "columns": ["category", "total_sales"],
    "rows": [{"category": "Electronics", "total_sales": 125000}],
    "row_count": 3
  },
  "insight": "Electronics leads with ₹1,25,000 in total sales...",
  "metadata": {
    "pipeline_time_seconds": 12.5,
    "tables_used": ["sales"]
  }
}
```

---

## 🔐 Security Features

- **SQL Injection Prevention** — Blocks `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, etc.
- **SELECT-only Enforcement** — Only read operations are allowed
- **Multi-statement Blocking** — Prevents semicolon injection attacks
- **Schema Validation** — Ensures referenced tables/columns exist in the database

---

## 🛠️ Tech Stack

| Component       | Technology                          |
|-----------------|-------------------------------------|
| Backend         | Python + FastAPI                    |
| LLM             | Ollama (qwen2.5-coder:3b) — Local  |
| Database        | SQLite (dynamic, user-provided)     |
| Embeddings      | sentence-transformers (all-MiniLM)  |
| Vector Store    | FAISS (CPU)                         |
| Frontend        | React + Vite + TailwindCSS         |
| RAG             | Custom (Embeddings + FAISS)         |

---

## 📄 License

This project is for educational and demonstration purposes.
