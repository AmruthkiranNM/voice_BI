"""
Agentic AI-Based Business Intelligence System
==============================================

Main FastAPI application entry point.

Initializes:
  1. Database (SQLite with sample data)
  2. Schema embeddings (sentence-transformers)
  3. FAISS vector store (for RAG retrieval)
  4. FastAPI server with query endpoint

Usage:
    uvicorn main:app --reload --port 8000
"""

import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Setup Logging ──
from config import LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s │ %(levelname)-8s │ %(name)-30s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Startup / Shutdown Lifecycle ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize DB, embeddings, and vector store on startup."""
    logger.info("=" * 60)
    logger.info("  Agentic AI BI System — Starting Up")
    logger.info("=" * 60)

    # Step 1: Initialize Database (Now handled dynamically via uploads)
    logger.info("[Startup] Ensuring database directory exists...")
    from config import DATABASE_PATH
    from pathlib import Path
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

    # Step 2: Build or load FAISS vector store
    from services.vector_store import load_index, build_index
    from models.schema_loader import generate_schema_documents

    if not load_index():
        logger.info("[Startup] Building FAISS index from current schema...")
        schema_docs = generate_schema_documents()
        if schema_docs:
            build_index(schema_docs)
            logger.info("[Startup] FAISS index built with %d documents.", len(schema_docs))
        else:
            logger.info("[Startup] Database is empty. Waiting for user uploads.")
    else:
        logger.info("[Startup] FAISS index loaded from disk.")

    logger.info("=" * 60)
    logger.info("  System Ready — All agents operational")
    logger.info("=" * 60)

    yield  # Application runs here

    logger.info("Shutting down Agentic AI BI System...")


# ── Create FastAPI App ──

app = FastAPI(
    title="Agentic AI BI System",
    description=(
        "Business Intelligence system powered by a multi-agent AI pipeline. "
        "Converts natural language queries into SQL using RAG-augmented LLM, "
        "executes them, and generates business insights."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware (for future frontend integration) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routes ──
from routes.query import router as query_router
from routes.upload import router as upload_router
app.include_router(query_router)
app.include_router(upload_router)


# ── Root Endpoint ──
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with system information."""
    return {
        "system": "Agentic AI-Based Business Intelligence System",
        "version": "1.0.0",
        "description": "Multi-agent pipeline: Planner → RAG → SQL → Validator → Execution → Insight",
        "endpoints": {
            "query": "POST /api/query",
            "health": "GET /api/health",
            "docs": "GET /docs",
        },
    }
