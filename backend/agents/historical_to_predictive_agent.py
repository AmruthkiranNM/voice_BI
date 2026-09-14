import logging
import json
import dataclasses
from collections import defaultdict
from typing import Any

from services.llm_service import call_llm
from prediction import service as prediction_service
from agents import ml_agent

logger = logging.getLogger(__name__)

DIMENSION_EXTRACTION_PROMPT = """You are a Semantic Data Resolver extracting forecasting parameters from a previous historical query.

Original Question: "{original_query}"
Columns in Data: {columns}

Extract the forecasting parameters so we can run a predictive model.
1. "target": The numerical column representing the target metric to forecast (e.g., "AMOUNT", "revenue", "sales"). Must be a column name from the list.
2. "group_dimensions": An array of column names used to group the data (e.g., ["GEO", "PRODUCT"] or ["country"]). Must be column names from the list.
3. "horizon": Number of periods to forecast (e.g., 12). If the user just says "next year", assume 12 periods (months).
4. "frequency": "months", "days", or "years". (Default "months").

Respond ONLY with a JSON object:
{{
  "target": "COLUMN_NAME",
  "group_dimensions": ["COL1", "COL2"],
  "horizon": 12,
  "frequency": "months"
}}
"""

EXPLANATION_PROMPT = """You are a Business Advisor AI.

The user asked: "{message}"

We have calculated the explanation deterministically using actual historical data, and ran a forecast model to get the future ranking.

CURRENT OBSERVED EXPLANATION (SECTION 1):
{diagnostic_text}

FUTURE FORECAST EXPLANATION (SECTION 2):
{forecast_text}

Write a seamless, 2-section response answering both parts of the user's question ("Why is it like this..." and "...will it be the same next year?").

RULES:
1. ONLY use the actual numerical values provided in the explanations above.
2. DO NOT invent causal claims (e.g., "better marketing"). Distinguish between "observed data" and "causal reasons". Say something like "These figures show the observed revenue distribution, but revenue data alone does not establish why customers purchased these products."
3. Make sure it reads smoothly but remains grounded entirely in the deterministic data provided.

Write the final response now:
"""

def run(message: str, context: dict[str, Any], history: list[dict[str, str]] | None = None) -> dict[str, Any] | str:
    logger.info("[HistoricalToPredictive] Entering compound diagnostic+predictive routing")
    
    original_query = context.get("query", "")
    result = context.get("result", {})
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    
    def _resolve_table_name(ctx: dict) -> str:
        t_name = ctx.get("table_name")
        if t_name:
            return t_name
            
        sql = ctx.get("sql", "")
        if sql:
            import re
            match = re.search(r"FROM\s+\[?\"?([a-zA-Z0-9_]+)\"?\]?", sql, re.IGNORECASE)
            if match:
                return match.group(1).strip()
                
        t_names = ctx.get("table_names")
        if t_names and isinstance(t_names, list) and len(t_names) > 0:
            return t_names[0]
            
        return "sales"
        
    table_name = _resolve_table_name(context)
    
    if not table_name:
        return "I couldn't determine the correct dataset to run the forecast."
    
    if not rows or not columns:
        return "I don't have enough historical data to generate a forecast."

    # 1. Extract Dimensions
    col_str = ", ".join(columns)
    prompt = DIMENSION_EXTRACTION_PROMPT.format(original_query=original_query, columns=col_str)
    try:
        ext_reply = call_llm(prompt, expect_json=True)
        params = json.loads(ext_reply)
    except Exception as e:
        logger.error(f"[HistoricalToPredictive] Extraction failed: {e}")
        return "I couldn't determine the correct dimensions to run the forecast."

    target_col = params.get("target")
    group_dims = params.get("group_dimensions", [])
    horizon = params.get("horizon", 12)
    freq = params.get("frequency", "months")

    if not target_col or target_col not in columns:
        # Fallback to the first numeric-looking column, or last column
        target_col = columns[-1]

    # 2. Diagnostic Phase (Calculate from current rows)
    diagnostic_text = _calculate_diagnostics(rows, target_col, group_dims)
    
    # Identify current Top 1 group for the primary dimension
    primary_dim = group_dims[0] if group_dims else None
    current_ranking = []
    if primary_dim:
        sums = defaultdict(float)
        for r in rows:
            try:
                val = float(r.get(target_col, 0) or 0)
                sums[str(r.get(primary_dim, "Unknown"))] += val
            except ValueError:
                pass
        current_ranking = sorted(sums.items(), key=lambda x: x[1], reverse=True)

    # 3. Forecast Phase
    try:
        prediction_result = prediction_service.predict_rows(
            table_name=table_name,
            target_col=target_col,
            task_type="grouped_forecasting" if group_dims else "forecasting",
            group_hints=group_dims,
            forecast_steps=horizon,
            forecast_frequency=freq
        )
    except Exception as e:
        logger.error(f"[HistoricalToPredictive] Forecast failed: {e}")
        return f"I couldn't run the forecast: {e}"

    # 4. Compare Current vs Future
    forecast_text = _calculate_forecast_comparison(prediction_result, current_ranking, group_dims, target_col)

    # 5. LLM Synthesis
    synthesis_prompt = EXPLANATION_PROMPT.format(
        message=message,
        diagnostic_text=diagnostic_text,
        forecast_text=forecast_text
    )
    
    try:
        final_answer = call_llm(synthesis_prompt, expect_json=False)
    except Exception as e:
        logger.error(f"[HistoricalToPredictive] Synthesis failed: {e}")
        final_answer = f"{diagnostic_text}\n\n{forecast_text}"

    # 6. Build new Response
    pred_dict = dataclasses.asdict(prediction_result)
    viz_metadata = ml_agent._build_visualization_metadata(prediction_result, False, "grouped_forecasting" if group_dims else "forecasting")
    
    new_result = {
        "pipeline_type": "PREDICTIVE",
        "prediction": pred_dict,
        "visualization": viz_metadata,
        "columns": ["metric", "value"],
        "rows": [],
        "row_count": 0
    }

    return {
        "reply": final_answer.strip(),
        "new_response": {"result": new_result, "insight": final_answer.strip()}
    }


