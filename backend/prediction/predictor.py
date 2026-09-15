"""
Prediction Package — Predictor

Runs inference on one or more rows using a trained model artifact.
Handles feature alignment and produces PredictionResult objects.
"""

import dataclasses
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
    ForecastModelMetadata,
    SeriesDiagnostics,
    UniversalPredictionResult,
    ForecastingRow,
)
from prediction import detector, forecast_selection, preprocessing, series_validation
from prediction import dimensions as dimension_validation

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
        UniversalPredictionResult with per-row predictions and metadata.
    """
    # Rebuild detection metadata for column classification
    detection = detector.detect(df, artifact.table_name, target_hint=artifact.target_column)

    # Select subset
    if row_indices is not None:
        subset = df.iloc[row_indices]
    else:
        subset = df.head(5)

    if subset.empty:
        return UniversalPredictionResult(
            task_type="classification" if getattr(artifact, "problem_type", "classification") == "classification" else "regression",
            row_predictions=[],
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

    return UniversalPredictionResult(
        task_type="classification" if is_classification else "regression",
        row_predictions=results,
        model_accuracy=accuracy_or_r2,
        target_column=artifact.target_column,
        table_name=artifact.table_name,
        count=len(results),
    )


def _historical_rows(series: pd.Series) -> list[ForecastingRow]:
    """
    Convert an aggregated series into reportable rows.

    A period with no data stays ``value=None``. It is never rendered as 0 —
    "we sold nothing" and "we have no record" are different claims.
    """
    return [
        ForecastingRow(
            date=str(date),
            is_historical=True,
            value=float(val) if pd.notna(val) else None,
        )
        for date, val in series.items()
    ]


def _forecast_rows(
    forecast_mean: pd.Series,
    ci_df: pd.DataFrame | None,
) -> list[ForecastingRow]:
    """Convert a point forecast plus optional intervals into reportable rows."""
    rows: list[ForecastingRow] = []
    for date, val in forecast_mean.items():
        lower = upper = None
        if ci_df is not None and date in ci_df.index:
            lower = float(ci_df.loc[date, "lower"])
            upper = float(ci_df.loc[date, "upper"])
        rows.append(ForecastingRow(
            date=str(date),
            is_historical=False,
            value=float(val) if pd.notna(val) else None,
            lower_bound=lower,
            upper_bound=upper,
        ))
    return rows


def run_series_forecast(
    series: pd.Series,
    *,
    steps: int,
    frequency: str,
    inferred_frequency: str | None = None,
    duplicate_timestamps: int = 0,
    n_trimmed_partial: int = 0,
) -> tuple[SeriesDiagnostics, ForecastModelMetadata, pd.Series, pd.DataFrame | None]:
    """
    Validate one series, select a model for it, and forecast — the single
    code path shared by ungrouped, grouped and trend-direction forecasting so
    every forecast in the system is produced under identical rules.

    Returns (diagnostics, model metadata, point forecast, intervals). The
    forecast is empty when validation refused the series.
    """
    diagnostics = series_validation.validate_series(
        series,
        requested_frequency=frequency,
        horizon=steps,
        inferred_frequency=inferred_frequency,
        duplicate_timestamps=duplicate_timestamps,
        n_trimmed_partial=n_trimmed_partial,
    )

    model, meta = forecast_selection.select_and_fit(series, diagnostics, steps)
    if model is None:
        return diagnostics, meta, pd.Series(dtype=float), None

    forecast_mean, ci_df = model.predict(steps=steps)
    forecast_mean, ci_df = forecast_selection.apply_non_negative_floor(
        forecast_mean, ci_df, meta.floor_applied
    )
    return diagnostics, meta, forecast_mean, ci_df


def forecast(
    df: pd.DataFrame,
    artifact: TrainedModelArtifact,
    steps: int = 12,
    frequency: str = "months",
) -> UniversalPredictionResult:
    """
    Run forecasting inference on a single (ungrouped) series.

    The model is selected from the series prepared at the *requested*
    frequency rather than reused from ``artifact``. A persisted artifact is
    keyed only by table and target, so reusing its fit silently answered a
    "next 3 days" question with monthly periods; selecting here keeps the
    reported history and the forecast on the same time axis.
    """
    detection = detector.detect(
        df, artifact.table_name,
        target_hint=artifact.target_column,
        problem_type_hint="forecasting",
    )

    ts_data, agg_info = preprocessing.aggregate_time_series(
        df, detection.date_column, detection.target_column, frequency=frequency,
    )

    diagnostics, meta, forecast_mean, ci_df = run_series_forecast(
        ts_data,
        steps=steps,
        frequency=frequency,
        inferred_frequency=agg_info.get("inferred_frequency"),
        duplicate_timestamps=agg_info.get("duplicate_timestamps", 0),
        n_trimmed_partial=agg_info.get("n_trimmed_partial", 0),
    )

    if forecast_mean.empty:
        logger.warning(
            "[Predictor] No forecast produced for %s.%s: %s",
            artifact.table_name, detection.target_column, diagnostics.reason,
        )

    return UniversalPredictionResult(
        task_type="forecasting",
        historical=_historical_rows(ts_data),
        forecast=_forecast_rows(forecast_mean, ci_df),
        model_accuracy=float(meta.selected_score) if meta.selected_score is not None else 0.0,
        target_column=artifact.target_column,
        date_column=detection.date_column,
        table_name=artifact.table_name,
        horizon=int(steps),
        series_diagnostics=diagnostics,
        model_metadata=meta,
        count=len(forecast_mean),
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

    # Average over periods that were actually observed. Dividing by `steps`
    # (rather than by the number of known values) previously diluted the
    # baseline whenever a period was missing, biasing the direction upward.
    observed = [r.value for r in historical if r.value is not None]
    baseline_window = observed[-steps:] if len(observed) >= steps else observed
    baseline_avg = (sum(baseline_window) / len(baseline_window)) if baseline_window else None

    forecast_values = [r.value for r in forecast_rows if r.value is not None]
    forecast_avg = (sum(forecast_values) / len(forecast_values)) if forecast_values else None

    if baseline_avg is None or forecast_avg is None:
        direction = "unknown"
    elif baseline_avg == 0:
        direction = "increase" if forecast_avg > 0 else "stable"
    else:
        diff_pct = (forecast_avg - baseline_avg) / abs(baseline_avg)
        if diff_pct > 0.02:
            direction = "increase"
        elif diff_pct < -0.02:
            direction = "decrease"
        else:
            direction = "stable"

    return UniversalPredictionResult(
        task_type="trend_direction_forecast",
        target_column=forecast_result.target_column,
        date_column=forecast_result.date_column,
        direction=direction,
        horizon=steps,
        historical=historical,
        forecast=forecast_rows,
        table_name=forecast_result.table_name,
        series_diagnostics=forecast_result.series_diagnostics,
        model_metadata=forecast_result.model_metadata,
        model_accuracy=forecast_result.model_accuracy,
    )


def _attach_dimensions(
    df: pd.DataFrame,
    dimensions: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Attach every requested dimension column to the fact table.

    Three properties this has to get right, all of which the previous
    implementation got wrong for at least one supported combination:

    * **One merge per table.** "country and product" pulls from two tables, but
      "product and category" both live in ``products``. Merging that table
      twice produced ``category_x``/``category_y`` and then a KeyError.
    * **Only the columns needed.** Pulling the whole dimension table in drags
      unrelated columns into the frame and invites name collisions with the
      fact table.
    * **Base-table dimensions need no join at all**, so a denormalised single
      table groups just like a star schema.

    Returns (frame, physical group columns, semantic dimension names) with the
    two lists positionally aligned to ``dimensions``.
    """
    merged = df
    group_cols: list[str] = []
    semantic_dimensions: list[str] = []

    # Group the requested dimensions by their source table so each table is
    # joined exactly once, carrying all of the columns wanted from it.
    by_table: dict[str, list[dict[str, Any]]] = {}
    for dim in dimensions:
        group_cols.append(dim["group_column"])
        semantic_dimensions.append(dim.get("semantic_hint") or dim["group_column"])
        if not dim.get("requires_join", True):
            continue
        # Dedupe by source table. Callers that predate named dimension specs
        # pass a frame without a table name, so fall back to the frame's
        # identity — two dims only share a merge when they share a frame.
        table_key = dim.get("target_table") or f"__frame_{id(dim.get('dim_df'))}"
        by_table.setdefault(table_key, []).append(dim)

    for table_key, dims in by_table.items():
        dim_df = dims[0].get("dim_df")
        target_table = dims[0].get("target_table") or dims[0].get("join_key_target", table_key)
        if dim_df is None:
            raise ValueError(
                f"No data was loaded for dimension table '{target_table}'."
            )
        join_key_base = dims[0]["join_key_base"]
        join_key_target = dims[0]["join_key_target"]
        wanted = [d["group_column"] for d in dims]

        missing = [c for c in wanted + [join_key_target] if c not in dim_df.columns]
        if missing:
            raise ValueError(
                f"Dimension table '{target_table}' is missing column(s) {missing}. "
                f"Available: {list(dim_df.columns)}"
            )
        if join_key_base not in merged.columns:
            raise ValueError(
                f"Fact table has no join key '{join_key_base}' for dimension table "
                f"'{target_table}'. Available: {list(merged.columns)}"
            )

        projection = dim_df[[join_key_target] + [c for c in wanted if c != join_key_target]]
        merged = pd.merge(
            merged, projection,
            left_on=join_key_base, right_on=join_key_target, how="inner",
        )

    for col in group_cols:
        if col not in merged.columns:
            raise ValueError(
                f"Grouping column '{col}' is not present after joining. "
                f"Available: {list(merged.columns)}"
            )

    return merged, group_cols, semantic_dimensions


