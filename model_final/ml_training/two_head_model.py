"""
Two-Head VENTE/LOCATION Regressor.
=============================================================
P2-A: Addresses the fundamental inadequacy of a single set of
coefficients for modeling two different market dynamics
(Diagnostics Report §5.4).

Sales prices are driven by location premium, property quality,
and investment potential. Rental prices are driven by proximity
to transport/employment/education and supply-demand dynamics.

This estimator trains separate sub-models for each transaction type
while sharing the same preprocessor. It is fully sklearn-compatible
(fit/predict/get_params/set_params).
"""

from typing import Any, Dict, Optional

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import HistGradientBoostingRegressor

from .config import logger, RANDOM_STATE


class VenteLocationTwoHeadRegressor(BaseEstimator, RegressorMixin):
    """Two-head regressor: separate models for VENTE and LOCATION.

    Routes each sample to the appropriate sub-model based on the
    ``is_vente`` column (identified by ``is_vente_col_idx``).

    Parameters
    ----------
    base_estimator : BaseEstimator, optional
        The base model to clone for each head.  Defaults to
        HistGradientBoostingRegressor with loss='absolute_error'.
    is_vente_col_idx : int, optional
        Column index of ``is_vente`` in the preprocessed feature matrix.
        If None, the model is fitted on all data as a single head (fallback).
    """

    def __init__(
        self,
        base_estimator: Optional[BaseEstimator] = None,
        is_vente_col_idx: Optional[int] = None,
    ):
        self.base_estimator = base_estimator
        self.is_vente_col_idx = is_vente_col_idx

    def _get_base(self) -> BaseEstimator:
        if self.base_estimator is not None:
            return self.base_estimator
        return HistGradientBoostingRegressor(
            loss='absolute_error',
            max_iter=300,
            random_state=RANDOM_STATE,
        )

    def fit(self, X: np.ndarray, y: np.ndarray, **fit_params) -> 'VenteLocationTwoHeadRegressor':
        X = np.asarray(X)
        y = np.asarray(y)

        if self.is_vente_col_idx is None or self.is_vente_col_idx >= X.shape[1]:
            # Fallback: single model
            logger.warning("TwoHead: is_vente_col_idx not set or out of range. "
                           "Falling back to single-head mode.")
            self.vente_model_ = clone(self._get_base())
            self.vente_model_.fit(X, y)
            self.location_model_ = None
            self.single_head_ = True
            return self

        self.single_head_ = False
        is_vente = X[:, self.is_vente_col_idx]

        vente_mask = is_vente > 0.5
        loc_mask = ~vente_mask

        n_vente = vente_mask.sum()
        n_loc = loc_mask.sum()
        logger.info(f"TwoHead fit: {n_vente} VENTE samples, {n_loc} LOCATION samples")

        self.vente_model_ = clone(self._get_base())
        self.location_model_ = clone(self._get_base())

        if n_vente > 0:
            self.vente_model_.fit(X[vente_mask], y[vente_mask])
        else:
            logger.warning("TwoHead: No VENTE samples in training data!")
            self.vente_model_.fit(X, y)

        if n_loc > 0:
            self.location_model_.fit(X[loc_mask], y[loc_mask])
        else:
            logger.warning("TwoHead: No LOCATION samples in training data!")
            self.location_model_.fit(X, y)

        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X)
        predictions = np.zeros(X.shape[0])

        if self.single_head_:
            return self.vente_model_.predict(X)

        is_vente = X[:, self.is_vente_col_idx]
        vente_mask = is_vente > 0.5
        loc_mask = ~vente_mask

        if vente_mask.sum() > 0:
            predictions[vente_mask] = self.vente_model_.predict(X[vente_mask])
        if loc_mask.sum() > 0:
            predictions[loc_mask] = self.location_model_.predict(X[loc_mask])

        return predictions

    @property
    def feature_importances_(self):
        """Combine feature importances from both heads (weighted average)."""
        if self.single_head_:
            if hasattr(self.vente_model_, 'feature_importances_'):
                return self.vente_model_.feature_importances_
            return None

        imp_v = getattr(self.vente_model_, 'feature_importances_', None)
        imp_l = getattr(self.location_model_, 'feature_importances_', None)

        if imp_v is not None and imp_l is not None:
            # Weight by 80/20 approximate VENTE/LOCATION split
            return 0.8 * imp_v + 0.2 * imp_l
        return imp_v if imp_v is not None else imp_l
