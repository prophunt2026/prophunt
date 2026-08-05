#!/usr/bin/env python3
"""
ML Model Training Script — Tunisian Real Estate Price Prediction
===============================================================

Production-ready CLI entry point for training a real estate price
prediction model for the Tunisian market. Uses log-transformed prices
as the target variable and follows a rigorous two-phase hyperparameter
tuning strategy.

This is a thin CLI wrapper: all the actual logic lives in the
`ml_training` package (see ml_training/__init__.py for the module map).

Usage:
    python train.py
    python train.py --data /path/to/cleaned_vente.csv --output-dir ./output
    python train.py --cv-folds 3

Output:
    best_model.joblib       — Trained model pipeline
    preprocessor.joblib     — Preprocessing pipeline (for inference)
    training_results.json   — Full training metrics and metadata
    visualizations/         — 13 diagnostic charts (PNG)

Author: ML Pipeline — Task 2-b
"""

import argparse
import os
import sys

from ml_training.config import logger
from ml_training.pipeline import main


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Train ML model for Tunisian real estate price prediction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--data', type=str, default=None,
        help='Path to cleaned_vente.csv (default: same directory as script)',
    )
    parser.add_argument(
        '--metadata', type=str, default=None,
        help='Path to feature_metadata.json (default: same directory as data)',
    )
    parser.add_argument(
        '--output-dir', type=str, default=None,
        help='Output directory for model artifacts (default: same directory as data)',
    )
    parser.add_argument(
        '--cv-folds', type=int, default=5,
        help='Number of cross-validation folds (default: 5)',
    )

    args = parser.parse_args()

    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = args.data or os.path.join(script_dir, 'cleaned_vente.csv')
    metadata_path = args.metadata or os.path.join(script_dir, 'feature_metadata.json')
    output_dir = args.output_dir or script_dir

    logger.info(f"Data path: {data_path}")
    logger.info(f"Metadata path: {metadata_path}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"CV folds: {args.cv_folds}")

    if not os.path.exists(data_path):
        logger.error(f"Data file not found: {data_path}")
        sys.exit(1)

    main(
        data_path=data_path,
        metadata_path=metadata_path,
        output_dir=output_dir,
        cv_folds=args.cv_folds,
    )