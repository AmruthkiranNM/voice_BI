"""
Prediction Package — Trainer

Orchestrates the full model training lifecycle:
  Detection → Preprocessing → Model creation → Fitting → Evaluation → Persistence.

Persists trained model artifacts to disk so subsequent predictions
are instant (no re-training).
"""

import dataclasses
import logging
import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from config import DATA_DIR
from prediction.schemas import DetectionResult, PreparedData, TrainedModelArtifact, EvaluationResult, TrainingExperimentResult
from prediction import detector, preprocessing, models, evaluator

logger = logging.getLogger(__name__)

# Directory to persist trained models
MODEL_DIR = DATA_DIR / "ml_models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def get_model_path(
    table_name: str,
    target_col: str,
    model_key: str | None = None,
    frequency: str | None = None,
) -> Path:
    """
    Return the on-disk path for a trained model artifact.

    ``frequency`` is part of the key for forecasting models. Without it, a
    model fitted on monthly buckets was reused to answer a question asked in
    days, returning monthly periods for a daily request.
    """
    parts = [table_name, target_col]
    if frequency:
        parts.append(f"freq-{frequency}")
    if model_key:
        parts.append(model_key)
    return MODEL_DIR / ("__".join(parts) + ".pkl")


def train_all(
    df: pd.DataFrame,
    table_name: str,
    target_col: str | None = None,
    selection_metric: str | None = None,
    forecast_frequency: str = "months",
    forecast_horizon: int = 12,
    problem_type_hint: str | None = None,
) -> TrainingExperimentResult:
    """
    Full training pipeline: detect → preprocess → train all models → evaluate → select best → save.

    Args:
        df:               Raw table DataFrame.
        table_name:       Table name (used for model persistence path).
        target_col:       Optional explicit target column. Auto-detected if None.
        selection_metric: Metric to use for best model selection (e.g., roc_auc, f1_score).
        forecast_frequency: Bucket size for forecasting ("months", "days", ...).
        forecast_horizon: Periods ahead the model will be asked for; sets the
                          validation window used to select a forecasting model.
        problem_type_hint: Optional hint for problem type (e.g. "forecasting").

    Returns:
        TrainingExperimentResult containing artifacts and metrics for all models, plus the chosen best model.
    """
    # 1. Detect
    detection = detector.detect(df, table_name, target_hint=target_col, problem_type_hint=problem_type_hint)
    if not detection.is_suitable:
        raise ValueError(f"Table '{table_name}' is not suitable: {detection.reason}")

    logger.info("[Trainer] Detection passed: target='%s', features=%d",
                detection.target_column, len(detection.feature_columns))

    # 2. Preprocess
    if detection.problem_type == "forecasting":
        from prediction import forecast_selection, series_validation

        frequency = series_validation.normalize_frequency(forecast_frequency)
        ts_data, agg_info = preprocessing.aggregate_time_series(
            df, detection.date_column, detection.target_column, frequency=frequency,
        )

        # Validate the series and choose a model by chronological backtest,
        # rather than assuming a single model fits every dataset.
        diagnostics = series_validation.validate_series(
            ts_data,
            requested_frequency=frequency,
            horizon=forecast_horizon,
            inferred_frequency=agg_info.get("inferred_frequency"),
            duplicate_timestamps=agg_info.get("duplicate_timestamps", 0),
            n_trimmed_partial=agg_info.get("n_trimmed_partial", 0),
        )
        model, selection_meta = forecast_selection.select_and_fit(
            ts_data, diagnostics, forecast_horizon,
        )

        experiment = TrainingExperimentResult(selection_metric=selection_meta.selection_metric)

        if model is None:
            logger.warning(
                "[Trainer] No forecasting model could be validated for %s.%s: %s",
                table_name, detection.target_column, diagnostics.reason,
            )
            experiment.training_results.append({
                "model_key": None,
                "training_status": "REFUSED",
                "reason": diagnostics.reason,
                "diagnostics": dataclasses.asdict(diagnostics),
            })
            return experiment

        artifact = TrainedModelArtifact(
            model=model,
            preprocessor=None,
            feature_names=[],
            target_column=detection.target_column,
            table_name=table_name,
            evaluation=EvaluationResult(),
            feature_importances=[],
            model_type=selection_meta.selected_model_label or model.model_name,
            problem_type="forecasting",
        )
        # Provenance travels with the artifact so a persisted forecast can
        # always state which model was chosen and how it scored.
        artifact.forecast_frequency = frequency
        artifact.series_diagnostics = diagnostics
        artifact.selection_metadata = selection_meta

        experiment.models.append(artifact)
        experiment.best_model_key = selection_meta.selected_model_key or models.DEFAULT_FORECASTING_KEY
        experiment.training_results.append({
            "model_key": selection_meta.selected_model_key,
            "model_name": selection_meta.selected_model_label,
            "training_status": "SUCCESS",
            "selection_method": selection_meta.selection_method,
            "selection_metric": selection_meta.selection_metric,
            "score": selection_meta.selected_score,
            "beats_naive": selection_meta.beats_naive,
            "n_folds": selection_meta.n_folds,
        })

        model_path = get_model_path(table_name, detection.target_column, frequency=frequency)
        with open(model_path, "wb") as f:
            pickle.dump(artifact, f)

        logger.info(
            "[Trainer] Forecasting model for %s.%s (%s): %s via %s (%s=%s, beats_naive=%s) → %s",
            table_name, detection.target_column, frequency,
            selection_meta.selected_model_label, selection_meta.selection_method,
            selection_meta.selection_metric, selection_meta.selected_score,
            selection_meta.beats_naive, model_path,
        )
        return experiment

    # Classification / Regression path
    prepared, preprocessor = preprocessing.prepare_training_data(df, detection)


    if not selection_metric:
        selection_metric = "roc_auc" if detection.problem_type == "classification" else "r2"
    elif detection.problem_type == "regression" and selection_metric in ("roc_auc", "f1_score", "accuracy"):
        selection_metric = "r2" # Fallback if classification metric was passed
    elif detection.problem_type == "classification" and selection_metric in ("r2", "mae", "rmse"):
        selection_metric = "roc_auc"

    experiment = TrainingExperimentResult(selection_metric=selection_metric)
    
    # Best score tracker
    minimize_metric = selection_metric in ("mae", "rmse")
    best_score = float("inf") if minimize_metric else -1.0
    best_artifact = None
    best_key = None

    # 3. Train all models
    for key, entry in models.MODEL_REGISTRY.items():
        if entry.get("problem_type", "classification") != detection.problem_type:
            continue

        logger.info("[Trainer] Fitting %s...", entry["label"])
        
        model = models.create_model(key)
        model.fit(prepared.X_train, prepared.y_train)

        eval_result = evaluator.evaluate(model, prepared.X_test, prepared.y_test)
        importances = _extract_importances(model, prepared.feature_names)

        artifact = TrainedModelArtifact(
            model=model,
            preprocessor=preprocessor,
            feature_names=prepared.feature_names,
            target_column=detection.target_column,
            table_name=table_name,
            evaluation=eval_result,
            feature_importances=importances,
            model_type=entry["label"],
            problem_type=detection.problem_type,
        )
        
        experiment.models.append(artifact)
        
        # Determine prediction/probability capabilities
        can_predict = hasattr(model, "predict")
        can_proba = hasattr(model, "predict_proba")

        metric_value = getattr(eval_result, selection_metric, 0.0)

        result_dict = {
            "model_key": key,
            "model_name": entry["label"],
            "training_status": "SUCCESS",
            "prediction_capability": can_predict,
            "probability_capability": can_proba,
        }
        
        if detection.problem_type == "regression":
            result_dict.update({
                "mae": eval_result.mae,
                "rmse": eval_result.rmse,
                "r2": eval_result.r2,
            })
        else:
            result_dict.update({
                "accuracy": eval_result.accuracy,
                "precision": eval_result.precision,
                "recall": eval_result.recall,
                "f1_score": eval_result.f1_score,
                "roc_auc": eval_result.roc_auc,
                "confusion_matrix": eval_result.confusion_matrix,
            })
            
        experiment.training_results.append(result_dict)
        
        # Model Selection
        is_better = metric_value < best_score if minimize_metric else metric_value > best_score
        if is_better:
            best_score = metric_value
            best_artifact = artifact
            best_key = key

    # 4. Save best model
    if best_artifact and best_key:
        experiment.best_model_key = best_key
        model_path = get_model_path(table_name, detection.target_column)
        with open(model_path, "wb") as f:
            pickle.dump(best_artifact, f)

        logger.info("[Trainer] Selected BEST model: %s (Metric %s = %.4f). Saved to %s", 
                    best_key, selection_metric, best_score, model_path)

    return experiment


def load_artifact(
    table_name: str,
    target_col: str,
    model_key: str | None = None,
    frequency: str | None = None,
) -> TrainedModelArtifact | None:
    """Load a previously trained model artifact from disk."""
    model_path = get_model_path(table_name, target_col, model_key, frequency)
    if not model_path.exists():
        return None
    with open(model_path, "rb") as f:
        artifact = pickle.load(f)
    # Handle legacy format: old ml_engine.py saved a plain dict
    if isinstance(artifact, dict):
        logger.warning("[Trainer] Found legacy model format; re-training required.")
        return None
    return artifact


def _extract_importances(model, feature_names: list[str]) -> list[tuple[str, float]]:
    """Extract and sort feature importances from a fitted model."""
    try:
        raw = model.feature_importances_
        pairs = list(zip(feature_names, [round(float(v), 4) for v in raw]))
        return sorted(pairs, key=lambda x: x[1], reverse=True)
    except AttributeError:
        return [(f, 0.0) for f in feature_names]
