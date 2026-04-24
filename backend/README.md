# Backend — Agentic AI BI System

The backend is a **FastAPI** application that orchestrates a 6-agent pipeline to convert natural language queries into SQL, execute them against a SQLite database, and generate AI-powered business insights.

All LLM inference runs **locally** via [Ollama](https://ollama.com/) — no API keys or cloud services required.

## Quick Start

```bash
# From project root
cd backend
pip install -r requirements.txt
pip install pandas python-multipart
uvicorn main:app --reload --port 8000
```

## Configuration

All settings are in `config.py`:

| Variable        | Default                        | Description                     |
|-----------------|--------------------------------|---------------------------------|
| `OLLAMA_HOST`   | `http://localhost:11434`       | Ollama server URL               |
| `OLLAMA_MODEL`  | `qwen2.5-coder:3b`            | Model for SQL generation        |
| `DATABASE_PATH` | `data/business.db`             | SQLite database file            |
| `RAG_TOP_K`     | `5`                            | Number of schema docs retrieved |
| `MAX_RESULT_ROWS` | `500`                        | Max rows returned per query     |

## Agent Pipeline

1. **Planner** — Extracts intent, metrics, filters, and grouping from the query
2. **RAG Retriever** — Searches the FAISS vector store for relevant table schemas
3. **SQL Generator** — Sends the schema context + query to Ollama to generate SQL
4. **Validator** — Blocks dangerous SQL keywords and validates table/column existence
5. **Execution** — Runs the validated SQL on the SQLite database
6. **Insight** — Sends the results back to Ollama for a plain-English summary

## API Reference

| Method | Endpoint       | Description                          |
|--------|----------------|--------------------------------------|
| POST   | `/api/query`   | Process a natural language query     |
| POST   | `/api/upload`  | Upload a CSV to create a new table   |
| GET    | `/api/health`  | Health check + vector store status   |
| GET    | `/docs`        | Swagger UI                           |