def _calculate_diagnostics(rows: list[dict], target_col: str, group_dims: list[str]) -> str:
    """Deterministically aggregate the historical rows to explain 'Why is it like this'."""
    if not group_dims:
        return f"The total {target_col} observed is {sum(float(r.get(target_col, 0) or 0) for r in rows):,.2f}."

    primary_dim = group_dims[0]
    has_secondary = len(group_dims) > 1
    secondary_dim = group_dims[1] if has_secondary else None

    # Aggregate
    primary_totals = defaultdict(float)
    primary_to_secondary = defaultdict(lambda: defaultdict(float))

    for r in rows:
        try:
            val = float(r.get(target_col, 0) or 0)
        except (ValueError, TypeError):
            continue
            
        p_val = str(r.get(primary_dim, "Unknown"))
        primary_totals[p_val] += val
        
        if has_secondary:
            s_val = str(r.get(secondary_dim, "Unknown"))
            primary_to_secondary[p_val][s_val] += val

    sorted_primary = sorted(primary_totals.items(), key=lambda x: x[1], reverse=True)
    if not sorted_primary:
        return "No valid numerical data was found to diagnose."

    lines = ["CURRENT OBSERVED RANKING & DIAGNOSTICS:"]
    for i, (p_name, p_total) in enumerate(sorted_primary[:3], 1):
        lines.append(f"{i}. {p_name}: Total {target_col} = {p_total:,.2f}")
        
        if has_secondary:
            sorted_sec = sorted(primary_to_secondary[p_name].items(), key=lambda x: x[1], reverse=True)
            if sorted_sec:
                top_sec_name, top_sec_val = sorted_sec[0]
                lines.append(f"   - Top {secondary_dim}: {top_sec_name} ({top_sec_val:,.2f})")
                top_3_sum = sum(v for k, v in sorted_sec[:3])
                lines.append(f"   - Top 3 {secondary_dim} contribution: {top_3_sum:,.2f}")

    return "\n".join(lines)


def _calculate_forecast_comparison(prediction_result, current_ranking: list[tuple[str, float]], group_dims: list[str], target_col: str) -> str:
    """Deterministically extract the forecast ranking and compare it."""
    if not hasattr(prediction_result, "predictions"):
        return "The forecast model did not return group-level predictions to compare."

    # Sort forecast predictions
    preds = prediction_result.predictions
    sorted_preds = sorted(preds, key=lambda p: float(p.get("final_value") or 0.0), reverse=True)
    
    lines = ["FUTURE FORECAST RANKING:"]
    
    if not sorted_preds:
        return "No forecast results available."
        
    for i, p in enumerate(sorted_preds[:3], 1):
        lines.append(f"{i}. {p['group']}: Predicted {target_col} = {float(p.get('final_value') or 0.0):,.2f}")

    if current_ranking and sorted_preds:
        curr_top = current_ranking[0][0]
        fut_top = sorted_preds[0]['group']
        if curr_top == fut_top:
            lines.append(f"\nCOMPARISON: {curr_top} remains the #1 ranked group in the forecast.")
        else:
            lines.append(f"\nCOMPARISON: Ranking changes! {curr_top} falls from #1, and {fut_top} takes the lead.")
            
    return "\n".join(lines)
