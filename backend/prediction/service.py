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
    customer_id: str | None = None,
    filters: dict[str, Any] | None = None,
    risk_thresholds: dict[str, float] | None = None,
    rank_by_probability: bool = False,
    task_type: str = "classification",
    group_hints: list[str] | None = None,
    forecast_steps: int = 12,
    forecast_frequency: str = "months",
    group_filter: dict[str, list[str]] | None = None,
) -> Any:
    """
    Run inference on specific row(s) from a table.

    If no model exists yet, trains one first (lazy training).

    ``group_filter`` ({dimension: [allowed values]}) restricts which groups are
    forecast. Pass it only when the user explicitly named the groups; by
    default every eligible combination is forecast and ranked afterwards.
    """
    logger.info(
        "[Service] predict_rows called", 
        extra={
            "table_name": table_name,
            "target_col": target_col,
            "task_type": task_type,
            "group_hints": group_hints,
            "forecast_steps": forecast_steps
        }
    )

    if not table_name:
        raise ValueError("table_name must be provided and cannot be empty.")
        
    if forecast_steps <= 0:
        raise ValueError(f"forecast_steps must be strictly positive, got {forecast_steps}")

    df = _load_table(table_name)
    if df.empty:
        raise ValueError(f"Table '{table_name}' is empty. Cannot perform predictions.")
    
    is_forecast = task_type in ("forecasting", "trend_direction_forecast", "grouped_forecasting", "grouped_ranking", "growth_analysis")

    # Always detect to resolve target_col (which might be a semantic hint) and problem type
    problem_hint = "forecasting" if is_forecast else None
    detection = detector.detect(df, table_name, target_hint=target_col, problem_type_hint=problem_hint)
    
    if not detection.is_suitable:
        logger.error(f"[Service] Table '{table_name}' failed detection: {detection.reason}")
        raise ValueError(f"Table '{table_name}' is not suitable for this task: {detection.reason}")
        
    resolved_target_col = detection.target_column
    logger.info(f"[Service] Resolved target column: {resolved_target_col}")

    # ── Target-type gate ──────────────────────────────────────────────
    # The column decides what can be predicted from it; the question decides
    # what is wanted. Checking both here means no caller can route a target
    # into a pipeline it does not support, however it derived its task_type.
    # A continuous measure asked for as "classification" is corrected to a
    # forecast rather than being handed to a classifier, which is what
    # produced "the least populated class in y has only 1 member" for BOXES.
    from prediction.target_resolution import resolve_prediction_type, resolve_target

    target_spec = resolve_target(
        resolved_target_col, df, has_time_axis=bool(detection.date_column),
    )
    if is_forecast:
        requested_type = "forecasting"
    elif task_type == "regression":
        requested_type = "regression"
    else:
        # ml_agent labels every non-forecast question "classification", so this
        # is the value that must actually be challenged against the column.
        requested_type = "classification"
    chosen_type, type_reason = resolve_prediction_type(
        target_spec, wants_future=is_forecast, requested=requested_type,
    )

    if chosen_type is None:
        raise ValueError(
            f"'{resolved_target_col}' cannot be predicted. {target_spec.reason}"
        )

    if chosen_type != requested_type:
        logger.warning(
            "[Service] Prediction type corrected: %s -> %s. %s",
            requested_type, chosen_type, type_reason,
        )
        if chosen_type == "forecasting" and not is_forecast:
            # Re-run detection in forecasting mode so the date column and the
            # forecasting-specific suitability checks are applied.
            is_forecast = True
            problem_hint = "forecasting"
            detection = detector.detect(
                df, table_name, target_hint=resolved_target_col,
                problem_type_hint=problem_hint,
            )
            if not detection.is_suitable:
                raise ValueError(
                    f"'{resolved_target_col}' is a continuous measure but cannot be "
                    f"forecast: {detection.reason}"
                )
            if task_type in ("classification", "regression"):
                task_type = "grouped_forecasting" if group_hints else "forecasting"
        elif chosen_type == "regression" and detection.problem_type == "classification":
            detection.problem_type = "regression"

    logger.info(
        "[Service] Target '%s' -> %s (%s); prediction type: %s",
        resolved_target_col, target_spec.semantic_role, target_spec.dtype, chosen_type,
    )

    # Load or train.
    # Forecasting artifacts are keyed by frequency as well as table+target: a
    # model fitted on monthly buckets cannot answer a question asked in days.
    from prediction.series_validation import normalize_frequency

    normalized_frequency = normalize_frequency(forecast_frequency)
    artifact = trainer.load_artifact(
        table_name,
        resolved_target_col,
        frequency=normalized_frequency if is_forecast else None,
    )

    needs_retrain = False
    if artifact is None:
        needs_retrain = True
    elif is_forecast and getattr(artifact, "problem_type", None) != "forecasting":
        needs_retrain = True
    elif not is_forecast and getattr(artifact, "problem_type", None) == "forecasting":
        needs_retrain = True
    elif is_forecast and getattr(artifact, "forecast_frequency", None) != normalized_frequency:
        needs_retrain = True

    # A grouped forecast fits one model per group from the group's own series,
    # so the table-level artifact would never be used. Skip that wasted fit.
    if task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis"):
        needs_retrain = False

    if needs_retrain:
        logger.info("[Service] No saved model or wrong type/frequency; training models now...")
        experiment = trainer.train_all(
            df, table_name,
            target_col=resolved_target_col,
            forecast_frequency=normalized_frequency,
            forecast_horizon=forecast_steps,
            problem_type_hint=problem_hint,
        )
        if not experiment.models:
            reason = ""
            if experiment.training_results:
                reason = experiment.training_results[0].get("reason", "")
            raise RuntimeError(
                f"No model could be trained for '{table_name}'."
                + (f" {reason}" if reason else "")
            )
        artifact = experiment.models[0]  # Just use the first one for lazy predict fallback

    if task_type == "trend_direction_forecast":
        logger.info(f"[Service] Executing trend_direction_forecast for {table_name}")
        return predictor.predict_trend_direction(df, artifact, steps=forecast_steps, frequency=forecast_frequency)
        
    if task_type in ("grouped_forecasting", "grouped_ranking", "growth_analysis"):
        if not group_hints:
             raise ValueError(f"Task type '{task_type}' requires group_hints to be provided.")
             
        logger.info(f"[Service] Executing {task_type} with hints: {group_hints}")
        # Keep the measure and the time axis out of the dimension catalog —
        # they are what is being forecast and when, never how it is grouped.
        exclude = {resolved_target_col}
        if detection.date_column:
            exclude.add(detection.date_column)

        dim_info_list = detector.detect_group_dimensions(
            group_hints, table_name, exclude_columns=exclude,
        )
        if not dim_info_list:
            raise ValueError(
                f"Could not find valid grouping dimensions for '{group_hints}' "
                f"connected to {table_name}."
            )

        # Load each distinct dimension table once. Dimensions that live in the
        # fact table itself need no join and therefore no extra load.
        loaded: dict[str, pd.DataFrame] = {}
        for dim_info in dim_info_list:
            if not dim_info.get("requires_join", True):
                continue
            target = dim_info.get("target_table")
            if not target:
                raise ValueError(f"Missing target_table in dimension info for hint: {dim_info}")
            if target not in loaded:
                loaded[target] = _load_table(target)
                if loaded[target].empty:
                    raise ValueError(
                        f"Dimension table '{target}' is empty, so '{dim_info['semantic_hint']}' "
                        "cannot be used to group this forecast."
                    )
            dim_info["dim_df"] = loaded[target]

        ranking_metric = "growth" if task_type == "growth_analysis" else "sum"

        return predictor.predict_grouped_forecast(
            df=df,
            dimensions=dim_info_list,
            target_col=resolved_target_col,
            steps=forecast_steps,
            frequency=forecast_frequency,
            table_name=table_name,
            ranking_metric=ranking_metric,
            group_filter=group_filter,
        )

    if task_type == "forecasting":
        logger.info(f"[Service] Executing forecasting for {table_name}")
        return predictor.forecast(df, artifact, steps=forecast_steps, frequency=forecast_frequency)

    # Locate target rows
    row_indices = None
    if customer_id is not None or filters:
        row_indices = predictor.find_rows_by_filter(
            df, filters=filters, customer_id=customer_id,
        )
        if not row_indices:
            logger.warning(f"[Service] No matching rows found in {table_name} for given filters/customer_id.")
            is_classification = getattr(artifact, 'problem_type', 'classification') == 'classification'
            accuracy_metric = artifact.evaluation.accuracy if is_classification else artifact.evaluation.r2
            return PredictionResult(
                predictions=[],
                model_accuracy=accuracy_metric,
                target_column=resolved_target_col,
                table_name=table_name,
                count=0,
            )

    logger.info(f"[Service] Executing classification/regression prediction for {table_name}")
    return predictor.predict(
        df, 
        artifact, 
        row_indices=row_indices, 
        risk_thresholds=risk_thresholds, 
        rank_by_probability=rank_by_probability
    )

