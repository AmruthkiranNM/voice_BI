"""
Prediction Package — Service (Facade)

High-level public API for the prediction package.

This is the ONLY module that outside code (e.g. agents/ml_agent.py)
should import. It hides the internal module boundaries and provides
simple train() / predict() / detect() entry points.
"""

import logging
from typing import Any

import pandas as pd

from prediction.schemas import (
    DetectionResult,
    TrainedModelArtifact,
    PredictionResult,
    ForecastingResult,
    EvaluationResult,
)
from prediction import detector, trainer, predictor

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# Data Loading (uses the existing database service)
# ────────────────────────────────────────────────────────────

def _load_table(table_name: str) -> pd.DataFrame:
    """Load a SQLite table into a DataFrame via the existing DB service."""
    from services.database import get_connection
    conn = get_connection()
    try:
        return pd.read_sql_query(f"SELECT * FROM [{table_name}]", conn)
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────

def detect_problem(table_name: str, target_hint: str | None = None) -> DetectionResult:
    """
    Scan a table and determine if it contains a viable
    classification or regression problem.

    Args:
        table_name:  SQLite table name.
        target_hint: Optional explicit target column name.

    Returns:
        DetectionResult describing the problem (or why it's not suitable).
    """
    df = _load_table(table_name)
    return detector.detect(df, table_name, target_hint=target_hint)


def train_models(
    table_name: str,
    target_col: str | None = None,
    selection_metric: str | None = None,
) -> dict[str, Any]:
    """
    Train all candidate models on the given table and select the best.

    Args:
        table_name:       SQLite table name.
        target_col:       Optional explicit target column (auto-detected if None).
        selection_metric: Metric to use for best model selection (e.g., roc_auc, f1_score).

    Returns:
        Dict with models and their training results.
    """
    df = _load_table(table_name)
    experiment = trainer.train_all(df, table_name, target_col=target_col, selection_metric=selection_metric)

    models_info = []
    for artifact in experiment.models:
        models_info.append({
            "model_type": artifact.model_type,
            "target_column": artifact.target_column,
            "feature_count": len(artifact.feature_names),
        })

    return {
        "best_model": experiment.best_model_key,
        "selection_metric": experiment.selection_metric,
        "models": models_info,
        "training_results": experiment.training_results,
    }


def predict_rows(
    table_name: str,
    target_col: str | None = None,
    customer_id: Any | None = None,
    filters: dict[str, Any] | None = None,
    risk_thresholds: dict[str, float] | None = None,
    rank_by_probability: bool = False,
    task_type: str = "classification",
    group_hint: str | None = None,
    forecast_steps: int = 12,
    forecast_frequency: str = "months",
) -> Any:
    """
    Run inference on specific row(s) from a table.

    If no model exists yet, trains one first (lazy training).

    Args:
        table_name:          SQLite table name.
        target_col:          Optional explicit target column.
        customer_id:         Shortcut to filter by ID column.
        filters:             {column: value} filters.
        risk_thresholds:     Optional configurable mapping for 'High' and 'Medium' risk boundaries.
        rank_by_probability: Whether to sort the final result by probability descending.
        task_type:           Type of task (e.g., forecasting, trend_direction_forecast, grouped_forecasting).
        group_hint:          Optional hint for grouped tasks (e.g., 'country').
        forecast_steps:      Number of periods to forecast.
        forecast_frequency:  Temporal frequency for the forecast.

    Returns:
        PredictionResult, ForecastingResult, TrendDirectionResult, or GroupedForecastingResult.
    """
    df = _load_table(table_name)
    
    is_forecast = task_type in ("forecasting", "trend_direction_forecast", "grouped_forecasting", "grouped_ranking")

    # Always detect to resolve target_col (which might be a semantic hint) and problem type
    problem_hint = "forecasting" if is_forecast else None
    detection = detector.detect(df, table_name, target_hint=target_col, problem_type_hint=problem_hint)
    
    if not detection.is_suitable:
        raise ValueError(f"Table '{table_name}' is not suitable for this task: {detection.reason}")
        
    resolved_target_col = detection.target_column

    # Load or train
    artifact = trainer.load_artifact(table_name, resolved_target_col)
    expected_problem_type = "forecasting" if is_forecast else "classification"
    
    # If it's a regression task but expected was classification, allow it (legacy behavior).
    # But if it's forecasting vs non-forecasting, we must retrain.
    needs_retrain = False
    if artifact is None:
        needs_retrain = True
    elif is_forecast and getattr(artifact, "problem_type", None) != "forecasting":
        needs_retrain = True
    elif not is_forecast and getattr(artifact, "problem_type", None) == "forecasting":
        needs_retrain = True

    if needs_retrain:
        logger.info("[Service] No saved model or wrong type; training models now...")
        experiment = trainer.train_all(df, table_name, target_col=resolved_target_col, forecast_frequency=forecast_frequency, problem_type_hint=problem_hint)
        artifact = experiment.models[0]  # Just use the first one for lazy predict fallback

    if task_type == "trend_direction_forecast":
        return predictor.predict_trend_direction(df, artifact, steps=forecast_steps, frequency=forecast_frequency)
        
    if task_type in ("grouped_forecasting", "grouped_ranking") and group_hint:
        dim_info = detector.detect_group_dimension(group_hint, table_name)
        if not dim_info:
            raise ValueError(f"Could not find a valid grouping dimension for '{group_hint}' connected to {table_name}.")
            
        dim_df = _load_table(dim_info["target_table"])
        
        return predictor.predict_grouped_forecast(
            df=df,
            dim_df=dim_df,
            target_col=resolved_target_col,
            group_col=dim_info["group_column"],
            join_key_base=dim_info["join_key_base"],
            join_key_target=dim_info["join_key_target"],
            steps=forecast_steps,
            frequency=forecast_frequency,
            table_name=table_name,
        )

    if task_type == "forecasting":
        return predictor.forecast(df, artifact, steps=forecast_steps, frequency=forecast_frequency)

    # Locate target rows
    row_indices = None
    if customer_id is not None or filters:
        row_indices = predictor.find_rows_by_filter(
            df, filters=filters, customer_id=customer_id,
        )
        if not row_indices:
            is_classification = getattr(artifact, 'problem_type', 'classification') == 'classification'
            accuracy_metric = artifact.evaluation.accuracy if is_classification else artifact.evaluation.r2
            return PredictionResult(
                predictions=[],
                model_accuracy=accuracy_metric,
                target_column=resolved_target_col,
                table_name=table_name,
                count=0,
            )

    return predictor.predict(
        df, 
        artifact, 
        row_indices=row_indices, 
        risk_thresholds=risk_thresholds, 
        rank_by_probability=rank_by_probability
    )

