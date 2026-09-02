"""
Prediction Package — Evaluator

Computes metrics for a trained model against held-out data.
Supports classification and regression.
"""

import logging
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from prediction.schemas import EvaluationResult

logger = logging.getLogger(__name__)


def evaluate(model: Any, X_test, y_test, problem_type: str = "classification") -> EvaluationResult:
    """
    Evaluate a fitted model on test data.
    """
    y_pred = model.predict(X_test)
    
    if problem_type == "regression":
        mae = mean_absolute_error(y_test, y_pred)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2 = r2_score(y_test, y_pred)
        
        logger.info("[Evaluator] Regression - MAE=%.4f, RMSE=%.4f, R2=%.4f", mae, rmse, r2)
        
        return EvaluationResult(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            r2=round(r2, 4),
        )

    # Otherwise, classification
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    # ROC-AUC requires probability estimates
    try:
        y_prob = model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)
    except Exception:
        auc = 0.0

    cm = confusion_matrix(y_test, y_pred).tolist()
    report = classification_report(y_test, y_pred, output_dict=True)

    logger.info(
        "[Evaluator] Classification - Accuracy=%.4f, Precision=%.4f, Recall=%.4f, F1=%.4f, AUC=%.4f",
        acc, prec, rec, f1, auc,
    )

    return EvaluationResult(
        accuracy=round(acc, 4),
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1_score=round(f1, 4),
        roc_auc=round(auc, 4),
        confusion_matrix=cm,
        classification_report=report,
    )
