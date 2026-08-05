"""
Preprocessing pipeline assembly.
=============================================================
Builds the sklearn ColumnTransformer that combines the numeric,
high-cardinality categorical, low-cardinality categorical, and binary
sub-pipelines, using the custom transformers from transformers.py.
"""

from typing import Any, Dict, List

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler

from .optional_deps import HAS_CATEGORY_ENCODERS, TargetEncoder
from .transformers import OutlierClipper, LogTransformer, RareCategoryMerger, BinaryImputer


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
