#!/usr/bin/env python3
"""
ML Model Training Script — Tunisian Real Estate Price Prediction
===============================================================

Production-ready script for training a real estate price prediction model
for the Tunisian market. Uses log-transformed prices as the target variable
and follows a rigorous two-phase hyperparameter tuning strategy.

Usage:
    python ml_model_training.py
    python ml_model_training.py --data /path/to/cleaned_vente.csv --output-dir ./output
    python ml_model_training.py --cv-folds 3

Output:
    best_model.joblib       — Trained model pipeline
    preprocessor.joblib     — Preprocessing pipeline (for inference)
    training_results.json   — Full training metrics and metadata
    visualizations/         — 13 diagnostic charts (PNG)

Author: ML Pipeline — Task 2-b
"""

import argparse
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

warnings.filterwarnings('ignore')

# ─── Imports ────────────────────────────────────────────────────────────────

import joblib
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless environments
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer, KNNImputer, SimpleImputer
from sklearn.linear_model import Lasso, LinearRegression, Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    RandomizedSearchCV,
    StratifiedKFold,
    cross_val_score,
    learning_curve,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler

try:
    from category_encoders import TargetEncoder
    HAS_CATEGORY_ENCODERS = True
except ImportError:
    HAS_CATEGORY_ENCODERS = False
    print("WARNING: category_encoders not installed. TargetEncoder will be skipped.")

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("WARNING: xgboost not installed. XGBoost model will be skipped.")

try:
    from lightgbm import LGBMRegressor
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False
    print("WARNING: lightgbm not installed. LightGBM model will be skipped.")

# ─── Logging Configuration ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────

RANDOM_STATE = 42
TARGET_COL = 'prix_log'
PRICE_COL = 'transaction.prix'

DEFAULT_FEATURES = {
    'numeric': [
        'bien.superficie_totale',
        'bien.nombre_pieces',
        'bien.nombre_chambres',
        'bien.nombre_salles_bain',
        'localisation.coordonnees.latitude',
        'localisation.coordonnees.longitude',
        'prix_m2_cleaned',
        'log_superficie',
        'nb_equipements',
        'medias.nombre_photos',
    ],
    'categorical_high_card': [
        'localisation.gouvernorat',
        'localisation.ville',
    ],
    'categorical_low_card': [
        'bien.type',
        'bien.etat_general',
        'contact.type_vendeur',
    ],
    'binary': [
        'equipements.climatisation',
        'equipements.cuisine_equipee',
        'equipements.terrasse',
        'equipements.garage',
        'equipements.ascenseur',
    ],
    'outlier_clip': [
        'bien.superficie_totale',
        'bien.nombre_pieces',
        'bien.nombre_chambres',
        'bien.nombre_salles_bain',
    ],
    'log_transform': [
        'bien.superficie_totale',
        'prix_m2_cleaned',
    ],
    'rare_category_merge': [
        'localisation.gouvernorat',
        'localisation.ville',
        'localisation.delegation',
        'bien.etat_general',
        'contact.type_vendeur',
    ],
}

MUBAWAB_SALES_BENCHMARK: Dict[str, Dict[str, Optional[float]]] = {
    'Jardins de Carthage': {'ancien': 4540, 'neuf': 5460},
    'Berges du Lac 2': {'ancien': 4980, 'neuf': None},
    'Ain Zaghouan Nord': {'ancien': 2990, 'neuf': 3690},
    'Cité Ennasr 2': {'ancien': 3850, 'neuf': 4410},
    'El Aouina': {'ancien': 2780, 'neuf': 3400},
    'La Soukra': {'ancien': 3350, 'neuf': 3690},
    'El Menzah 9C': {'ancien': 3190, 'neuf': 3700},
    "Jardins d'El Menzah 2": {'ancien': 4150, 'neuf': 4740},
    'La Marsa': {'ancien': 2990, 'neuf': 3660},
    'Riadh El Andalous': {'ancien': 3140, 'neuf': None},
    'La Manouba': {'ancien': 2860, 'neuf': 3530},
    'Ezzahra': {'ancien': 2480, 'neuf': 3030},
    'Boumhel': {'ancien': 2600, 'neuf': 3250},
    'Nouvelle Médina': {'ancien': 1930, 'neuf': 2210},
    'Mourouj 6': {'ancien': 2300, 'neuf': 2520},
    'Nabeul Centre': {'ancien': 3140, 'neuf': 3620},
    'Hammamet Sud': {'ancien': 2980, 'neuf': 3490},
    'Hammamet Nord': {'ancien': 2960, 'neuf': 3300},
    'El Kantaoui': {'ancien': 2600, 'neuf': 3560},
    'Sahloul 4': {'ancien': 4210, 'neuf': 4630},
    'Hammam Sousse': {'ancien': 2630, 'neuf': 3130},
    'Chott Meriem': {'ancien': 3330, 'neuf': 3610},
    'Hergla': {'ancien': 2580, 'neuf': 3170},
}

IPIM_REFERENCE = {
    'Q1_2024': 118.5,
    'Q4_2024': 121,
    'Q1_2025': 123,
    'Q2_2025': 120,
    'base_2015': 100,
    'annual_change_pct': 3.9,
}


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOM TRANSFORMERS
# ═══════════════════════════════════════════════════════════════════════════

class PriceBinTransformer(BaseEstimator, TransformerMixin):
    """Creates price quartile bins for stratified splitting.

    Fits on log-price to create quartile boundaries, then assigns
    each sample to a bin. Designed for use before train/test splitting.

    Attributes:
        quartile_boundaries_: Array of 3 cut points (Q1, Q2, Q3).
    """

    def __init__(self, price_col: str = 'prix_log', n_bins: int = 4):
        self.price_col = price_col
        self.n_bins = n_bins
        # BUG FIX: don't pre-declare 'quartile_boundaries_' (even as None) in
        # __init__ — check_is_fitted() only checks attribute presence, so a
        # None placeholder here would make an unfitted instance look fitted,
        # and would later fail with a confusing "NoneType is not iterable"
        # in transform() instead of a clear NotFittedError.

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None) -> 'PriceBinTransformer':
        """Compute quartile boundaries from the price column."""
        prices = X[self.price_col].dropna()
        self.quartile_boundaries_ = np.percentile(
            prices, [100 / self.n_bins * (i + 1) for i in range(self.n_bins - 1)]
        )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Assign each row to a price bin."""
        X = X.copy()
        bins = [-np.inf] + list(self.quartile_boundaries_) + [np.inf]
        X['price_bin'] = pd.cut(
            X[self.price_col], bins=bins, labels=False, include_lowest=True
        ).fillna(0).astype(int)
        return X


class LogTransformer(BaseEstimator, TransformerMixin):
    """Applies log1p transform to specified numeric columns.

    Useful for right-skewed features like area and price per m².
    """

    def __init__(self, columns: Optional[List[str]] = None):
        self.columns = columns

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None) -> 'LogTransformer':
        # BUG FIX (defensive): same class of bug as BinaryImputer — record an
        # explicit fitted marker so check_is_fitted() works correctly if this
        # transformer is ever placed as the last step of a pipeline.
        self.fitted_ = True
        # BUG FIX: record input column names so get_feature_names_out() can
        # report them. Without this, sklearn Pipeline.get_feature_names_out()
        # raises AttributeError as soon as it reaches this step (it calls
        # get_feature_names_out() on EVERY step, not just the last one),
        # which was silently caught upstream in main() and made the whole
        # pipeline fall back to generic 'feature_0', 'feature_1', ... names.
        self.feature_names_in_ = np.asarray(
            X.columns if hasattr(X, 'columns') else [f'x{i}' for i in range(np.asarray(X).shape[1])],
            dtype=object,
        )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Apply log1p to specified columns."""
        X = X.copy()
        if isinstance(X, np.ndarray):
            X = pd.DataFrame(X)
        if self.columns:
            for col in self.columns:
                if col in X.columns:
                    X[col] = np.log1p(X[col].clip(lower=0))
        return X

    def get_feature_names_out(self, input_features=None):
        # Pass-through: this transformer only rescales values in place, it
        # never adds, drops, or renames columns.
        if input_features is not None:
            return np.asarray(input_features, dtype=object)
        return self.feature_names_in_


