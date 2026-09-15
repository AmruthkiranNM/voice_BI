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

Determine what the user wants to do. The user may be asking for multiple things at once (e.g. "Why is Australia highest, and will it remain highest next year?").

Output a JSON object with:
1. "intents": An array of intent objects. Each object must have an "intent" field, which is one of:
   - "rank_highest": User wants to know which group/entity has the highest predicted value.
   - "rank_lowest": User wants to know which group/entity has the lowest predicted value.
   - "growth_highest": User wants to know which group has the highest predicted growth.
   - "peak": User wants to know the highest point/date for a specific group.
   - "change_horizon": User wants to change the forecast horizon.
   - "change_group": User wants to group by a different dimension (e.g. from Country to Product).
   - "change_target": User wants to predict a different metric.
   - "explain": General question asking to explain the existing prediction further.
   - "entity_detail": User asks about a specific entity (e.g., "What about India?").
   - "comparison": User asks to compare two entities (e.g., "Compare India with Australia.").
   - "future_comparison": User asks if the current ranking/entity will remain the same in the future (e.g., "Will Australia remain the highest next year?").
   - "hierarchical_forecast": User asks to drill down or forecast an inner dimension for the current entities (e.g., "What about their top products next year?" when currently grouped by country).

For each intent object in the "intents" array, include these additional fields if applicable:
- "new_horizon": (int or null) If intent is change_horizon or future_comparison.
- "new_frequency": (string or null) e.g., "months", "days", "years".
- "new_group": (list of strings or null) If intent is change_group.
- "new_target": (string or null) If intent is change_target.
- "entity": (string or null) If intent is peak, entity_detail, or future_comparison.
- "entities": (list of strings or null) If intent is comparison.
- "new_child_dimension": (string or null) If intent is hierarchical_forecast (e.g., "product").

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
        intent_data = {"intents": [{"intent": "explain"}]}

    intents_list = intent_data.get("intents", [])
    if not intents_list and "intent" in intent_data:
        # Fallback for old LLM output
        intents_list = [intent_data]
        
    logger.info(f"Predictive Follow-up Intents: {[i.get('intent') for i in intents_list]}")

    answers = []
    final_new_result = None
    
    for intent_obj in intents_list:
        intent = intent_obj.get("intent")
        if intent in ("change_horizon", "change_group", "change_target", "future_comparison"):
            res = _handle_parameter_change(message, intent_obj, context)
            answers.append(res.get("_deterministic_text", res.get("reply", "")))
            if res.get("new_response"):
                final_new_result = res["new_response"]["result"]
        elif intent in ("rank_highest", "rank_lowest", "growth_highest", "peak", "entity_detail", "comparison", "explain"):
            res = _handle_deterministic_calculation(message, intent_obj, context)
            answers.append(res.get("_deterministic_text", res.get("reply", "")))
            if res.get("new_response") and not final_new_result:
                final_new_result = res["new_response"]["result"]
        elif intent == "hierarchical_forecast":
            res = _handle_hierarchical_forecast(message, intent_obj, context)
            answers.append(res.get("_deterministic_text", res.get("reply", "")))
            if res.get("new_response") and not final_new_result:
                final_new_result = res["new_response"]["result"]
                
    combined_answer_data = "\n\n".join(answers)
    explanation = _generate_explanation(message, combined_answer_data)
    
    ret = {"reply": explanation}
    if final_new_result:
        ret["new_response"] = {"result": final_new_result, "insight": explanation}
    return ret

