#!/usr/bin/env python3
"""
ML Model Training Script — Tunisian Real Estate Price Prediction
===============================================================

Production-ready CLI entry point for training a real estate price
prediction model for the Tunisian market.

Unified Single-Model Architecture:
Trains a single model to predict log(price_per_m2) for both
VENTE and LOCATION listings, using an `is_vente` feature.

Usage:
    python train.py
    python train.py --data cleaned_unified.csv --metadata feature_metadata.json
"""

import argparse
import os
import sys

from ml_training.config import logger
from ml_training.pipeline import main


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train Unified Model for Real Estate Prediction')
    parser.add_argument('--data', type=str, default=None, help='Path to cleaned_unified.csv')
    parser.add_argument('--metadata', type=str, default=None, help='Path to feature_metadata.json')
    parser.add_argument('--output-dir', type=str, default=None, help='Output directory')
    parser.add_argument('--cv-folds', type=int, default=5, help='CV folds')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = args.data or os.path.join(script_dir, 'cleaned_unified.csv')
    metadata_path = args.metadata or os.path.join(script_dir, 'feature_metadata.json')
    output_dir = args.output_dir or os.path.join(script_dir, 'unified_model')

    if not os.path.exists(data_path):
        logger.error(f"Unified data not found: {data_path}")
        sys.exit(1)
        
    if not os.path.exists(metadata_path):
        logger.error(f"Metadata not found: {metadata_path}")
        sys.exit(1)

    logger.info("\n" + "="*70)
    logger.info("  --- Training Unified Model ---")
    logger.info("="*70)
    
    os.makedirs(output_dir, exist_ok=True)
    
    main(
        data_path=data_path,
        metadata_path=metadata_path,
        output_dir=output_dir,
        cv_folds=args.cv_folds,
    )