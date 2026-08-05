"""
Data reconstruction helpers.
=============================================================
The v1 cleaning script one-hot encoded several categorical columns
(bien.type, bien.etat_general, localisation.gouvernorat, etc.). These
helpers reverse that encoding so the ML pipeline can apply its own
encoding strategy (TargetEncoder, OneHotEncoder) inside a proper
sklearn pipeline, avoiding data leakage.
"""

import numpy as np
import pandas as pd

from .config import logger


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
