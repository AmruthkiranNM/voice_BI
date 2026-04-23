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
    llm_mode: str | None = Field(
        default=None,
        description="Optional LLM provider override: 'mock' or 'gemini'",
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
async def handle_query(request: QueryRequest):
    """Process a natural language query through the agent pipeline."""
    logger.info("Received query: %s", request.query)

    try:
        result = process_query(request.query, llm_mode=request.llm_mode)
        return QueryResponse(**result)

    except Exception as e:
        logger.exception("Unhandled error processing query")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/health",
    summary="Health check",
    description="Returns the health status of the API.",
)
async def health_check():
    """Simple health check endpoint."""
    from services.vector_store import is_index_ready

    return {
        "status": "healthy",
        "vector_store_ready": is_index_ready(),
    }
