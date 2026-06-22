"""
Query API Route

Handles the main query endpoint for the Agentic AI BI System.
Accepts natural language business queries and returns SQL, results, and insights.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.orchestrator import process_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Query"])


# ── Request / Response Models ──

class QueryRequest(BaseModel):
    """Request body for the /query endpoint."""
    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural language business question",
        examples=["Show total sales last month", "Top 5 customers by revenue"],
    )
    model: str | None = Field(
        default=None,
        description="Optional Ollama model override",
    )
    cache_mode: bool = Field(
        default=True,
        description="Use cached results for repeated identical queries",
    )
    fast_mode: bool = Field(
        default=False,
        description="Skip planner LLM call and use heuristic plan for faster execution",
    )
    skip_insight: bool = Field(
        default=False,
        description="Skip insight generation (auto-enabled when fast_mode is on)",
    )
    table_name: str | None = Field(
        default=None,
        description="Active uploaded table to query (scopes SQL to this dataset)",
    )


class QueryResponse(BaseModel):
    """Response body for the /query endpoint."""
    success: bool
    query: str
    sql: str | None = None
    result: dict = {}
    insight: str | None = None
    error: str | None = None
    llm_mode: str
    metadata: dict = {}
    agent_logs: list = []


# ── Endpoints ──

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Process a natural language business query",
    description=(
        "Accepts a natural language business question and processes it through "
        "the multi-agent pipeline: Planner → RAG → SQL Generator → Validator → "
        "Execution → Insight. Returns the generated SQL, query results, and "
        "AI-generated business insights."
    ),
)
def handle_query(request: QueryRequest):
    """Process a natural language query through the agent pipeline."""
    from services.database import has_datasets

    if not has_datasets():
        raise HTTPException(
            status_code=400,
            detail="No business data found. Please upload a CSV file before asking questions.",
        )

    logger.info("Received query: %s (table=%s)", request.query, request.table_name)

    table_name = request.table_name
    if not table_name:
        from services.database import get_all_table_names
        tables = get_all_table_names()
        if len(tables) == 1:
            table_name = tables[0]

    try:
        result = process_query(
            request.query,
            model=request.model,
            table_name=table_name,
            cache_mode=request.cache_mode,
            fast_mode=request.fast_mode,
            skip_insight=request.skip_insight,
        )
        return QueryResponse(**result)

    except Exception as e:
        logger.exception("Unhandled error processing query")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@router.delete(
    "/cache",
    summary="Clear query result cache",
)
def clear_cache():
    """Clear all cached query results."""
    from services import query_cache
    query_cache.invalidate()
    return {"success": True, "message": "Query cache cleared"}


@router.get(
    "/health",
    summary="Health check",
    description="Returns the health status of the API.",
)
def health_check():
    """Simple health check endpoint."""
    from services.vector_store import is_index_ready

    return {
        "status": "healthy",
        "vector_store_ready": is_index_ready(),
    }


@router.get(
    "/models",
    summary="List available local Ollama models",
    description="Fetches installed models from local Ollama service, falling back to a static list if offline.",
)
def list_models():
    """Fetch available local Ollama models."""
    import urllib.request
    import json
    import config

    try:
        url = f"{config.OLLAMA_HOST}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            # Ensure the default configured model is at least shown if not fetched
            if config.OLLAMA_MODEL not in models:
                models.insert(0, config.OLLAMA_MODEL)
            return {"models": models}
    except Exception as e:
        logger.warning("Failed to fetch models from Ollama: %s", e)
        # Fallback list including common/default models
        return {"models": [config.OLLAMA_MODEL, "qwen2.5-coder:3b", "qwen2.5-coder:1.5b"]}
