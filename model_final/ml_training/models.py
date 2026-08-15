"""
Model definitions and two-phase hyperparameter tuning.
=============================================================
Defines the six candidate models, their Phase-1 (RandomizedSearchCV)
parameter distributions, the Phase-2 narrow-grid refinement logic, and
the search-execution functions for both phases.
"""

import time
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestRegressor, VotingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Lasso, LinearRegression, Ridge
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV

from .config import logger, RANDOM_STATE
from .optional_deps import HAS_XGBOOST, XGBRegressor, HAS_LIGHTGBM, LGBMRegressor, HAS_CATBOOST, CatBoostRegressor
from .two_head_model import VenteLocationTwoHeadRegressor


def get_models() -> Dict[str, BaseEstimator]:
    """Return the 6 candidate models."""
    models = {
        'HistGradientBoosting': HistGradientBoostingRegressor(
            loss='absolute_error',
            max_iter=200,
            random_state=RANDOM_STATE,
        ),
        'RandomForest': RandomForestRegressor(
            n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1
        ),
    }
    if HAS_XGBOOST:
        # P1-B FIX: Changed from 'reg:pseudohubererror' which caused
        # exploding gradients (RMSE 165 vs ~0.43 for other models).
        # See Diagnostics Report §5.5.
        models['XGBoost'] = XGBRegressor(
            objective='reg:squarederror',
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            max_delta_step=1,           # gradient clipping
            tree_method='hist',         # consistent with HistGBT
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    if HAS_LIGHTGBM:
        models['LightGBM'] = LGBMRegressor(
            objective='huber',
            alpha=1.0, # Huber delta
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbose=-1,
        )
    if HAS_CATBOOST:
        models['CatBoost'] = CatBoostRegressor(
            loss_function='MAE',
            iterations=200,
            learning_rate=0.05,
            depth=6,
            random_seed=RANDOM_STATE,
            verbose=False,
            thread_count=-1,
        )
    if HAS_XGBOOST and HAS_LIGHTGBM:
        estimators = [
            ('xgb', models['XGBoost']),
            ('lgbm', models['LightGBM'])
        ]
        if HAS_CATBOOST:
            estimators.append(('cb', models['CatBoost']))
        models['Ensemble'] = VotingRegressor(
            estimators=estimators
        )

    # P2-A: Two-head model (separate VENTE/LOCATION sub-models).
    # The is_vente_col_idx is set dynamically in pipeline.py after
    # preprocessing, because the column index depends on ColumnTransformer
    # output ordering.  We register it here with idx=None (fallback mode)
    # and pipeline.py patches it before training.
    models['TwoHead'] = VenteLocationTwoHeadRegressor(
        is_vente_col_idx=None,  # set by pipeline.py
    )

    return models


def get_param_distributions() -> Dict[str, Dict[str, Any]]:
    """Define parameter search spaces for Phase 1 (RandomizedSearchCV)."""
    param_dist = {
        'HistGradientBoosting': {
            'learning_rate': [0.01, 0.05, 0.1],
            'max_iter': [100, 200, 300],
            'max_depth': [3, 5, 8, None],
            'min_samples_leaf': [10, 20, 50],
            'l2_regularization': [0.0, 0.1, 1.0, 5.0],
        },
        'RandomForest': {
            'n_estimators': [100, 200, 300, 500],
            'max_depth': [5, 10, 15, 20, None],
            'min_samples_split': [2, 5, 10, 20],
            'min_samples_leaf': [1, 2, 4, 8],
            'max_features': ['sqrt', 'log2', 0.5, 0.8],
        },
    }
    if HAS_XGBOOST:
        param_dist['XGBoost'] = {
            'n_estimators': [100, 200, 300, 500],
            'learning_rate': [0.01, 0.03, 0.05, 0.1],
            'max_depth': [3, 4, 5, 6, 8],
            'min_child_weight': [1, 3, 5, 7],
            'subsample': [0.7, 0.8, 0.9, 1.0],
            'colsample_bytree': [0.7, 0.8, 0.9, 1.0],
            'reg_alpha': [0, 0.01, 0.1, 1.0],
            'reg_lambda': [0.1, 1.0, 5.0, 10.0],
        }
    if HAS_LIGHTGBM:
        param_dist['LightGBM'] = {
            'n_estimators': [100, 200, 300, 500],
            'learning_rate': [0.01, 0.03, 0.05, 0.1],
            'max_depth': [8, 10, -1],
            'num_leaves': [40, 50, 63, 100],
            'min_child_samples': [10, 15, 20],
            'subsample': [0.7, 0.8, 0.9, 1.0],
            'colsample_bytree': [0.7, 0.8, 0.9, 1.0],
            'reg_alpha': [0, 0.01, 0.05, 0.1],
            'reg_lambda': [0, 0.1, 0.5, 1.0],
        }
    if HAS_CATBOOST:
        param_dist['CatBoost'] = {
            'iterations': [100, 200, 300, 500],
            'learning_rate': [0.01, 0.03, 0.05, 0.1],
            'depth': [4, 6, 8, 10],
            'l2_leaf_reg': [1, 3, 5, 7, 9],
            'subsample': [0.7, 0.8, 0.9, 1.0],
        }
    return param_dist


def narrow_param_grid(best_params: Dict[str, Any], model_name: str) -> Dict[str, List[Any]]:
    """Create a narrow grid around the best parameters from Phase 1.

    For each parameter, creates a list of [best - step, best, best + step]
    where step is a reasonable increment.
    """
    grid = {}

    step_map = {
        'alpha': [0.5, 1.0, 2.0, 5.0],
        'n_estimators': [50, 50, 100],
        'learning_rate': [0.01, 0.01, 0.02],
        'max_depth': [1, 1, 2],
        'min_child_weight': [1, 1, 2],
        'subsample': [0.05, 0.1, 0.1],
        'colsample_bytree': [0.05, 0.1, 0.1],
        'reg_alpha': [0.01, 0.05, 0.1],
        'reg_lambda': [0.5, 1.0, 2.0],
        'min_samples_split': [1, 2, 3],
        'min_samples_leaf': [1, 1, 2],
        'num_leaves': [8, 10, 15],
        'min_child_samples': [3, 5, 5],
        'max_iter': [1000, 1000, 2000],
        'iterations': [50, 50, 100],
        'depth': [1, 1, 2],
        'l2_leaf_reg': [1, 1, 2],
        'l2_regularization': [0.1, 0.5, 1.0],
    }

    param_min = {
        'min_samples_split': 2,
        'min_samples_leaf': 1,
        'num_leaves': 2,
        'min_child_samples': 1,
        'min_child_weight': 0,
        'n_estimators': 10,
        'max_depth': 1,
        'max_iter': 100,
        'learning_rate': 0.001,
        'alpha': 0.0001,
        'reg_alpha': 0.0,
        'reg_lambda': 0.0,
        'subsample': 0.1,
        'colsample_bytree': 0.1,
    }

    for param, val in best_params.items():
        if param == 'random_state' or param == 'n_jobs' or param == 'verbose':
            continue

        steps = step_map.get(param, [1])
        step = steps[0] if isinstance(steps, list) else steps
        floor = param_min.get(param, 0)

        if isinstance(val, (int, np.integer)):
            lower = max(floor, int(val - steps[0])) if len(steps) >= 2 else max(floor, val - step)
            upper = val + (steps[1] if len(steps) >= 2 else step)
            grid[param] = sorted(set([lower, val, upper]))
        elif isinstance(val, float):
            float_floor = max(floor, 0.001)
            lower = max(float_floor, round(val - steps[0], 4)) if len(steps) >= 2 else max(float_floor, round(val - step, 4))
            upper = round(val + (steps[1] if len(steps) >= 2 else step), 4)
            grid[param] = sorted(set([lower, val, upper]))
        else:
            grid[param] = [val]

    return grid


def phase1_random_search(
    models: Dict[str, BaseEstimator],
    X_train: np.ndarray,
    y_train: pd.Series,
    cv: Any = 5,
    n_iter: int = 100,
) -> Dict[str, Dict[str, Any]]:
    """Phase 1: RandomizedSearchCV for all models."""
    logger.info(f"\n{'='*60}")
    logger.info("PHASE 1: Randomized Hyperparameter Search")
    logger.info(f"{'='*60}")

    param_distributions = get_param_distributions()
    results = {}

    for name, model in models.items():
        logger.info(f"\n--- {name} ---")
        params = param_distributions.get(name, {})
        if not params:
            logger.info(f"  No search space defined. Skipping search.")
            model.fit(X_train, y_train)
            results[name] = {
                'model': model,
                'best_params': model.get_params(),
                'best_cv_rmse': None,
                'search': None,
            }
            continue

        # Prevent internal model multiprocessing from conflicting with GridSearchCV multiprocessing
        if hasattr(model, 'n_jobs'):
            model.set_params(n_jobs=1)

        search = RandomizedSearchCV(
            estimator=model,
            param_distributions=params,
            n_iter=min(n_iter, max(20, len(params) * 10)),
            scoring='neg_root_mean_squared_error',
            cv=cv,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbose=0,
            refit=True,
        )

        t0 = time.time()
        search.fit(X_train, y_train)
        elapsed = time.time() - t0

        best_rmse = -search.best_score_
        logger.info(f"  Best CV RMSE (log): {best_rmse:.4f}")
        logger.info(f"  Best params: {search.best_params_}")
        logger.info(f"  Time: {elapsed:.1f}s")

        results[name] = {
            'model': search.best_estimator_,
            'best_params': search.best_params_,
            'best_cv_rmse': best_rmse,
            'search': search,
        }

    return results


def phase2_grid_search(
    phase1_results: Dict[str, Dict[str, Any]],
    X_train: np.ndarray,
    y_train: pd.Series,
    cv: Any = 5,
    top_n: int = 3,
) -> Dict[str, Dict[str, Any]]:
    """Phase 2: Focused Grid Search / Random Search (top models) around Phase 1 best parameters."""
    logger.info(f"\n{'='*60}")
    logger.info("PHASE 2: Focused Hyperparameter Refinement (top models)")
    logger.info(f"{'='*60}")

    # Select top models by CV RMSE
    scored = [(name, r) for name, r in phase1_results.items() if r['best_cv_rmse'] is not None]
    scored.sort(key=lambda x: x[1]['best_cv_rmse'])
    top_models = scored[:top_n]

    logger.info(f"Top {top_n} models from Phase 1:")
    for name, r in top_models:
        logger.info(f"  {name}: RMSE={r['best_cv_rmse']:.4f}")

    refined_results = {}

    for name, phase1_result in top_models:
        logger.info(f"\n--- Refining {name} ---")

        param_grid = narrow_param_grid(phase1_result['best_params'], name)
        logger.info(f"  Narrow grid: {param_grid}")

        base_model = phase1_result['model']
        
        # Prevent internal model multiprocessing from conflicting with Scikit-Learn
        if hasattr(base_model, 'n_jobs'):
            base_model.set_params(n_jobs=1)

        # OPTIMIZATION: Use RandomizedSearchCV for tree-based models, GridSearchCV for linear ones
        if name in ['LightGBM', 'RandomForest', 'XGBoost', 'CatBoost', 'HistGradientBoosting']:
            logger.info(f"  Using RandomizedSearchCV for {name} to prevent combinatorial explosion.")
            search = RandomizedSearchCV(
                estimator=base_model,
                param_distributions=param_grid,
                n_iter=20,  # 20 iterations for refinement
                scoring='neg_root_mean_squared_error',
                cv=cv,
                random_state=RANDOM_STATE,
                n_jobs=-1,
                verbose=0,
                refit=True,
            )
        else:
            logger.info(f"  Using GridSearchCV for {name}.")
            search = GridSearchCV(
                estimator=base_model,
                param_grid=param_grid,
                scoring='neg_root_mean_squared_error',
                cv=cv,
                n_jobs=-1,
                verbose=0,
                refit=True,
            )

        t0 = time.time()
        search.fit(X_train, y_train)
        elapsed = time.time() - t0

        best_rmse = -search.best_score_
        logger.info(f"  Refined CV RMSE (log): {best_rmse:.4f}")
        logger.info(f"  Best params: {search.best_params_}")
        logger.info(f"  Time: {elapsed:.1f}s")

        refined_results[name] = {
            'model': search.best_estimator_,
            'best_params': search.best_params_,
            'best_cv_rmse': best_rmse,
            'search': search,
        }

    return refined_results
