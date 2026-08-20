#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_data_feature_engineering.py
==================================
Unified Single-Model Pipeline for VENTE and LOCATION.

Input  : merged_all.csv
Output : cleaned_unified.csv
         feature_metadata.json
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
INPUT_FILE           = "raw_data.csv"
OUTPUT_FILE_UNIFIED  = "cleaned_unified.csv"
METADATA_FILE        = "feature_metadata.json"
COLUMN_GROUPS_FILE   = "column_groups.json"

RARE_CATEGORY_MIN    = 30

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

ID_URL_DROP = [
    "listing.id_universel",
    "listing.url_canonique",
    "listing.url_source",
    # "listing.id_source", # Kept for vectorization
]

EQUIP_PREFIX = "equipements."

CATEGORICAL_IMPUTE_COLS = [
    "bien.etat_general",
    "bien.type",
    "bien.usage",
]

CATEGORICAL_CLEAN_COLS = [
    "bien.etat_general",
    "bien.type",
    "bien.usage",
    "localisation.gouvernorat",
    "localisation.ville",
    "localisation.delegation",
    "localisation.localite",
]

DEFAULT_NUMERIC_IMPUTE_COLS = [
    "bien.nombre_pieces",
    "bien.nombre_chambres",
    "bien.nombre_salles_bain",
    "localisation.coordonnees.latitude",
    "localisation.coordonnees.longitude",
]

# Columns to drop during feature engineering (leakage, text, metadata, IDs)
DROP_FEATURES = [
    "listing.source",
    "listing.methode_scraping",
    "listing.date_scraping",
    "listing.date_publication",
    "listing.date_maj",
    "listing.statut",
    "listing.langue",
    "transaction.type",
    "transaction.devise",
    "transaction.prix_m2",
    "transaction.prix",
    "transaction.loyer_mensuel",
    "medias.nombre_photos",
    "medias.photos",
    "medias.videos",
    "medias.plans",
    "contact.type_vendeur",
    "contact.nom_vendeur",
    "contact.nom_agence",
    "contact.telephone",
    "contact.email",
    "is_agence",
    # "price_or_rent", # Kept for vectorization
    "prix_per_m2",
    # "description.titre", # Kept for vectorization
    # "description.texte", # Kept for vectorization
    "description.points_forts",
    "localisation.pays",
    "localisation.pays_code",
    "localisation.adresse",
    "localisation.proximites",
    "localisation.localite",
    "bien.usage",
    "bien.etage",
    "metadonnees_scraping.source",
    "metadonnees_scraping.methode",
    "metadonnees_scraping.statut_scraping",
    "scoring_ia.alertes",
    "equipements.autres",
]


