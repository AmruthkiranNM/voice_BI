"""
Prediction Package — Schemas

Dataclass-based schemas defining the interfaces between prediction modules.
Every module in the prediction package communicates through these types,
keeping the contracts explicit and the modules decoupled.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class ColumnProfile:
    """Profile of a single column for prediction suitability analysis."""
    name: str
    dtype: str                     # "numeric", "categorical", "id", "text"
    unique_count: int = 0
    null_count: int = 0
    total_count: int = 0
    sample_values: list[Any] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class DetectionResult:
    """
    Result of scanning a table for prediction problems.
    """
    table_name: str
    is_suitable: bool
    target_column: str | None = None
    target_classes: list[Any] = dataclasses.field(default_factory=list)
    problem_type: str | None = None
    feature_columns: list[str] = dataclasses.field(default_factory=list)
    categorical_features: list[str] = dataclasses.field(default_factory=list)
    numeric_features: list[str] = dataclasses.field(default_factory=list)
    id_columns: list[str] = dataclasses.field(default_factory=list)
    drop_columns: list[str] = dataclasses.field(default_factory=list)
    missing_values: dict[str, int] = dataclasses.field(default_factory=dict)
    row_count: int = 0
    class_distribution: dict[str, int] = dataclasses.field(default_factory=dict)
    reason: str = ""
    date_column: str | None = None



@dataclasses.dataclass
class PreparedData:
    """
    Result of the preprocessing step: train/test split ready for a model.
    """
    X_train: Any  # pd.DataFrame
    X_test: Any   # pd.DataFrame
    y_train: Any  # pd.Series
    y_test: Any   # pd.Series
    feature_names: list[str] = dataclasses.field(default_factory=list)
    target_column: str = ""
    encoding_map: dict[str, list[str]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class EvaluationResult:
    """
    Model evaluation metrics.
    """
    # Classification metrics
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    roc_auc: float = 0.0
    confusion_matrix: list[list[int]] = dataclasses.field(default_factory=list)
    classification_report: dict[str, Any] = dataclasses.field(default_factory=dict)
    
    # Regression metrics
    mae: float = 0.0
    rmse: float = 0.0
    r2: float = 0.0


@dataclasses.dataclass
class TrainedModelArtifact:
    """
    Everything that needs to be persisted for a trained model.
    """
    model: Any                        # The sklearn estimator
    preprocessor: Any = None          # The fitted sklearn Pipeline/ColumnTransformer
    feature_names: list[str] = dataclasses.field(default_factory=list)
    target_column: str = ""
    table_name: str = ""
    evaluation: EvaluationResult = dataclasses.field(default_factory=EvaluationResult)
    feature_importances: list[tuple[str, float]] = dataclasses.field(default_factory=list)
    model_type: str = "RandomForestClassifier"
    problem_type: str = "classification" # "classification", "regression" or "forecasting"
    version: int = 1

    # ── Forecasting-only provenance ──
    # The bucket size the model was fitted on. A forecasting artifact is only
    # valid for the frequency it was trained at.
    forecast_frequency: str | None = None
    series_diagnostics: "SeriesDiagnostics | None" = None
    selection_metadata: "ForecastModelMetadata | None" = None


@dataclasses.dataclass
class PredictionRow:
    """
    Prediction output for a single row.
    """
    customer_id: Any                  # The primary identifier
    prediction: Any                   # Predicted class (int) or predicted value (float)
    probability: float | None = None  # P(positive class), None for regression
    risk: str | None = None           # "Low", "Medium", "High", None for regression
    row_data: dict[str, Any] = dataclasses.field(default_factory=dict)
    feature_impacts: list[dict[str, Any]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class PredictionResult:
    """
    Complete prediction output for one or more rows.
    """
    predictions: list[PredictionRow]
    model_accuracy: float
    target_column: str
    table_name: str
    count: int = 0
    truncated: bool = False


@dataclasses.dataclass
class SeriesDiagnostics:
    """
    Deterministic health report for one time series, produced *before* any
    model is fitted. Every forecast carries the diagnostics of the series it
    was built from, so a number can always be traced back to the amount and
    quality of history behind it.

    ``status`` is the gate: only "ok" and "fallback" series are forecast.
    """
    status: str = "ok"                # ok | fallback | no_data | insufficient_history | too_sparse
    reason: str = ""                  # human-readable explanation when not "ok"

    requested_frequency: str = ""     # what the question asked for
    inferred_frequency: str = ""      # what the raw timestamps actually support
    frequency_mismatch: bool = False  # requested finer than the data supports

    first_period: str | None = None
    last_period: str | None = None
    n_periods: int = 0                # buckets spanned (observed + missing)
    n_observed: int = 0               # buckets with a real value
    n_missing: int = 0                # buckets with no data (NEVER coerced to zero)
    missing_ratio: float = 0.0

    n_trimmed_partial: int = 0        # leading/trailing incomplete buckets dropped
    duplicate_timestamps: int = 0     # exact-duplicate raw timestamps seen before aggregation

    is_constant: bool = False
    is_all_zero: bool = False

    n_outliers: int = 0               # robust MAD-based, reported not removed
    outlier_periods: list[str] = dataclasses.field(default_factory=list)

    seasonal_periods: int | None = None
    seasonality_supported: bool = False   # >= 2 full cycles of history

    horizon: int = 0
    history_to_horizon_ratio: float = 0.0
    horizon_exceeds_history: bool = False

    warnings: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ValidationFold:
    """One chronological rolling-origin backtest fold for one candidate model."""
    fold: int
    train_end: str
    n_train: int
    n_validation: int
    mae: float | None = None
    rmse: float | None = None
    mase: float | None = None


@dataclasses.dataclass
class CandidateScore:
    """Aggregated backtest performance of one candidate model across all folds."""
    model_key: str
    model_label: str
    eligible: bool = True
    reason: str = ""
    mae: float | None = None
    rmse: float | None = None
    mase: float | None = None          # < 1.0 means it beat the naive baseline
    n_folds: int = 0
    folds: list[ValidationFold] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ForecastModelMetadata:
    """
    Everything needed to defend a forecast: which model won, how it was
    chosen, what it scored against the naive baseline, and what was done
    to the data before fitting.
    """
    selected_model_key: str = ""
    selected_model_label: str = ""
    selection_method: str = ""         # rolling_origin_backtest | fallback_no_validation | forced_constant
    selection_metric: str = "mase"
    selected_score: float | None = None
    beats_naive: bool | None = None    # selected MASE < naive MASE
    n_folds: int = 0
    validation_horizon: int = 0
    candidates: list[CandidateScore] = dataclasses.field(default_factory=list)
    n_imputed_for_fit: int = 0         # internal gaps interpolated for FITTING only
    floor_applied: bool = False        # forecasts clipped at 0 (series was non-negative)
    interval_source: str = ""          # validation_residuals | in_sample_residuals | none
    notes: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ForecastingRow:
    """
    Prediction output for a single time step in forecasting.
    """
    date: Any
    is_historical: bool
    value: float | None = None       # Actual historical value or the predicted point forecast
    lower_bound: float | None = None # Confidence interval lower bound
    upper_bound: float | None = None # Confidence interval upper bound


@dataclasses.dataclass
class ForecastingResult:
    """
    Complete forecasting output.
    """
    historical: list[ForecastingRow]
    forecast: list[ForecastingRow]
    model_accuracy: float
    target_column: str
    date_column: str
    table_name: str
    count: int = 0


@dataclasses.dataclass
class TrendDirectionResult:
    """
    Result for trend direction forecasting.
    """
    target_column: str
    date_column: str
    direction: str  # "increase", "decrease", "stable"
    horizon: int
    historical: list[ForecastingRow]
    forecast: list[ForecastingRow]
    table_name: str


@dataclasses.dataclass
class GroupedForecastingResult:
    """
    Result for grouped forecasting.
    """
    target_column: str
    date_column: str
    group_dimensions: list[str]
    horizon: int
    table_name: str
    predictions: list[dict[str, Any]] # e.g. [{"group": "India", "forecast": [ForecastingRow...], "final_value": 1500, "historical": [...]}]
    ranking_metric: str = "sum"
    best_group: str | None = None


@dataclasses.dataclass
class TrainingExperimentResult:
    """
    Result of training multiple candidate models.
    """
    models: list[TrainedModelArtifact] = dataclasses.field(default_factory=list)
    training_results: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    best_model_key: str = ""
    selection_metric: str = ""


@dataclasses.dataclass
class UniversalPredictionResult:
    """
    Unified result schema covering classification, regression, time-series, and grouped forecasting.
    Replaces the fragmented PredictionResult, ForecastingResult, etc.
    """
    task_type: str
    target_column: str
    table_name: str
    
    # Classification / Regression row predictions
    row_predictions: list[PredictionRow] = dataclasses.field(default_factory=list)
    
    # Time-series / Forecasting
    date_column: str | None = None
    historical: list[ForecastingRow] = dataclasses.field(default_factory=list)
    forecast: list[ForecastingRow] = dataclasses.field(default_factory=list)
    direction: str | None = None  # "increase", "decrease", "stable"
    horizon: int = 0
    
    # Grouped Forecasting
    dimensions: list[str] = dataclasses.field(default_factory=list)
    historical_ranking: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    forecast_ranking: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    raw_forecast_results: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    available_granularities: list[list[str]] = dataclasses.field(default_factory=list)
    
    # Store dynamic follow-up visualization data (e.g. deterministic rankings) without destroying raw data
    derived_insights: dict[str, Any] | None = None
    
    ranking_metric: str | None = None
    best_group: str | None = None

    # ── Forecast provenance (populated by the forecasting engine) ──
    # For an ungrouped forecast these describe the single series. For a
    # grouped forecast they describe the pooled/base series, while each entry
    # in raw_forecast_results carries its own "diagnostics" and "model".
    series_diagnostics: SeriesDiagnostics | None = None
    model_metadata: ForecastModelMetadata | None = None
    # Groups that were deliberately NOT forecast, with the reason why.
    excluded_groups: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    # How each requested dimension was resolved to a real column, including the
    # join key used and how confident the match was. Lets a caller verify the
    # forecast is grouped by what was actually asked for.
    dimension_specs: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    # Populated only when the user explicitly restricted the group set;
    # empty means every eligible combination was forecast before ranking.
    restricted_to: dict[str, list[str]] = dataclasses.field(default_factory=dict)

    # Metadata
    model_accuracy: float = 0.0
    count: int = 0
