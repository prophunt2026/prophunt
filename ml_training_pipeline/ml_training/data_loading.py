"""
Data loading, feature-config resolution, and train/val/test splitting.
=============================================================
Handles reading the cleaned CSV, reconstructing categorical columns,
resolving which columns to use as features (metadata-driven with
sensible defaults), building the composite stratification key, and
performing the 60/20/20 stratified split.
"""

import json
import os
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from .config import logger, RANDOM_STATE, TARGET_COL, PRICE_COL, DEFAULT_FEATURES
from .data_reconstruction import reconstruct_data


def load_metadata(metadata_path: str) -> Dict[str, Any]:
    """Load feature metadata JSON, with fallback to defaults."""
    if os.path.exists(metadata_path):
        logger.info(f"Loading metadata from {metadata_path}")
        with open(metadata_path, 'r') as f:
            return json.load(f)
    else:
        logger.warning(f"Metadata file not found at {metadata_path}. Using defaults.")
        return {}


def load_and_prepare_data(data_path: str, metadata: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.Series, Dict[str, List[str]]]:
    """Load cleaned CSV, reconstruct categoricals, and prepare X/y.

    Returns:
        Tuple of (full_df, y_series, features_config) where features_config
        contains the column lists for each feature type.
    """
    logger.info(f"Loading data from {data_path}")
    df = pd.read_csv(data_path, low_memory=False)
    logger.info(f"Raw data shape: {df.shape}")

    # Reconstruct categorical columns from one-hot encoding
    df = reconstruct_data(df)
    logger.info(f"After reconstruction: {df.shape}")

    # Drop rows where target is NaN
    target_col = metadata.get('target', TARGET_COL)
    if target_col not in df.columns:
        # Fallback: compute prix_log from transaction.prix
        if PRICE_COL in df.columns:
            logger.info(f"'{target_col}' not found. Computing from '{PRICE_COL}'")
            df['prix_log'] = np.log1p(df[PRICE_COL])
            target_col = 'prix_log'
        else:
            raise ValueError(f"Neither '{TARGET_COL}' nor '{PRICE_COL}' found in data.")

    n_before = len(df)
    df = df.dropna(subset=[target_col]).reset_index(drop=True)
    n_after = len(df)
    logger.info(f"Dropped {n_before - n_after} rows with missing target. Remaining: {n_after}")

    y = df[target_col].copy()

    # Build features config from metadata or defaults
    features_config = build_features_config(df, metadata)

    return df, y, features_config


