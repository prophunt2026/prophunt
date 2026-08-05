"""
Console report generation.
=============================================================
Prints the final human-readable training summary: best model, metrics,
overfitting diagnosis, Go/No-Go decision, and top feature importances.
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

    print(f"\n{'='*70}")
    print("  FINAL TRAINING REPORT")
    print(f"{'='*70}")

    print(f"\n  Best Model: {best_name}")
    print(f"  Best Parameters: {json.dumps(best_params, default=str, indent=4)}")
    print(f"  Total Training Time: {training_time:.1f}s")

    print(f"\n  {'─'*40}")
    print(f"  EVALUATION METRICS (Test Set, TND)")
    print(f"  {'─'*40}")
    for metric, value in test_metrics.items():
        target = {'RMSE': '<80K', 'MAE': '<50K', 'R2': '>0.75', 'MAPE': '<20%', 'MedAE': '<35K'}.get(metric, '')
        print(f"    {metric:8s}: {value:>12,.2f}  {target}")

    print(f"\n  {'─'*40}")
    print(f"  OVERFITTING DIAGNOSIS")
    print(f"  {'─'*40}")
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

    print(f"\n  {'─'*40}")
    print(f"  GO/NO-GO DECISION")
    print(f"  {'─'*40}")
    print(f"    Decision: {decision} (score: {score}/100)")
    for reason in go_nogo.get('reasons', []):
        print(f"    • {reason}")

    print(f"\n  {'─'*40}")
    print(f"  TOP 15 FEATURE IMPORTANCE")
    print(f"  {'─'*40}")
    for i, fi in enumerate(feature_importance[:15]):
        if 'feature' in fi and 'importance' in fi:
            cum = fi.get('cumulative_importance', 0)
            print(f"    {i+1:2d}. {fi['feature']:<45s} {fi['importance']:.4f}  (cum: {cum:.1f}%)")

    print(f"\n{'='*70}")
    print(f"  Training complete. Artifacts saved to output directory.")
    print(f"{'='*70}\n")
