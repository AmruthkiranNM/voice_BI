"""
Agent Orchestrator

Central controller that coordinates the multi-agent pipeline.
Manages the full flow from user query to final result:

    Query → Planner → RAG → SQL Generator → Validator → Execution → Insight

Includes retry logic for SQL generation failures and comprehensive logging.
"""

import logging
import time
from typing import Any

from agents import planner, rag_agent, sql_agent, validator, execution, insight
from agents.validator import ValidationError

logger = logging.getLogger(__name__)

# Maximum retries for SQL generation if validation fails
MAX_SQL_RETRIES = 3


def process_query(query: str, llm_mode: str | None = None) -> dict[str, Any]:
    """
    Process a natural language query through the full agent pipeline.

    Pipeline:
        1. Planner Agent      → Structured execution plan
        2. RAG Retriever Agent → Relevant database schema
        3. SQL Generator Agent → SQL query
        4. Validator Agent     → Security & schema check
        5. Execution Agent     → Query execution
        6. Insight Agent       → Business insight

    Args:
        query: Natural language business question.
        llm_mode: Optional LLM provider override ('mock' or 'gemini').

    Returns:
        Complete response with SQL, results, insights, and agent logs.
    """
    # Allow per-request LLM mode override
    import config
    original_provider = config.LLM_PROVIDER

    # Validate Gemini mode — check if API key is available
    effective_mode = llm_mode
    if llm_mode == "gemini" and not config.GEMINI_API_KEY:
        logger.warning(
            "[Orchestrator] Gemini mode requested but GEMINI_API_KEY is not set. "
            "Falling back to mock mode."
        )
        effective_mode = "mock"

    if effective_mode and effective_mode in ("mock", "gemini"):
        config.LLM_PROVIDER = effective_mode
        import services.llm_service as llm_svc
        llm_svc.LLM_PROVIDER = effective_mode

    pipeline_start = time.time()

    # Agent step logs for transparency
    agent_logs = []

    def log_step(agent_name: str, status: str, detail: Any = None):
        entry = {
            "agent": agent_name,
            "status": status,
            "detail": detail,
            "timestamp_ms": round((time.time() - pipeline_start) * 1000, 2),
        }
        agent_logs.append(entry)
        logger.info("[Orchestrator] %s → %s", agent_name, status)

    try:
        # ════════════════════════════════════════════
        # STEP 1: Planner Agent
        # ════════════════════════════════════════════
        plan = planner.run(query)
        log_step("Planner Agent", "completed", {
            "intent": plan.get("intent"),
            "steps": plan.get("steps"),
            "metrics": plan.get("metrics"),
        })

        # DEBUG: Log planner output
        logger.info("[DEBUG] Query: %s", query)
        logger.info("[DEBUG] Plan intent: %s | metrics: %s | grouping: %s",
                    plan.get('intent'), plan.get('metrics'), plan.get('grouping'))
        logger.info("[DEBUG] Plan steps: %s", plan.get('steps'))

        # ════════════════════════════════════════════
        # STEP 2: RAG Retriever Agent
        # ════════════════════════════════════════════
        rag_context = rag_agent.run(query, plan)
        log_step("RAG Retriever Agent", "completed", {
            "tables_retrieved": rag_context.get("retrieved_tables"),
            "similarity_scores": rag_context.get("similarity_scores"),
        })

        # DEBUG: Log retrieved schema
        logger.info("[DEBUG] RAG tables: %s", rag_context.get('retrieved_tables'))

        # ════════════════════════════════════════════
        # STEP 3 & 4: SQL Generation + Validation (with retry loop)
        # ════════════════════════════════════════════
        sql = None
        validation_result = None
        last_error = None

        for attempt in range(1, MAX_SQL_RETRIES + 1):
            logger.info(
                "[Orchestrator] SQL generation attempt %d/%d",
                attempt, MAX_SQL_RETRIES,
            )

            # Generate SQL
            sql = sql_agent.run(query, plan, rag_context)
            log_step("SQL Generator Agent", f"attempt_{attempt}", {
                "sql": sql,
            })

            # DEBUG: Log generated SQL
            logger.info("[DEBUG] Generated SQL: %s", sql)

            # Validate SQL
            try:
                validation_result = validator.run(
                    sql,
                    retrieved_tables=rag_context.get("retrieved_tables"),
                )
                log_step("Validator Agent", "passed", {
                    "warnings": validation_result.get("warnings", []),
                })
                break  # Validation passed — exit retry loop

            except ValidationError as ve:
                last_error = str(ve)
                log_step("Validator Agent", f"failed_attempt_{attempt}", {
                    "error": last_error,
                    "type": ve.violation_type,
                })

                if ve.violation_type == "security":
                    # Security failures are not retriable
                    return _error_response(
                        query=query,
                        error=f"Security violation: {last_error}",
                        agent_logs=agent_logs,
                        pipeline_time=time.time() - pipeline_start,
                    )

                # Schema errors might be fixed with a retry
                if attempt == MAX_SQL_RETRIES:
                    return _error_response(
                        query=query,
                        error=f"SQL generation failed after {MAX_SQL_RETRIES} attempts: {last_error}",
                        agent_logs=agent_logs,
                        pipeline_time=time.time() - pipeline_start,
                    )

        # ════════════════════════════════════════════
        # STEP 5: Execution Agent
        # ════════════════════════════════════════════
        exec_result = execution.run(sql)
        log_step("Execution Agent", "completed", {
            "row_count": exec_result.get("row_count"),
            "execution_time_ms": exec_result.get("execution_time_ms"),
        })

        if not exec_result["success"]:
            return _error_response(
                query=query,
                error=f"Query execution failed: {exec_result['error']}",
                sql=sql,
                agent_logs=agent_logs,
                pipeline_time=time.time() - pipeline_start,
            )

        # ════════════════════════════════════════════
        # STEP 6: Insight Agent
        # ════════════════════════════════════════════
        insight_text = insight.run(query, sql, exec_result)
        log_step("Insight Agent", "completed", {
            "insight_length": len(insight_text),
        })

        # ════════════════════════════════════════════
        # Build Final Response
        # ════════════════════════════════════════════
        pipeline_time = round(time.time() - pipeline_start, 3)

        response = {
            "success": True,
            "query": query,
            "sql": sql,
            "result": {
                "columns": exec_result["columns"],
                "rows": exec_result["rows"],
                "row_count": exec_result["row_count"],
            },
            "insight": insight_text,
            "llm_mode": config.LLM_PROVIDER,
            "metadata": {
                "pipeline_time_seconds": pipeline_time,
                "execution_time_ms": exec_result["execution_time_ms"],
                "tables_used": rag_context.get("retrieved_tables", []),
                "plan": plan,
                "validation_warnings": (
                    validation_result.get("warnings", []) if validation_result else []
                ),
            },
            "agent_logs": agent_logs,
        }

        logger.info(
            "[Orchestrator] Pipeline completed in %.3f seconds — %d rows returned",
            pipeline_time, exec_result["row_count"],
        )

        return response

    except Exception as e:
        logger.exception("[Orchestrator] Unexpected error in pipeline")
        return _error_response(
            query=query,
            error=f"Unexpected error: {str(e)}",
            agent_logs=agent_logs,
            pipeline_time=time.time() - pipeline_start,
        )
    finally:
        # Restore original LLM provider after request
        config.LLM_PROVIDER = original_provider
        if llm_mode and llm_mode in ("mock", "gemini"):
            import services.llm_service as llm_svc
            llm_svc.LLM_PROVIDER = original_provider


def _error_response(
    query: str,
    error: str,
    sql: str | None = None,
    agent_logs: list = None,
    pipeline_time: float = 0.0,
) -> dict[str, Any]:
    """Build a standardized error response."""
    return {
        "success": False,
        "query": query,
        "sql": sql,
        "result": {
            "columns": [],
            "rows": [],
            "row_count": 0,
        },
        "insight": None,
        "error": error,
        "llm_mode": "mock",
        "metadata": {
            "pipeline_time_seconds": round(pipeline_time, 3),
        },
        "agent_logs": agent_logs or [],
    }
