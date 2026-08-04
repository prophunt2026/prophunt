#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_data_feature_engineering.py
==================================
Pipeline de nettoyage et feature engineering pour le dataset immobilier tunisien.
10 étapes suivant l'analyse EDA du notebook preprocessing.ipynb,
avec adaptations pour compatibilité ML Training Strategy.

Input  : merged_all.csv  (7,230 lignes × 184 colonnes)
Output : cleaned_vente.csv        (listings vente nettoyés, sans encodage)
         cleaned_location.csv     (listings location pour usage futur)
         feature_metadata.json    (métadonnées des features pour le pipeline ML)

Changelog v2 (aligned with ML Training Strategy):
  - Step 5 : ajout de price_bin (quartiles du log-prix) pour stratification
  - Step 6 : remplacement du P99 cap par clipping IQR (Q3 + 3×IQR)
  - Step 8 : ajout imputation mode pour catégorielles, False pour équipements
  - Step 9 : suppression de l'encodage (one-hot / target) pour éviter la fuite
              de données ; nettoyage catégoriel + fusion rares (<30 → "Autre")
  - Step 10: ajout log_nombre_pieces, prix_m2_log
  - Export : feature_metadata.json avec groupes de colonnes
"""

import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
INPUT_FILE           = "merged_all.csv"
OUTPUT_FILE_VENTE    = "cleaned_vente.csv"
OUTPUT_FILE_LOCATION = "cleaned_location.csv"
METADATA_FILE        = "feature_metadata.json"
COLUMN_GROUPS_FILE   = "column_groups.json"
PRIX_MAX_VENTE       = 10_000_000   # Seuil outlier vente (TND)
TARGET_COL           = "transaction.prix"
RARE_CATEGORY_MIN    = 30           # Seuil fusion catégories rares
IQR_MULTIPLIER       = 3.0          # Multiplicateur IQR pour clipping
PRIX_M2_CAP          = 50_000       # Cap prix/m² (TND/m²)

# Colonnes de métadonnées scraping à SUPPRIMER
SCRAPING_META_DROP = [
    "metadonnees_scraping.proxy_utilise",
    "metadonnees_scraping.cache",
    "metadonnees_scraping.hash_contenu",
    "metadonnees_scraping.date_derniere_verification",
    "metadonnees_scraping.absences_consecutives",
    "metadonnees_scraping.erreurs",
    "metadonnees_scraping.user_agent",
    "metadonnees_scraping.temps_scraping_ms",
    "schema_name",
    "schema_version",
]

# Colonnes identifiants/URLs à supprimer après déduplication
ID_URL_DROP = [
    "listing.id_universel",
    "listing.url_canonique",
    "listing.url_source",
    "listing.id_source",
]

# Préfixe des colonnes équipements
EQUIP_PREFIX = "equipements."

# Colonnes catégorielles connues pour imputation mode
CATEGORICAL_IMPUTE_COLS = [
    "bien.etat_general",
    "bien.type",
    "bien.usage",
    "contact.type_vendeur",
]

# Colonnes catégorielles pour nettoyage (title case, rare merge)
CATEGORICAL_CLEAN_COLS = [
    "bien.etat_general",
    "bien.type",
    "bien.usage",
    "contact.type_vendeur",
    "localisation.gouvernorat",
    "localisation.ville",
    "localisation.delegation",
    "localisation.localite",
]

# Colonnes numériques pour imputation médiane (fallback defaults)
DEFAULT_NUMERIC_IMPUTE_COLS = [
    "bien.superficie_totale",
    "bien.nombre_pieces",
    "bien.nombre_chambres",
    "bien.nombre_salles_bain",
    "bien.superficie_habitable",
    "localisation.coordonnees.latitude",
    "localisation.coordonnees.longitude",
]

# Colonnes à exclure des features (metadata, identifiants, target)
DROP_FEATURES = [
    "listing.source",
    "listing.methode_scraping",
    "transaction.type",
]


def load_column_groups(file_path: str = COLUMN_GROUPS_FILE) -> dict:
    """Charge le fichier column_groups.json si présent."""
    path = Path(file_path)
    if not path.exists():
        print(f"[CONFIG] Fichier '{file_path}' introuvable — utilisation des règles par défaut.")

        return {}
    with path.open("r", encoding="utf-8") as f:
        groups = json.load(f)
    print(f"[INFO] Fichier de groupes chargé : '{file_path}'")
    return groups


def compute_iqr_bounds(series: pd.Series,
                       multiplier: float = IQR_MULTIPLIER) -> tuple[float, float]:
    """
    Calcule les bornes de clipping IQR : [Q1 - k*IQR, Q3 + k*IQR].
    Pour les valeurs strictement positives (compteurs de pièces), la borne
    inférieure est plafonnée à 0.
    """
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = max(0.0, q1 - multiplier * iqr)
    upper = q3 + multiplier * iqr
    return lower, upper


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Supprimer colonnes avec ≥80% NULL
# ─────────────────────────────────────────────────────────────────────────────
def remove_high_null_columns(df: pd.DataFrame,
                             threshold: float = 0.80,
                             column_groups: dict | None = None) -> pd.DataFrame:
    """Supprime les colonnes trop incomplètes, en cohérence avec le JSON d'analyse."""
    null_rates = df.isnull().mean()
    cols_by_threshold = null_rates[null_rates >= threshold].index.tolist()

    json_group_cols: list[str] = []
    if column_groups is not None:
        json_group_cols = column_groups.get("high_missing_ge80", [])

    cols_to_drop = list(dict.fromkeys(cols_by_threshold + json_group_cols))
    n_dropped = len(cols_to_drop)
    df_out = df.drop(columns=cols_to_drop, errors="ignore")
    print(f"[STEP 1] Colonnes ≥{threshold*100:.0f}% NULL + groupes JSON supprimées : {n_dropped}")
    print(f"         Colonnes restantes : {df_out.shape[1]}  (shape: {df_out.shape})")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Supprimer colonnes donnees_brutes.*
