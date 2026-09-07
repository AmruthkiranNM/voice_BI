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
    problem_type: str = "classification" # "classification" or "regression"
    version: int = 1


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