class OutlierClipper(BaseEstimator, TransformerMixin):
    """Clips values at Q3 + k*IQR (fit on train only, transform on all).

    Prevents extreme outliers from distorting model training while
    avoiding information leakage by fitting bounds only on training data.
    """

    def __init__(self, columns: Optional[List[str]] = None, k: float = 3.0):
        self.columns = columns
        self.k = k
        # BUG FIX: do NOT pre-declare 'bounds_' here. Any attribute ending in
        # '_' that already exists on __init__ makes sklearn's check_is_fitted()
        # believe the transformer is fitted even before .fit() is ever called
        # (it only checks attribute *presence*, not whether fit() ran). The
        # attribute is now created exclusively inside fit(), below.

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None) -> 'OutlierClipper':
        """Compute IQR-based clipping bounds for each column."""
        self.bounds_: Dict[str, Tuple[float, float]] = {}
        X_df = pd.DataFrame(X) if not isinstance(X, pd.DataFrame) else X
        for col in (self.columns or []):
            if col in X_df.columns:
                q1 = X_df[col].quantile(0.25)
                q3 = X_df[col].quantile(0.75)
                iqr = q3 - q1
                upper = q3 + self.k * iqr
                lower = q1 - self.k * iqr
                self.bounds_[col] = (max(lower, 0), upper)  # Don't clip below 0
        # BUG FIX: same reasoning as LogTransformer — record input column
        # names so get_feature_names_out() works. This transformer is used
        # as the FIRST step of the numeric sub-pipeline, so without this fix
        # the whole pipeline's get_feature_names_out() failed immediately.
        self.feature_names_in_ = np.asarray(
            X_df.columns if hasattr(X_df, 'columns') else [f'x{i}' for i in range(np.asarray(X_df).shape[1])],
            dtype=object,
        )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Clip values to the precomputed bounds."""
        X = X.copy()
        if not isinstance(X, pd.DataFrame):
            X = pd.DataFrame(X)
        for col, (lower, upper) in self.bounds_.items():
            if col in X.columns:
                X[col] = X[col].clip(lower, upper)
        return X

    def get_feature_names_out(self, input_features=None):
        # Pass-through: clipping never adds, drops, or renames columns.
        if input_features is not None:
            return np.asarray(input_features, dtype=object)
        return self.feature_names_in_


class RareCategoryMerger(BaseEstimator, TransformerMixin):
    """Merges categories with < threshold samples into 'Autre'.

    Category frequencies are computed on training data only to prevent
    data leakage. Rare categories in transform are mapped to 'Autre'.
    """

    def __init__(self, columns: Optional[List[str]] = None, threshold: int = 30):
        self.columns = columns
        self.threshold = threshold
        # BUG FIX: same reason as OutlierClipper — don't pre-declare
        # 'frequent_categories_' in __init__, or check_is_fitted() will
        # report this transformer as fitted before .fit() ever runs.

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None) -> 'RareCategoryMerger':
        """Identify frequent categories for each column."""
        self.frequent_categories_: Dict[str, set] = {}
        X_df = pd.DataFrame(X) if not isinstance(X, pd.DataFrame) else X
        for col in (self.columns or []):
            if col in X_df.columns:
                counts = X_df[col].value_counts(dropna=False)
                self.frequent_categories_[col] = set(counts[counts >= self.threshold].index)
        # BUG FIX: same reasoning as LogTransformer/OutlierClipper — record
        # input column names for get_feature_names_out(). This transformer
        # sits mid-pipeline in the 'cat_high_card' and 'cat_low_card'
        # branches (before the encoder), so without this fix
        # Pipeline.get_feature_names_out() broke there too.
        self.feature_names_in_ = np.asarray(
            X_df.columns if hasattr(X_df, 'columns') else [f'x{i}' for i in range(np.asarray(X_df).shape[1])],
            dtype=object,
        )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Replace rare categories with 'Autre'."""
        X = X.copy()
        if not isinstance(X, pd.DataFrame):
            X = pd.DataFrame(X)
        for col, frequent in self.frequent_categories_.items():
            if col in X.columns:
                X[col] = X[col].apply(
                    lambda x: x if x in frequent else 'Autre'
                )
        return X

    def get_feature_names_out(self, input_features=None):
        # Pass-through: merging rare categories never adds, drops, or
        # renames columns — only category values change.
        if input_features is not None:
            return np.asarray(input_features, dtype=object)
        return self.feature_names_in_


class ColumnSelector(BaseEstimator, TransformerMixin):
    """Selects a subset of columns from a DataFrame."""

    def __init__(self, columns: List[str]):
        self.columns = columns

    def fit(self, X, y=None):
        # BUG FIX: same class of bug as BinaryImputer (see below).
        self.fitted_ = True
        return self

    def transform(self, X):
        X_df = pd.DataFrame(X) if not isinstance(X, pd.DataFrame) else X
        available = [c for c in self.columns if c in X_df.columns]
        return X_df[available]


def _coerce_to_binary_numeric(series: pd.Series) -> pd.Series:
    """Convert mixed boolean-like values to 0/1 integers.

    Some cleaned CSV columns store booleans as strings ('True'/'False') or
    as free-text equipment labels (e.g. 'Central'). sklearn regressors need
    a purely numeric matrix, so every value is mapped to 0 or 1.
    """
    false_values = {'false', '0', 'no', 'n', 'non', 'sans chauffage'}
    true_values = {'true', '1', 'yes', 'y', 'oui'}

    def to_binary(value):
        if pd.isna(value):
            return 0
        if isinstance(value, (bool, np.bool_)):
            return int(value)
        if isinstance(value, (int, np.integer)):
            return 0 if value == 0 else 1
        if isinstance(value, (float, np.floating)):
            return 0 if value == 0 or np.isnan(value) else 1

        normalized = str(value).strip().lower()
        if normalized in false_values:
            return 0
        if normalized in true_values:
            return 1
        # Any other non-empty label means the equipment is present.
        return 1

    return series.map(to_binary).astype(int)


class BinaryImputer(BaseEstimator, TransformerMixin):
    """Coerce binary/equipment columns to 0/1 and fill NaN with 0."""

    def fit(self, X, y=None):
        # BUG FIX: fit() must record a fitted-state attribute (name ending
        # in '_'), otherwise sklearn's check_is_fitted() can't tell this
        # transformer apart from an unfitted one. Since BinaryImputer is the
        # *only* (and therefore last) step of the 'binary' sub-pipeline,
        # ColumnTransformer.transform() calls check_is_fitted() on it directly
        # before delegating — without this attribute it always raises
        # NotFittedError, even right after a successful fit_transform().
        self.fitted_ = True
        # BUG FIX: record input column names for get_feature_names_out().
        # BinaryImputer is the ONLY step of the 'binary' sub-pipeline, so
        # Pipeline.get_feature_names_out() failed on it immediately —
        # this was the most direct cause of the AttributeError bubbling up
        # to preprocessor.get_feature_names_out() and triggering the
        # 'feature_0', 'feature_1', ... fallback for the ENTIRE feature set.
        X_df = pd.DataFrame(X) if not isinstance(X, pd.DataFrame) else X
        self.feature_names_in_ = np.asarray(X_df.columns, dtype=object)
        return self

    def transform(self, X):
        X_df = pd.DataFrame(X) if not isinstance(X, pd.DataFrame) else X
        return X_df.apply(_coerce_to_binary_numeric)

    def get_feature_names_out(self, input_features=None):
        # Pass-through: this transformer only coerces values to 0/1, it
        # never adds, drops, or renames columns.
        if input_features is not None:
            return np.asarray(input_features, dtype=object)
        return self.feature_names_in_


