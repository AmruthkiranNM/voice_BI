"""
ML Agent

Orchestrates the predictive analytics pipeline:
  1. Parses the user's natural-language question to extract entity identifiers
     (e.g. customer ID) and the prediction target.
  2. Determines which table/dataset to use.
  3. Calls the prediction.service facade for inference.
  4. Generates a natural-language explanation of the prediction.

This agent is invoked by the Orchestrator when the Router classifies
a query as PREDICTIVE.
"""

import dataclasses
import logging
import re
from typing import Any

from services.llm_service import call_llm
from services.database import get_all_table_names, get_table_schema

logger = logging.getLogger(__name__)


# ── Tables that are likely to contain ML-ready data ──
_ML_TABLE_HINTS = [
    "churn", "customer", "exited", "attrition", "subscriber",
    "sales", "revenue", "price", "salary", "employee",
]


def _find_ml_table() -> str | None:
    """
    Scan the user's database for a table that looks suitable for
    classification / churn prediction.
    """
    tables = get_all_table_names()
    for table in tables:
        name_lower = table.lower()
        if any(hint in name_lower for hint in _ML_TABLE_HINTS):
            return table

    # Fallback: look for a table with a binary 'exited' or 'churn' column
    for table in tables:
        schema = get_table_schema(table)
        col_names = [c["column_name"].lower() for c in schema]
        if "exited" in col_names or "churn" in col_names or "churned" in col_names:
            return table

    return None


def _extract_customer_id(query: str) -> str | None:
    """
    Try to pull a customer/user ID from the query text.
    Examples:
      - "Will customer 15634602 churn?"
      - "Predict churn for user ID 123"
      - "What is the churn probability for customer #456?"
    """
    patterns = [
        r"(?:customer|user|client|id)\s*(?:#|number|no\.?)?\s*(\d+)",
        r"#\s*(\d+)",
        r"\b(\d{5,})\b",  # Any long number likely to be an ID
    ]
    for pat in patterns:
        match = re.search(pat, query, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_target_hint(query: str) -> str | None:
    """
    Try to extract a target metric from the query.
    """
    # 1. Check explicit keywords first
    keywords = ["sales", "revenue", "amount", "customers", "boxes", "salary", "churn", "exited"]
    for kw in keywords:
        if re.search(rf"\b{kw}\b", query, re.IGNORECASE):
            return kw
            
    # 2. Fallback to patterns
    patterns = [
        r"predict\s+(?:the\s+)?(?:number\s+of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+){0,3})",
        r"forecast\s+(?:the\s+)?(?:number\s+of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+){0,3})",
        r"estimate\s+(?:the\s+)?(?:number\s+of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+){0,3})",
    ]
    stop_words = {"for", "of", "the", "this", "a", "an", "my", "our", "customer", "user", "churn", "next", "in", "over"}
    
    for pat in patterns:
        match = re.search(pat, query, re.IGNORECASE)
        if match:
            raw = match.group(1).strip().lower()
            words = raw.split()
            # Remove stop words from the END
            while words and words[-1] in stop_words:
                words.pop()
            # Remove stop words from the START
            while words and words[0] in stop_words:
                words.pop(0)
                
            if words:
                return " ".join(words)
                
    return None


def _extract_forecast_horizon(query: str) -> tuple[int, str] | None:
    """
    Try to extract how many periods to forecast from the query, and the temporal unit.
    Returns: (horizon, unit)
    """
    patterns = [
        r"next\s+(\d+)\s+(days|months|years|periods|weeks)",
        r"forecast\s+(\d+)\s+(days|months|years|periods|weeks)",
    ]
    for pat in patterns:
        match = re.search(pat, query, re.IGNORECASE)
        if match:
            return int(match.group(1)), match.group(2).lower()
    
    # Textual numbers
    text_nums = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "twelve": 12}
    for word, num in text_nums.items():
        match = re.search(rf"next\s+{word}\s+(days|months|years|periods|weeks)", query, re.IGNORECASE)
        if match:
            return num, match.group(1).lower()
            
    # Default fallback if unit is found without number
    match = re.search(r"next\s+(day|month|year|period|week)", query, re.IGNORECASE)
    if match:
        unit = match.group(1).lower()
        return 1, f"{unit}s"
            
    # Default overall
    return None


