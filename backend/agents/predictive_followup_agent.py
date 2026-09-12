import logging
import json
import dataclasses
from typing import Any
from services.llm_service import call_llm
from agents import ml_agent
from prediction import service as prediction_service
from prediction.schemas import GroupedForecastingResult, ForecastingResult

logger = logging.getLogger(__name__)

FOLLOWUP_INTENT_PROMPT = """You are a predictive analytics intent resolver.
The user is looking at a machine learning prediction or forecast, and just asked a follow up question.

Original Query: "{original_query}"
Prediction Target: {target}
Prediction Type: {task_type}

Follow-up Question: "{message}"

Determine what the user wants to do. Output a JSON object with:
1. "intent": One of:
   - "rank_highest": User wants to know which group/entity has the highest predicted value (e.g., "Which country has the highest predicted revenue?")
   - "rank_lowest": User wants to know which group/entity has the lowest predicted value.
   - "growth_highest": User wants to know which group has the highest predicted growth.
   - "peak": User wants to know the highest point/date for a specific group (e.g. "When is the peak for Germany?")
   - "change_horizon": User wants to change the forecast horizon (e.g., "What about the next 12 months?")
   - "change_group": User wants to group by a different dimension (e.g., "Break it down by category instead")
   - "change_target": User wants to predict a different metric (e.g., "Predict sales instead")
   - "explain": General question asking to explain the existing prediction further.
2. "new_horizon": (int or null) If intent is change_horizon, extract the new number of periods.
3. "new_frequency": (string or null) e.g., "months", "days", "years".
4. "new_group": (list of strings or null) If intent is change_group, extract the new grouping dimension(s).
5. "new_target": (string or null) If intent is change_target, extract the new target metric.
6. "entity": (string or null) If intent is peak, extract the specific group entity mentioned (e.g. "Germany").

Respond ONLY with the JSON object.
"""

EXPLANATION_PROMPT = """You are a Business Advisor AI.
The user asked: "{message}"
We deterministically calculated the answer based on the prediction model results: {answer_data}

Write a short (1-2 sentences), friendly response giving the user the exact answer. Do not hallucinate or guess.
"""