def build_features_config(df: pd.DataFrame, metadata: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build column lists for each feature type.

    Uses metadata when available, falls back to DEFAULT_FEATURES,
    and further filters to only include columns present in the DataFrame.
    """
    config = {
        'numeric': DEFAULT_FEATURES['numeric'][:],
        'categorical_high_card': DEFAULT_FEATURES['categorical_high_card'][:],
        'categorical_low_card': DEFAULT_FEATURES['categorical_low_card'][:],
        'binary': DEFAULT_FEATURES['binary'][:],
        'outlier_clip': DEFAULT_FEATURES['outlier_clip'][:],
        'log_transform': DEFAULT_FEATURES['log_transform'][:],
        'rare_category_merge': DEFAULT_FEATURES['rare_category_merge'][:],
    }

    # Pre-compute existing columns for membership checks below
    existing_cols = set(df.columns)

    # Override with metadata if available
    if metadata.get('numeric_features'):
        config['numeric'] = metadata['numeric_features']
    if metadata.get('categorical_features'):
        all_cat = metadata['categorical_features']
        if metadata.get('categorical_cardinality'):
            card = metadata['categorical_cardinality']
            high = [c for c in all_cat if card.get(c, 0) > 15]
            low = [c for c in all_cat if card.get(c, 0) <= 15]
            config['categorical_high_card'] = high
            config['categorical_low_card'] = low
    if metadata.get('binary_features'):
        config['binary'] = metadata['binary_features']

    # --- Override outlier_clip from metadata ---
    # Extend defaults with derived log/skewed features that exist in data
    extra_outlier_candidates = ['log_superficie', 'log_nombre_pieces', 'prix_m2_cleaned', 'prix_m2_log']
    for col in extra_outlier_candidates:
        if col in existing_cols and col not in config['outlier_clip']:
            config['outlier_clip'].append(col)

    # --- Override log_transform from metadata ---
    # Extend defaults with log-derived features that exist in data
    extra_log_candidates = ['log_nombre_pieces', 'prix_m2_log']
    derived_in_metadata = set(metadata.get('derived_features', []))
    for col in extra_log_candidates:
        if col in existing_cols and col not in config['log_transform']:
            # Accept if it's a known derived feature OR simply present in the dataframe
            config['log_transform'].append(col)

    # --- Override rare_category_merge from metadata ---
    # Extend defaults with any categorical feature whose cardinality > 10
    if metadata.get('categorical_features') and metadata.get('categorical_cardinality'):
        card = metadata['categorical_cardinality']
        for col in metadata['categorical_features']:
            if card.get(col, 0) > 10 and col not in config['rare_category_merge'] and col in existing_cols:
                config['rare_category_merge'].append(col)

    # Filter to only columns that exist in the DataFrame
    for key in config:
        config[key] = [c for c in config[key] if c in existing_cols]

    # Ensure no overlap between binary and numeric
    config['numeric'] = [c for c in config['numeric'] if c not in config['binary']]

    logger.info("Feature configuration:")
    for key, cols in config.items():
        logger.info(f"  {key}: {len(cols)} features — {cols[:5]}{'...' if len(cols) > 5 else ''}")

    return config


def create_composite_stratifier(df: pd.DataFrame) -> pd.Series:
    """Create a composite stratification key from gouvernorat × type × price_bin.

    Falls back to price_bin alone if gouvernorat or bien.type are unavailable.
    """
    # Create price_bin if not present
    if 'price_bin' not in df.columns:
        if 'prix_log' in df.columns:
            df = df.copy()
            df['price_bin'] = pd.qcut(df['prix_log'], q=4, labels=False, duplicates='drop').fillna(0).astype(int)
        else:
            df = df.copy()
            df['price_bin'] = 0

    gouv = df['localisation.gouvernorat'].fillna('unknown').astype(str) if 'localisation.gouvernorat' in df.columns else pd.Series('unknown', index=df.index)
    btype = df['bien.type'].fillna('unknown').astype(str) if 'bien.type' in df.columns else pd.Series('unknown', index=df.index)
    pbin = df['price_bin'].astype(str)

    return (gouv + '_' + btype + '_' + pbin).astype('category')


def stratified_train_val_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    stratify_col: pd.Series,
    test_size: float = 0.2,
    val_size: float = 0.2,
    random_state: int = RANDOM_STATE
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Perform 60/20/20 stratified train/val/test split.

    Uses StratifiedKFold on composite stratification key.
    Falls back to random split if stratification produces too-small groups.
    """
    n = len(X)
    # Compute n_splits from test_size and val_size
    # First split: (1 - test_size) / test_size → n_splits
    n_splits_1 = max(2, round(1.0 / test_size))
    # Second split: (1 - test_size - val_size) / val_size of remaining → n_splits
    val_ratio_of_remaining = val_size / (1.0 - test_size)
    n_splits_2 = max(2, round(1.0 / val_ratio_of_remaining))

    try:
        skf1 = StratifiedKFold(n_splits=n_splits_1, shuffle=True, random_state=random_state)
        # Get the first fold: (1 - test_size) train+val, test_size test
        train_val_idx, test_idx = list(skf1.split(X, stratify_col))[0]

        X_train_val, X_test = X.iloc[train_val_idx], X.iloc[test_idx]
        y_train_val, y_test = y.iloc[train_val_idx], y.iloc[test_idx]
        stratify_train_val = stratify_col.iloc[train_val_idx]

        # Second split: train vs val from train_val
        skf2 = StratifiedKFold(n_splits=n_splits_2, shuffle=True, random_state=random_state)
        train_idx, val_idx = list(skf2.split(X_train_val, stratify_train_val))[0]

        X_train, X_val = X_train_val.iloc[train_idx], X_train_val.iloc[val_idx]
        y_train, y_val = y_train_val.iloc[train_idx], y_train_val.iloc[val_idx]

    except ValueError as e:
        logger.warning(f"Stratified split failed ({e}). Falling back to random split.")
        np.random.seed(random_state)
        indices = np.random.permutation(n)
        test_end = int(n * test_size)
        val_end = int(n * (test_size + val_size))
        test_idx = indices[:test_end]
        val_idx = indices[test_end:val_end]
        train_idx = indices[val_end:]

        X_train, X_val, X_test = X.iloc[train_idx], X.iloc[val_idx], X.iloc[test_idx]
        y_train, y_val, y_test = y.iloc[train_idx], y.iloc[val_idx], y.iloc[test_idx]

    logger.info(f"Split sizes: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")
    return X_train, X_val, X_test, y_train, y_val, y_test