def _extract_task_type(query: str) -> str:
    """
    Identify the specific predictive task type from the query.
    """
    q = query.lower()
    
    if re.search(r"increase\s+or\s+decrease|go\s+up\s+or\s+down|trend", q):
        return "trend_direction_forecast"
        
    has_group = bool(re.search(r"\b(each|every|by|which)\b", q))
    has_rank = bool(re.search(r"\b(highest|lowest|most|least|top|bottom|strongest|weakest)\b", q))
    has_forecast = bool(re.search(r"\b(forecast|predict\s+next|future|next\s+(day|month|year|period|week))\b", q))
    
    if has_group and has_rank and has_forecast:
        if bool(re.search(r"\bgrowth\b", q)):
            return "growth_analysis"
        return "grouped_ranking"
    elif has_group and has_forecast:
        return "grouped_forecasting"
    elif has_forecast:
        return "forecasting"
        
    return "classification"


def _normalize_group_phrase(phrase: str) -> str:
    """Strip grammatical connectors from a phrase."""
    # Remove leading operators
    phrase = re.sub(r"^(?:for each|for every|within each|in each|across|by|per|for)\s+", "", phrase, flags=re.IGNORECASE)
    # Remove trailing operators if accidentally captured (like "country for")
    phrase = re.sub(r"\s+(?:for|in|is|will|likely|has)$", "", phrase, flags=re.IGNORECASE)
    return phrase.strip()


def _extract_group_hints(query: str) -> list[str]:
    """
    Extract the grouping dimensions from queries and return as a list.
    Handles multiple dimensions e.g. "by country and product category" -> ["country", "product category"]
    """
    patterns = [
        r"(?:for each|for every|within each|in each|across|by|per)\s+([a-zA-Z_\s]+?(?:\s+and\s+[a-zA-Z_\s]+?)?)(?=\s+(?:for|in|is|will|likely|has|over|next|month|year|highest|lowest|$))",
        r"which\s+([a-zA-Z_\s]+?(?:\s+and\s+[a-zA-Z_\s]+?)?)\s+(?:is|will|likely|has)",
    ]
    
    for pat in patterns:
        match = re.search(pat, query, re.IGNORECASE)
        if match:
            raw = match.group(1).strip().lower()
            
            # Split by "and" or ","
            parts = re.split(r"\s+and\s+|,", raw)
            
            dims = []
            for part in parts:
                clean = _normalize_group_phrase(part)
                if clean:
                    dims.append(clean)
            if dims:
                return dims
    return []



def _generate_explanation(query: str, prediction_result) -> str:
    """
    Use the LLM to produce a friendly, non-technical explanation
    of the ML prediction result.
    """
    predictions = prediction_result.predictions
    if not predictions:
        return "No prediction could be made for the given input."

    pred = predictions[0]
    row_data = pred.row_data
    feature_impacts = pred.feature_impacts

    # Determine format based on problem type (classification vs regression)
    if pred.probability is not None:
        # Classification
        predicted_value_text = f"{pred.probability:.1%} probability (Risk: {pred.risk})"
        quality_metric_text = f"Accuracy: {prediction_result.model_accuracy}"
    else:
        # Regression
        predicted_value_text = f"{pred.prediction:,.2f}"
        quality_metric_text = f"R² Score: {prediction_result.model_accuracy}"

    # Build a concise feature-impact summary
    impact_lines = []
    for fi in feature_impacts[:5]:
        impact_lines.append(f"  - {fi['feature']}: importance={fi['importance']}, value={fi['value']}")
    impact_text = "\n".join(impact_lines) if impact_lines else "  (no feature details available)"

    # Build a concise row summary (exclude very long fields)
    row_summary_parts = []
    for k, v in list(row_data.items())[:10]:
        row_summary_parts.append(f"{k}: {v}")
    row_summary = ", ".join(row_summary_parts)

    prompt = f"""You are a Business Advisor AI. A prediction model has analyzed data.

The user asked: "{query}"

PREDICTION RESULT:
- Predicted value: {predicted_value_text}
- Model quality metric: {quality_metric_text}

DATA:
{row_summary}

FACTORS CONTRIBUTING TO PREDICTION:
{impact_text}

Write a clear, friendly explanation for a non-technical business owner.
Rules:
1. Start with the headline prediction.
2. Highlight the top 2-3 factors contributing to the model's prediction.
3. CRITICAL: Do NOT make causal claims (e.g. do NOT say "X happens because of Y"). Use associative language like "Factors contributing most to this model prediction include...". Do not invent reasons.
4. Keep it under 150 words. Use **bold** for key terms.
5. Never mention model names, algorithms, or technical terms like "Random Forest".

Write the explanation now:"""

    try:
        explanation = call_llm(prompt, expect_json=False)
        return explanation.strip()
    except Exception as e:
        logger.warning("[ML Agent] LLM explanation failed: %s. Using fallback.", e)
        return (
            f"**Predicted {prediction_result.target_column}:** {predicted_value_text}\n\n"
            f"Factors contributing most to this model prediction: {', '.join(fi['feature'] for fi in feature_impacts[:3])}.\n\n"
            f"Model quality metric: **{quality_metric_text}**."
        )