def _handle_parameter_change(message: str, intent_data: dict, context: dict) -> dict:
    original_query = context.get("query", "")
    result = context.get("result", {})
    pred_data = result.get("prediction", {})
    table_name = pred_data.get("table_name") or context.get("table_name")
    
    if not table_name:
        sql = context.get("sql", "")
        if sql:
            import re
            match = re.search(r"FROM\s+\[?\"?([a-zA-Z0-9_]+)\"?\]?", sql, re.IGNORECASE)
            if match:
                table_name = match.group(1).strip()
        if not table_name:
            t_names = context.get("table_names")
            if t_names and isinstance(t_names, list) and len(t_names) > 0:
                table_name = t_names[0]
            else:
                table_name = "sales"
    
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
        config = getattr(prediction_result, "config", None) or pred_data.get("_config", {})
        pred_dict["_config"] = dataclasses.asdict(config) if dataclasses.is_dataclass(config) else config
        
        # Context Immutability - Preserve previous results
        context_history = pred_data.get("context_history", [])
        context_history.append({
            "dimensions": pred_data.get("dimensions", []),
            "target": pred_data.get("target_column"),
            "table_name": pred_data.get("table_name"),
            "raw_forecast_results": pred_data.get("raw_forecast_results", []),
            "_config": pred_data.get("_config", {}),
        })
        pred_dict["context_history"] = context_history
        viz_metadata = ml_agent._build_visualization_metadata(prediction_result, False, task_type)
        
        new_result = {
            "pipeline_type": "PREDICTIVE",
            "prediction": pred_dict,
            "visualization": viz_metadata,
            "columns": ["metric", "value"],
            "rows": [],
            "row_count": 0
        }
        
        intent = intent_data.get("intent")
        if intent == "future_comparison":
            # Compare current ranking (from pred_data) with new prediction_result
            current_preds = pred_data.get("predictions", [])
            if current_preds and hasattr(prediction_result, "predictions") and prediction_result.predictions:
                curr_sorted = sorted(current_preds, key=lambda p: float(p.get("final_value") or 0.0), reverse=True)
                new_sorted = sorted(prediction_result.predictions, key=lambda p: float(p.get("final_value") or 0.0), reverse=True)
                
                curr_top = curr_sorted[0]["group"] if curr_sorted else "Unknown"
                new_top = new_sorted[0]["group"] if new_sorted else "Unknown"
                
                entity = intent_data.get("entity")
                
                explanation = f"New forecast generated for {horizon} periods. "
                if curr_top == new_top:
                    explanation += f"{curr_top} is projected to remain the highest ranked group."
                else:
                    explanation += f"The ranking is expected to change. {curr_top} falls from the top spot, and {new_top} takes the lead."
                    
                if entity:
                    # Find entity's new rank
                    for i, p in enumerate(new_sorted, 1):
                        if entity.lower() in str(p["group"]).lower():
                            explanation += f" {p['group']} is predicted to rank #{i} with a value of {float(p.get('final_value') or 0.0):,.2f}."
                            break
            else:
                explanation = ml_agent._generate_forecasting_explanation(message, prediction_result, task_type)
        else:
            explanation = ml_agent._generate_forecasting_explanation(message, prediction_result, task_type)
        
        return {"_deterministic_text": explanation, "reply": explanation, "new_response": {"result": new_result, "insight": explanation}}
        
    except Exception as e:
        logger.exception("Failed to rerun prediction")
        return {"reply": f"I couldn't generate the new prediction: {str(e)}", "new_response": None}


def _handle_deterministic_calculation(message: str, intent_data: dict, context: dict) -> dict:
    pred_data = context.get("result", {}).get("prediction", {})
    intent = intent_data.get("intent")
    
    # We must have predictions
    predictions = pred_data.get("raw_forecast_results", pred_data.get("predictions"))
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
                
                horizon = len(fcst)
                baseline_len = min(len(hist), horizon)
                baseline_total = sum(r.get("value") or 0.0 for r in hist[-baseline_len:])
                forecast_total = sum(r.get("value") or 0.0 for r in fcst)
                
                if baseline_total and baseline_total > 0:
                    return ((forecast_total - baseline_total) / baseline_total) * 100
                return 0.0
            else:
                return float(p.get("final_value") or 0.0)

        sorted_preds = sorted(predictions, key=get_val, reverse=reverse)
        top_pred = sorted_preds[0]
        top_val = get_val(top_pred)
        
        group_val = top_pred.get("group", "Unknown Group")
        
        if is_growth:
            answer_data = f"Top group is {group_val} with {top_val:.1f}% growth."
        else:
            answer_data = f"Group {group_val} has the value {top_val:,.2f}."
            
        # Update visualization to be a bar chart ranking!
        # Do not destroy the raw forecast results. Instead, pass insights through derived_insights.
        task_type = "growth_analysis" if is_growth else "grouped_ranking"
        
        # We need a dummy structure that ml_agent's chart builder accepts, or we update the builder
        # But we must NOT mutate new_result["prediction"]["predictions"].
        class DummyResult:
            pass
        dummy = DummyResult()
        dummy.forecast_ranking = sorted_preds
        dummy.dimensions = pred_data.get("dimensions", [])
        dummy.target_column = pred_data.get("target_column", "")
        
        viz_metadata = {
            "mode": "forecast",
            "problem_type": "forecasting",
            "charts": [ml_agent._build_grouped_forecasting_ranking_chart(dummy, task_type)]
        }
        
        new_result = context.get("result").copy()
        # Create a deep-ish copy of prediction to avoid mutating the original
        new_result["prediction"] = {**pred_data}
        new_result["prediction"]["derived_insights"] = {
            "task_type": task_type,
            "sorted_preds": sorted_preds
        }
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
            
    elif intent == "entity_detail":
        entity = intent_data.get("entity")
        if not entity:
            answer_data = "I'm not sure which entity you are asking about."
        else:
            found = next((p for p in predictions if entity.lower() in str(p.get("group", "")).lower()), None)
            if found:
                answer_data = f"For {found['group']}, the predicted value is {float(found.get('final_value') or 0.0):,.2f}."
            else:
                answer_data = f"I couldn't find {entity} in the prediction results."
                
    elif intent == "comparison":
        entities = intent_data.get("entities", [])
        if len(entities) >= 2:
            e1 = next((p for p in predictions if entities[0].lower() in str(p.get("group", "")).lower()), None)
            e2 = next((p for p in predictions if entities[1].lower() in str(p.get("group", "")).lower()), None)
            
            if e1 and e2:
                v1 = float(e1.get("final_value") or 0.0)
                v2 = float(e2.get("final_value") or 0.0)
                diff = abs(v1 - v2)
                higher = e1['group'] if v1 > v2 else e2['group']
                answer_data = f"{e1['group']} is predicted at {v1:,.2f} and {e2['group']} at {v2:,.2f}. {higher} is higher by {diff:,.2f}."
            else:
                answer_data = "I couldn't find both entities to compare."
        else:
            answer_data = "I need at least two entities to compare."
            
    elif intent == "explain":
        answer_data = "The user asked for a general explanation of the current prediction."
            
    response_dict = {"_deterministic_text": answer_data, "reply": answer_data}
    if new_result:
        response_dict["new_response"] = {"result": new_result, "insight": answer_data}
        
    return response_dict