def run(message: str, context: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    original_query = context.get("query", "")
    result = context.get("result", {})
    pred_data = result.get("prediction", {})
    task_type = result.get("visualization", {}).get("problem_type", "classification")
    if result.get("visualization", {}).get("mode") == "forecast":
        task_type = "forecasting"
        
    target = pred_data.get("target_column", "unknown")

    prompt = FOLLOWUP_INTENT_PROMPT.format(
        original_query=original_query,
        target=target,
        task_type=task_type,
        message=message
    )

    try:
        raw_intent = call_llm(prompt, expect_json=True)
        intent_data = json.loads(raw_intent)
    except Exception as e:
        logger.error(f"Failed to parse followup intent: {e}")
        intent_data = {"intent": "explain"}

    intent = intent_data.get("intent")
    logger.info(f"Predictive Follow-up Intent: {intent}")

    if intent in ("change_horizon", "change_group", "change_target"):
        return _handle_parameter_change(message, intent_data, context)
    elif intent in ("rank_highest", "rank_lowest", "growth_highest", "peak"):
        return _handle_deterministic_calculation(message, intent_data, context)
    else:
        # Default fallback: Just use LLM to explain the existing context
        explanation = _generate_explanation(message, "Look at the provided charts and data to answer.")
        return {"reply": explanation, "new_response": None}

def _handle_parameter_change(message: str, intent_data: dict, context: dict) -> dict:
    original_query = context.get("query", "")
    result = context.get("result", {})
    pred_data = result.get("prediction", {})
    table_name = pred_data.get("table_name") or context.get("table_name")
    
    if not table_name:
        return {"reply": "I need a valid dataset to run this prediction.", "new_response": None}

    # Recover previous parameters
    target = pred_data.get("target_column")
    horizon = pred_data.get("horizon", 12)
    task_type = ml_agent._extract_task_type(original_query) # fallback
    if "group_dimensions" in pred_data:
        task_type = "grouped_forecasting"
        group_hints = pred_data["group_dimensions"]
    else:
        group_hints = []

    # Override parameters
    if intent_data.get("new_target"):
        target = intent_data["new_target"]
    if intent_data.get("new_horizon"):
        horizon = intent_data["new_horizon"]
    if intent_data.get("new_group"):
        group_hints = intent_data["new_group"]
        task_type = "grouped_forecasting"

    frequency = intent_data.get("new_frequency") or "months"

    logger.info(f"Re-running prediction with: target={target}, horizon={horizon}, groups={group_hints}")
    
    try:
        prediction_result = prediction_service.predict_rows(
            table_name=table_name,
            target_col=target,
            task_type=task_type,
            group_hints=group_hints,
            forecast_steps=horizon,
            forecast_frequency=frequency
        )
        
        # Build new response
        pred_dict = dataclasses.asdict(prediction_result)
        viz_metadata = ml_agent._build_visualization_metadata(prediction_result, False, task_type)
        
        new_result = {
            "pipeline_type": "PREDICTIVE",
            "prediction": pred_dict,
            "visualization": viz_metadata,
            "columns": ["metric", "value"],
            "rows": [],
            "row_count": 0
        }
        
        explanation = ml_agent._generate_forecasting_explanation(message, prediction_result, task_type)
        
        return {"reply": explanation, "new_response": {"result": new_result, "insight": explanation}}
        
    except Exception as e:
        logger.exception("Failed to rerun prediction")
        return {"reply": f"I couldn't generate the new prediction: {str(e)}", "new_response": None}


def _handle_deterministic_calculation(message: str, intent_data: dict, context: dict) -> dict:
    pred_data = context.get("result", {}).get("prediction", {})
    intent = intent_data.get("intent")
    
    # We must have predictions
    if "predictions" not in pred_data:
        return {"reply": "I don't have grouped prediction results to answer that.", "new_response": None}
        
    predictions = pred_data["predictions"]
    if not predictions:
        return {"reply": "There are no predictions available to analyze.", "new_response": None}
        
    answer_data = ""
    new_result = None
    
    if intent in ("rank_highest", "rank_lowest", "growth_highest"):
        # Sort predictions
        is_growth = (intent == "growth_highest")
        reverse = intent in ("rank_highest", "growth_highest")
        
        def get_val(p):
            if is_growth:
                hist = p.get("historical", [])
                fcst = p.get("forecast", [])
                if not hist or not fcst: return 0.0
                start_val = hist[-1]["value"]
                end_val = fcst[-1]["value"]
                return ((end_val - start_val) / max(0.0001, abs(start_val))) * 100
            else:
                return float(p.get("final_value") or 0.0)

        sorted_preds = sorted(predictions, key=get_val, reverse=reverse)
        top_pred = sorted_preds[0]
        top_val = get_val(top_pred)
        
        if is_growth:
            answer_data = f"Top group is {top_pred['group']} with {top_val:.1f}% growth."
        else:
            answer_data = f"Group {top_pred['group']} has the value {top_val:,.2f}."
            
        # Update visualization to be a bar chart ranking!
        # Create a dummy GroupedForecastingResult to pass to ml_agent formatter
        dummy_result = GroupedForecastingResult(
            target_column=pred_data.get("target_column", ""),
            date_column=pred_data.get("date_column", ""),
            group_dimensions=pred_data.get("group_dimensions", []),
            horizon=pred_data.get("horizon", 12),
            table_name=pred_data.get("table_name", ""),
            predictions=sorted_preds,
            best_group=top_pred["group"]
        )
        task_type = "growth_analysis" if is_growth else "grouped_ranking"
        viz_metadata = {
            "mode": "forecast",
            "problem_type": "forecasting",
            "charts": [ml_agent._build_grouped_forecasting_ranking_chart(dummy_result, task_type)]
        }
        new_result = context.get("result").copy()
        new_result["prediction"]["predictions"] = sorted_preds
        new_result["visualization"] = viz_metadata
        
    elif intent == "peak":
        entity = intent_data.get("entity")
        target_pred = None
        if entity:
            for p in predictions:
                if entity.lower() in str(p.get("group", "")).lower():
                    target_pred = p
                    break
        if not target_pred:
            target_pred = predictions[0] # fallback
            
        fcst = target_pred.get("forecast", [])
        if not fcst:
            answer_data = f"No forecast data for {target_pred['group']}."
        else:
            peak = max(fcst, key=lambda x: x["value"])
            answer_data = f"The peak for {target_pred['group']} is {peak['value']:,.2f} on {peak['date']}."
            
    explanation = _generate_explanation(message, answer_data)
    
    response_dict = {"reply": explanation}
    if new_result:
        response_dict["new_response"] = {"result": new_result, "insight": explanation}
        
    return response_dict

def _generate_explanation(message: str, answer_data: str) -> str:
    prompt = EXPLANATION_PROMPT.format(message=message, answer_data=answer_data)
    try:
        return call_llm(prompt, expect_json=False).strip()
    except Exception:
        return answer_data
