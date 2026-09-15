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

def _forecast_evidence(prediction_result, target: str | None, horizon: int) -> str:
    """Deterministic evidence lines describing a forecast result."""
    from agents import forecast_comparison as fc

    ranked = fc.extract_forecast_ranking(prediction_result)
    dims = getattr(prediction_result, "dimensions", None) or []
    label = " and ".join(dims) if dims else "group"
    lines = [
        f"FORECAST: {target or getattr(prediction_result, 'target_column', 'the measure')} "
        f"over the next {horizon} periods, by {label}.",
    ]
    meta = getattr(prediction_result, "model_metadata", None)
    if meta is not None:
        lines.append(
            f"MODEL: {getattr(meta, 'selected_model_label', 'selected model')} "
            f"({getattr(meta, 'selection_method', 'selected')})."
        )
    if ranked:
        lines.append("RANKED FORECAST TOTALS:")
        for e in ranked[:5]:
            lines.append(f"  {e.rank}. {e.group}: {e.value:,.2f}")
        lines.append(f"({len(ranked)} groups were forecast and ranked.)")
    else:
        lines.append("No group produced a forecast.")
    return "\n".join(lines)

def run(message: str, context: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    result = context.get("result", {})

    # ── Generic path ──
    # When the previous turn carried a PredictionConfig, the follow-up is just
    # another question resolved against it: the resolver inherits every slot
    # and overrides only what this question restates. Target switches,
    # dimension switches and horizon switches are all the same operation, so
    # none of them needs its own handler.
    stored_config = result.get("config") or context.get("prediction_config")
    if stored_config:
        from agents import prediction_agent

        scope = context.get("table_names") or (
            [context["table_name"]] if context.get("table_name") else None
        )
        outcome = prediction_agent.run(
            message, table_names=scope, inherited_config=stored_config,
        )
        return {
            "reply": outcome.get("insight", ""),
            "new_response": {
                "result": outcome.get("result", {}),
                "insight": outcome.get("insight", ""),
            },
        }

    # ── Legacy path ──
    # Results produced before configs were carried still resolve through the
    # original intent handlers.
    original_query = context.get("query", "")
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

    # ── Inherit the previous prediction's configuration ──
    # Every slot is carried forward from the result the user is looking at, and
    # only the slots the follow-up actually names are overridden. Re-deriving
    # the task type from the *original* question is what previously broke a
    # target switch: "Which country generated the most revenue?" parses as a
    # non-forecasting question, so "what about boxes sold?" inherited that and
    # sent a continuous measure into a per-row pipeline.
    target = pred_data.get("target_column")
    horizon = pred_data.get("horizon") or 12
    frequency = (pred_data.get("series_diagnostics") or {}).get("requested_frequency") or "months"
    ranking_metric = pred_data.get("ranking_metric") or "sum"

    # The result records what kind of prediction it was; trust that over a
    # re-parse of stale text. `dimensions` is the real field name — the old
    # code looked for `group_dimensions`, which never exists, so grouped
    # follow-ups silently lost their dimensions.
    task_type = pred_data.get("task_type") or "forecasting"
    group_hints = list(pred_data.get("dimensions") or [])
    if group_hints and task_type in ("forecasting", "grouped_forecasting"):
        task_type = "grouped_forecasting"

    # ── Apply only what this follow-up changed ──
    if intent_data.get("new_target"):
        target = intent_data["new_target"]
    if intent_data.get("new_horizon"):
        horizon = intent_data["new_horizon"]
    if intent_data.get("new_frequency"):
        frequency = intent_data["new_frequency"]
    if intent_data.get("new_group"):
        group_hints = intent_data["new_group"]
        task_type = "grouped_forecasting"

    # A question about the future stays about the future even when the measure
    # changes. The service re-validates this against the column itself, so a
    # measure can never end up in a classifier.
    if intent_data.get("intent") == "future_comparison" and task_type == "classification":
        task_type = "grouped_forecasting" if group_hints else "forecasting"

    logger.info(
        "Follow-up prediction config: target=%s task=%s dims=%s horizon=%s freq=%s",
        target, task_type, group_hints, horizon, frequency,
    )

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
            # Compare the ranking the user is looking at against the new
            # forecast, deterministically and over ALL eligible groups.
            from agents import forecast_comparison as fc

            current = fc.extract_forecast_ranking(pred_data)
            future = fc.extract_forecast_ranking(prediction_result)

            if future:
                top_n = max(1, min(3, len(future)))
                comparison = fc.compare_rankings(
                    current, future, top_n=top_n,
                    n_excluded=len(getattr(prediction_result, "excluded_groups", None) or []),
                )
                dimension_label = (group_hints or ["group"])[0]
                explanation = fc.format_comparison(
                    comparison, target=target or "the measure",
                    dimension_label=dimension_label,
                    horizon_label=f"the next {horizon} periods",
                )
                entity = intent_data.get("entity")
                if entity:
                    match = next(
                        (e for e in future if entity.lower() in e.group.lower()), None,
                    )
                    if match:
                        explanation += (
                            f"\n  {match.group} is forecast at {match.value:,.2f}, "
                            f"ranked {match.rank} of {len(future)}."
                        )
            else:
                explanation = _forecast_evidence(prediction_result, target, horizon)
        else:
            explanation = _forecast_evidence(prediction_result, target, horizon)

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
    """
    Phrase the deterministic answer, and verify the phrasing before returning.

    The numbers were already computed; the model only writes them up. Anything
    it adds that is not in the evidence — an invented figure or a reason for
    the trend — invalidates the wording and the deterministic text is returned
    instead.
    """
    from agents import explanation as explanation_layer

    return explanation_layer.explain(message, answer_data, fallback=answer_data)


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
