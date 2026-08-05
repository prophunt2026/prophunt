"""
Main training pipeline orchestrator.
=============================================================
Wires together data loading, splitting, preprocessing, model
selection/tuning, evaluation, the 7-step validation pipeline,
visualizations, feature importance, and artifact saving into a single
`main()` entry point.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd

from .config import logger, RANDOM_STATE
from .data_loading import (
    load_metadata,
    load_and_prepare_data,
    create_composite_stratifier,
    stratified_train_val_test_split,
)
from .preprocessing import build_preprocessing_pipeline, get_all_feature_columns
from .models import get_models, phase1_random_search, phase2_grid_search
from .evaluation import compute_metrics, evaluate_on_splits
from .validation import run_full_validation
from .visualizations import generate_all_visualizations
from .feature_importance import get_feature_importance_table
from .reporting import print_final_report


def main(
    data_path: str,
    metadata_path: str,
    output_dir: str,
    cv_folds: int,
):
    """Main training pipeline orchestrator."""
    start_time = time.time()

    os.makedirs(output_dir, exist_ok=True)
    vis_dir = os.path.join(output_dir, 'visualizations')

    # ── 1. Load data ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 1: DATA LOADING & PREPARATION")
    logger.info(f"{'#'*60}")

    metadata = load_metadata(metadata_path)
    df, y, features_config = load_and_prepare_data(data_path, metadata)

    # Get feature columns
    feature_cols = get_all_feature_columns(features_config)
    logger.info(f"Total features selected: {len(feature_cols)}")

    # Filter to available columns
    available_features = [c for c in feature_cols if c in df.columns]
    missing_features = [c for c in feature_cols if c not in df.columns]
    if missing_features:
        logger.warning(f"Missing features (will be skipped): {missing_features}")

    X = df[available_features].copy()

    # ── 2. Create composite stratifier ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 2: TRAIN/VAL/TEST SPLIT (60/20/20)")
    logger.info(f"{'#'*60}")

    stratify_col = create_composite_stratifier(df)
    X_train, X_val, X_test, y_train, y_val, y_test = stratified_train_val_test_split(
        X, y, stratify_col, random_state=RANDOM_STATE
    )

    # Reset indexes to avoid index mismatch with category_encoders TargetEncoder
    # (it validates that X and y have matching indexes)
    df_train = df.loc[X_train.index].reset_index(drop=True)
    df_val   = df.loc[X_val.index].reset_index(drop=True)
    df_test  = df.loc[X_test.index].reset_index(drop=True)

    # Reset indexes pour TargetEncoder
    X_train = X_train.reset_index(drop=True)
    X_val   = X_val.reset_index(drop=True)
    X_test  = X_test.reset_index(drop=True)
    y_train = y_train.reset_index(drop=True)
    y_val   = y_val.reset_index(drop=True)
    y_test  = y_test.reset_index(drop=True)

    # ── 3. Build preprocessing pipeline ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 3: BUILDING PREPROCESSING PIPELINE")
    logger.info(f"{'#'*60}")

    #  CORRECTION 2 : Supprimer X_sample=X qui causait le TypeError
    preprocessor = build_preprocessing_pipeline(features_config)
    transformer_names = [t[0] for t in preprocessor.transformers]
    logger.info(f"Preprocessor transformers: {transformer_names}")
     # Fit preprocessor on training data, transform all sets
    logger.info("Fitting preprocessor on training data...")
    X_train_processed = preprocessor.fit_transform(X_train, y_train)
    X_val_processed = preprocessor.transform(X_val)
    X_test_processed = preprocessor.transform(X_test)
    logger.info(f"Processed shapes: train={X_train_processed.shape}, val={X_val_processed.shape}, test={X_test_processed.shape}")

    # Get feature names after preprocessing
    try:
        feature_names = list(preprocessor.get_feature_names_out())
    except Exception:
        feature_names = [f'feature_{i}' for i in range(X_train_processed.shape[1])]
    logger.info(f"Feature count after preprocessing: {len(feature_names)}")

    # ── 4. Model selection & training ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 4: MODEL SELECTION & TRAINING")
    logger.info(f"{'#'*60}")

    models = get_models()
    logger.info(f"Candidate models: {list(models.keys())}")

    # ── 5. Phase 1: RandomizedSearchCV ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 5: PHASE 1 — RANDOMIZED SEARCH")
    logger.info(f"{'#'*60}")

    phase1_results = phase1_random_search(models, X_train_processed, y_train, cv_folds=cv_folds, n_iter=100)

    # ── 6. Phase 2: Focused GridSearchCV ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 6: PHASE 2 — FOCUSED GRID SEARCH")
    logger.info(f"{'#'*60}")

    phase2_results = phase2_grid_search(phase1_results, X_train_processed, y_train, cv_folds=cv_folds, top_n=3)

    # ── 7. Select best model ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 7: BEST MODEL SELECTION")
    logger.info(f"{'#'*60}")

    # Combine Phase 1 and Phase 2 results
    all_results = {}
    for name, result in phase1_results.items():
        if name in phase2_results:
            all_results[name] = phase2_results[name]
        else:
            all_results[name] = result

    # BUG FIX: le modèle gagnant doit être choisi sur le jeu de VALIDATION,
    # jamais sur le jeu de TEST — sinon le test set est utilisé pour une
    # décision de modélisation et cesse d'être une estimation non biaisée
    # de la performance finale (fuite de données / sélection optimiste).
    # On calcule quand même les métriques test ici, mais uniquement pour
    # le reporting comparatif — elles n'entrent pas dans le choix.
    best_name = None
    best_val_rmse = float('inf')

    for name, result in all_results.items():
        model = result['model']

        y_pred_val = model.predict(X_val_processed)
        val_metrics = compute_metrics(y_val.values, y_pred_val)
        result['val_metrics'] = val_metrics

        y_pred_test = model.predict(X_test_processed)
        test_metrics = compute_metrics(y_test.values, y_pred_test)
        result['test_metrics'] = test_metrics

        logger.info(
            f"  {name}: Val RMSE={val_metrics['RMSE']:,.0f}, "
            f"Test RMSE={test_metrics['RMSE']:,.0f}, Test R²={test_metrics['R2']:.4f}"
        )

        if val_metrics['RMSE'] < best_val_rmse:
            best_val_rmse = val_metrics['RMSE']
            best_name = name

    logger.info(f"\n  >>> Best model: {best_name} (Val RMSE: {best_val_rmse:,.0f} TND)")

    best_model = all_results[best_name]['model']
    best_params = all_results[best_name]['best_params']

    # ── 8. Final evaluation ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 8: FINAL EVALUATION")
    logger.info(f"{'#'*60}")

    eval_results = evaluate_on_splits(
        best_model, X_train_processed, y_train,
        X_val_processed, y_val, X_test_processed, y_test
    )

    for split in ['train', 'val', 'test']:
        m = eval_results[split]['metrics']
        logger.info(f"  {split:5s}: RMSE={m['RMSE']:>10,.0f}  MAE={m['MAE']:>10,.0f}  R²={m['R2']:.4f}  MAPE={m['MAPE']:.1f}%")

    # ── 9. Validation pipeline ──
    validation_results = run_full_validation(
        best_model,
        X_train_processed, y_train,
        X_val_processed, y_val,
        X_test_processed, y_test,
        df_test, df,
        eval_results,
    )

    # ── 10. Visualizations ──
    generate_all_visualizations(
        best_model, eval_results,
        X_train_processed, y_train,
        X_test_processed, y_test,
        df_test, df,
        phase1_results, validation_results,
        feature_names, cv_folds, vis_dir,
    )

    # ── 11. Feature importance ──
    feature_importance = get_feature_importance_table(best_model, feature_names)

    # ── 12. Save artifacts ──
    logger.info(f"\n{'#'*60}")
    logger.info("  STEP 12: SAVING ARTIFACTS")
    logger.info(f"{'#'*60}")

    model_path = os.path.join(output_dir, 'best_model.joblib')
    preprocessor_path = os.path.join(output_dir, 'preprocessor.joblib')
    results_path = os.path.join(output_dir, 'training_results.json')

    joblib.dump(best_model, model_path)
    logger.info(f"  Saved model: {model_path}")

    joblib.dump(preprocessor, preprocessor_path)
    logger.info(f"  Saved preprocessor: {preprocessor_path}")

    # Build results dict
    training_time = time.time() - start_time
    results_dict = {
        'best_model': best_name,
        'best_params': {k: str(v) for k, v in best_params.items()},
        'training_time_seconds': round(training_time, 2),
        'timestamp': datetime.now().isoformat(),
        'data_info': {
            'data_path': data_path,
            'n_samples': len(df),
            'n_features': len(available_features),
            'split_sizes': {
                'train': len(X_train),
                'val': len(X_val),
                'test': len(X_test),
            },
        },
        'evaluation': {
            split: eval_results[split]['metrics']
            for split in ['train', 'val', 'test']
        },
        'validation': validation_results,
        'feature_importance': feature_importance[:30],
        'all_models_test_metrics': {
            name: result.get('test_metrics', {}) for name, result in all_results.items()
        },
    }

    # Custom JSON serialization for numpy/pandas types.
    # NOTE: np.generic is the base class for ALL numpy scalars (np.bool_,
    # np.integer, np.floating, np.complexfloating...). Comparisons like
    # `value <= target` in the validation pipeline (e.g. within_tolerance,
    # passed) produce np.bool_, which is NOT a subclass of np.integer or
    # np.floating and was previously falling through to the default
    # encoder -> "Object of type bool is not JSON serializable" (NumPy 2.x
    # renamed np.bool_'s __name__ to "bool", which is why the error message
    # looked like it was about a native Python bool). Catching via
    # np.generic covers this case and any future numpy scalar type in one
    # place instead of enumerating subclasses one at a time.
    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.generic):
                return obj.item()
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            return super().default(obj)

    with open(results_path, 'w') as f:
        json.dump(results_dict, f, cls=NpEncoder, indent=2, ensure_ascii=False)
    logger.info(f"  Saved results: {results_path}")

    # ── 13. Print report ──
    print_final_report(best_name, best_params, eval_results, validation_results, feature_importance, training_time)

    return best_model, preprocessor, results_dict
