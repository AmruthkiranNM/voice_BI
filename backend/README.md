# Backend — Voice BI

FastAPI backend that orchestrates a multi-agent pipeline to help business owners analyze their uploaded CSV data using local Ollama inference.

## Quick Start

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## User Flow

1. Owner uploads a CSV via `POST /api/upload`
2. System creates a SQLite table and builds a FAISS schema index
3. Owner asks a question via `POST /api/query` (text or voice-transcribed on frontend)
4. Pipeline returns SQL, data, charts metadata, and business insight

## Configuration (`config.py`)

| Variable           | Default                  | Description              |
|--------------------|--------------------------|--------------------------|
| `OLLAMA_MODEL`     | `qwen2.5-coder:3b`       | Local LLM for SQL/insight |
| `MAX_UPLOAD_ROWS`  | `100000`                 | Max CSV rows             |
| `MAX_UPLOAD_MB`    | `50`                     | Max upload file size     |
| `CACHE_TTL_SECONDS`| `3600`                   | Query cache lifetime     |

## API

| Method | Endpoint        | Description              |
|--------|-----------------|--------------------------|
| POST   | `/api/upload`   | Upload business CSV      |
| GET    | `/api/datasets` | Dataset status           |
| POST   | `/api/query`    | Natural language query   |
| DELETE | `/api/cache`    | Clear query cache        |
