"""
test.py - Evaluate unified best_model.joblib on real unseen data from test_data.csv.

When test_data.csv contains listings with real price/rent values,
the script computes full accuracy metrics directly on that data.
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
import argparse
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, median_absolute_error
from sklearn.metrics import confusion_matrix, accuracy_score, classification_report, balanced_accuracy_score

warnings.filterwarnings('ignore')

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from ml_training.data_reconstruction import reconstruct_data

# ============================================================================
# STEP 1 — RAW DATA LOADING WITH COLUMN-SHIFT REPAIR
# ============================================================================

def load_raw_data(test_data_path: str) -> pd.DataFrame:
    df = pd.read_csv(test_data_path, low_memory=False)
    
    # ── Shift B: latitude / longitude swap ───────────────────────────────────
    LAT = 'localisation.coordonnees.latitude'
    LON = 'localisation.coordonnees.longitude'
    if LAT in df.columns and LON in df.columns:
        lat_col = pd.to_numeric(df[LAT], errors='coerce')
        lon_col = pd.to_numeric(df[LON], errors='coerce')
        if lat_col.dropna().lt(20).mean() > 0.7:          # lat < 20 → is actually lon
            df[LAT], df[LON] = lon_col.values, lat_col.values

    return df


# ============================================================================
# STEP 2 — PREPROCESSING (mirror of training pipeline)
# ============================================================================

def compute_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    # is_vente
    tx_type = df.get("transaction.type", pd.Series("vente")).astype(str).str.lower().str.strip()
    df["is_vente"] = (tx_type == "vente").astype(int)

    # Impute surface
    sup = pd.to_numeric(df.get("bien.superficie_totale"), errors="coerce").fillna(0)
    pieces = pd.to_numeric(df.get("bien.nombre_pieces"), errors="coerce")
    btype = df.get("bien.type", pd.Series("")).astype(str).str.lower()
    
    def impute_surface(row, s, p, t):
        if s > 0: return s
        if "villa" in t or "maison" in t: return 180.0
        if pd.isna(p): return np.nan
        if p == 1: return 35.0
        if p == 2: return 55.0
        if p == 3: return 75.0
        if p >= 4: return 100.0
        return np.nan
        
    sup_imputed = [impute_surface(r, s, p, t) for r, s, p, t in zip(df.index, sup, pieces, btype)]
    df["bien.superficie_totale"] = sup_imputed
    
    # Other features
    df['log_superficie'] = np.log1p(pd.to_numeric(df["bien.superficie_totale"], errors="coerce").clip(lower=0))
    if "bien.nombre_pieces" in df.columns:
        df["log_nombre_pieces"] = np.log1p(pd.to_numeric(df["bien.nombre_pieces"], errors="coerce").clip(lower=0))
        
    equip_cols = [c for c in df.columns if c.startswith("equipements.") and c != "equipements.autres"]
    if equip_cols:
        def _is_true(val):
            if pd.isna(val): return 0
            return 1 if str(val).lower().strip() in ("1", "true", "oui", "yes", "1.0") else 0
        df["nb_equipements"] = df[equip_cols].apply(lambda row: row.map(_is_true).sum(), axis=1)
    else:
        df["nb_equipements"] = 0
        
    if "listing.date_publication" in df.columns and "listing.date_scraping" in df.columns:
        pub = pd.to_datetime(df["listing.date_publication"], errors="coerce", utc=True)
        scrap = pd.to_datetime(df["listing.date_scraping"], errors="coerce", utc=True)
        df["jours_depuis_publication"] = (scrap - pub).dt.days.clip(lower=0).fillna(0)
    else:
        df["jours_depuis_publication"] = 0
        
    if "localisation.coordonnees.latitude" in df.columns and "localisation.coordonnees.longitude" in df.columns:
        lat = pd.to_numeric(df["localisation.coordonnees.latitude"], errors="coerce")
        lon = pd.to_numeric(df["localisation.coordonnees.longitude"], errors="coerce")
        df["has_coordinates"] = (lat.notna() & lon.notna()).astype(int)
    else:
        df["has_coordinates"] = 0

    if "localisation.gouvernorat" in df.columns:
        coastal = ["Tunis", "Nabeul", "Sousse", "Monastir", "Ben Arous"]
        df["coastal_premium"] = df["localisation.gouvernorat"].astype(str).str.title().isin(coastal).astype(int)
        
    if "bien.superficie_totale" in df.columns:
        # Discretize surface into quantiles (using fixed bins since we don't have training quantiles saved)
        # Fallback to simple binning based on typical values
        def _get_size_category(x):
            if pd.isna(x): return -1
            if x <= 50: return 0
            if x <= 80: return 1
            if x <= 120: return 2
            if x <= 180: return 3
            return 4
        df["size_category"] = df["bien.superficie_totale"].apply(_get_size_category)
    else:
        df["size_category"] = -1
        
    if "localisation.delegation" not in df.columns:
        df["localisation.delegation"] = "unknown"

    return df


def preprocess_for_inference(df: pd.DataFrame, preprocessor) -> np.ndarray:
    df = reconstruct_data(df)
    df = compute_derived_features(df)
    # Some historical cleaning steps add auxiliary columns (e.g. 'label_conflict')
    # which the saved `preprocessor` expects. Ensure those columns exist with
    # safe defaults before transforming.
    try:
        expected_cols = []
        # Try to read expected feature names from the preprocessor if available
        if hasattr(preprocessor, 'feature_names_in_'):
            expected_cols = list(preprocessor.feature_names_in_)
        elif hasattr(preprocessor, 'get_feature_names_out'):
            try:
                expected_cols = list(preprocessor.get_feature_names_out())
            except Exception:
                expected_cols = []

        # If 'label_conflict' is expected but missing, add it as False
        if 'label_conflict' in expected_cols and 'label_conflict' not in df.columns:
            df['label_conflict'] = False

        # Also ensure any expected columns missing from df are added as NA/0 defaults
        for c in expected_cols:
            if c not in df.columns:
                # boolean-like columns -> False, numeric -> NaN, object -> empty string
                if c.endswith('_flag') or c.startswith('is_') or c in ('label_conflict',):
                    df[c] = 0
                else:
                    df[c] = np.nan

    except Exception:
        # Fail-safe: if introspection fails, at minimum ensure known historical
        # auxiliary columns exist so transform does not error.
        if 'label_conflict' not in df.columns:
            df['label_conflict'] = False

    return preprocessor.transform(df)


# ============================================================================
# STEP 3 — EXTRACT GROUND-TRUTH PRICES (if available)
# ============================================================================

def extract_ground_truth(df_raw: pd.DataFrame):
    df_raw = df_raw.copy()
    tx_type = df_raw.get("transaction.type", pd.Series("vente")).astype(str).str.lower().str.strip()
    is_vente = (tx_type == "vente").astype(int)
    
    prix = pd.to_numeric(df_raw.get("transaction.prix"), errors="coerce")
    loyer = pd.to_numeric(df_raw.get("transaction.loyer_mensuel"), errors="coerce")
    
    prices = np.where(is_vente == 1, prix, loyer)
    
    mask = prices > 0
    
    if mask.sum() == 0:
        return None, None

    return prices, mask


# ============================================================================
# STEP 4 — COMPUTE ACCURACY METRICS
# ============================================================================

def compute_accuracy_metrics(y_true_price: np.ndarray,
                              y_pred_price: np.ndarray,
                              mask: np.ndarray) -> dict:
    yt = y_true_price[mask]
    yp = y_pred_price[mask]

    yt_log = np.log1p(yt)
    yp_log = np.log1p(yp)

    log_err = np.abs(yp_log - yt_log)

    return {
        'n':                    int(mask.sum()),
        'R2':                   r2_score(yt, yp),
        'MAE':                  mean_absolute_error(yt, yp),
        'MedAE':                median_absolute_error(yt, yp),
        'RMSE':                 float(np.sqrt(mean_squared_error(yt, yp))),
        'MAPE':                 float(np.mean(np.abs((yt - yp) / np.maximum(yt, 1))) * 100),
        'within_10pct':         float(np.mean(log_err < 0.10) * 100),
        'within_20pct':         float(np.mean(log_err < 0.20) * 100),
        'within_30pct':         float(np.mean(log_err < 0.30) * 100),
        'within_50pct':         float(np.mean(log_err < 0.50) * 100),
        'within_100pct':        float(np.mean(log_err < 1.00) * 100),
        'overall_accuracy':     float(np.mean(log_err < 0.30) * 100),  # 30 % threshold
    }


def compute_precision_stats(y_true_price: np.ndarray, y_pred_price: np.ndarray, mask: np.ndarray) -> dict:
    """Compute precision-related statistics for absolute errors on the masked set.

    Returns std, coefficient of variation, 2.5/97.5 percentiles, and
    percentages within several relative error thresholds.
    """
    if mask is None or mask.sum() == 0:
        return {}
    yt = y_true_price[mask]
    yp = y_pred_price[mask]
    err = yp - yt
    pct_err = np.abs(err) / np.maximum(yt, 1)

    stats = {
        'std_error': float(np.std(err, ddof=1)),
        'mean_error': float(np.mean(err)),
        'cv_error': float(np.std(err, ddof=1) / max(np.mean(yt), 1)),
        'error_p2_5': float(np.percentile(err, 2.5)),
        'error_p97_5': float(np.percentile(err, 97.5)),
        'within_10pct': float(np.mean(pct_err < 0.10) * 100),
        'within_20pct': float(np.mean(pct_err < 0.20) * 100),
        'within_30pct': float(np.mean(pct_err < 0.30) * 100),
        'within_50pct': float(np.mean(pct_err < 0.50) * 100),
    }
    return stats


# ============================================================================
# STEP 5 — REPORTING
# ============================================================================

def build_results_table(df_raw: pd.DataFrame,
                        y_pred_price: np.ndarray,
                        y_true_price: np.ndarray,
                        mask) -> pd.DataFrame:

    true_col  = np.full(len(df_raw), np.nan)
    error_col = np.full(len(df_raw), np.nan)
    pct_col   = np.full(len(df_raw), np.nan)

    if mask is not None:
        for i in range(len(df_raw)):
            if mask[i] and not np.isnan(y_true_price[i]):
                true_col[i]  = y_true_price[i]
                error_col[i] = y_pred_price[i] - y_true_price[i]
                pct_col[i]   = (y_pred_price[i] - y_true_price[i]) / max(y_true_price[i], 1) * 100

    return pd.DataFrame({
        'id':                  df_raw.get('listing.id_source', pd.Series(range(len(df_raw)))).values,
        'type':                df_raw.get('bien.type',                  pd.Series('N/A')).values,
        'ville':               df_raw.get('localisation.ville',         pd.Series('N/A')).values,
        'surface_m2':          pd.to_numeric(df_raw.get('bien.superficie_totale', pd.Series(np.nan)), errors='coerce').values,
        'true_price_TND':      true_col,
        'predicted_price_TND': y_pred_price,
        'error_TND':           error_col,
        'error_pct':           pct_col,
    })


def compute_error_diagnostics(results: pd.DataFrame) -> dict:
    """Return diagnostics: counts of valid preds, supported/concerning/critical errors, and top worst errors."""
    df = results.copy()
    # valid predictions are those with non-null true price
    valid = df['true_price_TND'].notna()
    n_valid = int(valid.sum())
    n_total = len(df)

    # absolute error and relative pct (already in df)
    df['abs_error'] = df['error_TND'].abs()
    df['rel_error'] = df['error_pct'].abs() / 100.0

    # thresholds: supported <=30%, concerning >30% and <=50%, critical >100% or abs_error very large
    supported_mask = valid & (df['rel_error'] <= 0.30)
    concerning_mask = valid & (df['rel_error'] > 0.30) & (df['rel_error'] <= 0.50)
    critical_mask = valid & ((df['rel_error'] > 1.00) | (df['abs_error'] > 500000))

    supported = int(supported_mask.sum())
    concerning = int(concerning_mask.sum())
    critical = int(critical_mask.sum())

    # top worst absolute errors
    top_worst = df[valid].sort_values('abs_error', ascending=False).head(10)[[
        'id','type','ville','surface_m2','true_price_TND','predicted_price_TND','error_TND','error_pct'
    ]]

    diagnostics = {
        'n_total': n_total,
        'n_valid': n_valid,
        'n_supported': supported,
        'n_concerning': concerning,
        'n_critical': critical,
        'supported_pct': supported / max(n_valid,1) * 100,
        'concerning_pct': concerning / max(n_valid,1) * 100,
        'critical_pct': critical / max(n_valid,1) * 100,
        'top_worst': top_worst,
    }
    return diagnostics


# ---------------------------------------------------------------------------
# Classification helpers: map continuous prices to canonical total-price buckets
# ---------------------------------------------------------------------------
DEFAULT_CLASS_BUCKETS = [
    (0, 200_000, "Budget"),
    (200_000, 600_000, "Mid"),
    (600_000, 1_500_000, "Premium"),
    (1_500_000, float("inf"), "Luxury"),
]


def _price_to_label(price: float, buckets=DEFAULT_CLASS_BUCKETS):
    try:
        v = float(price)
    except Exception:
        return None
    for lo, hi, name in buckets:
        if lo <= v < hi:
            return name
    return None


def compute_classification_from_prices(y_true_price: np.ndarray, y_pred_price: np.ndarray, mask: np.ndarray, buckets=DEFAULT_CLASS_BUCKETS):
    if mask is None or mask.sum() == 0:
        return None
    yt = y_true_price[mask]
    yp = y_pred_price[mask]
    y_true_labels = [_price_to_label(v, buckets) for v in yt]
    y_pred_labels = [_price_to_label(v, buckets) for v in yp]
    # filter pairs where either label is None
    pairs = [(t, p) for t, p in zip(y_true_labels, y_pred_labels) if t is not None and p is not None]
    if not pairs:
        return None
    y_true_f, y_pred_f = zip(*pairs)
    labels = sorted(list(set(y_true_f + y_pred_f)))
    bal = balanced_accuracy_score(y_true_f, y_pred_f)
    rep = classification_report(y_true_f, y_pred_f, labels=labels, zero_division=0)
    return {'balanced_accuracy': bal, 'labels': labels, 'report': rep}


def _parse_numeric_token(tok: str) -> float:
    tok = tok.strip()
    if tok.endswith('+'):
        tok = tok[:-1]
        plus = True
    else:
        plus = False
    mult = 1
    if tok.lower().endswith('k'):
        mult = 1_000
        tok = tok[:-1]
    elif tok.lower().endswith('m'):
        mult = 1_000_000
        tok = tok[:-1]
    try:
        val = float(tok) * mult
    except Exception:
        val = None
    return val, plus


def parse_price_bin_intervals(labels: list) -> dict:
    """Parse textual price_bin labels into (low, high) intervals in TND.
    Returns dict label -> (low, high) where high may be float('inf')."""
    intervals = {}
    for lab in labels:
        if not isinstance(lab, str) or not lab.strip():
            continue
        s = lab.strip()
        if '-' in s:
            a, b = s.split('-', 1)
            a_val, _ = _parse_numeric_token(a)
            b_val, _ = _parse_numeric_token(b)
            if a_val is None or b_val is None:
                continue
            intervals[lab] = (a_val, b_val)
        elif s.endswith('+'):
            v, _ = _parse_numeric_token(s)
            if v is None: continue
            intervals[lab] = (v, float('inf'))
        else:
            # single value fallback
            v, _ = _parse_numeric_token(s)
            if v is None: continue
            intervals[lab] = (v, v)
    return intervals


def assign_predicted_bin(pred_price: float, intervals: dict) -> str:
    for lab, (low, high) in intervals.items():
        if pred_price >= low and pred_price <= high:
            return lab
    # if none matched, try nearest lower bin
    lows = sorted([(low, lab) for lab, (low, _) in intervals.items()])
    for low, lab in reversed(lows):
        if pred_price >= low:
            return lab
    return None


def compute_classification_from_bins(df_raw: pd.DataFrame, results: pd.DataFrame):
    if 'price_bin' not in df_raw.columns:
        return None
    true_bins = df_raw['price_bin'].values
    # collect unique labels from data
    labels = pd.Series(true_bins).dropna().unique().tolist()
    intervals = parse_price_bin_intervals(labels)
    if not intervals:
        return None

    y_true = []
    y_pred = []
    for i in range(len(results)):
        tb = true_bins[i]
        tp = results.loc[i, 'predicted_price_TND']
        if pd.isna(tb) or pd.isna(tp):
            continue
        pred_lab = assign_predicted_bin(float(tp), intervals)
        if pred_lab is None:
            continue
        y_true.append(tb)
        y_pred.append(pred_lab)

    if not y_true:
        return None

    # keep consistent label order
    label_order = sorted(list(set(y_true + y_pred)))
    cm = confusion_matrix(y_true, y_pred, labels=label_order)
    acc = accuracy_score(y_true, y_pred)
    cr = classification_report(y_true, y_pred, labels=label_order, zero_division=0)
    return {'confusion_matrix': cm, 'labels': label_order, 'accuracy': acc, 'report': cr}


def print_simple_summary(data_label: str,
                         diagnostics: dict,
                         live_metrics: dict,
                         precision_stats: dict):
    """Print a concise, human-readable summary of key metrics to the terminal."""
    print("\n" + "="*60)
    print(f"SIMPLE SUMMARY — {data_label}")
    print("="*60)

    print(f"Total rows: {diagnostics.get('n_total')}")
    print(f"Valid rows (with ground truth): {diagnostics.get('n_valid')}")

    if live_metrics:
        print(f"R2: {live_metrics.get('R2'):.4f}   MAE: {int(live_metrics.get('MAE')):,} TND   RMSE: {int(live_metrics.get('RMSE')):,} TND")
        print(f"MAPE: {live_metrics.get('MAPE'):.1f}%   Overall accuracy (within 30%): {live_metrics.get('overall_accuracy'):.1f}%")

    if precision_stats:
        print(f"Std error: {int(precision_stats.get('std_error',0)):,} TND   Mean error: {int(precision_stats.get('mean_error',0)):+,} TND")

    print(f"Supported (<=30%): {diagnostics.get('n_supported')} ({diagnostics.get('supported_pct'):.1f}%) | Concerning (30-50%): {diagnostics.get('n_concerning')} ({diagnostics.get('concerning_pct'):.1f}%) | Critical: {diagnostics.get('n_critical')} ({diagnostics.get('critical_pct'):.1f}%)")

    # compact list of worst IDs (id:error_tnd:error_pct)
    top = diagnostics.get('top_worst')
    if top is not None and not top.empty:
        pairs = []
        for _, r in top.iterrows():
            pairs.append(f"{r['id']}:{int(r['error_TND']):+,}TND:{r['error_pct']:.1f}%")
        print("Top worst (id:error:%%): " + " | ".join(pairs))



def print_report(results: pd.DataFrame,
                 n_samples: int,
                 live_metrics,
                 precision_stats: dict,
                 training_results_path: Path,
                 summary_only: bool = False,
                 print_n: int = 20,
                 print_all: bool = False):

    prices = results['predicted_price_TND'].values
    has_gt = live_metrics is not None

    print("\n" + "=" * 70)
    print(" " * 18 + "MODEL TEST ON REAL UNSEEN DATA")
    print("=" * 70)
    print(f"\n  Source:     test_data.csv  (never seen during training)")
    print(f"  Samples:    {n_samples}")
    print(f"  Model:      unified_model/best_model.joblib")
    print(f"  Run at:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if has_gt:
        print(f"  Ground truth available: YES  ({live_metrics['n']} listings with real prices/rents)")
    
    print("\n" + "-" * 70)
    print("[PREDICTIONS PER PROPERTY]")
    print("-" * 70)

    if not summary_only:
        to_print = results if print_all else results.head(print_n)
        print(f"  {'#':<3}  {'ID':<26}  {'Type':<12}  {'m²':>5}  {'True Price':>14}  {'Predicted':>14}  {'Error':>10}  {'%':>7}")
        print("  " + "-" * 95)
        for i, row in to_print.iterrows():
            surf  = f"{row['surface_m2']:.0f}" if pd.notna(row['surface_m2']) else "N/A"
            true_s = f"{row['true_price_TND']:>12,.0f}" if pd.notna(row['true_price_TND']) else f"{'N/A':>12}"
            pred_s = f"{row['predicted_price_TND']:>12,.0f}"
            err_s  = f"{row['error_TND']:>+10,.0f}" if pd.notna(row['error_TND']) else f"{'N/A':>10}"
            pct_s  = f"{row['error_pct']:>+6.1f}%" if pd.notna(row['error_pct']) else f"{'N/A':>7}"
            verdict = ""
            if pd.notna(row['error_pct']):
                verdict = "GOOD" if abs(row['error_pct']) < 30 else "OFF"
            print(f"  {i+1:<3}  {str(row['id']):<26}  {str(row['type']):<12}  {surf:>5}  {true_s} TND  {pred_s} TND  {err_s}  {pct_s}  {verdict}")
            
    if has_gt:
        m = live_metrics
        r2_interp = "GOOD" if m['R2'] > 0.5 else "MODERATE" if m['R2'] > 0.3 else "POOR"

        print(f"""