class FeatureNameExtractor(BaseEstimator, TransformerMixin):
    """Extracts feature names from a column transformer's output.

    Wraps a ColumnTransformer and provides get_feature_names_out().
    """

    def __init__(self, preprocessor):
        self.preprocessor = preprocessor

    def fit(self, X, y=None):
        self.preprocessor.fit(X, y)
        # BUG FIX: fitting the wrapped preprocessor doesn't set a fitted
        # attribute on THIS wrapper itself, so check_is_fitted(self) would
        # still fail if this wrapper were ever used as a pipeline step.
        self.fitted_ = True
        return self

    def transform(self, X):
        return self.preprocessor.transform(X)

    def get_feature_names_out(self, input_features=None):
        try:
            return self.preprocessor.get_feature_names_out(input_features)
        except AttributeError:
            # Fallback for older sklearn
            names = []
            for name, trans, cols in self.preprocessor.transformers_:
                if trans == 'drop' or trans is None:
                    continue
                if hasattr(trans, 'get_feature_names_out'):
                    try:
                        names.extend(trans.get_feature_names_out(cols))
                    except Exception:
                        names.extend(cols)
                else:
                    names.extend(cols)
            return np.array(names)


# ═══════════════════════════════════════════════════════════════════════════
# DATA RECONSTRUCTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def reconstruct_categorical_from_onehot(
    df: pd.DataFrame,
    prefix: str,
    target_col: str
) -> pd.DataFrame:
    """Reconstruct a categorical column from one-hot encoded columns.

    Args:
        df: DataFrame containing one-hot columns.
        prefix: Column name prefix (e.g., 'bien_type_' or 'localisation_gouvernorat_').
        target_col: Name of the reconstructed column.

    Returns:
        DataFrame with the reconstructed column added.
    """
    oh_cols = [c for c in df.columns if c.startswith(prefix)]
    if not oh_cols:
        logger.warning(f"No one-hot columns found with prefix '{prefix}'")
        df[target_col] = np.nan
        return df

    # Extract category labels from column names
    labels = [c[len(prefix):] for c in oh_cols]

    # Replace NaN with 0 so argmax returns the correct one-hot column
    oh_data = np.nan_to_num(df[oh_cols].values.astype(float), nan=0.0)
    max_indices = np.argmax(oh_data, axis=1)

    # If all zeros or NaN (no category), assign NaN
    row_sums = np.nansum(oh_data, axis=1)
    labels_arr = list(labels)
    result = np.array([labels_arr[i] if row_sums[i] > 0 and i < len(labels_arr) else np.nan for i in max_indices], dtype=object)
    df[target_col] = result
    return df


