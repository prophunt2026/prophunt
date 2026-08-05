"""
ml_training — Tunisian Real Estate Price Prediction training package.
=======================================================================

Package layout:
    config.py              Constants, logging setup, external benchmark data
    optional_deps.py        Optional third-party import detection (xgboost, lightgbm, category_encoders)
    transformers.py          Custom sklearn transformers (PriceBinTransformer, LogTransformer, ...)
    data_reconstruction.py   One-hot -> categorical reconstruction helpers
    data_loading.py         CSV loading, feature-config resolution, stratified splitting
    preprocessing.py         ColumnTransformer pipeline assembly
    models.py                Candidate models + two-phase hyperparameter search
    evaluation.py             Metrics (RMSE, MAE, R2, MAPE, MedAE)
    validation.py             7-step validation pipeline (incl. external benchmarks)
    visualizations.py         13 diagnostic charts
    feature_importance.py     Feature importance table extraction
    reporting.py               Console summary report
    pipeline.py                 main() orchestrator tying everything together

Usage:
    from ml_training.pipeline import main
    main(data_path=..., metadata_path=..., output_dir=..., cv_folds=5)

Or simply run the top-level `train.py` CLI script.
"""

from .pipeline import main

__all__ = ["main"]
