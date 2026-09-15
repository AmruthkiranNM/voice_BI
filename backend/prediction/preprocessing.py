"""
Prediction Package — Preprocessing

Transforms raw DataFrames into train/test-ready numeric matrices using
a reusable scikit-learn pipeline.

Responsibilities:
  - Drop ID and irrelevant columns.
  - Encode categorical columns (one-hot).
  - Fill missing values.
  - Scale numerical features.
  - Drop constant columns.
  - Train/test split with stratification.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.feature_selection import VarianceThreshold

from prediction.schemas import DetectionResult, PreparedData
from prediction.series_validation import (
    frequency_rule,
    infer_frequency,
    median_step_days,
    normalize_frequency,
)

logger = logging.getLogger(__name__)

# Default test split ratio
_TEST_SIZE = 0.2
_RANDOM_STATE = 42


def build_preprocessor(numeric_features: list[str], categorical_features: list[str]) -> Pipeline:
    """Build a scikit-learn preprocessing pipeline."""
    
    # Numeric pipeline: Impute missing values with median -> Scale
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])

    # Categorical pipeline: Impute with 'missing' -> OneHotEncode
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
        ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
    ])

    # Combine into a ColumnTransformer
    preprocessor_ct = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ],
        remainder='drop'  # Drop any columns not explicitly specified
    )

    # Wrap the entire thing in a pipeline that also removes constant variance columns
    full_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor_ct),
        ('variance_threshold', VarianceThreshold(threshold=0.0))  # drop constants
    ])
    
    return full_pipeline


def prepare_training_data(
    df: pd.DataFrame,
    detection: DetectionResult,
    test_size: float = _TEST_SIZE,
) -> tuple[PreparedData, Pipeline]:
    """
    Transform raw data into train/test splits for model training, and
    return the fitted preprocessing pipeline.

    Args:
        df:        The raw table DataFrame.
        detection: DetectionResult from the detector module.
        test_size: Fraction of data for the test set.

    Returns:
        (PreparedData with X_train, X_test, y_train, y_test, metadata),
        Fitted sklearn Pipeline object
    """
    target_col = detection.target_column
    is_classification = (detection.problem_type or "classification") == "classification"

    if is_classification:
        # Labels may be text ("Yes"/"No"), so encode rather than assume ints.
        y = df[target_col]
        if not pd.api.types.is_numeric_dtype(y):
            y = y.astype("category").cat.codes
        else:
            y = y.astype(int)
    else:
        y = pd.to_numeric(df[target_col], errors="coerce")

    # 1. Train/Test split FIRST to prevent data leakage during imputation/scaling.
    #    Stratification only makes sense for classification: it asks for every
    #    class to be represented in both splits. Applied to a continuous
    #    measure, every distinct value becomes its own "class" and the split
    #    fails with "the least populated class in y has only 1 member" — a
    #    classification error raised on a regression target, which is what made
    #    a numeric measure look like a routing problem.
    df_train, df_test, y_train, y_test = train_test_split(
        df, y,
        test_size=test_size,
        random_state=_RANDOM_STATE,
        stratify=y if is_classification else None,
    )

    # 2. Build and fit preprocessor on training data ONLY
    num_cols = detection.numeric_features
    cat_cols = detection.categorical_features
    
    preprocessor = build_preprocessor(num_cols, cat_cols)
    
    # Fit and transform training data
    X_train_transformed = preprocessor.fit_transform(df_train)
    
    # Transform test data (using parameters learned from training data)
    X_test_transformed = preprocessor.transform(df_test)

    # 3. Extract feature names from the fitted pipeline
    feature_names = _get_feature_names_out(preprocessor, num_cols, cat_cols)

    logger.info(
        "[Preprocessing] Fitted pipeline: %d features, %d train rows, %d test rows.",
        len(feature_names), len(X_train_transformed), len(X_test_transformed),
    )

    prepared = PreparedData(
        X_train=X_train_transformed,
        X_test=X_test_transformed,
        y_train=y_train,
        y_test=y_test,
        feature_names=feature_names,
        target_column=target_col,
    )

    return prepared, preprocessor


def prepare_inference_data(
    df: pd.DataFrame,
    preprocessor: Pipeline,
) -> Any:
    """
    Transform raw data rows using the fitted preprocessor.

    Args:
        df:           Raw data rows to predict on.
        preprocessor: The fitted sklearn Pipeline.

    Returns:
        NumPy array (or sparse matrix) ready for model.predict().
    """
    return preprocessor.transform(df)


def _period_freq(rule: str) -> str | None:
    """Map a resample rule onto the pandas Period alias used to test completeness."""
    return {"W": "W", "ME": "M", "QE": "Q", "YE": "Y"}.get(rule)


def _trim_partial_edges(
    series: pd.Series,
    raw_min: pd.Timestamp,
    raw_max: pd.Timestamp,
    rule: str,
    step_days: float = 0.0,
) -> tuple[pd.Series, int]:
    """
    Drop leading/trailing buckets the raw data does not meaningfully cover.

    A quarter of data summed into an annual bucket is not an annual figure;
    comparing it against complete years, or forecasting from it, understates
    the level by construction.

    The test is a tolerance, not an exact boundary match. A business with no
    transaction on the 1st of the month still had a complete month, so an edge
    bucket is only considered partial when the uncovered span exceeds both a
    couple of the data's own reporting steps and 15% of the bucket length.
    Daily buckets are never trimmed — a day with any data is a complete day.

    Returns (series, number of buckets removed).
    """
    period_alias = _period_freq(rule)
    if period_alias is None or len(series) == 0:
        return series, 0

    def uncovered_is_material(uncovered_days: float, period_days: float) -> bool:
        tolerance = max(2.0 * step_days, 0.15 * period_days)
        return uncovered_days > tolerance

    trimmed = 0

    # Leading bucket
    first_period = series.index[0].to_period(period_alias)
    period_days = (first_period.end_time - first_period.start_time).total_seconds() / 86400.0
    lead_gap = (raw_min.normalize() - first_period.start_time.normalize()).total_seconds() / 86400.0
    if lead_gap > 0 and uncovered_is_material(lead_gap, period_days):
        series = series.iloc[1:]
        trimmed += 1

    # Trailing bucket
    if len(series):
        last_period = series.index[-1].to_period(period_alias)
        period_days = (last_period.end_time - last_period.start_time).total_seconds() / 86400.0
        tail_gap = (last_period.end_time.normalize() - raw_max.normalize()).total_seconds() / 86400.0
        if tail_gap > 0 and uncovered_is_material(tail_gap, period_days):
            series = series.iloc[:-1]
            trimmed += 1

    return series, trimmed


def aggregate_time_series(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    frequency: str = "months",
) -> tuple[pd.Series, dict]:
    """
    Aggregate transactional rows into a regular, gap-aware time series.

    Two properties matter more than anything else here:

    * A period with no rows becomes **NaN, never 0**. ``resample().sum()``
      returns 0.0 for an empty bucket, which is indistinguishable from a real
      zero and silently drags trend models downward; ``min_count=1`` makes the
      absence explicit so validation and the models can treat it as unknown.
    * Incomplete leading/trailing periods are trimmed, so a partial month or
      quarter is never compared against, or extrapolated from, full ones.

    Returns:
        (series indexed by period end, info dict with the facts validation needs)
    """
    rule = frequency_rule(frequency)

    frame = df[[date_col, target_col]].copy()
    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
    frame[target_col] = pd.to_numeric(frame[target_col], errors="coerce")
    frame = frame.dropna(subset=[date_col, target_col])

    info = {
        "rule": rule,
        "frequency": normalize_frequency(frequency),
        "inferred_frequency": "months",
        "duplicate_timestamps": 0,
        "n_trimmed_partial": 0,
        "median_step_days": 0.0,
        "n_rows": int(len(frame)),
    }

    if frame.empty:
        return pd.Series(dtype=float), info

    info["inferred_frequency"] = infer_frequency(frame[date_col])
    info["median_step_days"] = median_step_days(frame[date_col])
    info["duplicate_timestamps"] = int(frame.duplicated().sum())

    raw_min, raw_max = frame[date_col].min(), frame[date_col].max()
    frame = frame.sort_values(date_col).set_index(date_col)

    # min_count=1 → empty buckets are NaN rather than a fabricated 0.0
    series = frame[target_col].resample(rule).sum(min_count=1)

    series, trimmed = _trim_partial_edges(
        series, raw_min, raw_max, rule, step_days=info["median_step_days"],
    )
    info["n_trimmed_partial"] = trimmed

    return series, info


def prepare_forecasting_data(
    df: pd.DataFrame,
    detection: DetectionResult,
    frequency: str = "months",
) -> pd.Series:
    """
    Preprocess time-series data for forecasting.

    Thin wrapper over :func:`aggregate_time_series` kept for the existing
    callers (trainer, predictor). Empty periods come back as NaN, not zero.
    """
    series, _ = aggregate_time_series(
        df, detection.date_column, detection.target_column, frequency=frequency
    )
    return series


def prepare_grouped_forecasting_data(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    group_cols: list[str],
    frequency: str = "months",
) -> dict[tuple, pd.Series]:
    """
    Aggregate one time series per group combination.

    Keys are **tuples** of the group values, one element per entry in
    ``group_cols``, so a country x product forecast keeps both dimensions
    addressable downstream. (They used to be pre-joined strings, which made
    the product dimension unrecoverable once the series was built.)

    Every group is returned, including ones too sparse to forecast — the
    caller decides what to do with them and reports the reason.
    """
    series_by_group, _ = prepare_grouped_forecasting_data_with_info(
        df, date_col, target_col, group_cols, frequency=frequency
    )
    return series_by_group


def prepare_grouped_forecasting_data_with_info(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    group_cols: list[str],
    frequency: str = "months",
) -> tuple[dict[tuple, pd.Series], dict[tuple, dict]]:
    """Same as :func:`prepare_grouped_forecasting_data`, plus per-group aggregation facts."""
    cols_to_keep = [date_col, target_col] + list(group_cols)
    frame = df[cols_to_keep].copy()

    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
    frame[target_col] = pd.to_numeric(frame[target_col], errors="coerce")
    frame = frame.dropna(subset=[date_col, target_col] + list(group_cols))

    series_by_group: dict[tuple, pd.Series] = {}
    info_by_group: dict[tuple, dict] = {}

    if frame.empty:
        return series_by_group, info_by_group

    for group_vals, group_df in frame.groupby(list(group_cols), dropna=True):
        key = group_vals if isinstance(group_vals, tuple) else (group_vals,)
        key = tuple(str(v) for v in key)

        series, info = aggregate_time_series(
            group_df, date_col, target_col, frequency=frequency
        )
        series_by_group[key] = series
        info_by_group[key] = info

    return series_by_group, info_by_group

def _get_feature_names_out(pipeline: Pipeline, numeric_features: list[str], categorical_features: list[str]) -> list[str]:
    """
    Extract human-readable feature names from a fitted Pipeline containing a ColumnTransformer
    and a VarianceThreshold.
    """
    # 1. Get names out of the ColumnTransformer
    ct = pipeline.named_steps['preprocessor']
    
    names = []
    
    # Add numeric feature names
    names.extend(numeric_features)
    
    # Add categorical feature names (from OneHotEncoder)
    if 'cat' in ct.named_transformers_:
        cat_pipe = ct.named_transformers_['cat']
        if cat_pipe != 'drop' and hasattr(cat_pipe.named_steps['onehot'], 'get_feature_names_out'):
            ohe = cat_pipe.named_steps['onehot']
            cat_names = ohe.get_feature_names_out(categorical_features)
            names.extend(cat_names.tolist())

    # 2. Filter out names that were dropped by VarianceThreshold
    vt = pipeline.named_steps['variance_threshold']
    if hasattr(vt, 'get_support'):
        support = vt.get_support()
        if len(support) == len(names):
            names = [names[i] for i in range(len(names)) if support[i]]
            
    return names
