"""
Query API Route

Handles the main query endpoint for the Agentic AI BI System.
Accepts natural language business queries and returns SQL, results, and insights.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.orchestrator import process_query
from services.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Query"], dependencies=[Depends(require_auth)])


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
        description="Single active table to query (legacy; prefer table_names)",
    )
    table_names: list[str] | None = Field(
        default=None,
        description="Tables in scope for this query (one data source's tables). "
                    "SQL is restricted to exactly these; multiple enables joins.",
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


class PaginateRequest(BaseModel):
    sql: str
    page: int = 1
    page_size: int = 25
    sort_column: str | None = None
    sort_dir: str = "asc"
    search_term: str | None = None



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

    logger.info(
        "Received query: %s (tables=%s)",
        request.query, request.table_names or request.table_name,
    )

    # Resolve the scope: an explicit table_names list wins; fall back to the
    # single legacy table_name; else if there's exactly one table, use it.
    table_names = request.table_names
    if not table_names and request.table_name:
        table_names = [request.table_name]
    
    # Do NOT fall back to get_all_table_names() if the request provided no tables.
    # If the user is on a source with no tables (or the frontend didn't send them),
    # we should let process_query/task_router fail explicitly instead of silently
    # querying unrelated datasets like Churn_Modelling.
    try:
        result = process_query(
            request.query,
            model=request.model,
            table_names=table_names,
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

@router.post(
    "/query/paginate",
    summary="Paginate an existing SQL query",
)
def paginate_query(request: PaginateRequest):
    """Execute a query with pagination, search, and sorting."""
    from services.database import execute_paginated_query
    
    try:
        result = execute_paginated_query(
            sql=request.sql,
            page=request.page,
            page_size=request.page_size,
            sort_col=request.sort_column,
            sort_dir=request.sort_dir,
            search=request.search_term
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.exception("Pagination failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/query/export",
    summary="Export complete results of a query",
)
def export_query(request: PaginateRequest):
    """Execute query and stream all matching rows for export."""
    from services.database import execute_paginated_query
    from fastapi.responses import StreamingResponse
    import io
    import csv
    import json
    
    try:
        # Fetch all by passing page_size=0 or very large
        result = execute_paginated_query(
            sql=request.sql,
            page=1,
            page_size=1000000, # Large enough for export, or we could stream properly
            sort_col=request.sort_column,
            sort_dir=request.sort_dir,
            search=request.search_term
        )
        
        # Determine format (default CSV)
        # We can implement simple JSON or CSV based on a format param if needed, 
        # but returning JSON array directly is fine for the frontend to handle.
        return {"success": True, "result": result}
    except Exception as e:
        logger.exception("Export failed")
        raise HTTPException(status_code=500, detail=str(e))


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