def _generate_forecasting_explanation(query: str, forecast_result, task_type: str = "forecasting") -> str:
    """Generate an explanation for forecasting results."""
    
    if task_type == "trend_direction_forecast":
        direction = forecast_result.direction
        prompt = f"""You are a Business Advisor AI. A time-series model has forecasted the trend direction.
The user asked: "{query}"
FORECAST RESULT: Target: {forecast_result.target_column}, Direction: {direction} over {forecast_result.horizon} periods.
Write a clear, friendly explanation.
Rules:
1. State the forecasted direction clearly (increase/decrease/stable).
2. Keep it under 50 words.
Write the explanation now:"""
    elif task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis"):
        best = forecast_result.best_group
        prompt = f"""You are a Business Advisor AI. A time-series model has forecasted multiple groups.
The user asked: "{query}"
FORECAST RESULT: Target: {forecast_result.target_column}, Top forecasted group: {best}.
Write a clear, friendly explanation.
Rules:
1. State the top forecasted group.
2. Keep it under 50 words.
Write the explanation now:"""
    else:
        target = forecast_result.target_column
        forecast_rows = forecast_result.forecast
        if not forecast_rows:
            return "No forecast could be generated."
            
        last_forecast = forecast_rows[-1]
        
        prompt = f"""You are a Business Advisor AI. A time-series forecasting model has analyzed data.

The user asked: "{query}"

FORECAST RESULT:
- Target metric: {target}
- Periods forecasted: {len(forecast_rows)}
- Final forecasted value: {last_forecast.value:,.2f} at {last_forecast.date}

Write a clear, friendly explanation for a non-technical business owner summarizing this forecast.
Rules:
1. Start with the headline forecasting result.
2. Keep it under 100 words. Use **bold** for key terms.
3. Do not invent reasons for trends.

Write the explanation now:"""

    try:
        explanation = call_llm(prompt, expect_json=False)
        return explanation.strip()
    except Exception as e:
        logger.warning("[ML Agent] LLM explanation failed: %s. Using fallback.", e)
        if task_type == "trend_direction_forecast":
            return f"The model expects a **{forecast_result.direction}** in {forecast_result.target_column} over the next {forecast_result.horizon} periods."
        elif task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis"):
            return f"The model predicts **{forecast_result.best_group}** will have the highest {forecast_result.target_column}."
        return "Forecast complete."



