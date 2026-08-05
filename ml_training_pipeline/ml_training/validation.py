"""
Seven-step validation pipeline.
=============================================================
Held-out evaluation, overfitting diagnosis, segment-level error
analysis, bootstrap prediction intervals, external Mubawab benchmark
comparison, INS IPIM index comparison, and the final Go/No-Go
decision matrix.
"""

from typing import Any, Dict

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

from .config import logger, RANDOM_STATE, MUBAWAB_SALES_BENCHMARK, IPIM_REFERENCE
from .evaluation import expm1_to_original


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
