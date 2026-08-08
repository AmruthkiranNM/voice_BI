"""
Investigate API Route

Autonomous multi-hop root-cause drill-down on an already-answered query.
Separate from /api/query so a normal question stays fast — this is only
run when the user explicitly asks the system to dig deeper.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.investigator import investigate
from services.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Investigate"], dependencies=[Depends(require_auth)])


class InvestigateRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="The original question already answered")
    sql: str | None = Field(default=None, description="The SQL that answered the original question")
    result: dict = Field(..., description="The original query's result ({columns, rows, row_count})")
    model: str | None = Field(default=None)
    table_names: list[str] | None = Field(default=None)


@router.post(
    "/investigate",
    summary="Autonomously drill into why an already-answered query's result looks the way it does",
)
def handle_investigate(request: InvestigateRequest):
    from services.database import has_datasets

    if not has_datasets():
        raise HTTPException(status_code=400, detail="No business data found.")

    try:
        outcome = investigate(
            request.query,
            request.sql or "",
            request.result,
            model=request.model,
            table_names=request.table_names,
        )
        return {"success": True, **outcome}
    except Exception as e:
        logger.exception("Unhandled error during investigation")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
