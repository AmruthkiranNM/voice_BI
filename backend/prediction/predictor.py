"""
Prediction Package — Predictor

Runs inference on one or more rows using a trained model artifact.
Handles feature alignment and produces PredictionResult objects.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from prediction.schemas import (
    DetectionResult,
    TrainedModelArtifact,
    PredictionRow,
    PredictionResult,
    ForecastingResult,
    ForecastingRow,
)
from prediction import detector, preprocessing

logger = logging.getLogger(__name__)


def predict(
    df: pd.DataFrame,
    artifact: TrainedModelArtifact,
    row_indices: list[int] | None = None,
    risk_thresholds: dict[str, float] | None = None,
    rank_by_probability: bool = False,
) -> PredictionResult:
    """
    Run inference on specific rows of a DataFrame.

    Args:
        df:                  The full table DataFrame.
        artifact:            A TrainedModelArtifact loaded from disk.
        row_indices:         Which rows to predict. None = first 5 rows.
        risk_thresholds:     Dict defining 'High' and 'Medium' thresholds (e.g., {"High": 0.7, "Medium": 0.4}).
        rank_by_probability: If True, sorts the resulting predictions by probability descending.

    Returns:
        PredictionResult with per-row predictions and metadata.
    """
    # Rebuild detection metadata for column classification
    detection = detector.detect(df, artifact.table_name, target_hint=artifact.target_column)

    # Select subset
    if row_indices is not None:
        subset = df.iloc[row_indices]
    else:
        subset = df.head(5)

    if subset.empty:
        return PredictionResult(
            predictions=[],
            model_accuracy=artifact.evaluation.accuracy,
            target_column=artifact.target_column,
            table_name=artifact.table_name,
            count=0,
        )

    # Prepare features aligned to training space
    X_subset_transformed = preprocessing.prepare_inference_data(subset, artifact.preprocessor)

    # Predict
    model = artifact.model
    predictions_raw = model.predict(X_subset_transformed)
    
    is_classification = getattr(artifact, "problem_type", "classification") == "classification"
    
    if is_classification:
        probabilities = model.predict_proba(X_subset_transformed)
    else:
        probabilities = None

    # Build per-row results
    importances_dict = dict(artifact.feature_importances)
    results: list[PredictionRow] = []

    # Reconstruct original row features mapped to their model feature names
    # to maintain feature impact visibility
    if hasattr(X_subset_transformed, "toarray"):
        X_subset_arr = X_subset_transformed.toarray()
    else:
        X_subset_arr = np.array(X_subset_transformed)

    id_cols = [c for c in subset.columns if "id" in c.lower()]
    id_col = id_cols[0] if id_cols else None

    for i, idx in enumerate(subset.index):
        row_data = subset.loc[idx].to_dict()
        if is_classification:
            prob_positive = float(probabilities[i][1]) if probabilities.shape[1] > 1 else float(probabilities[i][0])
            risk = _risk_level(prob_positive, risk_thresholds)
            pred_value = int(predictions_raw[i])
        else:
            prob_positive = None
            risk = None
            pred_value = float(predictions_raw[i])
        
        customer_id = row_data.get(id_col) if id_col else idx

        # Top feature impacts for this row
        row_features = pd.Series(X_subset_arr[i], index=artifact.feature_names)
        feature_impacts = _compute_feature_impacts(
            row_features,
            importances_dict,
            top_n=6,
        )

        results.append(PredictionRow(
            customer_id=_serialize(customer_id),
            prediction=pred_value,
            probability=round(prob_positive, 4) if prob_positive is not None else None,
            risk=risk,
            row_data={k: _serialize(v) for k, v in row_data.items()},
            feature_impacts=feature_impacts,
        ))

    if rank_by_probability:
        if is_classification:
            results.sort(key=lambda r: r.probability, reverse=True)
        else:
            # For regression, sort by predicted value descending
            results.sort(key=lambda r: r.prediction, reverse=True)

    accuracy_or_r2 = artifact.evaluation.accuracy if is_classification else artifact.evaluation.r2

    return PredictionResult(
        predictions=results,
        model_accuracy=accuracy_or_r2,
        target_column=artifact.target_column,
        table_name=artifact.table_name,
        count=len(results),
    )


def forecast(
    df: pd.DataFrame,
    artifact: TrainedModelArtifact,
    steps: int = 12,
    frequency: str = "months",
) -> ForecastingResult:
    """
    Run forecasting inference.
    """
    detection = detector.detect(df, artifact.table_name, target_hint=artifact.target_column, problem_type_hint="forecasting")
    
    # Re-prepare historical data
    ts_data = preprocessing.prepare_forecasting_data(df, detection, frequency=frequency)
    
    # Predict
    model = artifact.model
    forecast_mean, ci_df = model.predict(steps=steps)
    
    historical_rows = []
    for date, val in ts_data.items():
        historical_rows.append(ForecastingRow(
            date=str(date),
            is_historical=True,
            value=float(val) if pd.notna(val) else None,
        ))
        
    forecast_rows = []
    for date, val in forecast_mean.items():
        lower = float(ci_df.loc[date, "lower"]) if ci_df is not None else None
        upper = float(ci_df.loc[date, "upper"]) if ci_df is not None else None
        forecast_rows.append(ForecastingRow(
            date=str(date),
            is_historical=False,
            value=float(val) if pd.notna(val) else None,
            lower_bound=lower,
            upper_bound=upper,
        ))

    return ForecastingResult(
        historical=historical_rows,
        forecast=forecast_rows,
        model_accuracy=0.0,  # Or calculate MAPE/RMSE if held-out test was used
        target_column=artifact.target_column,
        date_column=detection.date_column,
        table_name=artifact.table_name,
        count=len(forecast_rows),
    )


def find_rows_by_filter(
    df: pd.DataFrame,
    filters: dict[str, Any] | None = None,
    customer_id: Any | None = None,
) -> list[int]:
    """
    Locate row indices matching the given filters or customer ID.

    Args:
        df:          Full table DataFrame.
        filters:     {column: value} exact-match filters.
        customer_id: Shortcut: matches against any column containing 'id'.

    Returns:
        List of integer row indices.
    """
    mask = pd.Series([True] * len(df), index=df.index)

    if customer_id is not None:
        id_cols = [c for c in df.columns if "id" in c.lower()]
        if id_cols:
            id_col = id_cols[0]
            mask = mask & (df[id_col].astype(str) == str(customer_id))

    if filters:
        for col, val in filters.items():
            if col in df.columns:
                mask = mask & (df[col].astype(str) == str(val))

    matched = df[mask].index.tolist()
    return matched


def _compute_feature_impacts(
    row_features: pd.Series,
    importances: dict[str, float],
    top_n: int = 6,
) -> list[dict[str, Any]]:
    """
    Approximate feature impact for a single prediction row by combining
    global feature importance with the row's actual feature values.
    """
    impacts = []
    for fname in sorted(importances, key=importances.get, reverse=True)[:top_n]:
        impacts.append({
            "feature": fname.replace("_", " "),
            "importance": round(importances.get(fname, 0.0), 4),
            "value": round(float(row_features.get(fname, 0)), 4),
        })
    return impacts


def _risk_level(probability: float, thresholds: dict[str, float] | None = None) -> str:
    """Map a probability to a human-readable risk label using configurable thresholds."""
    if thresholds is None:
        thresholds = {"High": 0.75, "Medium": 0.45}
        
    high_t = thresholds.get("High", 0.75)
    medium_t = thresholds.get("Medium", 0.45)
    
    if probability >= high_t:
        return "High"
    elif probability >= medium_t:
        return "Medium"
    return "Low"


def _serialize(v):
    """Make numpy/pandas types JSON-serializable."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if pd.isna(v):
        return None
    return v
