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


def predict_trend_direction(
    df: pd.DataFrame,
    artifact: TrainedModelArtifact,
    steps: int = 3,
    frequency: str = "months",
):
    """Run a forecast and determine whether the overall trend is increase, decrease, or stable."""
    from prediction.schemas import TrendDirectionResult
    
    # 1. Get the forecast using existing function
    forecast_result = forecast(df, artifact, steps=steps, frequency=frequency)
    
    historical = forecast_result.historical
    forecast_rows = forecast_result.forecast
    
    if len(historical) < steps:
        baseline_avg = sum(r.value for r in historical if r.value is not None) / len(historical) if historical else 0
    else:
        baseline_avg = sum(r.value for r in historical[-steps:] if r.value is not None) / steps

    if forecast_rows:
        forecast_avg = sum(r.value for r in forecast_rows if r.value is not None) / len(forecast_rows)
    else:
        forecast_avg = baseline_avg

    if baseline_avg == 0:
        direction = "increase" if forecast_avg > 0 else "stable"
    else:
        diff_pct = (forecast_avg - baseline_avg) / abs(baseline_avg)
        if diff_pct > 0.02:
            direction = "increase"
        elif diff_pct < -0.02:
            direction = "decrease"
        else:
            direction = "stable"
            
    return TrendDirectionResult(
        target_column=forecast_result.target_column,
        date_column=forecast_result.date_column,
        direction=direction,
        horizon=steps,
        historical=historical,
        forecast=forecast_rows,
        table_name=forecast_result.table_name,
    )


def predict_grouped_forecast(
    df: pd.DataFrame,
    dimensions: list[dict[str, Any]],
    target_col: str,
    steps: int = 1,
    frequency: str = "months",
    table_name: str = "",
    ranking_metric: str = "sum",
):
    """Run forecasting on multiple groups by joining with dimension tables."""
    from prediction.schemas import GroupedForecastingResult
    
    detection = detector.detect(df, table_name, target_hint=target_col, problem_type_hint="forecasting")
    date_col = detection.date_column
    
    # 1. Join tables iteratively
    merged_df = df
    group_cols = []
    semantic_dimensions = []
    
    for dim in dimensions:
        dim_df = dim["dim_df"]
        join_key_base = dim["join_key_base"]
        join_key_target = dim["join_key_target"]
        group_col = dim["group_column"]
        
        merged_df = pd.merge(merged_df, dim_df, left_on=join_key_base, right_on=join_key_target, how="inner")
        group_cols.append(group_col)
        semantic_dimensions.append(dim.get("semantic_hint", group_col))
    
    # 2. Preprocess grouped data
    grouped_series = preprocessing.prepare_grouped_forecasting_data(
        merged_df,
        date_col=date_col,
        target_col=detection.target_column,
        group_cols=group_cols,
        frequency=frequency
    )
    
    # 3. Forecast each group
    from prediction.models import create_model
    predictions = []
    
    for group_name, ts_data in grouped_series.items():
        try:
            model = create_model(problem_type="forecasting")
            model.fit(ts_data)
            forecast_mean, _ = model.predict(steps=steps)
            
            # Format historical
            hist_rows = [{"date": str(d), "value": float(v) if pd.notna(v) else None} for d, v in ts_data.items()]
            
            # Format forecast
            fc_rows = [{"date": str(d), "value": float(v) if pd.notna(v) else None} for d, v in forecast_mean.items()]
            
            if not fc_rows:
                continue
                
            # Ranking Calculation
            if ranking_metric == "growth":
                baseline_len = min(len(hist_rows), steps)
                baseline_total = sum(r["value"] for r in hist_rows[-baseline_len:] if r["value"])
                forecast_total = sum(r["value"] for r in fc_rows if r["value"])
                
                if baseline_total and baseline_total > 0:
                    final_val = ((forecast_total - baseline_total) / baseline_total) * 100
                else:
                    final_val = 0.0
            else:
                final_val = sum(r["value"] for r in fc_rows if r["value"])
            
            predictions.append({
                "group": str(group_name),
                "historical": hist_rows,
                "forecast": fc_rows,
                "final_value": final_val,
            })
        except Exception as e:
            logger.warning(f"Failed to forecast group {group_name}: {e}")
            
    # Rank them
    predictions.sort(key=lambda x: x.get("final_value", 0) or 0, reverse=True)
    best_group = predictions[0]["group"] if predictions else None
            
    return GroupedForecastingResult(
        target_column=detection.target_column,
        date_column=date_col,
        group_dimensions=semantic_dimensions,
        horizon=steps,
        table_name=table_name,
        predictions=predictions,
        ranking_metric=ranking_metric,
        best_group=best_group,
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