# ─────────────────────────────────────────────────────────────────────────────
def remove_donnees_brutes_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime toutes les colonnes commençant par 'donnees_brutes.'."""
    cols_to_drop = [c for c in df.columns if c.startswith("donnees_brutes.")]
    df_out = df.drop(columns=cols_to_drop)
    print(f"[STEP 2] Colonnes donnees_brutes.* supprimées : {len(cols_to_drop)}")
    print(f"         Colonnes restantes : {df_out.shape[1]}  (shape: {df_out.shape})")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Supprimer métadonnées scraping non utiles
# ─────────────────────────────────────────────────────────────────────────────
def remove_scraping_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime les colonnes de métadonnées scraping non prédictives."""
    existing = [c for c in SCRAPING_META_DROP if c in df.columns]
    df_out = df.drop(columns=existing)
    print(f"[STEP 3] Métadonnées scraping supprimées : {len(existing)}")
    print(f"         Colonnes restantes : {df_out.shape[1]}  (shape: {df_out.shape})")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Dédupliquer par URL canonique
# ─────────────────────────────────────────────────────────────────────────────
def deduplicate_by_canonical_url(df: pd.DataFrame) -> pd.DataFrame:
    """
    Groupe par listing.url_canonique et conserve le snapshot le plus récent
    (basé sur listing.date_scraping). Supprime ensuite les colonnes d'identifiants.
    """
    n_before = len(df)

    url_col  = "listing.url_canonique"
    date_col = "listing.date_scraping"

    if url_col in df.columns and date_col in df.columns:
        df_out = (
            df.sort_values(date_col, ascending=False, na_position="last")
              .drop_duplicates(subset=[url_col], keep="first")
        )
    else:
        print(f"[STEP 4] Colonnes '{url_col}' ou '{date_col}' absentes — pas de dédup.")
        df_out = df.copy()

    existing_ids = [c for c in ID_URL_DROP if c in df_out.columns]
    df_out = df_out.drop(columns=existing_ids)

    n_after = len(df_out)
    print(f"[STEP 4] Déduplication par URL canonique : {n_before:,} → {n_after:,} lignes")
    print(f"         Lignes supprimées (doublons) : {n_before - n_after:,}")
    print(f"         Colonnes id/URL supprimées  : {len(existing_ids)}")
    print(f"         Shape finale : {df_out.shape}")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Nettoyer la variable cible transaction.prix
