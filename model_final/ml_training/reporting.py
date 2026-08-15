"""
Console report generation.
=============================================================
Prints the final human-readable training summary: best model, metrics,
overfitting diagnosis, Go/No-Go decision, and top feature importances.

P1-A: Updated to display both raw-price TND and log-space metrics,
with raw-price metrics as the PRIMARY evaluation.
"""

import json
from typing import Dict, List


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
    test_raw = eval_results['test'].get('raw_metrics', {})
    train_raw = eval_results['train'].get('raw_metrics', {})
    test_log = eval_results['test'].get('log_metrics', {})

    print(f"\n{'='*70}")
    print("  FINAL TRAINING REPORT")
    print(f"{'='*70}")

    print(f"\n  Best Model: {best_name}")
    print(f"  Best Parameters: {json.dumps(best_params, default=str, indent=4)}")
    print(f"  Total Training Time: {training_time:.1f}s")

    # ── PRIMARY: Raw Total-Price Metrics (TND) ──
    if test_raw:
        print(f"\n  {'-'*50}")
        print(f"  PRIMARY METRICS — Raw Total Price (TND)")
        print(f"  {'-'*50}")
        targets = {'RMSE_raw': '<80K', 'MAE_raw': '<50K', 'R2_raw': '>0.50', 'MAPE_raw': '<40%', 'MedAE_raw': '<35K'}
        for metric, target in targets.items():
            value = test_raw.get(metric, 'N/A')
            if isinstance(value, (int, float)):
                print(f"    {metric:12s}: {value:>12,.2f}  {target}")
            else:
                print(f"    {metric:12s}: {value:>12s}  {target}")

    # ── SECONDARY: Per-m² Metrics ──
    print(f"\n  {'-'*50}")
    print(f"  SECONDARY METRICS — Per-m² Price Space (TND/m²)")
    print(f"  {'-'*50}")
    for metric, value in test_metrics.items():
        target = {'RMSE': '<1.5K', 'MAE': '<900', 'R2': '>0.50', 'MAPE': '<40%', 'MedAE': '<600'}.get(metric, '')
        print(f"    {metric:8s}: {value:>12,.2f}  {target}")

    # ── REFERENCE: Log-space Metrics ──
    if test_log:
        print(f"\n  {'-'*50}")
        print(f"  REFERENCE — Log-Space Metrics (log(price/m²))")
        print(f"  {'-'*50}")
        for metric, value in test_log.items():
            print(f"    {metric:12s}: {value:>12.4f}")

    # ── Overfitting Diagnosis ──
    print(f"\n  {'-'*50}")
    print(f"  OVERFITTING DIAGNOSIS")
    print(f"  {'-'*50}")
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

    # Raw-price overfitting (if available)
    if test_raw and train_raw:
        print(f"\n    --- Raw TND Overfitting ---")
        for metric in ['RMSE_raw', 'MAE_raw']:
            t_val = train_raw.get(metric, 0)
            v_val = test_raw.get(metric, 0)
            gap = v_val - t_val
            ratio = v_val / max(t_val, 1)
            print(f"    {metric:12s}: train={t_val:,.0f}, test={v_val:,.0f}, gap={gap:,.0f}, ratio={ratio:.2f}x")

    # ── Go/No-Go ──
    print(f"\n  {'-'*50}")
    print(f"  GO/NO-GO DECISION")
    print(f"  {'-'*50}")
    print(f"    Decision: {decision} (score: {score}/100)")
    for reason in go_nogo.get('reasons', []):
        print(f"    * {reason}")

    # ── Feature Importance ──
    print(f"\n  {'-'*50}")
    print(f"  TOP 15 FEATURE IMPORTANCE")
    print(f"  {'-'*50}")
    for i, fi in enumerate(feature_importance[:15]):
        if 'feature' in fi and 'importance' in fi:
            cum = fi.get('cumulative_importance', 0)
            print(f"    {i+1:2d}. {fi['feature']:<45s} {fi['importance']:.4f}  (cum: {cum:.1f}%)")

    print(f"\n{'='*70}")
    print(f"  Training complete. Artifacts saved to output directory.")
    print(f"{'='*70}\n")