def load_column_groups(file_path: str = COLUMN_GROUPS_FILE) -> dict:
    path = Path(file_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def remove_high_null_columns(df: pd.DataFrame, threshold: float = 0.80, column_groups: dict | None = None) -> pd.DataFrame:
    null_rates = df.isnull().mean()
    cols_by_threshold = null_rates[null_rates >= threshold].index.tolist()
    json_group_cols = column_groups.get("high_missing_ge80", []) if column_groups else []
    cols_to_drop = list(dict.fromkeys(cols_by_threshold + json_group_cols))
    
    # Don't drop these yet, we need them for unified target
    for c in ["transaction.loyer_mensuel", "transaction.prix"]:
        if c in cols_to_drop:
            cols_to_drop.remove(c)
            
    df_out = df.drop(columns=cols_to_drop, errors="ignore")
    print(f"[STEP 1] Colonnes supprimées (>=80% NULL): {len(cols_to_drop)}")
    return df_out


def deduplicate_and_clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    cols_to_drop = [c for c in df_out.columns if c.startswith("donnees_brutes.")]
    df_out = df_out.drop(columns=cols_to_drop)
    
    existing_meta = [c for c in SCRAPING_META_DROP if c in df_out.columns]
    df_out = df_out.drop(columns=existing_meta)
    
    date_col = "listing.date_scraping"
    url_col = "listing.url_canonique"
    if url_col in df_out.columns and date_col in df_out.columns:
        df_out = df_out.sort_values(date_col, ascending=False, na_position="last").drop_duplicates(subset=[url_col], keep="first")
        
    existing_ids = [c for c in ID_URL_DROP if c in df_out.columns]
    df_out = df_out.drop(columns=existing_ids)
    
    print(f"[STEP 2-4] Deduplication et nettoyage. Shape: {df_out.shape}")
    return df_out


def recover_location_and_property_features(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    for col in ["localisation.gouvernorat", "localisation.delegation", "localisation.ville"]:
        if col in df_out.columns:
            df_out[col] = df_out[col].astype(str).str.strip().str.title().replace("Nan", np.nan)
    
    if "localisation.gouvernorat" in df_out.columns:
        spell_map = {"Ben Arous": "Ben Arous", "La Manouba": "Manouba", "Beja": "Beja", "Gabes": "Gabes", "Medenine": "Medenine", "Sfax": "Sfax", "Ben arous": "Ben Arous", "sfax": "Sfax"}
        df_out["localisation.gouvernorat"] = df_out["localisation.gouvernorat"].replace(spell_map)
    
    for col in ["localisation.ville", "localisation.delegation"]:
        if col in df_out.columns:
            mask = df_out[col].notna() & df_out[col].astype(str).str.contains(" - ")
            if mask.sum() > 0:
                splits = df_out.loc[mask, col].str.split(" - ", n=1, expand=True)
                if col == "localisation.ville":
                    df_out.loc[mask, "localisation.delegation"] = splits[0].str.strip()
                df_out.loc[mask, col] = splits[1].str.strip()

    if "localisation.delegation" in df_out.columns and "localisation.gouvernorat" in df_out.columns:
        valid_map = df_out.dropna(subset=["localisation.delegation", "localisation.gouvernorat"])
        if not valid_map.empty:
            del_gov_map = valid_map.groupby("localisation.delegation")["localisation.gouvernorat"].apply(
                lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else np.nan
            ).to_dict()
            df_out["localisation.gouvernorat"] = df_out["localisation.gouvernorat"].fillna(
                df_out["localisation.delegation"].map(del_gov_map)
            )
            
    if "localisation.ville" in df_out.columns and "localisation.gouvernorat" in df_out.columns:
        valid_map_ville = df_out.dropna(subset=["localisation.ville", "localisation.gouvernorat"])
        if not valid_map_ville.empty:
            ville_gov_map = valid_map_ville.groupby("localisation.ville")["localisation.gouvernorat"].apply(
                lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else np.nan
            ).to_dict()
            df_out["localisation.gouvernorat"] = df_out["localisation.gouvernorat"].fillna(
                df_out["localisation.ville"].map(ville_gov_map)
            )

    if "localisation.gouvernorat" in df_out.columns:
        df_out["localisation.gouvernorat"] = df_out["localisation.gouvernorat"].fillna("Autres")
    if "localisation.delegation" in df_out.columns:
        df_out["localisation.delegation"] = df_out["localisation.delegation"].fillna("Autres")
    if "localisation.ville" in df_out.columns:
        df_out["localisation.ville"] = df_out["localisation.ville"].fillna("Autres")

    if "bien.type" in df_out.columns:
        df_out["bien.type"] = df_out["bien.type"].replace({"Local Commercial": "Local_commercial", "local commercial": "local_commercial"})
        df_out["bien.type"] = df_out["bien.type"].fillna("appartement")

    print(f"[STEP 4.5] Location & Property Type Recovery terminée. Shape: {df_out.shape}")
    return df_out


def create_unified_target_and_filter(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    
    tx_type = df_out["transaction.type"].astype(str).str.lower().str.strip()
    df_out["is_vente"] = (tx_type == "vente").astype(int)
    
    prix = pd.to_numeric(df_out.get("transaction.prix"), errors="coerce")
    loyer = pd.to_numeric(df_out.get("transaction.loyer_mensuel"), errors="coerce")
    
    df_out["price_or_rent"] = np.where(df_out["is_vente"] == 1, prix, loyer)
    
    # Filter non-positive
    df_out = df_out[df_out["price_or_rent"] > 0]
    
    # Impute surface with stronger hierarchical strategy: given surface missing,
    # use median by (type, ville) -> median by type -> sensible defaults.
    sup = pd.to_numeric(df_out.get("bien.superficie_totale"), errors="coerce")
    pieces = pd.to_numeric(df_out.get("bien.nombre_pieces"), errors="coerce")
    btype = df_out.get("bien.type", pd.Series("")).astype(str).str.lower()

    # Group medians
    grp_median = None
    try:
        grp_median = df_out.groupby(["bien.type", "localisation.ville"])['bien.superficie_totale'].median()
    except Exception:
        grp_median = None

    type_median = df_out.groupby("bien.type")['bien.superficie_totale'].median().to_dict() if 'bien.type' in df_out.columns else {}
    global_median = np.nanmedian(sup.dropna()) if sup.dropna().size > 0 else 100.0

    def impute_surface_row(idx, s, p, t, ville):
        if s is not None and not pd.isna(s) and s > 0:
            return float(s)
        # try group median
        if grp_median is not None:
            try:
                gm = grp_median.get((t, ville), np.nan)
                if not pd.isna(gm):
                    return float(gm)
            except Exception:
                pass
        # try type median
        if t in type_median and not pd.isna(type_median[t]):
            return float(type_median[t])
        # fallback to simple heuristics from pieces
        if not pd.isna(p):
            if p == 1: return 35.0
            if p == 2: return 55.0
            if p == 3: return 75.0
            if p >= 4: return 100.0
        # final fallback
        return float(global_median)

    villes = df_out.get('localisation.ville', pd.Series([np.nan]*len(df_out))).astype(str).str.title().replace('Nan', np.nan)
    sup_imputed = [impute_surface_row(i, s, p, t, v) for i, (s, p, t, v) in enumerate(zip(sup, pieces, btype, villes))]
    df_out["bien.superficie_totale"] = sup_imputed

    # Clip unrealistic surfaces
    df_out["bien.superficie_totale"] = pd.to_numeric(df_out["bien.superficie_totale"], errors='coerce').clip(lower=10, upper=2000)

    # Filter null surface
    df_out = df_out[df_out["bien.superficie_totale"].notna() & (df_out["bien.superficie_totale"] > 0)]
    
    # Filter Price bounds
    vente_mask = df_out["is_vente"] == 1
    loc_mask = df_out["is_vente"] == 0
    
    # Vente bounds
    valid_vente = (df_out["price_or_rent"] >= 5000) & (df_out["price_or_rent"] <= 10000000) & (df_out["price_or_rent"] != 6500000)
    
    # Location bounds
    valid_loc = (df_out["price_or_rent"] <= 100000) & (df_out["price_or_rent"] != 5350000)
    
    df_out = df_out[(vente_mask & valid_vente) | (loc_mask & valid_loc)]
    
    # Calculate price per m2 (computed canonical label)
    df_out["prix_per_m2"] = df_out["price_or_rent"] / df_out["bien.superficie_totale"]

    # Detect possible unit-scale errors: extremely large prix_per_m2 may indicate
    # prices recorded in millimes or another unit. Try rescaling by 1/1000 when that
    # brings the price/m2 into a reasonable range.
    high_pm2_mask = df_out["prix_per_m2"] > 100_000
    if high_pm2_mask.any():
        n_high = int(high_pm2_mask.sum())
        print(f"[SCALE_FIX] Detected {n_high} rows with prix_per_m2 > 100k. Attempting /1000 rescale on those rows.")
        candidate = (df_out.loc[high_pm2_mask, "price_or_rent"] / 1000.0) / df_out.loc[high_pm2_mask, "bien.superficie_totale"]
        accept_mask = candidate < 50_000
        if accept_mask.any():
            idxs = df_out.loc[high_pm2_mask].index[accept_mask.values]
            df_out.loc[idxs, "price_or_rent"] = df_out.loc[idxs, "price_or_rent"] / 1000.0
            df_out.loc[idxs, "prix_per_m2"] = df_out.loc[idxs, "price_or_rent"] / df_out.loc[idxs, "bien.superficie_totale"]
            print(f"[SCALE_FIX] Rescaled {len(idxs)} rows by /1000 to correct unit mismatch.")

    # If transaction.prix_m2 exists, compare and flag conflicts (mixed-label issue)
    if 'transaction.prix_m2' in df_out.columns:
        trans_pm2 = pd.to_numeric(df_out.get('transaction.prix_m2'), errors='coerce')
        # relative diff
        rel_diff = np.abs(trans_pm2 - df_out['prix_per_m2']) / np.maximum(df_out['prix_per_m2'], 1)
        df_out['label_conflict'] = rel_diff > 0.20
        nconf = int(df_out['label_conflict'].sum())
        if nconf > 0:
            print(f"[LABEL] Detected {nconf} rows with >20% conflict between reported and computed prix/m2 — removing these rows to ensure label consistency")
            df_out = df_out[~df_out['label_conflict']]

    # Robust winsorization using median ± k*MAD per segment
    def robust_winsorize(series, k=4.0):
        s = series.dropna()
        if s.empty:
            return series
        med = float(np.median(s))
        mad = float(np.median(np.abs(s - med)))
        # scale MAD to approximate std (1.4826) then compute bounds
        if mad == 0:
            lower = s.quantile(0.01)
            upper = s.quantile(0.99)
        else:
            sigma = mad * 1.4826
            lower = med - k * sigma
            upper = med + k * sigma
        # ensure reasonable lower bound > 0 for prices
        lower = max(lower, 0)
        return series.clip(lower=lower, upper=upper)

    df_out.loc[vente_mask, 'prix_per_m2'] = robust_winsorize(df_out.loc[vente_mask, 'prix_per_m2'])
    df_out.loc[loc_mask, 'prix_per_m2']   = robust_winsorize(df_out.loc[loc_mask, 'prix_per_m2'])

    # Clip extreme surfaces per-segment as well
    df_out.loc[vente_mask, 'bien.superficie_totale'] = robust_winsorize(df_out.loc[vente_mask, 'bien.superficie_totale'], k=6.0)
    df_out.loc[loc_mask,   'bien.superficie_totale'] = robust_winsorize(df_out.loc[loc_mask,   'bien.superficie_totale'], k=6.0)

    # Log target
    df_out['prix_per_m2_log'] = np.log1p(df_out['prix_per_m2'].clip(lower=0))
    
    print(f"[STEP 5-8] Target variable + filtering + winsorization. Shape: {df_out.shape}")
    return df_out


def impute_features(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    
    for col in DEFAULT_NUMERIC_IMPUTE_COLS:
        if col in df_out.columns:
            col_num = pd.to_numeric(df_out[col], errors="coerce")
            if col_num.notna().sum() > 0:
                df_out[col] = col_num.fillna(col_num.median())
                
    for col in CATEGORICAL_IMPUTE_COLS:
        if col in df_out.columns and df_out[col].notna().sum() > 0:
            df_out[col] = df_out[col].fillna(df_out[col].mode().iloc[0])
            
    equip_cols = [c for c in df_out.columns if c.startswith(EQUIP_PREFIX)]
    for col in equip_cols:
        df_out[col] = df_out[col].fillna(False)
        
    return df_out


def clean_categorical_features(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    for col in CATEGORICAL_CLEAN_COLS:
        if col in df_out.columns:
            df_out[col] = df_out[col].astype(str).str.strip().str.title().replace("Nan", np.nan)
            value_counts = df_out[col].value_counts(dropna=True)
            rare = value_counts[value_counts < RARE_CATEGORY_MIN].index.tolist()
            if rare:
                df_out[col] = df_out[col].replace(rare, "Autres")
    return df_out


def feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    
    df_out["log_superficie"] = np.log1p(pd.to_numeric(df_out["bien.superficie_totale"], errors="coerce").clip(lower=0))
    if "bien.nombre_pieces" in df_out.columns:
        df_out["log_nombre_pieces"] = np.log1p(pd.to_numeric(df_out["bien.nombre_pieces"], errors="coerce").clip(lower=0))
        
    equip_cols = [c for c in df_out.columns if c.startswith(EQUIP_PREFIX) and c != "equipements.autres"]
    if equip_cols:
        def _is_true(val):
            if pd.isna(val): return 0
            return 1 if str(val).lower().strip() in ("1", "true", "oui", "yes", "1.0") else 0
        try:
            df_out["nb_equipements"] = df_out[equip_cols].map(_is_true).sum(axis=1)
        except AttributeError:
            df_out["nb_equipements"] = df_out[equip_cols].applymap(_is_true).sum(axis=1)
    else:
        df_out["nb_equipements"] = 0
        
    if "listing.date_publication" in df_out.columns and "listing.date_scraping" in df_out.columns:
        pub = pd.to_datetime(df_out["listing.date_publication"], errors="coerce", utc=True)
        scrap = pd.to_datetime(df_out["listing.date_scraping"], errors="coerce", utc=True)
        df_out["jours_depuis_publication"] = (scrap - pub).dt.days.clip(lower=0).fillna(0)
    else:
        df_out["jours_depuis_publication"] = 0
        
    if "localisation.coordonnees.latitude" in df_out.columns and "localisation.coordonnees.longitude" in df_out.columns:
        lat = pd.to_numeric(df_out["localisation.coordonnees.latitude"], errors="coerce")
        lon = pd.to_numeric(df_out["localisation.coordonnees.longitude"], errors="coerce")
        df_out["has_coordinates"] = (lat.notna() & lon.notna()).astype(int)
    else:
        df_out["has_coordinates"] = 0

    if "localisation.gouvernorat" in df_out.columns:
        coastal = ["Tunis", "Nabeul", "Sousse", "Monastir", "Ben Arous"]
        df_out["coastal_premium"] = df_out["localisation.gouvernorat"].astype(str).str.title().isin(coastal).astype(int)
        
    if "bien.superficie_totale" in df_out.columns:
        # Discretize surface into quantiles
        sup_valid = df_out["bien.superficie_totale"].dropna()
        if len(sup_valid) > 0:
            df_out["size_category"] = pd.qcut(sup_valid, q=5, labels=False, duplicates="drop").fillna(-1).astype(int)
            
    # Drop columns that cause leakage or bias
    drop_cols = [c for c in DROP_FEATURES if c in df_out.columns]
    df_out = df_out.drop(columns=drop_cols)
    
    print(f"[STEP 9-10] Feature engineering terminée. Shape: {df_out.shape}")
    return df_out


def build_feature_metadata(df: pd.DataFrame) -> dict:
    all_cols = list(df.columns)
    
    target = "prix_per_m2_log"
    binary_features = [c for c in all_cols if c.startswith(EQUIP_PREFIX)] + ["is_vente", "has_coordinates", "coastal_premium"]
    categorical_features = []
    categorical_cardinality = {}
    
    ignore_for_modeling = ["listing.id_source", "description.texte", "description.titre", "price_or_rent"]
    
    for col in all_cols:
        if col == target or col in binary_features or col in ignore_for_modeling: continue
        if df[col].dtype in ("object", "category") or df[col].dtype.name == "string":
            categorical_features.append(col)
            categorical_cardinality[col] = int(df[col].nunique(dropna=True))
            
    numeric_features = [c for c in all_cols if c != target and c not in binary_features and c not in categorical_features and c not in ignore_for_modeling and pd.api.types.is_numeric_dtype(df[c])]
    
    metadata = {
        "target": target,
        "numeric_features": sorted(numeric_features),
        "categorical_features": sorted(categorical_features),
        "categorical_cardinality": categorical_cardinality,
        "binary_features": sorted(binary_features),
        "n_samples": len(df),
        "n_features": len(all_cols),
        "generated_at": datetime.now().isoformat(),
        "pipeline_version": "3.0_unified",
    }
    return metadata


if __name__ == "__main__":
    print("PIPELINE NETTOYAGE & FEATURE ENGINEERING v3 (Unified Model)")
    try:
        df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig", low_memory=False)
    except FileNotFoundError:
        print(f"Erreur : Fichier '{INPUT_FILE}' introuvable.")
        raise SystemExit(1)
        
    df = remove_high_null_columns(df)
    df = deduplicate_and_clean_columns(df)
    df = recover_location_and_property_features(df)
    df = create_unified_target_and_filter(df)
    df = impute_features(df)
    df = clean_categorical_features(df)
    df = feature_engineering(df)
    
    metadata = build_feature_metadata(df)
    with Path(METADATA_FILE).open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        
    df.to_csv(OUTPUT_FILE_UNIFIED, index=False, encoding="utf-8-sig")
    print(f"Fichier unifié sauvegardé: '{OUTPUT_FILE_UNIFIED}' ({df.shape[0]} lignes × {df.shape[1]} colonnes)")
