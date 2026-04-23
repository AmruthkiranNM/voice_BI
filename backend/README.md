# Agentic AI-Based Business Intelligence System using RAG

A production-quality backend system that converts natural language business queries into SQL, executes them, and generates AI-powered insights — powered by a multi-agent pipeline.

## 🏗️ Architecture

```
User (Text Query)
       ↓
  FastAPI Backend
       ↓
  Agent Orchestrator
       ↓
 ┌─────────────────────────────┐
 │   1. Planner Agent          │  → Breaks query into steps
 │   2. RAG Retriever Agent    │  → Fetches relevant schema via FAISS
 │   3. SQL Generator Agent    │  → Generates SQL using LLM + schema
 │   4. Validator Agent        │  → Security + schema validation
 │   5. Execution Agent        │  → Runs SQL on database
 │   6. Insight Agent          │  → Generates business insights
 └─────────────────────────────┘
       ↓
  Structured Response (SQL + Data + Insights)
```

## 📁 Project Structure

```
backend/
├── main.py                    # FastAPI app entry point
├── config.py                  # Central configuration
├── requirements.txt           # Python dependencies
├── test_pipeline.py           # Pipeline test script
│
├── routes/
│   └── query.py               # API endpoint: POST /api/query
│
├── agents/
│   ├── orchestrator.py        # Central controller (pipeline coordinator)
│   ├── planner.py             # Query planning & intent extraction
│   ├── rag_agent.py           # RAG-based schema retrieval
│   ├── sql_agent.py           # SQL generation using LLM
│   ├── validator.py           # Security & schema validation
│   ├── execution.py           # Database query execution
│   └── insight.py             # AI insight generation
│
├── services/
│   ├── database.py            # SQLite database management
│   ├── embeddings.py          # Sentence-transformer embeddings
│   ├── vector_store.py        # FAISS vector index management
│   └── llm_service.py         # LLM provider (Gemini / Mock)
│
├── models/
│   └── schema_loader.py       # Schema-to-document converter
│
├── data/
│   └── sample_db.sql          # Sample database (sales, customers, etc.)
│
└── vector_store/              # Auto-generated FAISS index files
```

## 🚀 Setup & Run

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# Required: Google Gemini API Key
set GEMINI_API_KEY=your_api_key_here

# Optional: Use mock LLM for testing without API key
set LLM_PROVIDER=mock
```

### 3. Run the Server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Test the API

Open `http://localhost:8000/docs` for the interactive Swagger UI.

Or use curl:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show total sales last month"}'
```

### 5. Run Pipeline Test (without server)

```bash
cd backend
python test_pipeline.py
```

## 📡 API Endpoints

| Method | Endpoint       | Description                          |
|--------|----------------|--------------------------------------|
| POST   | `/api/query`   | Process a natural language query     |
| GET    | `/api/health`  | Health check + vector store status   |
| GET    | `/docs`        | Swagger API documentation            |

### Request Body

```json
{
  "query": "Show total sales last month"
}
```

### Response

```json
{
  "success": true,
  "query": "Show total sales last month",
  "sql": "SELECT SUM(total_price) as total_sales FROM sales WHERE ...",
  "result": {
    "columns": ["total_sales"],
    "rows": [{"total_sales": 47500.0}],
    "row_count": 1
  },
  "insight": "Total sales for last month were ₹47,500...",
  "metadata": {
    "pipeline_time_seconds": 2.34,
    "tables_used": ["sales"],
    "plan": { ... }
  },
  "agent_logs": [ ... ]
}
```

## 🔐 Security Features

- **SQL Injection Prevention**: Blocks DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, etc.
- **SELECT-only Enforcement**: Only read operations are allowed.
- **Multi-statement Blocking**: Prevents semicolon injection attacks.
- **Schema Validation**: Ensures referenced tables/columns exist in the database.

## 🛠️ Tech Stack

| Component     | Technology                |
|---------------|---------------------------|
| Backend       | Python + FastAPI          |
| Database      | SQLite                    |
| LLM           | Google Gemini             |
| Embeddings    | sentence-transformers     |
| Vector Store  | FAISS                     |
| RAG           | Custom (Embeddings+FAISS) |