def _generate_explanation(message: str, answer_data: str) -> str:
    prompt = EXPLANATION_PROMPT.format(message=message, answer_data=answer_data)
    try:
        return call_llm(prompt, expect_json=False).strip()
    except Exception:
        return answer_data


def _handle_hierarchical_forecast(message: str, intent_data: dict, context: dict) -> dict:
    original_query = context.get("query", "")
    result = context.get("result", {})
    pred_data = result.get("prediction", {})
    table_name = pred_data.get("table_name") or context.get("table_name")
    
    if not table_name:
        return {"reply": "I need a valid dataset to run this prediction.", "new_response": None}

    parent_dims = pred_data.get("dimensions", [])
    if not parent_dims:
        parent_dims = ["country"] # fallback
        
    child_dim = intent_data.get("new_child_dimension") or "product"
    
    # Avoid duplicate dims
    target_dims = parent_dims.copy()
    if child_dim not in target_dims:
        target_dims.append(child_dim)
        
    target = pred_data.get("target_column")
    horizon = pred_data.get("horizon", 12)
    frequency = "months"
    
    logger.info(f"Hierarchical Forecast: parents={parent_dims}, child={child_dim}, new_dims={target_dims}")
    
    try:
        prediction_result = prediction_service.predict_rows(
            table_name=table_name,
            target_col=target,
            task_type="grouped_forecasting",
            group_hints=target_dims,
            forecast_steps=horizon,
            forecast_frequency=frequency
        )
        
        # Build hierarchy
        preds = getattr(prediction_result, "raw_forecast_results", [])
        
        # Group by parent dimensions
        hierarchy = {}
        for p in preds:
            group_dict = p.get("group_dict", {})
            # Parent key
            parent_key_parts = [str(group_dict.get(d, "Unknown")) for d in parent_dims]
            parent_key = " - ".join(parent_key_parts)
            
            child_val = str(group_dict.get(child_dim, "Unknown"))
            
            if parent_key not in hierarchy:
                hierarchy[parent_key] = []
                
            hierarchy[parent_key].append({
                "child": child_val,
                "final_value": float(p.get("final_value") or 0.0),
                "forecast": p.get("forecast", [])
            })
            
        # Sort children
        explanation_parts = []
        top_hierarchical_preds = []
        for parent_key, children in hierarchy.items():
            children.sort(key=lambda x: x["final_value"], reverse=True)
            top_children = children[:3]
            
            part = f"**{parent_key}**:\n"
            for i, c in enumerate(top_children, 1):
                part += f"{i}. {c['child']} — {c['final_value']:,.2f}\n"
                
                # Add to a flat list for visualization
                top_hierarchical_preds.append({
                    "group": f"{parent_key} - {c['child']}",
                    "final_value": c['final_value'],
                    "historical": [],
                    "forecast": c['forecast']
                })
            explanation_parts.append(part)
            
        explanation = "Here are the top products forecasted for each group next year:\n\n" + "\n".join(explanation_parts)
        
        # Update visualization to use the derived_insights
        pred_dict = dataclasses.asdict(prediction_result)
        
        class DummyResult:
            pass
        dummy = DummyResult()
        dummy.forecast_ranking = top_hierarchical_preds
        dummy.dimensions = target_dims
        dummy.target_column = target
        
        viz_metadata = {
            "mode": "forecast",
            "problem_type": "forecasting",
            "charts": [ml_agent._build_grouped_forecasting_ranking_chart(dummy, "grouped_ranking")]
        }
        
        new_result = context.get("result").copy()
        new_result["prediction"] = pred_dict
        new_result["prediction"]["derived_insights"] = {
            "task_type": "hierarchical_ranking",
            "hierarchy": hierarchy
        }
        new_result["visualization"] = viz_metadata
        
        return {"_deterministic_text": explanation, "reply": explanation, "new_response": {"result": new_result, "insight": explanation}}
        
    except Exception as e:
        logger.exception("Failed to run hierarchical forecast")
        return {"reply": f"I couldn't generate the hierarchical prediction: {str(e)}", "new_response": None}