def predict_grouped_forecast(
    df: pd.DataFrame,
    dimensions: list[dict[str, Any]],
    target_col: str,
    steps: int = 1,
    frequency: str = "months",
    table_name: str = "",
    ranking_metric: str = "sum",
    group_filter: dict[str, list[str]] | None = None,
) -> UniversalPredictionResult:
    """
    Forecast every observed combination of the requested dimensions.

    Args:
        dimensions: resolved dimension specs (see ``prediction.dimensions``).
        group_filter: optional {semantic dimension: [allowed values]}. Only
            applied when the user explicitly restricted the groups — the
            default is to forecast **all** eligible combinations and rank
            afterwards, so a group currently outside the top N can still be
            shown to overtake it.

    Combinations come from the data itself, so only combinations that actually
    occur are forecast; the cross-product is never materialised.
    """
    detection = detector.detect(df, table_name, target_hint=target_col, problem_type_hint="forecasting")
    date_col = detection.date_column

    # 1. Attach dimension columns (one merge per source table)
    merged_df, group_cols, semantic_dimensions = _attach_dimensions(df, dimensions)

    # 2. Apply an explicit restriction, if and only if one was given
    restricted_to: dict[str, list[str]] = {}
    if group_filter:
        for semantic, allowed in group_filter.items():
            if semantic not in semantic_dimensions or not allowed:
                continue
            physical = group_cols[semantic_dimensions.index(semantic)]
            wanted = {str(v) for v in allowed}
            merged_df = merged_df[merged_df[physical].astype(str).isin(wanted)]
            restricted_to[semantic] = sorted(wanted)
        logger.info("[Predictor] Group set explicitly restricted to %s", restricted_to)

    # 2. Preprocess grouped data (keys are tuples, one element per dimension)
    grouped_series, grouped_info = preprocessing.prepare_grouped_forecasting_data_with_info(
        merged_df,
        date_col=date_col,
        target_col=detection.target_column,
        group_cols=group_cols,
        frequency=frequency,
    )

    # 3. Validate, select a model, and forecast — independently per series
    predictions: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for group_key, ts_data in grouped_series.items():
        # Every dimension stays individually addressable. Collapsing the key
        # into one "India - Bars" string here is what previously made the
        # product dimension unrecoverable for hierarchical follow-ups.
        group_dict = {dim: str(val) for dim, val in zip(semantic_dimensions, group_key)}
        group_str = " - ".join(str(v) for v in group_key)

        info = grouped_info.get(group_key, {})
        hist_rows = [
            {"date": str(d), "value": float(v) if pd.notna(v) else None}
            for d, v in ts_data.items()
        ]

        try:
            diagnostics, meta, forecast_mean, ci_df = run_series_forecast(
                ts_data,
                steps=steps,
                frequency=frequency,
                inferred_frequency=info.get("inferred_frequency"),
                duplicate_timestamps=info.get("duplicate_timestamps", 0),
                n_trimmed_partial=info.get("n_trimmed_partial", 0),
            )
        except Exception as e:
            logger.warning("Failed to forecast group %s: %s", group_str, e)
            excluded.append({
                "group": group_str, "group_dict": group_dict,
                "status": "error", "reason": str(e),
            })
            predictions.append({
                "group": group_str, "group_dict": group_dict,
                "historical": hist_rows, "forecast": [],
                "final_value": None, "status": "error", "reason": str(e),
                "diagnostics": None, "model": None,
            })
            continue

        entry: dict[str, Any] = {
            "group": group_str,
            "group_dict": group_dict,
            "historical": hist_rows,
            "forecast": [],
            "final_value": None,
            "status": diagnostics.status,
            "reason": diagnostics.reason,
            "is_fallback": meta.selection_method in ("fallback_no_validation", "forced_constant"),
            "diagnostics": dataclasses.asdict(diagnostics),
            "model": dataclasses.asdict(meta),
        }

        if forecast_mean.empty:
            # Refused on purpose: report why instead of emitting a number.
            entry["status"] = diagnostics.status if diagnostics.status != "ok" else "not_forecast"
            excluded.append({
                "group": group_str,
                "group_dict": group_dict,
                "status": entry["status"],
                "reason": diagnostics.reason or "No forecast could be produced.",
                "n_observed": diagnostics.n_observed,
            })
            predictions.append(entry)
            continue

        fc_rows = []
        for d, v in forecast_mean.items():
            row = {"date": str(d), "value": float(v) if pd.notna(v) else None}
            if ci_df is not None and d in ci_df.index:
                row["lower"] = float(ci_df.loc[d, "lower"])
                row["upper"] = float(ci_df.loc[d, "upper"])
            fc_rows.append(row)

        entry["forecast"] = fc_rows
        entry["final_value"] = _ranking_value(hist_rows, fc_rows, steps, ranking_metric)
        predictions.append(entry)

    # 4. Rank deterministically. A group without a value is NOT worth zero —
    #    it sorts to the end and keeps its stated reason.
    predictions.sort(key=_rank_sort_key, reverse=False)
    ranked = [p for p in predictions if p.get("final_value") is not None]
    best_group = ranked[0]["group"] if ranked else None

    result = UniversalPredictionResult(
        task_type="grouped_forecasting",
        target_column=detection.target_column,
        date_column=date_col,
        dimensions=semantic_dimensions,
        horizon=steps,
        table_name=table_name,
        raw_forecast_results=predictions,
        forecast_ranking=predictions,
        ranking_metric=ranking_metric,
        best_group=best_group,
        excluded_groups=excluded,
        dimension_specs=[
            {k: v for k, v in dim.items() if k != "dim_df"} for dim in dimensions
        ],
        restricted_to=restricted_to,
        count=len(ranked),
    )

    # 5. Hard dimensionality check. A grouped forecast that has quietly lost a
    #    dimension still looks like a valid result, so this fails loudly rather
    #    than shipping a confidently mislabelled answer.
    dimension_validation.validate_result_dimensions(result, semantic_dimensions, strict=True)

    logger.info(
        "[Predictor] %s x %s: %d combination(s) forecast, %d excluded, ranked by %s",
        table_name, " x ".join(semantic_dimensions), len(ranked), len(excluded), ranking_metric,
    )
    return result


