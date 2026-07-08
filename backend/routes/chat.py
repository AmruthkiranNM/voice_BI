"""
Chat API Route

Handles conversational follow-up questions about an existing query result,
e.g. "how can I improve my sales with this data?" asked right after a
query response. Answers directly from the result already shown to the
user instead of re-running the full SQL pipeline.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents import chat as chat_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatTurn(BaseModel):
    role: str = Field(..., description='"user" or "assistant"')
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="The follow-up question")
    query: str = Field(..., description="The original natural language question this thread is about")
    sql: str | None = Field(default=None, description="The SQL that produced the result, for reference")
    result: dict = Field(..., description="The result object ({columns, rows, row_count}) being discussed")
    insight: str | None = Field(default=None, description="The insight text originally generated for this result")
    history: list[ChatTurn] = Field(default_factory=list, description="Prior turns in this follow-up thread")
    model: str | None = Field(default=None, description="Optional Ollama model override")
    table_name: str | None = Field(default=None, description="The active dataset table name")


class ChatResponse(BaseModel):
    success: bool
    reply: str | None = None
    error: str | None = None


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a conversational follow-up about an existing query result",
)
def handle_chat(request: ChatRequest):
    import config

    original_model = config.OLLAMA_MODEL
    if request.model:
        config.OLLAMA_MODEL = request.model

    try:
        from agents import followup_orchestrator
        
        reply = followup_orchestrator.run_followup(
            message=request.message,
            context={
                "query": request.query,
                "sql": request.sql,
                "result": request.result,
                "insight": request.insight,
                "table_name": request.table_name,
            },
            history=[turn.model_dump() for turn in request.history],
        )
        return ChatResponse(success=True, reply=reply)
    except Exception as e:
        logger.exception("Chat follow-up failed")
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")
    finally:
        config.OLLAMA_MODEL = original_model