+-----------------------------------------------------------------------+
|   ACCURACY ON test_data.csv  ({m['n']} properties with real prices) |
+-----------------------------------------------------------------------+
|                                                                        |
|  R2 Score:          {m['R2']:>8.4f}  ({m['R2']*100:>6.1f}% variance explained)        |
|  MAE:               {m['MAE']:>12,.0f} TND                              |
|  MedAE:             {m['MedAE']:>12,.0f} TND                              |
|  RMSE:              {m['RMSE']:>12,.0f} TND                              |
|  MAPE:              {m['MAPE']:>12.1f}%                                 |
+-----------------------------------------------------------------------+
""")

        if precision_stats:
            ps = precision_stats
            print("\n+---------------- Precision stats (absolute errors) ----------------+")
            print(f"  Std error:    {ps.get('std_error', float('nan')):,.0f} TND")
            print(f"  Mean error:   {ps.get('mean_error', float('nan')):,.0f} TND")
            print(f"  CV (error):   {ps.get('cv_error', float('nan')):.3f}")
            print(f"  95% err int:  [{ps.get('error_p2_5', float('nan')):,.0f}, {ps.get('error_p97_5', float('nan')):,.0f}] TND")
            print(f"  Within 10%:   {ps.get('within_10pct', 0):.1f}%")
            print(f"  Within 20%:   {ps.get('within_20pct', 0):.1f}%")
            print(f"  Within 30%:   {ps.get('within_30pct', 0):.1f}%")
            print(f"  Within 50%:   {ps.get('within_50pct', 0):.1f}%")
            print("+-------------------------------------------------------------------+")


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='Evaluate unified model on dataset')
    parser.add_argument('--data', default=str(SCRIPT_DIR / 'cleaned_unified.csv'), help='Path to CSV data (default: cleaned_unified.csv)')
    parser.add_argument('--model-dir', default=str(SCRIPT_DIR / 'unified_model'), help='Model directory containing artifacts')
    parser.add_argument('--summary-only', action='store_true', help='Show only summary metrics (no per-property table)')
    parser.add_argument('--diagnostics', action='store_true', help='Output diagnostics (supported/concerning/critical counts and top errors)')
    parser.add_argument('--print-n', type=int, default=20, help='Number of per-listing rows to print (default 20)')
    parser.add_argument('--print-all', action='store_true', help='Print all per-listing rows')
    parser.add_argument('--save-results', default=None, help='Path to save per-listing results CSV (predictions and errors)')
    args = parser.parse_args()

    test_data_path    = Path(args.data)
    model_path        = Path(args.model_dir) / 'best_model.joblib'
    preprocessor_path = Path(args.model_dir) / 'preprocessor.joblib'
    training_results_path = Path(args.model_dir) / 'training_results.json'

    for p in [test_data_path, model_path, preprocessor_path]:
        if not p.exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    print("\n" + "=" * 70)
    print(" " * 24 + "LOADING FILES")
    print("=" * 70)
    
    model        = joblib.load(model_path)
    preprocessor = joblib.load(preprocessor_path)
    df_raw    = load_raw_data(str(test_data_path))
    
    n_samples = len(df_raw)
    print(f"\n  Loaded {n_samples} rows from test_data.csv")

    y_true_price, mask = extract_ground_truth(df_raw)
    if mask is not None:
        print(f"  Ground-truth sale prices detected: {mask.sum()} / {n_samples} rows")
        
    print("\n[PREPROCESSING]")
    df_derived = compute_derived_features(df_raw)
    X = preprocess_for_inference(df_raw.copy(), preprocessor)
    print(f"  Done — feature matrix: {X.shape}")

    print("\n[PREDICTING]")
    y_pred_log_per_m2 = model.predict(X)
    
    # Reconstruct absolute price: exp(y_pred_log_per_m2 - 1) * surface
    surface = df_derived['bien.superficie_totale'].values
    y_pred_price = np.expm1(y_pred_log_per_m2) * surface
    
    print(f"  Generated {len(y_pred_price)} absolute price predictions")

    live_metrics = None
    precision_stats = None
    if mask is not None and mask.sum() > 0:
        live_metrics = compute_accuracy_metrics(y_true_price, y_pred_price, mask)
        precision_stats = compute_precision_stats(y_true_price, y_pred_price, mask)

    results = build_results_table(df_raw, y_pred_price, y_true_price, mask)
    print_report(results, n_samples, live_metrics, precision_stats, training_results_path, summary_only=args.summary_only, print_n=args.print_n, print_all=args.print_all)

    # Always compute diagnostics and print a concise simple summary for the user.
    diag = compute_error_diagnostics(results)
    if args.diagnostics:
        print("\nDIAGNOSTICS:\n")
        print(f"  Total rows: {diag['n_total']}")
        print(f"  Valid ground-truth rows: {diag['n_valid']}")
        print(f"  Supported (<=30%): {diag['n_supported']} ({diag['supported_pct']:.1f}%)")
        print(f"  Concerning (30-50%): {diag['n_concerning']} ({diag['concerning_pct']:.1f}%)")
        print(f"  Critical (>100% abs or >500k TND): {diag['n_critical']} ({diag['critical_pct']:.1f}%)")

        print("\nTop worst absolute errors (showing up to 10):")
        print(diag['top_worst'].to_string(index=False))
        # print the simple summary block for terminal
        print_simple_summary(str(test_data_path.name), diag, live_metrics, precision_stats)
    else:
        # concise summary shown by default for quick terminal reading
        print_simple_summary(str(test_data_path.name), diag, live_metrics, precision_stats)

    # Optionally save full per-listing results to CSV for exact inspection
    if args.save_results:
        out_path = Path(args.save_results)
        results.to_csv(out_path, index=False)
        print(f"\nPer-listing results saved to: {out_path}")

    # compute classification/confusion matrix based on price bins if available
    cls = compute_classification_from_bins(df_raw, results)
    if cls is not None:
        print("\nCLASSIFICATION (price bins):")
        print(f"  Accuracy: {cls['accuracy']:.3f}")
        print("  Labels:", cls['labels'])
        print("  Confusion matrix:")
        print(cls['confusion_matrix'])
        print("\n  Classification report:\n")
        print(cls['report'])

    # compute classification metrics by mapping continuous prices to canonical buckets
    price_cls = compute_classification_from_prices(y_true_price, y_pred_price, mask)
    if price_cls is not None:
        print("\nCLASSIFICATION (canonical total-price buckets):")
        print(f"  Balanced accuracy: {price_cls['balanced_accuracy']:.3f}")
        print("  Labels:", price_cls['labels'])
        print("\n  Classification report:\n")
        print(price_cls['report'])

    return results


if __name__ == '__main__':
    main()