def run(query: str) -> dict[str, Any]:
    """
    Main entry point for the ML Agent.

    Args:
        query: The user's natural-language question.

    Returns:
        A dict with 'result' and 'insight' keys, structured to match
        the Orchestrator's expected response shape.
    """
    from prediction import service as prediction_service

    logger.info("[ML Agent] Processing predictive query: %s", query[:100])

    # 1. Find the right table
    table_name = _find_ml_table()
    if table_name is None:
        return {
            "result": {
                "pipeline_type": "PREDICTIVE",
                "prediction": None,
                "error": "No suitable dataset found for prediction. Please upload a dataset with a target column.",
            },
            "insight": "I couldn't find a dataset suitable for prediction. Please upload a dataset with a suitable target column.",
        }

    logger.info("[ML Agent] Using table: %s", table_name)

    # 2. Extract customer ID and target hint
    customer_id = _extract_customer_id(query)
    target_hint = _extract_target_hint(query)
    is_single_customer = customer_id is not None
    logger.info("[ML Agent] Extracted customer ID: %s, target hint: %s", customer_id, target_hint)
    
    task_type = _extract_task_type(query)
    group_hints = _extract_group_hints(query) if task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis") else []
    
    logger.info("[ML Agent] Extracted task_type: %s, group_hints: %s", task_type, group_hints)
    
    forecast_horizon = 12
    forecast_frequency = "months"
    extracted_horizon = _extract_forecast_horizon(query)
    if extracted_horizon:
        forecast_horizon, forecast_frequency = extracted_horizon

    # 3. Run prediction via the prediction package facade
    try:
        prediction_result = prediction_service.predict_rows(
            table_name=table_name,
            target_col=target_hint,
            customer_id=customer_id,
            rank_by_probability=not is_single_customer,
            task_type=task_type,
            group_hints=group_hints,
            forecast_steps=forecast_horizon,
            forecast_frequency=forecast_frequency,
        )
    except Exception as e:
        logger.exception("[ML Agent] Prediction failed")
        return {
            "result": {
                "pipeline_type": "PREDICTIVE",
                "prediction": None,
                "error": str(e),
            },
            "insight": f"Prediction failed: {e}",
        }

    # For batch queries (no specific customer), show top 20 ranked by probability
    is_forecast = task_type in ("forecasting", "trend_direction_forecast", "grouped_forecasting", "grouped_ranking", "growth_analysis")
    max_display = 20
    if not is_forecast and not is_single_customer and getattr(prediction_result, "count", 0) > max_display:
        prediction_result.predictions = prediction_result.predictions[:max_display]
        prediction_result.count = max_display
        prediction_result.truncated = True

    # 4. Generate explanation
    if is_forecast:
        explanation = _generate_forecasting_explanation(query, prediction_result, task_type)
    else:
        explanation = _generate_explanation(query, prediction_result)

    # 5. Format result for the frontend
    pred_dict = dataclasses.asdict(prediction_result)

    # 6. Build visualization metadata
    viz_metadata = _build_visualization_metadata(prediction_result, is_single_customer, task_type)

    result = {
        "pipeline_type": "PREDICTIVE",
        "prediction": pred_dict,
        "visualization": viz_metadata,
        "columns": ["metric", "value"],
        "rows": [],
        "row_count": 0,
    }

    # Build a simple table representation for backward compatibility
    if task_type == "trend_direction_forecast":
        result["rows"].append({"metric": "Trend Direction", "value": prediction_result.direction.title()})
        result["rows"].append({"metric": "Horizon", "value": f"{prediction_result.horizon} periods"})
    elif task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis"):
        for p in prediction_result.predictions[:5]:
            val = p.get("final_value")
            result["rows"].append({
                "metric": p["group"],
                "value": f"{val:,.2f}" if val is not None else "N/A"
            })
    elif task_type == "forecasting":
        for f in prediction_result.forecast[:5]:
            result["rows"].append({
                "metric": f.date,
                "value": f"{f.value:,.2f}" if f.value else "N/A"
            })
    else:
        for pred in prediction_result.predictions:
            if pred.probability is not None:
                result["rows"].append({
                    "metric": "Probability",
                    "value": f"{pred.probability:.1%}",
                })
                result["rows"].append({
                    "metric": "Risk Level",
                    "value": pred.risk,
                })
            else:
                result["rows"].append({
                    "metric": f"Predicted {prediction_result.target_column}",
                    "value": f"{pred.prediction:,.2f}",
                })
            result["rows"].append({
                "metric": "Model Quality",
                "value": f"{prediction_result.model_accuracy}",
            })
            # Add key row attributes
            for k, v in list(pred.row_data.items())[:8]:
                if k.lower() not in ("surname", "rownumber", "row_number"):
                    result["rows"].append({"metric": k.replace("_", " ").title(), "value": str(v)})
            break  # Only show first prediction in table form

    result["row_count"] = len(result["rows"])

    return {
        "result": result,
        "insight": explanation,
    }