# ─────────────────────────────────────────────────────────────────────────────
def clean_target_variable(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Convertit en numérique, remplace 'sur demande' → NaN
    - Remplace prix = 0 → NaN
    - Remplace prix > PRIX_MAX_VENTE → NaN  (outliers extrêmes)
    - Applique log1p → colonne prix_log
    - Crée price_bin (quartile du log-prix) pour stratification
    """
    if TARGET_COL not in df.columns:
        print(f"[STEP 5] Colonne '{TARGET_COL}' absente — étape ignorée.")
        return df

    df_out = df.copy()

    # Remplacement des chaînes non numériques
    sur_demande_mask = df_out[TARGET_COL].astype(str).str.lower().str.strip() == "sur demande"
    df_out.loc[sur_demande_mask, TARGET_COL] = np.nan

    # Conversion numérique
    df_out[TARGET_COL] = pd.to_numeric(df_out[TARGET_COL], errors="coerce")

    # Statistiques AVANT
    valid_before = df_out[TARGET_COL].dropna()
    print(f"[STEP 5] Avant nettoyage :")
    print(f"         n valide     : {len(valid_before):,}")
    print(f"         médiane      : {valid_before.median():,.0f} TND")
    print(f"         moyenne      : {valid_before.mean():,.0f} TND")
    print(f"         skewness     : {stats.skew(valid_before):.2f}")
   

    # Prix = 0 → NaN
    zero_mask = df_out[TARGET_COL] == 0
    df_out.loc[zero_mask, TARGET_COL] = np.nan

    # Outliers extrêmes (vente) → NaN
    outlier_mask = df_out[TARGET_COL] > PRIX_MAX_VENTE
    df_out.loc[outlier_mask, TARGET_COL] = np.nan

    # Transformation log1p
    df_out["prix_log"] = np.log1p(df_out[TARGET_COL].fillna(0))
    df_out.loc[df_out[TARGET_COL].isna(), "prix_log"] = np.nan

    # Quartiles du log-prix pour stratification (price_bin)
    valid_log = df_out["prix_log"].dropna()
    if len(valid_log) > 0:
        df_out["price_bin"] = pd.qcut(
            valid_log, 
            q=4,
            labels=["Q1", "Q2", "Q3", "Q4"],
            duplicates="drop",
        ).reindex(df_out.index)
        bin_counts = df_out["price_bin"].value_counts().sort_index()
        print(f"price_bin créé : {dict(bin_counts)}")
    else:
        df_out["price_bin"] = np.nan
        print(f"[STEP 5] price_bin non créé (aucune valeur cible valide).")

    # Statistiques APRÈS
    valid_after = df_out[TARGET_COL].dropna()
    print(f"[STEP 5] Après nettoyage (sur demande={sur_demande_mask.sum()}, "
              f"zéros={zero_mask.sum()}, outliers={outlier_mask.sum()}) :")
    print(f"         n valide     : {len(valid_after):,}")
    print(f"         médiane      : {valid_after.median():,.0f} TND")
    print(f"         moyenne      : {valid_after.mean():,.0f} TND")
    print(f"         skewness     : {stats.skew(valid_after.dropna()):.2f}")

    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Corriger valeurs négatives et clipper avec IQR
# ─────────────────────────────────────────────────────────────────────────────
def fix_room_counts_iqr_clip(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Remplace les valeurs négatives dans les colonnes de comptage par NaN.
    - Clippe les outliers avec la méthode IQR : Q3 + k×IQR (k=3 par défaut).
      Remplace les valeurs au-dessus de la borne supérieure par NaN.
    """
    df_out = df.copy()
    room_cols = [
        "bien.nombre_pieces",
        "bien.nombre_chambres",
        "bien.nombre_salles_bain",
    ]

    for col in room_cols:
        if col not in df_out.columns:
            continue

        col_num = pd.to_numeric(df_out[col], errors="coerce")

        # Valeurs négatives → NaN
        neg_mask = col_num < 0
        n_neg = neg_mask.sum()
        col_num.loc[neg_mask] = np.nan

        # Clipping IQR
        valid = col_num.dropna()
        if len(valid) == 0:
            df_out[col] = col_num
            continue

        lower, upper = compute_iqr_bounds(valid, multiplier=IQR_MULTIPLIER)
        clip_mask = col_num > upper
        n_clip = clip_mask.sum()
        col_num.loc[clip_mask] = np.nan

        df_out[col] = col_num

        if n_neg > 0 or n_clip > 0:
            print(f"{col}: {n_neg} négatives → NaN, "
                     f"{n_clip} >borne IQR ({upper:.0f}) → NaN")

    print(f"[STEP 6] Correction IQR terminée. Shape: {df_out.shape}")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Filtrer par type de transaction (vente / location)
# ─────────────────────────────────────────────────────────────────────────────
def filter_by_transaction_type(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Sépare le dataset en deux sous-ensembles :
      - df_vente    : transaction.type == 'vente'
      - df_location : transaction.type == 'location'
    Retourne un tuple (df_vente, df_location).
    """
    tx_col = "transaction.type"
    if tx_col not in df.columns:
        print(f"[STEP 7] Colonne '{tx_col}' absente — pas de filtrage.")
        return df.copy(), pd.DataFrame()

    n_total = len(df)
    df_vente    = df[df[tx_col].astype(str).str.lower().str.strip() == "vente"].copy()
    df_location = df[df[tx_col].astype(str).str.lower().str.strip() == "location"].copy()
    n_other     = n_total - len(df_vente) - len(df_location)

    print(f"[STEP 7] Filtrage par type de transaction :")
    print(f"         Total initial : {n_total:,}")
    print(f"         Vente         : {len(df_vente):,} ({len(df_vente)/n_total*100:.1f}%)")
    print(f"         Location      : {len(df_location):,} ({len(df_location)/n_total*100:.1f}%)")
    print(f"         Autres/NaN    : {n_other:,}")
    return df_vente, df_location


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Imputation
# ─────────────────────────────────────────────────────────────────────────────
def impute_features(df: pd.DataFrame,
                    column_groups: dict | None = None,
                    label: str = "vente") -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Impute les features manquantes :
      - Variables numériques → médiane
      - Variables catégorielles → mode
      - Variables équipements binaires → False (0)

    Returns
    -------
    df_out : pd.DataFrame
    imputation_log : dict mapping column → method used
    """
    df_out = df.copy()
    imputation_log: dict[str, str] = {}

    # ── 8a. Imputation numérique (médiane) ────────────────────────────────
    numeric_candidates: list[str] = []
    if column_groups is not None:
        numeric_candidates = [
            c for c in column_groups.get("meaningful_numeric_features", [])
            if c in df_out.columns
        ]
    if not numeric_candidates:
        numeric_candidates = [
            c for c in DEFAULT_NUMERIC_IMPUTE_COLS if c in df_out.columns
        ]

    for col in numeric_candidates:
        col_num = pd.to_numeric(df_out[col], errors="coerce")
        n_missing = col_num.isna().sum()
        if n_missing == 0:
            continue

        valid = col_num.dropna()
        if len(valid) == 0:
            print(f"{col} ({label}): 100% NULL — ignorée.")
            continue

        fill_val = valid.median()
        df_out[col] = col_num.fillna(fill_val)
        imputation_log[col] = f"median={fill_val:.2f}"
        print(f"{col} ({label}): {n_missing:,} NaN → médiane ({fill_val:.2f})")

    # ── 8b. Imputation catégorielle (mode) ────────────────────────────────
    cat_impute = [c for c in CATEGORICAL_IMPUTE_COLS if c in df_out.columns]
    for col in cat_impute:
        n_missing = df_out[col].isna().sum()
        if n_missing == 0:
            continue

        mode_val = df_out[col].mode()
        fill_val = mode_val.iloc[0] if len(mode_val) > 0 else "Inconnu"
        df_out[col] = df_out[col].fillna(fill_val)
        imputation_log[col] = f"mode={fill_val}"
        print(f"{col} ({label}): {n_missing:,} NaN → mode ('{fill_val}')")

    # ── 8c. Imputation équipements binaires → False (0) ──────────────────
    equip_cols = [c for c in df_out.columns
                  if c.startswith(EQUIP_PREFIX) and c != "equipements.autres"]

    for col in equip_cols:
        n_missing = df_out[col].isna().sum()
        if n_missing == 0:
            continue

        df_out[col] = df_out[col].fillna(False)
        imputation_log[col] = "binary_false"
        print(f"{col} ({label}): {n_missing:,} NaN → False")

    print(f"[STEP 8] Imputation terminée ({label}) : {len(imputation_log)} colonnes traitées")
    return df_out, imputation_log


# ─────────────────────────────────────────────────────────────────────────────
# STEP 9 — Nettoyage des variables catégorielles (SANS encodage)
# ─────────────────────────────────────────────────────────────────────────────
def clean_categorical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie les colonnes catégorielles sans les encoder :
      - Strip les espaces
      - Title case
      - Fusionne les catégories rares (< RARE_CATEGORY_MIN occurrences) → "Autre"

    L'encodage (TargetEncoder, OneHot) est laissé au pipeline ML pour
    éviter la fuite de données (data leakage).
    """
    df_out = df.copy()
    rare_merge_log: dict[str, int] = {}

    for col in CATEGORICAL_CLEAN_COLS:
        if col not in df_out.columns:
            continue

        # Strip + Title case
        df_out[col] = (
            df_out[col]
            .astype(str)
            .str.strip()
            .str.title()
        )
        # Replace 'Nan' string back to actual NaN
        df_out[col] = df_out[col].replace("Nan", np.nan)

        # Fusion des catégories rares
        value_counts = df_out[col].value_counts(dropna=True)
        rare_categories = value_counts[value_counts < RARE_CATEGORY_MIN].index.tolist()

        if rare_categories:
            n_affected = df_out[col].isin(rare_categories).sum()
            df_out[col] = df_out[col].replace(rare_categories, "Autre")
            rare_merge_log[col] = n_affected
            print(f"{col}: {len(rare_categories)} catégories rares (<{RARE_CATEGORY_MIN}) "
                  f"→ 'Autre' ({n_affected} lignes affectées)")

    print(f"[STEP 9] Nettoyage catégoriel terminé. {len(rare_merge_log)} colonnes avec fusion rare.")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 10 — Feature engineering
# ─────────────────────────────────────────────────────────────────────────────
def feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crée les features dérivées suivantes :
    1. prix_m2_cleaned       = transaction.prix / bien.superficie_totale
                               (capé à PRIX_M2_CAP TND/m²)
    2. log_superficie        = log1p(bien.superficie_totale)
    3. log_nombre_pieces     = log1p(bien.nombre_pieces)
    4. prix_m2_log           = log1p(prix_m2_cleaned) quand valide
    5. nb_equipements        = compte des True parmi les colonnes equipements.*
    6. jours_depuis_publication = listing.date_scraping - listing.date_publication
    7. has_coordinates       = flag binaire si latitude/longitude disponibles
    """
    df_out = df.copy()

    # ── 1. prix_m2_cleaned ──────────────────────────────────────────────────
    prix_num = pd.to_numeric(df_out.get(TARGET_COL, pd.Series(dtype=float)),
                             errors="coerce")
    sup = pd.to_numeric(df_out.get("bien.superficie_totale", pd.Series(dtype=float)),
                        errors="coerce")

    prix_m2 = np.where(
        (prix_num > 0) & (sup > 0),
        prix_num / sup,
        np.nan,
    )
    prix_m2 = np.where(
        np.asarray(prix_m2, dtype=float) > PRIX_M2_CAP,
        np.nan,
        prix_m2,
    )
    df_out["prix_m2_cleaned"] = prix_m2
    n_valid = (~np.isnan(np.asarray(prix_m2, dtype=float))).sum()
    print(f"prix_m2_cleaned créé (n valide={n_valid:,}, cap={PRIX_M2_CAP:,} TND/m²)")

    # ── 2. log_superficie ──────────────────────────────────────────────────
    if "bien.superficie_totale" in df_out.columns:
        sup_num = pd.to_numeric(df_out["bien.superficie_totale"], errors="coerce")
        df_out["log_superficie"] = np.log1p(sup_num.clip(lower=0))
        print("log_superficie créé")

    # ── 3. log_nombre_pieces ────────────────────────────────────────────────
    if "bien.nombre_pieces" in df_out.columns:
        pieces_num = pd.to_numeric(df_out["bien.nombre_pieces"], errors="coerce")
        df_out["log_nombre_pieces"] = np.log1p(pieces_num.clip(lower=0))
        print("log_nombre_pieces créé")

    # ── 4. prix_m2_log ──────────────────────────────────────────────────────
    prix_m2_valid = pd.to_numeric(df_out["prix_m2_cleaned"], errors="coerce")
    df_out["prix_m2_log"] = np.where(
        prix_m2_valid.notna() & (prix_m2_valid > 0),
        np.log1p(prix_m2_valid),
        np.nan,
    )
    n_valid_prix_m2_log = df_out["prix_m2_log"].notna().sum()
    print(f"prix_m2_log créé (n valide={n_valid_prix_m2_log:,})")

    # ── 5. nb_equipements ──────────────────────────────────────────────────
    equip_cols = [c for c in df_out.columns
                  if c.startswith(EQUIP_PREFIX) and c != "equipements.autres"]

    if equip_cols:
        def _is_true(val) -> int:
            if pd.isna(val):
                return 0
            s = str(val).lower().strip()
            return 1 if s in ("1", "true", "oui", "yes", "1.0") else 0

        try:
            equip_matrix = df_out[equip_cols].map(_is_true)
        except AttributeError:
            equip_matrix = df_out[equip_cols].applymap(_is_true)
        df_out["nb_equipements"] = equip_matrix.sum(axis=1)
        print(f"nb_equipements créé ({len(equip_cols)} colonnes équipements)")
    else:
        df_out["nb_equipements"] = 0
        print("nb_equipements = 0 (aucune colonne equipements.* trouvée)")

    # ── 6. jours_depuis_publication ────────────────────────────────────────
    pub_col   = "listing.date_publication"
    scrap_col = "listing.date_scraping"

    if pub_col in df_out.columns and scrap_col in df_out.columns:
        pub_date   = pd.to_datetime(df_out[pub_col],   errors="coerce", utc=True)
        scrap_date = pd.to_datetime(df_out[scrap_col], errors="coerce", utc=True)
        delta = (scrap_date - pub_date).dt.days
        df_out["jours_depuis_publication"] = delta.clip(lower=0)
        n_valid_days = delta.notna().sum()
        print(f"jours_depuis_publication créé (n valide={n_valid_days:,})")
    else:
        df_out["jours_depuis_publication"] = np.nan
        print("jours_depuis_publication = NaN (colonnes date absentes)")

    # ── 7. has_coordinates ────────────────────────────────────────────────
    lat_col = "localisation.coordonnees.latitude"
    lon_col = "localisation.coordonnees.longitude"

    if lat_col in df_out.columns and lon_col in df_out.columns:
        lat_num = pd.to_numeric(df_out[lat_col], errors="coerce")
        lon_num = pd.to_numeric(df_out[lon_col], errors="coerce")
        df_out["has_coordinates"] = (lat_num.notna() & lon_num.notna()).astype(int)
        n_with = int(df_out["has_coordinates"].sum())
        print(f"has_coordinates créé (n avec coordonnées={n_with:,})")
    else:
        df_out["has_coordinates"] = 0
        print("has_coordinates = 0 (colonnes coordonnées absentes)")

    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE METADATA EXPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_feature_metadata(df: pd.DataFrame,
                           imputation_log: dict[str, str]) -> dict[str, Any]:
    """
    Construit le dictionnaire de métadonnées des features pour le pipeline ML.

    Identifie automatiquement les groupes de colonnes :
      - numeric_features : colonnes numériques (excluant target et derived)
      - categorical_features : colonnes catégorielles avec cardinalité
      - binary_features : colonnes équipements (bool/binary)
      - derived_features : colonnes créées par le feature engineering
      - drop_features : colonnes à exclure du ML
    """
    all_cols = list(df.columns)

    # Derived features (created by this pipeline)
    derived_set = {
        "prix_log",
        "price_bin",
        "prix_m2_cleaned",
        "log_superficie",
        "log_nombre_pieces",
        "prix_m2_log",
        "nb_equipements",
        "jours_depuis_publication",
        "has_coordinates",
    }
    derived_features = sorted(derived_set & set(all_cols))

    # Target columns
    target_set = {TARGET_COL, "prix_log", "price_bin"}

    # Drop features (non-predictive)
    drop_set = set(DROP_FEATURES) & set(all_cols)

    # Binary equipment columns
    binary_features = sorted([
        c for c in all_cols
        if c.startswith(EQUIP_PREFIX) and c != "equipements.autres"
    ])

    # Categorical columns (exclude target, binary, derived, drop)
    exclude = target_set | set(binary_features) | derived_set | drop_set
    categorical_features = []
    categorical_cardinality: dict[str, int] = {}

    for col in all_cols:
        if col in exclude:
            continue
        if df[col].dtype in ("object", "category") or df[col].dtype.name == "string":
            n_unique = int(df[col].nunique(dropna=True))
            categorical_features.append(col)
            categorical_cardinality[col] = n_unique

    # Numeric columns (float/int, not in binary/target/derived/drop)
    numeric_features = []
    for col in all_cols:
        if col in exclude or col in set(categorical_features) or col in set(binary_features):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_features.append(col)

    # Statistics
    prix = pd.to_numeric(df[TARGET_COL], errors="coerce").dropna() if TARGET_COL in df.columns else pd.Series(dtype=float)
    statistics: dict[str, Any] = {}
    if len(prix) > 0:
        statistics = {
            "target_n_valid": int(len(prix)),
            "target_median": round(float(prix.median()), 2),
            "target_mean": round(float(prix.mean()), 2),
            "target_std": round(float(prix.std()), 2),
            "target_skewness": round(float(stats.skew(prix)), 4),
            "target_min": round(float(prix.min()), 2),
            "target_max": round(float(prix.max()), 2),
            "target_q25": round(float(prix.quantile(0.25)), 2),
            "target_q75": round(float(prix.quantile(0.75)), 2),
        }

    metadata = {
        "target": "prix_log",
        "target_raw": TARGET_COL,
        "target_log": "prix_log",
        "price_bin": "price_bin",
        "numeric_features": sorted(numeric_features),
        "categorical_features": sorted(categorical_features),
        "categorical_cardinality": categorical_cardinality,
        "binary_features": binary_features,
        "derived_features": derived_features,
        "drop_features": sorted(drop_set),
        "n_samples": len(df),
        "n_features": len(all_cols),
        "statistics": statistics,
        "imputation_log": imputation_log,
        "generated_at": datetime.now().isoformat(),
        "pipeline_version": "2.0",
    }

    return metadata


def save_feature_metadata(metadata: dict[str, Any],
                          file_path: str = METADATA_FILE) -> None:
    """Sauvegarde les métadonnées au format JSON."""
    path = Path(file_path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
    print("Métadonnées features sauvegardées : '%s' (%.1f KB)",
                file_path, path.stat().st_size / 1024)


# ─────────────────────────────────────────────────────────────────────────────
# RÉSUMÉ FINAL
# ─────────────────────────────────────────────────────────────────────────────
def print_final_summary(df_original: pd.DataFrame,
                        df_vente: pd.DataFrame,
                        df_location: pd.DataFrame) -> None:
    """Affiche un résumé complet du pipeline."""
    print("\n" + "=" * 70)
    print("  RÉSUMÉ FINAL DU PIPELINE (v2 — ML-compatible)")
    print("=" * 70)

    print(f"\n  Shape originale        : {df_original.shape}")
    print(f"  Shape vente nettoyée   : {df_vente.shape}")
    print(f"  Shape location         : {df_location.shape}")

    n_dropped_cols = df_original.shape[1] - df_vente.shape[1]
    print(f"\n  Colonnes supprimées    : {n_dropped_cols}")
    print(f"  Colonnes conservées    : {df_vente.shape[1]}")
    print(f"  Lignes supprimées total: {df_original.shape[0] - len(df_vente) - len(df_location):,}")

    print(f"\n  Lignes vente           : {len(df_vente):,}")
    print(f"  Lignes location        : {len(df_location):,}")

    # Stats de la variable cible (vente)
    if TARGET_COL in df_vente.columns:
        prix = pd.to_numeric(df_vente[TARGET_COL], errors="coerce").dropna()
        if len(prix) > 0:
            print(f"\n  Variable cible ({TARGET_COL}) — vente :")
            print(f"    n valide  : {len(prix):,}")
            print(f"    médiane   : {prix.median():,.0f} TND")
            print(f"    moyenne   : {prix.mean():,.0f} TND")
            print(f"    skewness  : {stats.skew(prix):.2f}")

    # Mémoire
    mem_orig = df_original.memory_usage(deep=True).sum() / 1e6
    mem_vente = df_vente.memory_usage(deep=True).sum() / 1e6
    print(f"\n  Mémoire originale      : {mem_orig:.1f} MB")
    print(f"  Mémoire vente nettoyée : {mem_vente:.1f} MB")
    if mem_orig > 0:
        print(f"  Réduction mémoire      : {(1 - mem_vente/mem_orig)*100:.1f}%")

    # Feature groups summary
    n_numeric = len([c for c in df_vente.columns if pd.api.types.is_numeric_dtype(df_vente[c])])
    n_categorical = len(df_vente.select_dtypes(include=["object", "category"]).columns)
    print(f"\n  Colonnes numériques    : {n_numeric}")
    print(f"  Colonnes catégorielles: {n_categorical}")

    print("\n  ⚠️  Encodage catégoriel laissé au pipeline ML (pas de fuite de données)")
    print("  ⚠️  OutlierClipper, RareCategoryMerger à appliquer dans le pipeline ML")
    print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — bloc d'exécution principal
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    
    print("  PIPELINE NETTOYAGE & FEATURE ENGINEERING v2")
    print("  Dataset immobilier tunisien (ML-compatible)")
    

    # ── Chargement ──────────────────────────────────────────────────────────
    print("Chargement de '%s'...", INPUT_FILE)
    try:
        df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig", low_memory=False)
    except FileNotFoundError:
        print(f"Erreur : Fichier '%s' introuvable. Vérifiez le chemin.", INPUT_FILE)
        raise SystemExit(1)

    df_original = df.copy()   # conservation pour résumé final
    print("Dataset chargé : %s lignes × %s colonnes", df.shape[0], df.shape[1])

    column_groups = load_column_groups()

    # ── STEP 1 : suppression colonnes ≥80% NULL ─────────────────────────────
    df = remove_high_null_columns(df, threshold=0.80, column_groups=column_groups)

    # ── STEP 2 : suppression donnees_brutes.* ───────────────────────────────
    df = remove_donnees_brutes_columns(df)

    # ── STEP 3 : suppression métadonnées scraping ───────────────────────────
    df = remove_scraping_metadata(df)

    # ── STEP 4 : déduplication par URL canonique ────────────────────────────
    df = deduplicate_by_canonical_url(df)

    # ── STEP 5 : nettoyage variable cible + price_bin ───────────────────────
    df = clean_target_variable(df)

    # ── STEP 6 : correction IQR (remplace P99 capping) ─────────────────────
    df = fix_room_counts_iqr_clip(df)

    # ── STEP 7 : séparation vente / location ────────────────────────────────
    df_vente, df_location = filter_by_transaction_type(df)

    # ── STEP 8 : imputation (vente) ────────────────────────────────────────
    df_vente, impute_log_vente = impute_features(
        df_vente, column_groups=column_groups, label="vente"
    )

    # ── STEP 8b : imputation (location) ────────────────────────────────────
    if len(df_location) > 0:
        df_location, impute_log_location = impute_features(
            df_location, column_groups=column_groups, label="location"
        )

    # ── STEP 9 : nettoyage catégoriel SANS encodage ────────────────────────
    df_vente = clean_categorical_features(df_vente)
    if len(df_location) > 0:
        df_location = clean_categorical_features(df_location)

    # ── STEP 10 : feature engineering (vente) ────────────────────────────────
    print("Feature engineering (vente) :")
    df_vente = feature_engineering(df_vente)

    # ── STEP 10b : feature engineering (location) ───────────────────────────
    if len(df_location) > 0:
        print("Feature engineering (location) :")
        df_location = feature_engineering(df_location)

    # ── Export métadonnées features ─────────────────────────────────────────
    metadata = build_feature_metadata(df_vente, impute_log_vente)
    save_feature_metadata(metadata, METADATA_FILE)

    # ── Sauvegarde CSV ──────────────────────────────────────────────────────
    df_vente.to_csv(OUTPUT_FILE_VENTE, index=False, encoding="utf-8-sig")
    print("Fichier vente sauvegardé : '%s' (%s lignes × %s colonnes)",
          OUTPUT_FILE_VENTE, df_vente.shape[0], df_vente.shape[1])

    if len(df_location) > 0:
        df_location.to_csv(OUTPUT_FILE_LOCATION, index=False, encoding="utf-8-sig")
        print("Fichier location sauvegardé : '%s' (%s lignes × %s colonnes)",
              OUTPUT_FILE_LOCATION, df_location.shape[0], df_location.shape[1])

    # ── Résumé final ────────────────────────────────────────────────────────
    print_final_summary(df_original, df_vente, df_location)