def _sum_values(rows: list[dict]) -> float | None:
    """
    Sum the ``value`` field of forecast/history rows.

    ``is not None`` rather than a truthiness test: a genuine 0.0 period is a
    real observation and belongs in the total, while a missing period must not
    be silently counted as zero.
    """
    values = [r["value"] for r in rows if r.get("value") is not None]
    return float(sum(values)) if values else None


def _ranking_value(
    hist_rows: list[dict],
    fc_rows: list[dict],
    steps: int,
    ranking_metric: str,
) -> float | None:
    """
    Compute the scalar a group is ranked by: either the forecast total over
    the horizon, or growth against a like-for-like historical baseline.

    Growth returns None (never 0, never infinity) when the baseline is absent
    or non-positive, so an undefined percentage is reported as undefined.
    """
    forecast_total = _sum_values(fc_rows)
    if ranking_metric != "growth":
        return forecast_total

    if forecast_total is None:
        return None

    observed = [r for r in hist_rows if r.get("value") is not None]
    if not observed:
        return None

    baseline_rows = observed[-min(len(observed), steps):]
    baseline_total = _sum_values(baseline_rows)
    if baseline_total is None or baseline_total <= 0:
        return None

    return ((forecast_total - baseline_total) / baseline_total) * 100.0


def _rank_sort_key(entry: dict):
    """Sort descending by final_value, with unforecastable groups last."""
    value = entry.get("final_value")
    return (value is None, -value if value is not None else 0.0)


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