def reconstruct_data(df: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct original categorical columns from one-hot encoded versions.

    The v1 cleaning script one-hot encoded several categorical columns.
    This function reverses that encoding so the ML pipeline can apply
    its own encoding strategy (TargetEncoder, OneHotEncoder) inside
    a proper sklearn pipeline to avoid data leakage.
    """
    df = df.copy()

    # Reconstruct bien.type from bien_type_* columns
    if 'bien.type' not in df.columns:
        oh_type_cols = [c for c in df.columns if c.startswith('bien_type_')]
        if oh_type_cols:
            df = reconstruct_categorical_from_onehot(df, 'bien_type_', 'bien.type')
            # Drop one-hot columns
            df.drop(columns=oh_type_cols, inplace=True, errors='ignore')
            logger.info(f"Reconstructed 'bien.type' from {len(oh_type_cols)} one-hot columns")

    # Reconstruct bien.etat_general from bien_etat_general_* columns
    if 'bien.etat_general' not in df.columns:
        oh_etat_cols = [c for c in df.columns if c.startswith('bien_etat_general_')]
        if oh_etat_cols:
            df = reconstruct_categorical_from_onehot(df, 'bien_etat_general_', 'bien.etat_general')
            df.drop(columns=oh_etat_cols, inplace=True, errors='ignore')
            logger.info(f"Reconstructed 'bien.etat_general' from {len(oh_etat_cols)} one-hot columns")

    # Reconstruct localisation.gouvernorat from localisation_gouvernorat_* columns
    if 'localisation.gouvernorat' not in df.columns:
        oh_gouv_cols = [c for c in df.columns if c.startswith('localisation_gouvernorat_')]
        if oh_gouv_cols:
            df = reconstruct_categorical_from_onehot(df, 'localisation_gouvernorat_', 'localisation.gouvernorat')
            df.drop(columns=oh_gouv_cols, inplace=True, errors='ignore')
            logger.info(f"Reconstructed 'localisation.gouvernorat' from {len(oh_gouv_cols)} one-hot columns")

    # Reconstruct bien.usage from bien_usage_* columns
    if 'bien.usage' not in df.columns:
        oh_usage_cols = [c for c in df.columns if c.startswith('bien_usage_')]
        if oh_usage_cols:
            df = reconstruct_categorical_from_onehot(df, 'bien_usage_', 'bien.usage')
            df.drop(columns=oh_usage_cols, inplace=True, errors='ignore')
            logger.info(f"Reconstructed 'bien.usage' from {len(oh_usage_cols)} one-hot columns")

    # BUG FIX: 'localisation.ville' n'était jamais reconstruite, contrairement
    # aux 4 autres catégorielles ci-dessus. Elle disparaissait donc silencieusement
    # des features (categorical_high_card / rare_category_merge) ET l'étape 5 de
    # validation (benchmark Mubawab, qui groupe par ville) tombait systématiquement
    # dans le cas "colonne indisponible".
    if 'localisation.ville' not in df.columns:
        oh_ville_cols = [c for c in df.columns if c.startswith('localisation_ville_')]
        if oh_ville_cols:
            df = reconstruct_categorical_from_onehot(df, 'localisation_ville_', 'localisation.ville')
            df.drop(columns=oh_ville_cols, inplace=True, errors='ignore')
            logger.info(f"Reconstructed 'localisation.ville' from {len(oh_ville_cols)} one-hot columns")

    # BUG FIX: même oubli pour 'localisation.delegation' (utilisée dans
    # rare_category_merge).
    if 'localisation.delegation' not in df.columns:
        oh_deleg_cols = [c for c in df.columns if c.startswith('localisation_delegation_')]
        if oh_deleg_cols:
            df = reconstruct_categorical_from_onehot(df, 'localisation_delegation_', 'localisation.delegation')
            df.drop(columns=oh_deleg_cols, inplace=True, errors='ignore')
            logger.info(f"Reconstructed 'localisation.delegation' from {len(oh_deleg_cols)} one-hot columns")

    # Drop other unnecessary columns
    cols_to_drop = [
        'localisation.ville_target_enc',  # Pre-computed target encoding (leakage)
        'transaction_type_vente',          # Constant (all are sales)
        'transaction_devise_EUR',          # Redundant currency flag
        'transaction_devise_TND',          # Redundant currency flag
        'listing.date_scraping',
        'listing.date_publication',
        'listing.date_maj',
        'listing.statut',
        'listing.langue',
        'localisation.pays',
        'localisation.pays_code',
        'localisation.proximites',
        'localisation.adresse',
        'localisation.localite',
        'description.titre',
        'description.texte',
        'medias.photos',
        'contact.nom_vendeur',
        'contact.nom_agence',
        'contact.telephone',
        'contact.email',
        'metadonnees_scraping.source',
        'metadonnees_scraping.methode',
        'metadonnees_scraping.statut_scraping',
        'transaction.prix_m2',  # Use prix_m2_cleaned instead
    ]
    existing_drop = [c for c in cols_to_drop if c in df.columns]
    if existing_drop:
        df.drop(columns=existing_drop, inplace=True)
        logger.info(f"Dropped {len(existing_drop)} non-feature columns")

    return df


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING & SPLITTING
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# PREPROCESSING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def build_preprocessing_pipeline(features_config: Dict[str, List[str]]) -> ColumnTransformer:
    """Build the sklearn ColumnTransformer preprocessing pipeline.

    Creates three sub-pipelines:
    1. Numeric: imputation → RobustScaler (with optional log transform)
    2. Categorical: imputation → rare category merge → encoding
    3. Binary: fill NaN → 0
    """
    numeric_cols = features_config['numeric']
    high_card_cols = features_config['categorical_high_card']
    low_card_cols = features_config['categorical_low_card']
    binary_cols = features_config['binary']
    outlier_clip_cols = features_config['outlier_clip']
    log_cols = features_config['log_transform']
    rare_merge_cols = features_config['rare_category_merge']

    transformers = []

    # ── Numeric pipeline ──
    if numeric_cols:
        numeric_steps = []
        # Step 1: Clip outliers (fit on train only to prevent leakage)
        numeric_clip_cols = [c for c in outlier_clip_cols if c in numeric_cols]
        if numeric_clip_cols:
            numeric_steps.append(('clipper', OutlierClipper(columns=numeric_clip_cols, k=3.0)))
        # Step 2: Log-transform skewed features
        numeric_log_cols = [c for c in log_cols if c in numeric_cols]
        if numeric_log_cols:
            numeric_steps.append(('log_transform', LogTransformer(columns=numeric_log_cols)))
        # Step 3: Imputation and scaling
        numeric_steps.append(('imputer', SimpleImputer(strategy='median')))
        numeric_steps.append(('scaler', RobustScaler()))
        numeric_pipeline = Pipeline(numeric_steps)
        transformers.append(('numeric', numeric_pipeline, numeric_cols))

    # ── High-cardinality categorical pipeline (Target Encoding) ──
    if high_card_cols and HAS_CATEGORY_ENCODERS:
        # Find which high-card cols need rare category merging
        high_card_rare = [c for c in high_card_cols if c in rare_merge_cols]
        high_card_no_rare = [c for c in high_card_cols if c not in rare_merge_cols]

        # BUG FIX: SimpleImputer renvoie un ndarray par défaut, ce qui fait
        # perdre les noms de colonnes. L'étape suivante (RareCategoryMerger
        # et/ou TargetEncoder(cols=...)) a besoin de retrouver les noms
        # originaux ('bien.type', 'localisation.gouvernorat', ...) pour
        # savoir sur quelles colonnes travailler. Sans ça, RareCategoryMerger
        # ne fait plus rien silencieusement (aucune colonne ne matche des
        # noms entiers 0,1,2...) et TargetEncoder plante avec
        # "ValueError: X does not contain the columns listed in cols".
        # .set_output(transform='pandas') force l'imputer à conserver un
        # DataFrame avec les vrais noms de colonnes en sortie.
        if high_card_rare:
            high_card_pipeline = Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent').set_output(transform='pandas')),
                ('rare_merger', RareCategoryMerger(columns=high_card_rare, threshold=30)),
                ('encoder', TargetEncoder(cols=high_card_rare, smoothing=1.0)),
            ])
            transformers.append(('cat_high_card', high_card_pipeline, high_card_rare))

        if high_card_no_rare:
            high_card_pipeline2 = Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent').set_output(transform='pandas')),
                ('encoder', TargetEncoder(cols=high_card_no_rare, smoothing=1.0)),
            ])
            transformers.append(('cat_high_card_other', high_card_pipeline2, high_card_no_rare))
    elif high_card_cols:
        # Fallback: use OneHotEncoder if category_encoders not available
        for col in high_card_cols:
            transformers.append((f'cat_hc_{col}', Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent').set_output(transform='pandas')),
                ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
            ]), [col]))

    # ── Low-cardinality categorical pipeline (OneHot Encoding) ──
    if low_card_cols:
        low_card_rare = [c for c in low_card_cols if c in rare_merge_cols]
        low_card_no_rare = [c for c in low_card_cols if c not in rare_merge_cols]

        # BUG FIX: même problème que pour les pipelines high-card ci-dessus —
        # sans .set_output(transform='pandas'), RareCategoryMerger perdait les
        # noms de colonnes et le regroupement des catégories rares devenait un
        # no-op silencieux (aucune erreur, mais aucune fusion n'était faite).
        if low_card_rare:
            low_card_pipeline = Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent').set_output(transform='pandas')),
                ('rare_merger', RareCategoryMerger(columns=low_card_rare, threshold=30)),
                ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
            ])
            transformers.append(('cat_low_card', low_card_pipeline, low_card_rare))

        if low_card_no_rare:
            low_card_pipeline2 = Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent').set_output(transform='pandas')),
                ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
            ])
            transformers.append(('cat_low_card_other', low_card_pipeline2, low_card_no_rare))

    # ── Binary pipeline ──
    if binary_cols:
        binary_pipeline = Pipeline([
            ('imputer', BinaryImputer()),
        ])
        transformers.append(('binary', binary_pipeline, binary_cols))

    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder='drop',
        verbose_feature_names_out=True,
    )

    return preprocessor


def get_all_feature_columns(features_config: Dict[str, List[str]]) -> List[str]:
    """Get the ordered list of all feature columns for the pipeline."""
    cols = []
    cols.extend(features_config['numeric'])
    cols.extend(features_config['categorical_high_card'])
    cols.extend(features_config['categorical_low_card'])
    cols.extend(features_config['binary'])
    return cols


# ═══════════════════════════════════════════════════════════════════════════
# MODEL DEFINITIONS & TRAINING
# ═══════════════════════════════════════════════════════════════════════════

def get_models() -> Dict[str, BaseEstimator]:
    """Return the 6 candidate models."""
    models = {
        'LinearRegression': LinearRegression(),
        'Ridge': Ridge(alpha=1.0, random_state=RANDOM_STATE),
        'Lasso': Lasso(alpha=0.1, max_iter=5000, random_state=RANDOM_STATE),
        'RandomForest': RandomForestRegressor(
            n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1
        ),
    }
    if HAS_XGBOOST:
        models['XGBoost'] = XGBRegressor(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    if HAS_LIGHTGBM:
        models['LightGBM'] = LGBMRegressor(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbose=-1,
        )
    return models


def get_param_distributions() -> Dict[str, Dict[str, Any]]:
    """Define parameter search spaces for Phase 1 (RandomizedSearchCV)."""
    param_dist = {
        'Ridge': {
            'alpha': [0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0],
        },
        'Lasso': {
            'alpha': [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
            'max_iter': [3000, 5000, 8000],
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
            'max_depth': [3, 4, 5, 6, 8, -1],
            'num_leaves': [15, 31, 50, 63, 100],
            'min_child_samples': [5, 10, 20, 30],
            'subsample': [0.7, 0.8, 0.9, 1.0],
            'colsample_bytree': [0.7, 0.8, 0.9, 1.0],
            'reg_alpha': [0, 0.01, 0.1, 1.0],
            'reg_lambda': [0.1, 1.0, 5.0, 10.0],
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
    cv_folds: int = 5,
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
            cv=cv_folds,
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
    cv_folds: int = 5,
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
        if name in ['LightGBM', 'RandomForest', 'XGBoost']:
            logger.info(f"  Using RandomizedSearchCV for {name} to prevent combinatorial explosion.")
            search = RandomizedSearchCV(
                estimator=base_model,
                param_distributions=param_grid,
                n_iter=40,  # 40 iterations is typically enough to find the global minimum in a narrow grid
                scoring='neg_root_mean_squared_error',
                cv=cv_folds,
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
                cv=cv_folds,
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


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATION METRICS
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION PIPELINE (7 steps)
# ═══════════════════════════════════════════════════════════════════════════

def validation_step1_heldout(test_metrics: Dict[str, float]) -> Dict[str, Any]:
    """Step 1: Held-out test validation."""
    targets = {'RMSE': 80000, 'MAE': 50000, 'R2': 0.75, 'MAPE': 20, 'MedAE': 35000}
    results = {}
    for metric, target in targets.items():
        value = test_metrics.get(metric, float('inf'))
        if metric == 'R2':
            passed = value >= target
        else:
            passed = value <= target
        results[metric] = {'value': value, 'target': target, 'passed': passed}
    return results


def validation_step2_overfitting(train_metrics: Dict[str, float], test_metrics: Dict[str, float]) -> Dict[str, Any]:
    """Step 2: Overfitting diagnosis (train vs test gap)."""
    gaps = {}
    for metric in ['RMSE', 'MAE', 'R2', 'MAPE']:
        train_val = train_metrics.get(metric, 0)
        test_val = test_metrics.get(metric, 0)
        if metric in ('RMSE', 'MAE', 'MAPE'):
            gap = test_val - train_val
            ratio = test_val / max(train_val, 1e-6)
        else:  # R2
            gap = train_val - test_val
            ratio = train_val / max(test_val, 1e-6)
        gaps[metric] = {
            'train': train_val,
            'test': test_val,
            'gap': round(gap, 2),
            'ratio': round(ratio, 4),
            'severity': 'low' if ratio < 1.2 else ('moderate' if ratio < 1.5 else 'high'),
        }
    return gaps


def validation_step3_segment_analysis(
    df_test: pd.DataFrame,
    y_test: np.ndarray,
    y_pred_test: np.ndarray,
) -> Dict[str, Any]:
    """Step 3: Segment-level analysis by gouvernorat, bien.type, and price range."""
    results = {}
    df_analysis = df_test.copy()
    df_analysis['y_true'] = expm1_to_original(y_test)
    df_analysis['y_pred'] = expm1_to_original(y_pred_test)
    df_analysis['error'] = abs(df_analysis['y_true'] - df_analysis['y_pred'])
    df_analysis['pct_error'] = (df_analysis['error'] / df_analysis['y_true'].clip(lower=1)) * 100

    # By gouvernorat
    if 'localisation.gouvernorat' in df_analysis.columns:
        gouv_stats = df_analysis.groupby('localisation.gouvernorat').agg(
            n=('error', 'count'),
            mae=('error', 'mean'),
            mape=('pct_error', 'mean'),
            median_error=('error', 'median'),
        ).round(2).to_dict('index')
        results['by_gouvernorat'] = gouv_stats

    # By bien.type
    if 'bien.type' in df_analysis.columns:
        type_stats = df_analysis.groupby('bien.type').agg(
            n=('error', 'count'),
            mae=('error', 'mean'),
            mape=('pct_error', 'mean'),
            median_error=('error', 'median'),
        ).round(2).to_dict('index')
        results['by_bien_type'] = type_stats

    # By price range
    df_analysis['price_range'] = pd.qcut(df_analysis['y_true'], q=4, labels=['Q1 (low)', 'Q2', 'Q3', 'Q4 (high)'], duplicates='drop')
    price_stats = df_analysis.groupby('price_range').agg(
        n=('error', 'count'),
        mae=('error', 'mean'),
        mape=('pct_error', 'mean'),
    ).round(2).to_dict('index')
    results['by_price_range'] = price_stats

    return results


def validation_step4_prediction_intervals(
    model: BaseEstimator,
    X_test: np.ndarray,
    y_test: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> Dict[str, Any]:
    """Step 4: Prediction intervals via bootstrap."""
    logger.info(f"  Computing prediction intervals ({n_bootstrap} bootstrap samples)...")
    n = len(X_test)
    alpha = 1 - confidence

    bootstrap_preds = np.zeros((n_bootstrap, n))
    rng = np.random.RandomState(RANDOM_STATE)

    for i in range(n_bootstrap):
        idx = rng.choice(n, size=n, replace=True)
        X_boot = X_test[idx]
        try:
            bootstrap_preds[i] = model.predict(X_boot)
        except Exception:
            bootstrap_preds[i] = model.predict(X_test)

    lower = np.percentile(bootstrap_preds, 100 * alpha / 2, axis=0)
    upper = np.percentile(bootstrap_preds, 100 * (1 - alpha / 2), axis=0)
    mean_pred = np.mean(bootstrap_preds, axis=0)

    # Coverage: fraction of true values within the interval
    in_interval = (y_test >= lower) & (y_test <= upper)
    coverage = np.mean(in_interval)

    return {
        'lower': lower,
        'upper': upper,
        'mean_pred': mean_pred,
        'coverage': round(float(coverage), 4),
        'expected_coverage': confidence,
        'n_bootstrap': n_bootstrap,
    }


def validation_step5_external_benchmark(
    df: pd.DataFrame,
    y_pred_log: np.ndarray,
    tolerance_pct: float = 15.0,
) -> Dict[str, Any]:
    """Step 5: External geographic validation vs Mubawab benchmarks.

    Compares model's average predicted prix_m2 per zone against
    Mubawab's published reference prices (TND/m²).
    """
    results = {}
    df_eval = df.copy()
    df_eval['y_pred'] = expm1_to_original(y_pred_log)

    if 'bien.superficie_totale' in df_eval.columns:
        df_eval['pred_prix_m2'] = df_eval['y_pred'] / df_eval['bien.superficie_totale'].clip(lower=1)

    if 'localisation.ville' not in df_eval.columns:
        results['note'] = 'localisation.ville column not available for benchmark comparison'
        return results

    ville_prices = df_eval.groupby('localisation.ville')['pred_prix_m2'].median().to_dict()

    for zone, ref_prices in MUBAWAB_SALES_BENCHMARK.items():
        # Try to match zone to a ville in our data
        matched = False
        for ville, model_price in ville_prices.items():
            if zone.lower() in ville.lower() or ville.lower() in zone.lower():
                for condition, ref_price in ref_prices.items():
                    if ref_price is None:
                        continue
                    diff_pct = abs(model_price - ref_price) / ref_price * 100
                    within_tol = diff_pct <= tolerance_pct
                    key = f"{zone} ({condition})"
                    results[key] = {
                        'model_prix_m2': round(model_price, 2),
                        'mubawab_prix_m2': ref_price,
                        'diff_pct': round(diff_pct, 2),
                        'within_tolerance': within_tol,
                    }
                matched = True
                break

    if not results:
        results['note'] = 'No zone matches found between model data and Mubawab benchmarks'
    else:
        within_count = sum(1 for v in results.values() if isinstance(v, dict) and v.get('within_tolerance'))
        total_count = sum(1 for v in results.values() if isinstance(v, dict))
        results['summary'] = {
            'zones_compared': total_count,
            'within_tolerance': within_count,
            'tolerance_pct': tolerance_pct,
            'pass_rate': round(within_count / max(total_count, 1) * 100, 1),
        }

    return results


def validation_step6_ipim_comparison(df: pd.DataFrame, y_pred_log: np.ndarray) -> Dict[str, Any]:
    """Step 6: Index comparison vs INS IPIM.

    Computes a simple price index from model predictions and compares
    with the published IPIM trend.
    """
    results = {'ipim_reference': IPIM_REFERENCE}
    df_eval = df.copy()
    df_eval['y_pred'] = expm1_to_original(y_pred_log)

    # Compute median price index by gouvernorat (normalized to base)
    if 'localisation.gouvernorat' in df_eval.columns:
        gouv_median = df_eval.groupby('localisation.gouvernorat')['y_pred'].median()
        if len(gouv_median) > 0:
            # Normalize so the median gouvernorat = 100
            overall_median = gouv_median.median()
            price_index = (gouv_median / overall_median * 100).round(2).to_dict()
            results['model_price_index_by_gouvernorat'] = price_index

            # Compare annual change
            results['analysis'] = (
                f"IPIM reports {IPIM_REFERENCE['annual_change_pct']}% annual change. "
                f"Model can be re-baselined to IPIM for deployment."
            )

    return results


def validation_step7_go_nogo(
    step1: Dict,
    step2: Dict,
    step5: Dict,
) -> Dict[str, Any]:
    """Step 7: Go/No-Go decision matrix."""
    # Count passed targets from step 1
    targets_passed = sum(1 for v in step1.values() if isinstance(v, dict) and v.get('passed'))
    targets_total = sum(1 for v in step1.values() if isinstance(v, dict))

    # Overfitting severity
    severities = [v['severity'] for v in step2.values() if isinstance(v, dict)]
    high_overfit = severities.count('high')

    # External benchmark
    benchmark_summary = step5.get('summary', {})
    benchmark_pass_rate = benchmark_summary.get('pass_rate', 0)

    # Decision logic
    score = 0
    reasons = []

    # Target achievement (0-40 points)
    target_score = targets_passed / max(targets_total, 1) * 40
    score += target_score
    if targets_passed >= 4:
        reasons.append(f"PASS: {targets_passed}/{targets_total} metric targets met")
    elif targets_passed >= 3:
        reasons.append(f"WARN: {targets_passed}/{targets_total} metric targets met")
    else:
        reasons.append(f"FAIL: Only {targets_passed}/{targets_total} metric targets met")

    # Overfitting (0-30 points)
    if high_overfit == 0:
        score += 30
        reasons.append("PASS: No severe overfitting detected")
    elif high_overfit <= 1:
        score += 15
        reasons.append(f"WARN: {high_overfit} metric(s) show high overfitting")
    else:
        reasons.append(f"FAIL: {high_overfit} metric(s) show high overfitting")

    # External validation (0-30 points)
    if benchmark_pass_rate >= 60:
        score += 30
        reasons.append(f"PASS: {benchmark_pass_rate}% of benchmark zones within tolerance")
    elif benchmark_pass_rate >= 40:
        score += 15
        reasons.append(f"WARN: {benchmark_pass_rate}% of benchmark zones within tolerance")
    else:
        reasons.append(f"FAIL: Only {benchmark_pass_rate}% of benchmark zones within tolerance")

    decision = 'GO' if score >= 70 else ('CONDITIONAL' if score >= 50 else 'NO-GO')

    return {
        'decision': decision,
        'score': round(score, 1),
        'max_score': 100,
        'reasons': reasons,
        'targets_passed': targets_passed,
        'targets_total': targets_total,
        'high_overfit_count': high_overfit,
        'benchmark_pass_rate': benchmark_pass_rate,
    }


def run_full_validation(
    model: BaseEstimator,
    X_train: np.ndarray, y_train: pd.Series,
    X_val: np.ndarray, y_val: pd.Series,
    X_test: np.ndarray, y_test: pd.Series,
    df_test: pd.DataFrame,
    df_full: pd.DataFrame,
    eval_results: Dict,
) -> Dict[str, Any]:
    """Run all 7 validation steps."""
    logger.info(f"\n{'='*60}")
    logger.info("VALIDATION PIPELINE (7 steps)")
    logger.info(f"{'='*60}")

    test_metrics = eval_results['test']['metrics']
    train_metrics = eval_results['train']['metrics']
    y_pred_test = eval_results['test']['y_pred']

    # Step 1
    logger.info("\nStep 1: Held-out test validation...")
    step1 = validation_step1_heldout(test_metrics)
    for metric, info in step1.items():
        status = "PASS" if info['passed'] else "FAIL"
        logger.info(f"  {metric}: {info['value']} (target: {info['target']}) [{status}]")

    # Step 2
    logger.info("\nStep 2: Overfitting diagnosis...")
    step2 = validation_step2_overfitting(train_metrics, test_metrics)
    for metric, info in step2.items():
        logger.info(f"  {metric}: train={info['train']}, test={info['test']}, gap={info['gap']}, severity={info['severity']}")

    # Step 3
    logger.info("\nStep 3: Segment-level analysis...")
    step3 = validation_step3_segment_analysis(df_test, y_test, y_pred_test)
    for segment_name, segment_data in step3.items():
        logger.info(f"  {segment_name}: {len(segment_data)} groups")

    # Step 4
    logger.info("\nStep 4: Prediction intervals (bootstrap)...")
    step4 = validation_step4_prediction_intervals(model, X_test, y_test)
    logger.info(f"  Coverage: {step4['coverage']*100:.1f}% (expected: {step4['expected_coverage']*100:.0f}%)")

    # Step 5
    logger.info("\nStep 5: External benchmark validation...")
    step5 = validation_step5_external_benchmark(df_test, y_pred_test)
    if 'summary' in step5:
        logger.info(f"  {step5['summary']}")
    else:
        logger.info(f"  {step5.get('note', 'N/A')}")

    # Step 6
    logger.info("\nStep 6: IPIM index comparison...")
    step6 = validation_step6_ipim_comparison(df_test, y_pred_test)
    if 'analysis' in step6:
        logger.info(f"  {step6['analysis']}")

    # Step 7
    logger.info("\nStep 7: Go/No-Go decision...")
    step7 = validation_step7_go_nogo(step1, step2, step5)
    logger.info(f"  Decision: {step7['decision']} (score: {step7['score']}/{step7['max_score']})")
    for reason in step7['reasons']:
        logger.info(f"    {reason}")

    return {
        'step1_heldout': step1,
        'step2_overfitting': step2,
        'step3_segments': step3,
        'step4_prediction_intervals': step4,
        'step5_external_benchmark': step5,
        'step6_ipim': {k: v for k, v in step6.items() if k != 'ipim_reference'},
        'step7_go_nogo': step7,
    }


# ═══════════════════════════════════════════════════════════════════════════
# VISUALIZATIONS
# ═══════════════════════════════════════════════════════════════════════════

def setup_plotting():
    """Configure matplotlib/seaborn defaults."""
    plt.style.use('seaborn-v0_8-whitegrid')
    sns.set_palette('husl')
    plt.rcParams.update({
        'figure.dpi': 150,
        'savefig.dpi': 150,
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
    })


def plot_01_actual_vs_predicted(
    y_true: np.ndarray, y_pred: np.ndarray, path: str
):
    """Chart 1: Actual vs Predicted scatter plot."""
    fig, ax = plt.subplots(figsize=(8, 8))
    y_true_orig = np.expm1(y_true)
    y_pred_orig = expm1_to_original(y_pred)

    # Clip for visualization
    max_val = np.percentile(y_true_orig, 99)
    mask = (y_true_orig < max_val) & (y_pred_orig < max_val)

    ax.scatter(y_true_orig[mask], y_pred_orig[mask], alpha=0.3, s=10, c='steelblue', edgecolors='none')
    max_plot = max_val * 1.1
    ax.plot([0, max_plot], [0, max_plot], 'r--', linewidth=2, label='Perfect prediction')
    ax.set_xlim(0, max_plot)
    ax.set_ylim(0, max_plot)
    ax.set_xlabel('Actual Price (TND)')
    ax.set_ylabel('Predicted Price (TND)')
    ax.set_title('Actual vs Predicted Prices')
    ax.legend(loc='upper left')
    ax.set_aspect('equal', adjustable='box')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_02_residual_distribution(residuals: np.ndarray, path: str):
    """Chart 2: Residual distribution histogram."""
    fig, ax = plt.subplots(figsize=(10, 6))
    # Show residuals in log-space with histogram and KDE
    ax.hist(residuals, bins=60, color='steelblue', alpha=0.7, edgecolor='white', density=True)
    sns.kdeplot(residuals, ax=ax, color='darkred', linewidth=2)
    ax.axvline(x=0, color='black', linestyle='--', linewidth=1)
    ax.set_xlabel('Residual (log-space)')
    ax.set_ylabel('Density')
    ax.set_title('Distribution of Residuals (log-space)')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_03_residual_vs_predicted(y_pred: np.ndarray, residuals: np.ndarray, path: str):
    """Chart 3: Residual vs Predicted plot."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(y_pred, residuals, alpha=0.3, s=10, c='steelblue', edgecolors='none')
    ax.axhline(y=0, color='red', linestyle='--', linewidth=1)
    ax.set_xlabel('Predicted (log-space)')
    ax.set_ylabel('Residual (log-space)')
    ax.set_title('Residuals vs Predicted Values')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_04_feature_importance(model: BaseEstimator, feature_names: List[str], path: str):
    """Chart 4: Feature importance (top 20)."""
    importances = None

    if hasattr(model, 'feature_importances_'):
        importances = model.feature_importances_
    elif hasattr(model, 'coef_'):
        importances = np.abs(model.coef_)

    if importances is None:
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.text(0.5, 0.5, 'Feature importance not available for this model type',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    if len(importances) != len(feature_names):
        logger.warning(f"Feature names ({len(feature_names)}) != importances ({len(importances)}). Skipping feature importance plot.")
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.text(0.5, 0.5, 'Feature name mismatch — cannot plot',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    n_show = min(20, len(importances))
    indices = np.argsort(importances)[-n_show:][::-1]

    fig, ax = plt.subplots(figsize=(10, 8))
    names = [feature_names[i] for i in indices]
    values = importances[indices]

    bars = ax.barh(range(len(names)), values, color='steelblue', edgecolor='white')
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('Importance')
    ax.set_title(f'Top {n_show} Feature Importances')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_05_learning_curves(
    model: BaseEstimator,
    X_train: np.ndarray, y_train: pd.Series,
    cv_folds: int, path: str,
):
    """Chart 5: Learning curves."""
    try:
        train_sizes, train_scores, val_scores = learning_curve(
            model, X_train, y_train,
            train_sizes=np.linspace(0.1, 1.0, 10),
            cv=cv_folds,
            scoring='neg_root_mean_squared_error',
            n_jobs=-1,
            shuffle=True,
            random_state=RANDOM_STATE,
        )

        train_rmse = -train_scores.mean(axis=1)
        val_rmse = -val_scores.mean(axis=1)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(train_sizes, train_rmse, 'o-', color='steelblue', label='Training RMSE')
        ax.plot(train_sizes, val_rmse, 'o-', color='darkorange', label='Validation RMSE')
        ax.fill_between(train_sizes, train_rmse - train_scores.std(axis=1),
                        train_rmse + train_scores.std(axis=1), alpha=0.1, color='steelblue')
        ax.fill_between(train_sizes, val_rmse - val_scores.std(axis=1),
                        val_rmse + val_scores.std(axis=1), alpha=0.1, color='darkorange')
        ax.set_xlabel('Training Set Size')
        ax.set_ylabel('RMSE (log-space)')
        ax.set_title('Learning Curves')
        ax.legend(loc='best')
        plt.tight_layout()
        plt.savefig(path, bbox_inches='tight')
        plt.close()
    except Exception as e:
        logger.warning(f"Could not generate learning curves: {e}")
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, f'Learning curves unavailable: {e}',
                ha='center', va='center', transform=ax.transAxes, fontsize=12)
        plt.savefig(path, bbox_inches='tight')
        plt.close()


def plot_06_prediction_intervals(
    y_true: np.ndarray, y_pred: np.ndarray,
    lower: np.ndarray, upper: np.ndarray, path: str,
):
    """Chart 6: Prediction interval plot."""
    fig, ax = plt.subplots(figsize=(12, 6))
    n_show = min(200, len(y_true))
    idx = np.random.RandomState(RANDOM_STATE).choice(len(y_true), n_show, replace=False)
    idx = np.sort(idx)

    y_true_orig = np.expm1(y_true[idx])
    y_pred_orig = expm1_to_original(y_pred[idx])
    lower_orig = expm1_to_original(lower[idx])
    upper_orig = expm1_to_original(upper[idx])

    x = np.arange(n_show)
    ax.fill_between(x, lower_orig, upper_orig, alpha=0.3, color='steelblue', label='95% CI')
    ax.plot(x, y_true_orig, 'o', color='black', markersize=3, alpha=0.5, label='Actual')
    ax.plot(x, y_pred_orig, '-', color='darkorange', linewidth=1, alpha=0.8, label='Predicted')
    ax.set_xlabel('Sample Index')
    ax.set_ylabel('Price (TND)')
    ax.set_title('Prediction Intervals (95% Confidence)')
    ax.legend(loc='best')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_07_mae_by_gouvernorat(
    df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, path: str,
):
    """Chart 7: MAE by gouvernorat bar chart."""
    df_plot = df.copy()
    df_plot['y_true'] = np.expm1(y_true)
    df_plot['y_pred'] = expm1_to_original(y_pred)
    df_plot['error'] = abs(df_plot['y_true'] - df_plot['y_pred'])

    if 'localisation.gouvernorat' not in df_plot.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'gouvernorat column not available',
                ha='center', va='center', transform=ax.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    gouv_mae = df_plot.groupby('localisation.gouvernorat')['error'].mean().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#e74c3c' if v > 50000 else '#f39c12' if v > 35000 else '#27ae60' for v in gouv_mae.values]
    ax.barh(range(len(gouv_mae)), gouv_mae.values, color=colors, edgecolor='white')
    ax.set_yticks(range(len(gouv_mae)))
    ax.set_yticklabels(gouv_mae.index, fontsize=9)
    ax.set_xlabel('Mean Absolute Error (TND)')
    ax.set_title('MAE by Gouvernorat')
    ax.axvline(x=50000, color='red', linestyle='--', alpha=0.7, label='Target (50,000 TND)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_08_mae_by_bien_type(
    df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, path: str,
):
    """Chart 8: MAE by bien.type bar chart."""
    df_plot = df.copy()
    df_plot['y_true'] = np.expm1(y_true)
    df_plot['y_pred'] = expm1_to_original(y_pred)
    df_plot['error'] = abs(df_plot['y_true'] - df_plot['y_pred'])

    if 'bien.type' not in df_plot.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'bien.type column not available',
                ha='center', va='center', transform=ax.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    type_mae = df_plot.groupby('bien.type')['error'].mean().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#e74c3c' if v > 50000 else '#f39c12' if v > 35000 else '#27ae60' for v in type_mae.values]
    ax.barh(range(len(type_mae)), type_mae.values, color=colors, edgecolor='white')
    ax.set_yticks(range(len(type_mae)))
    ax.set_yticklabels(type_mae.index, fontsize=9)
    ax.set_xlabel('Mean Absolute Error (TND)')
    ax.set_title('MAE by Property Type')
    ax.axvline(x=50000, color='red', linestyle='--', alpha=0.7, label='Target (50,000 TND)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_09_price_distribution_kde(y_true: np.ndarray, y_pred: np.ndarray, path: str):
    """Chart 9: Price distribution (actual vs predicted KDE)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    y_true_orig = np.expm1(y_true)
    y_pred_orig = expm1_to_original(y_pred)

    # Clip for visualization
    max_val = np.percentile(y_true_orig, 98)
    sns.kdeplot(y_true_orig[y_true_orig < max_val], ax=ax, label='Actual', color='steelblue', linewidth=2)
    sns.kdeplot(y_pred_orig[y_pred_orig < max_val], ax=ax, label='Predicted', color='darkorange', linewidth=2, linestyle='--')
    ax.set_xlabel('Price (TND)')
    ax.set_ylabel('Density')
    ax.set_title('Price Distribution: Actual vs Predicted')
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_10_qq_residuals(residuals: np.ndarray, path: str):
    """Chart 10: Q-Q plot of residuals."""
    fig, ax = plt.subplots(figsize=(8, 8))
    stats.probplot(residuals, dist='norm', plot=ax)
    ax.set_title('Q-Q Plot of Residuals (log-space)')
    ax.get_lines()[0].set_markerfacecolor('steelblue')
    ax.get_lines()[0].set_markeredgecolor('steelblue')
    ax.get_lines()[0].set_markersize(3)
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_11_cv_scores_boxplot(cv_results: Dict[str, Any], path: str):
    """Chart 11: Cross-validation scores boxplot."""
    fig, ax = plt.subplots(figsize=(10, 6))

    model_names = []
    all_scores = []

    for name, result in cv_results.items():
        if result.get('search') and hasattr(result['search'], 'cv_results_'):
            cv_res = result['search'].cv_results_
            # Extract all fold scores
            test_scores = []
            for key in cv_res:
                if 'split' in key and '_test_score' in key:
                    test_scores.extend(cv_res[key])
            if test_scores:
                model_names.append(name)
                all_scores.append([-s for s in test_scores])  # Convert back from neg

    if not model_names:
        ax.text(0.5, 0.5, 'No CV score data available',
                ha='center', va='center', transform=ax.transAxes)
    else:
        bp = ax.boxplot(all_scores, labels=model_names, patch_artist=True)
        colors = sns.color_palette('husl', len(model_names))
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
    ax.set_ylabel('RMSE (log-space)')
    ax.set_title('Cross-Validation Scores by Model')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_12_hyperparameter_sensitivity(phase1_results: Dict[str, Any], path: str):
    """Chart 12: Hyperparameter sensitivity heatmap."""
    fig, axes = plt.subplots(1, 1, figsize=(12, 6))

    data_rows = []
    for name, result in phase1_results.items():
        if result.get('search') and hasattr(result['search'], 'cv_results_'):
            cv_res = result['search'].cv_results_
            if 'mean_test_score' in cv_res:
                best_idx = result['search'].best_index_
                best_rmse = -cv_res['mean_test_score'][best_idx]
                std_rmse = cv_res['std_test_score'][best_idx]
                data_rows.append({
                    'Model': name,
                    'Best RMSE': best_rmse,
                    'Std': std_rmse,
                    'Params Tested': len(cv_res['params']),
                })

    if not data_rows:
        axes.text(0.5, 0.5, 'No hyperparameter search data available',
                  ha='center', va='center', transform=axes.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    df_hp = pd.DataFrame(data_rows).set_index('Model')
    sns.heatmap(df_hp, annot=True, fmt='.4f', cmap='YlOrRd_r', ax=axes, linewidths=0.5)
    axes.set_title('Hyperparameter Search Summary')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_13_external_validation(external_results: Dict[str, Any], path: str):
    """Chart 13: External validation comparison (model vs Mubawab)."""
    fig, ax = plt.subplots(figsize=(12, 8))

    # Extract comparable results
    zones = []
    model_prices = []
    mubawab_prices = []

    for key, val in external_results.items():
        if isinstance(val, dict) and 'model_prix_m2' in val:
            zones.append(key)
            model_prices.append(val['model_prix_m2'])
            mubawab_prices.append(val['mubawab_prix_m2'])

    if not zones:
        ax.text(0.5, 0.5, 'No external benchmark comparison data available',
                ha='center', va='center', transform=ax.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    x = np.arange(len(zones))
    width = 0.35

    ax.bar(x - width/2, model_prices, width, label='Model (median prix/m²)', color='steelblue', alpha=0.8)
    ax.bar(x + width/2, mubawab_prices, width, label='Mubawab Reference', color='darkorange', alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(zones, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Price per m² (TND)')
    ax.set_title('Model Predictions vs Mubawab Benchmarks')
    ax.legend(loc='best')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def generate_all_visualizations(
    best_model: BaseEstimator,
    eval_results: Dict,
    X_train: np.ndarray, y_train: pd.Series,
    X_test: np.ndarray, y_test: pd.Series,
    df_test: pd.DataFrame,
    df_full: pd.DataFrame,
    phase1_results: Dict,
    validation_results: Dict,
    feature_names: List[str],
    cv_folds: int,
    vis_dir: str,
):
    """Generate all 13 visualization charts."""
    logger.info(f"\n{'='*60}")
    logger.info("GENERATING VISUALIZATIONS")
    logger.info(f"{'='*60}")

    os.makedirs(vis_dir, exist_ok=True)
    setup_plotting()

    y_pred_test = eval_results['test']['y_pred']
    residuals = y_test.values - y_pred_test
    pi_data = validation_results.get('step4_prediction_intervals', {})

    charts = [
        ('01_actual_vs_predicted.png', lambda p: plot_01_actual_vs_predicted(y_test.values, y_pred_test, p)),
        ('02_residual_distribution.png', lambda p: plot_02_residual_distribution(residuals, p)),
        ('03_residual_vs_predicted.png', lambda p: plot_03_residual_vs_predicted(y_pred_test, residuals, p)),
        ('04_feature_importance.png', lambda p: plot_04_feature_importance(best_model, feature_names, p)),
        ('05_learning_curves.png', lambda p: plot_05_learning_curves(best_model, X_train, y_train, cv_folds, p)),
        ('06_prediction_intervals.png', lambda p: plot_06_prediction_intervals(
            y_test.values, y_pred_test,
            pi_data.get('lower', np.zeros(len(y_test))),
            pi_data.get('upper', np.ones(len(y_test))),
            p,
        )),
        ('07_mae_by_gouvernorat.png', lambda p: plot_07_mae_by_gouvernorat(df_test, y_test.values, y_pred_test, p)),
        ('08_mae_by_bien_type.png', lambda p: plot_08_mae_by_bien_type(df_test, y_test.values, y_pred_test, p)),
        ('09_price_distribution_kde.png', lambda p: plot_09_price_distribution_kde(y_test.values, y_pred_test, p)),
        ('10_qq_residuals.png', lambda p: plot_10_qq_residuals(residuals, p)),
        ('11_cv_scores_boxplot.png', lambda p: plot_11_cv_scores_boxplot(phase1_results, p)),
        ('12_hyperparameter_sensitivity.png', lambda p: plot_12_hyperparameter_sensitivity(phase1_results, p)),
        ('13_external_validation.png', lambda p: plot_13_external_validation(
            validation_results.get('step5_external_benchmark', {}), p
        )),
    ]

    for filename, plot_func in charts:
        filepath = os.path.join(vis_dir, filename)
        try:
            plot_func(filepath)
            logger.info(f"  Saved: {filepath}")
        except Exception as e:
            logger.error(f"  Failed to generate {filename}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE IMPORTANCE TABLE
# ═══════════════════════════════════════════════════════════════════════════

def get_feature_importance_table(model: BaseEstimator, feature_names: List[str]) -> List[Dict[str, Any]]:
    """Extract feature importance as a sorted list of dicts."""
    importances = None

    if hasattr(model, 'feature_importances_'):
        importances = model.feature_importances_
    elif hasattr(model, 'coef_'):
        importances = np.abs(model.coef_)

    if importances is None or len(importances) != len(feature_names):
        return [{'feature': 'N/A', 'importance': 0, 'note': 'Not available for this model type'}]

    # Create DataFrame for clean display
    fi_df = pd.DataFrame({
        'feature': feature_names,
        'importance': importances,
    }).sort_values('importance', ascending=False)

    fi_df['cumulative_importance'] = fi_df['importance'].cumsum() / fi_df['importance'].sum() * 100

    return fi_df.to_dict('records')


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def print_final_report(
    best_name: str,
    best_params: Dict,
    eval_results: Dict,
    validation_results: Dict,
    feature_importance: List[Dict],
    training_time: float,
):
    """Print comprehensive training summary."""
    go_nogo = validation_results.get('step7_go_nogo', {})
    decision = go_nogo.get('decision', 'UNKNOWN')
    score = go_nogo.get('score', 0)

    test_metrics = eval_results['test']['metrics']
    train_metrics = eval_results['train']['metrics']

    print(f"\n{'='*70}")
    print("  FINAL TRAINING REPORT")
    print(f"{'='*70}")

    print(f"\n  Best Model: {best_name}")
    print(f"  Best Parameters: {json.dumps(best_params, default=str, indent=4)}")
    print(f"  Total Training Time: {training_time:.1f}s")

    print(f"\n  {'─'*40}")
    print(f"  EVALUATION METRICS (Test Set, TND)")
    print(f"  {'─'*40}")
    for metric, value in test_metrics.items():
        target = {'RMSE': '<80K', 'MAE': '<50K', 'R2': '>0.75', 'MAPE': '<20%', 'MedAE': '<35K'}.get(metric, '')
        print(f"    {metric:8s}: {value:>12,.2f}  {target}")

    print(f"\n  {'─'*40}")
    print(f"  OVERFITTING DIAGNOSIS")
    print(f"  {'─'*40}")
    for metric in ['RMSE', 'MAE', 'R2']:
        t_val = train_metrics.get(metric, 0)
        v_val = test_metrics.get(metric, 0)
        if metric == 'R2':
            gap = t_val - v_val
            print(f"    {metric:8s}: train={t_val:.4f}, test={v_val:.4f}, gap={gap:.4f}")
        else:
            gap = v_val - t_val
            ratio = v_val / max(t_val, 1)
            print(f"    {metric:8s}: train={t_val:,.0f}, test={v_val:,.0f}, gap={gap:,.0f}, ratio={ratio:.2f}x")

    print(f"\n  {'─'*40}")
    print(f"  GO/NO-GO DECISION")
    print(f"  {'─'*40}")
    print(f"    Decision: {decision} (score: {score}/100)")
    for reason in go_nogo.get('reasons', []):
        print(f"    • {reason}")

    print(f"\n  {'─'*40}")
    print(f"  TOP 15 FEATURE IMPORTANCE")
    print(f"  {'─'*40}")
    for i, fi in enumerate(feature_importance[:15]):
        if 'feature' in fi and 'importance' in fi:
            cum = fi.get('cumulative_importance', 0)
            print(f"    {i+1:2d}. {fi['feature']:<45s} {fi['importance']:.4f}  (cum: {cum:.1f}%)")

    print(f"\n{'='*70}")
    print(f"  Training complete. Artifacts saved to output directory.")
    print(f"{'='*70}\n")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN TRAINING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

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