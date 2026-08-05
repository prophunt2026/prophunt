"""
Evaluation metrics.
=============================================================
Back-transforms log-space predictions to original TND scale and
computes the five business-facing metrics (RMSE, MAE, R2, MAPE, MedAE)
used throughout validation, reporting, and visualization.
"""

from typing import Any, Dict

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
)


def expm1_to_original(y_log: np.ndarray) -> np.ndarray:
    """Back-transform log-space targets/predictions to original scale (TND).

    Uses ``np.maximum`` instead of ``.clip(lower=0)`` because NumPy ndarrays
    accept ``min``/``max`` clip kwargs, not pandas-style ``lower``/``upper``.
    """
    return np.maximum(np.expm1(np.asarray(y_log, dtype=float)), 0.0)


def compute_metrics(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
) -> Dict[str, float]:
    """Compute all evaluation metrics in original price space (TND).

    Back-transforms from log-space: actual = expm1(y_log)
    """
    y_true = expm1_to_original(y_true_log)
    y_pred = expm1_to_original(y_pred_log)

    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    medae = median_absolute_error(y_true, y_pred)

    # MAPE (avoid division by zero)
    mask = y_true > 0
    mape = mean_absolute_percentage_error(y_true[mask], y_pred[mask]) * 100 if mask.sum() > 0 else float('inf')

    return {
        'RMSE': round(rmse, 2),
        'MAE': round(mae, 2),
        'R2': round(r2, 4),
        'MAPE': round(mape, 2),
        'MedAE': round(medae, 2),
    }


def evaluate_on_splits(
    model: BaseEstimator,
    X_train: np.ndarray, y_train: pd.Series,
    X_val: np.ndarray, y_val: pd.Series,
    X_test: np.ndarray, y_test: pd.Series,
) -> Dict[str, Dict[str, Any]]:
    """Evaluate model on train, val, and test splits."""
    results = {}

    for split_name, X, y in [
        ('train', X_train, y_train),
        ('val', X_val, y_val),
        ('test', X_test, y_test),
    ]:
        y_pred = model.predict(X)
        metrics = compute_metrics(y.values, y_pred)
        results[split_name] = {
            'metrics': metrics,
            'y_true': y.values,
            'y_pred': y_pred,
        }

    return results
