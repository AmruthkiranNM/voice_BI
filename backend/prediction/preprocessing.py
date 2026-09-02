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
    y = df[target_col].astype(int)

    # 1. Train/Test split FIRST to prevent data leakage during imputation/scaling
    df_train, df_test, y_train, y_test = train_test_split(
        df, y,
        test_size=test_size,
        random_state=_RANDOM_STATE,
        stratify=y,
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


def prepare_forecasting_data(
    df: pd.DataFrame,
    detection: DetectionResult,
    frequency: str = "months",
) -> pd.Series:
    """
    Preprocess time-series data for forecasting.
    Sorts chronologically, aggregates if needed, and returns a Series with a datetime index.
    """
    date_col = detection.date_column
    target_col = detection.target_column

    # Convert to datetime and drop invalid
    df_ts = df[[date_col, target_col]].copy()
    df_ts[date_col] = pd.to_datetime(df_ts[date_col], errors="coerce")
    df_ts = df_ts.dropna(subset=[date_col, target_col])

    # Convert target to numeric
    df_ts[target_col] = pd.to_numeric(df_ts[target_col], errors="coerce")
    df_ts = df_ts.dropna(subset=[target_col])

    # Sort chronologically
    df_ts = df_ts.sort_values(date_col)

    # Convert frequency string to Pandas offset alias
    freq_map = {
        "months": "M", "month": "M",
        "days": "D", "day": "D",
        "years": "Y", "year": "Y",
        "weeks": "W", "week": "W",
        "periods": "M", "period": "M",
    }
    rule = freq_map.get(frequency.lower(), "M")

    # Set index and resample/aggregate
    df_ts = df_ts.set_index(date_col)
    series_ts = df_ts[target_col].resample(rule).sum()

    return series_ts


def prepare_grouped_forecasting_data(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    group_col: str,
    frequency: str = "months",
) -> dict[str, pd.Series]:
    """
    Preprocess time-series data grouped by a dimension.
    Returns a dictionary mapping group names to their aggregated Series.
    """
    df_ts = df[[date_col, target_col, group_col]].copy()
    df_ts[date_col] = pd.to_datetime(df_ts[date_col], errors="coerce")
    df_ts[target_col] = pd.to_numeric(df_ts[target_col], errors="coerce")
    df_ts = df_ts.dropna(subset=[date_col, target_col, group_col])
    
    freq_map = {
        "months": "M", "month": "M",
        "days": "D", "day": "D",
        "years": "Y", "year": "Y",
        "weeks": "W", "week": "W",
        "periods": "M", "period": "M",
    }
    rule = freq_map.get(frequency.lower(), "M")

    grouped_series = {}
    
    # Iterate over unique groups
    for group_name, group_df in df_ts.groupby(group_col):
        # Sort chronologically
        g_df = group_df.sort_values(date_col)
        # Set index and aggregate
        g_df = g_df.set_index(date_col)
        s = g_df[target_col].resample(rule).sum()
        
        # Keep only groups with at least a few points
        if len(s) >= 3:
            grouped_series[str(group_name)] = s
            
    return grouped_series

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
