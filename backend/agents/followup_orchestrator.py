import logging
import json
from typing import Any

from services.llm_service import call_llm
from agents.orchestrator import process_query

logger = logging.getLogger(__name__)

RESOLVER_PROMPT_TEMPLATE = """You are a Semantic Data Resolver. Your job is to resolve conversational follow-up questions into standalone analytical questions that can be queried independently against a database.

PREVIOUS CONTEXT:
Original Question: "{original_query}"
Previous Data Returned:
{results_text}

USER'S FOLLOW-UP:
"{message}"

INSTRUCTIONS:
1. Identify what the user is referring to (e.g. "those", "them", "the top two").
2. Look at the Previous Data Returned to figure out the exact entities they mean.
3. Replace the pronouns with the literal entity names in a new, fully self-contained question.
4. Keep any metrics, dimensions, or filters from the original question if the user hasn't changed them (e.g., if original was "sales in 2003" and follow up is "what about 2004?", the resolved question is "What were the sales in 2004?").
5. Determine if a new database query is needed (true for data, ranking, numerical questions; false if they just ask for a summary of the already visible data).

Return ONLY a JSON object with this exact structure:
{{
  "type": "FILTER_REFINEMENT" | "ENTITY_REFERENCE" | "COMPARISON" | "EXPLANATION" | "NEW_INDEPENDENT_QUESTION" | "NO_NEW_DATA",
  "resolved_question": "The standalone, explicit question with all entities named",
  "needs_new_query": true/false
}}
"""

STRICT_ANSWER_PROMPT = """You are a Data Analyst answering a follow-up question.
You MUST base your answer ONLY on the data rows below. Do not guess, do not estimate, and do not use outside knowledge.

Original Follow-up Question: "{message}"
Resolved Question executed against DB: "{resolved_question}"

Query Result Rows:
{new_results_text}

RULES:
1. If there are no rows, respond EXACTLY: "I couldn't determine that reliably from the available data."
2. State the final answer clearly based on the rows.
3. Do not mention that you ran a query. Just answer the question.

Write your final answer now:"""

def _format_results(rows: list[dict], max_rows: int = 15) -> str:
    if not rows:
        return "No results."
    display_rows = rows[:max_rows]
    lines = []
    for i, row in enumerate(display_rows, 1):
        lines.append(" | ".join(f"{k}: {v}" for k, v in row.items()))
    return "\n".join(lines)


def run_followup(message: str, context: dict[str, Any], history: list[dict[str, str]] | None = None) -> str:
    import uuid
    req_id = str(uuid.uuid4())[:8]
    logger.info(f"[FOLLOWUP:{req_id}] 04 backend endpoint entered")
    
    result = context.get("result") or {}
    rows = result.get("rows", [])
    
    # 1. Resolve context
    prompt = RESOLVER_PROMPT_TEMPLATE.format(
        original_query=context.get("query", ""),
        results_text=_format_results(rows, max_rows=15),
        message=message
    )
    
    logger.info(f"[FOLLOWUP:{req_id}] 08 reference resolution started")
    resolver_reply = call_llm(prompt, expect_json=True)
    logger.info(f"[FOLLOWUP:{req_id}] 09 reference resolution completed")
    
    try:
        if isinstance(resolver_reply, str):
            parsed = json.loads(resolver_reply)
        else:
            parsed = resolver_reply
    except Exception:
        parsed = {"resolved_question": message, "needs_new_query": True}
        
    resolved_question = parsed.get("resolved_question", message)
    needs_new_query = parsed.get("needs_new_query", True)
    
    logger.info(f"[FOLLOWUP:{req_id}] 09b Resolved Question: {resolved_question}, needs_new_query: {needs_new_query}")
    
    if not needs_new_query:
        from agents.chat import run as run_chat
        return run_chat(message, context, history)
        
    # 2. Execute new query using Orchestrator
    try:
        logger.info(f"[FOLLOWUP:{req_id}] 10 query planning started")
        scope = context.get("table_names") or (
            [context["table_name"]] if context.get("table_name") else None
        )
        new_result = process_query(
            resolved_question,
            fast_mode=False,
            skip_insight=True,
            table_names=scope,
        )
        logger.info(f"[FOLLOWUP:{req_id}] 16 result validation completed")
        
        if not new_result["success"]:
            logger.error(f"[FOLLOWUP:{req_id}] Query failed: {new_result.get('error')}")
            return "I couldn't process that follow-up due to a query error. Please try again."
            
        new_rows = new_result["result"].get("rows", [])
        
        # 3. Grounded Answer Generation
        logger.info(f"[FOLLOWUP:{req_id}] 17 answer generation started")
        answer_prompt = STRICT_ANSWER_PROMPT.format(
            message=message,
            resolved_question=resolved_question,
            new_results_text=_format_results(new_rows, max_rows=20)
        )
        
        final_answer = call_llm(answer_prompt, expect_json=False).strip()
        logger.info(f"[FOLLOWUP:{req_id}] 18 answer generation completed")
        return final_answer
        
    except Exception as e:
        logger.exception(f"[FOLLOWUP:{req_id}] Orchestration failed")
        return "I couldn't determine that reliably from the available data."
