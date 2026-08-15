"""
Evaluation metrics.
=============================================================
Back-transforms log-space predictions to original TND scale and
computes the five business-facing metrics (RMSE, MAE, R2, MAPE, MedAE)
used throughout validation, reporting, and visualization.

P1-A: Added raw total-price evaluation as primary metric
(Diagnostics Report §4.1, §5.1 — the "log-space illusion").
"""

from typing import Any, Dict, Optional

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


def compute_log_space_metrics(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
) -> Dict[str, float]:
    """Compute evaluation metrics in log-space (for reference/comparison).

    These are the metrics that were previously used as primary.
    Now kept as secondary diagnostics alongside raw-price metrics.
    """
    y_true = np.asarray(y_true_log, dtype=float)
    y_pred = np.asarray(y_pred_log, dtype=float)

    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    medae = median_absolute_error(y_true, y_pred)

    mask = np.abs(y_true) > 1e-6
    mape = mean_absolute_percentage_error(y_true[mask], y_pred[mask]) * 100 if mask.sum() > 0 else float('inf')

    return {
        'RMSE_log': round(rmse, 4),
        'MAE_log': round(mae, 4),
        'R2_log': round(r2, 4),
        'MAPE_log': round(mape, 2),
        'MedAE_log': round(medae, 4),
    }


def compute_raw_price_metrics(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
    surface: np.ndarray,
) -> Dict[str, float]:
    """P1-A: Compute metrics in raw total-price space (TND).

    Converts log(price/m²) predictions to total price:
        total_price = expm1(log_per_m2) * surface

    This is the PRIMARY evaluation metric per the diagnostics report
    (§4.1, §5.1 — the "log-space illusion"). Log-space RMSE of 0.43
    hides MAE of 115K–400K TND in raw price space.
    """
    surface = np.asarray(surface, dtype=float)
    # Guard against zero/NaN surface
    surface_safe = np.where(np.isfinite(surface) & (surface > 0), surface, 1.0)

    y_true_price = expm1_to_original(y_true_log) * surface_safe
    y_pred_price = expm1_to_original(y_pred_log) * surface_safe

    # Filter out invalid entries
    valid = np.isfinite(y_true_price) & np.isfinite(y_pred_price) & (y_true_price > 0)
    if valid.sum() == 0:
        return {
            'RMSE_raw': float('inf'),
            'MAE_raw': float('inf'),
            'R2_raw': 0.0,
            'MAPE_raw': float('inf'),
            'MedAE_raw': float('inf'),
        }

    yt = y_true_price[valid]
    yp = y_pred_price[valid]

    return {
        'RMSE_raw': round(float(np.sqrt(mean_squared_error(yt, yp))), 2),
        'MAE_raw': round(float(mean_absolute_error(yt, yp)), 2),
        'R2_raw': round(float(r2_score(yt, yp)), 4),
        'MAPE_raw': round(float(mean_absolute_percentage_error(yt, yp) * 100), 2),
        'MedAE_raw': round(float(median_absolute_error(yt, yp)), 2),
    }


def evaluate_on_splits(
    model: BaseEstimator,
    X_train: np.ndarray, y_train: pd.Series,
    X_val: np.ndarray, y_val: pd.Series,
    X_test: np.ndarray, y_test: pd.Series,
    surface_train: Optional[np.ndarray] = None,
    surface_val: Optional[np.ndarray] = None,
    surface_test: Optional[np.ndarray] = None,
) -> Dict[str, Dict[str, Any]]:
    """Evaluate model on train, val, and test splits.

    P1-A: Now computes metrics in three spaces:
    1. Per-m² price space (expm1 of log target) — original behavior
    2. Log-space — secondary diagnostics
    3. Raw total-price TND — PRIMARY metric for business alignment
    """
    results = {}
    surfaces = {
        'train': surface_train,
        'val': surface_val,
        'test': surface_test,
    }

    for split_name, X, y in [
        ('train', X_train, y_train),
        ('val', X_val, y_val),
        ('test', X_test, y_test),
    ]:
        y_pred = model.predict(X)
        metrics = compute_metrics(y.values, y_pred)
        log_metrics = compute_log_space_metrics(y.values, y_pred)

        result = {
            'metrics': metrics,
            'log_metrics': log_metrics,
            'y_true': y.values,
            'y_pred': y_pred,
        }

        # P1-A: Add raw-price metrics if surface data is available
        surf = surfaces.get(split_name)
        if surf is not None:
            raw_metrics = compute_raw_price_metrics(y.values, y_pred, surf)
            result['raw_metrics'] = raw_metrics

        results[split_name] = result

    return results
