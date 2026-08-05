"""
Custom scikit-learn transformers.
=============================================================
Self-contained transformer classes used throughout the preprocessing
pipeline (PriceBinTransformer, LogTransformer, OutlierClipper,
RareCategoryMerger, ColumnSelector, BinaryImputer, FeatureNameExtractor).

These have no dependency on the rest of the package — they only need
numpy/pandas/sklearn — so they can be imported independently.
"""

from typing import List, Optional, Tuple, Dict

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


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