def _build_visualization_metadata(prediction_result, is_single_customer: bool, task_type: str = "classification") -> dict[str, Any]:
    """
    Build structured visualization metadata from the prediction result.
    
    This tells the frontend what kind of charts to render and with what data,
    without the frontend needing to understand the ML internals.
    """
    if task_type == "forecasting":
        return {
            "mode": "forecast",
            "problem_type": "forecasting",
            "charts": [_build_forecasting_charts(prediction_result)],
        }
    elif task_type == "trend_direction_forecast":
        return {
            "mode": "forecast",
            "problem_type": "forecasting",
            "charts": [_build_forecasting_charts(prediction_result, title=f"Trend: {prediction_result.direction.title()}")],
        }
    elif task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis"):
        charts = [_build_grouped_forecasting_line_chart(prediction_result)]
        if task_type in ("grouped_ranking", "growth_analysis"):
            charts.append(_build_grouped_forecasting_ranking_chart(prediction_result, task_type))
            
        return {
            "mode": "forecast",
            "problem_type": "forecasting",
            "charts": charts,
        }

    predictions = prediction_result.predictions
    if not predictions:
        return {"charts": []}

    first_pred = predictions[0]
    is_classification = first_pred.probability is not None

    if is_classification:
        charts = _build_classification_charts(prediction_result)
    else:
        charts = _build_regression_charts(prediction_result)

    # ── Feature Importance (shared between both) ──
    if first_pred.feature_impacts:
        feature_importance = {
            "type": "feature_importance",
            "title": "Factors Contributing Most to Prediction",
            "data": [
                {
                    "feature": fi["feature"],
                    "importance": round(fi["importance"] * 100, 1),
                }
                for fi in first_pred.feature_impacts
            ],
        }
        charts.append(feature_importance)

    return {
        "mode": "single" if is_single_customer else "batch",
        "problem_type": "classification" if is_classification else "regression",
        "charts": charts,
    }


def _build_forecasting_charts(forecast_result, title: str | None = None) -> dict:
    """Build a time-series line chart for forecasting."""
    historical = [{"date": r.date, "value": r.value} for r in forecast_result.historical[-50:]]
    
    forecast = []
    for r in forecast_result.forecast:
        forecast.append({
            "date": r.date,
            "value": r.value,
            "lower": getattr(r, "lower_bound", None),
            "upper": getattr(r, "upper_bound", None),
        })
        
    return {
        "type": "time_series_forecast",
        "title": title or f"Forecast: {forecast_result.target_column}",
        "data": {
            "historical": historical,
            "forecast": forecast,
        }
    }

def _build_grouped_forecasting_line_chart(forecast_result) -> dict:
    """Build a multi-line chart for grouped forecasting."""
    group_label = " and ".join(forecast_result.group_dimensions) if hasattr(forecast_result, "group_dimensions") else getattr(forecast_result, "group_column", "Group")
    
    series_data = []
    for p in forecast_result.predictions:
        series_data.append({
            "group": str(p["group"]),
            "historical": p.get("historical", [])[-50:],
            "forecast": p.get("forecast", []),
        })
        
    return {
        "type": "grouped_time_series_forecast",
        "title": f"Forecast {forecast_result.target_column} by {group_label}",
        "dimension": "group",
        "data": series_data
    }

def _build_grouped_forecasting_ranking_chart(forecast_result, task_type: str = "grouped_ranking") -> dict:
    """Build a bar chart for grouped forecasting ranking."""
    ranking_data = []
    for p in forecast_result.predictions:
        ranking_data.append({
            "group": str(p["group"]),
            "value": round(float(p["final_value"]), 2) if p["final_value"] is not None else 0.0,
            "color": "#6366f1",
        })
        
    group_label = " and ".join(forecast_result.group_dimensions) if hasattr(forecast_result, "group_dimensions") else getattr(forecast_result, "group_column", "Group")
        
    if task_type == "growth_analysis":
        title = f"Expected Growth % by {group_label}"
    else:
        title = f"Predicted {forecast_result.target_column} by {group_label}"
        
    return {
        "type": "value_ranking",
        "title": title,
        "dimension": "group",
        "metric": "value",
        "sort": "descending",
        "data": ranking_data[:20],
    }


