"""
Feature importance table extraction.
=============================================================
Extracts and ranks feature importances (or absolute linear
coefficients) as a JSON-friendly list of records, with cumulative
importance for Pareto-style reporting.
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator


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