def _build_classification_charts(prediction_result) -> list[dict]:
    """Build charts specific to classification (churn) predictions."""
    predictions = prediction_result.predictions

    # Risk Distribution (pie/donut)
    risk_counts = {"High": 0, "Medium": 0, "Low": 0}
    for p in predictions:
        risk_counts[p.risk] = risk_counts.get(p.risk, 0) + 1

    risk_distribution = {
        "type": "risk_distribution",
        "title": "Churn Risk Distribution",
        "data": [
            {"name": risk, "value": count, "color": _risk_hex(risk)}
            for risk, count in risk_counts.items() if count > 0
        ],
    }

    # Probability Ranking (horizontal bar)
    ranking_data = []
    for p in predictions:
        ranking_data.append({
            "customer_id": str(p.customer_id),
            "probability": round(p.probability * 100, 1),
            "risk": p.risk,
            "color": _risk_hex(p.risk),
        })
    ranking_data.sort(key=lambda x: x["probability"], reverse=True)

    probability_ranking = {
        "type": "probability_ranking",
        "title": "Top Churn Risk Customers",
        "dimension": "customer_id",
        "metric": "churn_probability",
        "sort": "descending",
        "data": ranking_data[:20],
    }

    # Predicted Class Distribution
    churned = sum(1 for p in predictions if p.prediction == 1)
    retained = sum(1 for p in predictions if p.prediction == 0)
    class_distribution = {
        "type": "class_distribution",
        "title": "Predicted Churn vs Retained",
        "data": [
            {"name": "Churned", "value": churned, "color": "#ef4444"},
            {"name": "Retained", "value": retained, "color": "#22c55e"},
        ],
    }

    # Model Performance
    model_performance = {
        "type": "model_performance",
        "title": "Model Performance",
        "accuracy": prediction_result.model_accuracy,
        "target_column": prediction_result.target_column,
        "table_name": prediction_result.table_name,
        "total_predicted": prediction_result.count,
    }

    return [risk_distribution, probability_ranking, class_distribution, model_performance]


def _build_regression_charts(prediction_result) -> list[dict]:
    """Build charts specific to regression predictions."""
    predictions = prediction_result.predictions
    target = prediction_result.target_column

    # Value Distribution (histogram-like bins)
    values = [p.prediction for p in predictions]
    if values:
        import numpy as np
        hist, bin_edges = np.histogram(values, bins=min(10, len(set(values))))
        histogram = {
            "type": "value_distribution",
            "title": f"Predicted {target} Distribution",
            "data": [
                {
                    "range": f"{bin_edges[i]:.0f}-{bin_edges[i+1]:.0f}",
                    "count": int(hist[i]),
                }
                for i in range(len(hist))
            ],
        }
    else:
        histogram = {"type": "value_distribution", "title": f"Predicted {target} Distribution", "data": []}

    # Value Ranking (horizontal bar - top/bottom)
    ranking_data = []
    for p in predictions:
        ranking_data.append({
            "customer_id": str(p.customer_id),
            "value": round(float(p.prediction), 2),
            "color": "#6366f1",
        })
    ranking_data.sort(key=lambda x: x["value"], reverse=True)

    value_ranking = {
        "type": "value_ranking",
        "title": f"Top Predicted {target}",
        "dimension": "customer_id",
        "metric": target,
        "sort": "descending",
        "data": ranking_data[:20],
    }

    # Model Performance (R²)
    model_performance = {
        "type": "model_performance",
        "title": "Model Performance",
        "accuracy": prediction_result.model_accuracy,
        "metric_name": "R² Score",
        "target_column": prediction_result.target_column,
        "table_name": prediction_result.table_name,
        "total_predicted": prediction_result.count,
    }

    return [histogram, value_ranking, model_performance]


def _risk_hex(risk: str) -> str:
    """Map risk level to a hex color."""
    return {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}.get(risk, "#6b7280")

