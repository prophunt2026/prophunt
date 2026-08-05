"""
Diagnostic visualizations (13 charts).
=============================================================
Actual vs predicted, residual diagnostics, feature importance,
learning curves, prediction intervals, segment-level MAE bar charts,
price distribution KDE, Q-Q plot, CV score boxplot, hyperparameter
sensitivity heatmap, and external benchmark comparison — plus the
orchestrator that generates and saves all of them.
"""

import os
from typing import Any, Dict, List

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless environments
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from sklearn.base import BaseEstimator
from sklearn.model_selection import learning_curve

from .config import logger, RANDOM_STATE
from .evaluation import expm1_to_original


def setup_plotting():
    """Configure matplotlib/seaborn defaults."""
    plt.style.use('seaborn-v0_8-whitegrid')
    sns.set_palette('husl')
    plt.rcParams.update({
        'figure.dpi': 150,
        'savefig.dpi': 150,
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
    })


def plot_01_actual_vs_predicted(
    y_true: np.ndarray, y_pred: np.ndarray, path: str
):
    """Chart 1: Actual vs Predicted scatter plot."""
    fig, ax = plt.subplots(figsize=(8, 8))
    y_true_orig = np.expm1(y_true)
    y_pred_orig = expm1_to_original(y_pred)

    # Clip for visualization
    max_val = np.percentile(y_true_orig, 99)
    mask = (y_true_orig < max_val) & (y_pred_orig < max_val)

    ax.scatter(y_true_orig[mask], y_pred_orig[mask], alpha=0.3, s=10, c='steelblue', edgecolors='none')
    max_plot = max_val * 1.1
    ax.plot([0, max_plot], [0, max_plot], 'r--', linewidth=2, label='Perfect prediction')
    ax.set_xlim(0, max_plot)
    ax.set_ylim(0, max_plot)
    ax.set_xlabel('Actual Price (TND)')
    ax.set_ylabel('Predicted Price (TND)')
    ax.set_title('Actual vs Predicted Prices')
    ax.legend(loc='upper left')
    ax.set_aspect('equal', adjustable='box')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_02_residual_distribution(residuals: np.ndarray, path: str):
    """Chart 2: Residual distribution histogram."""
    fig, ax = plt.subplots(figsize=(10, 6))
    # Show residuals in log-space with histogram and KDE
    ax.hist(residuals, bins=60, color='steelblue', alpha=0.7, edgecolor='white', density=True)
    sns.kdeplot(residuals, ax=ax, color='darkred', linewidth=2)
    ax.axvline(x=0, color='black', linestyle='--', linewidth=1)
    ax.set_xlabel('Residual (log-space)')
    ax.set_ylabel('Density')
    ax.set_title('Distribution of Residuals (log-space)')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_03_residual_vs_predicted(y_pred: np.ndarray, residuals: np.ndarray, path: str):
    """Chart 3: Residual vs Predicted plot."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(y_pred, residuals, alpha=0.3, s=10, c='steelblue', edgecolors='none')
    ax.axhline(y=0, color='red', linestyle='--', linewidth=1)
    ax.set_xlabel('Predicted (log-space)')
    ax.set_ylabel('Residual (log-space)')
    ax.set_title('Residuals vs Predicted Values')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_04_feature_importance(model: BaseEstimator, feature_names: List[str], path: str):
    """Chart 4: Feature importance (top 20)."""
    importances = None

    if hasattr(model, 'feature_importances_'):
        importances = model.feature_importances_
    elif hasattr(model, 'coef_'):
        importances = np.abs(model.coef_)

    if importances is None:
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.text(0.5, 0.5, 'Feature importance not available for this model type',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    if len(importances) != len(feature_names):
        logger.warning(f"Feature names ({len(feature_names)}) != importances ({len(importances)}). Skipping feature importance plot.")
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.text(0.5, 0.5, 'Feature name mismatch — cannot plot',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    n_show = min(20, len(importances))
    indices = np.argsort(importances)[-n_show:][::-1]

    fig, ax = plt.subplots(figsize=(10, 8))
    names = [feature_names[i] for i in indices]
    values = importances[indices]

    bars = ax.barh(range(len(names)), values, color='steelblue', edgecolor='white')
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('Importance')
    ax.set_title(f'Top {n_show} Feature Importances')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_05_learning_curves(
    model: BaseEstimator,
    X_train: np.ndarray, y_train: pd.Series,
    cv_folds: int, path: str,
):
    """Chart 5: Learning curves."""
    try:
        train_sizes, train_scores, val_scores = learning_curve(
            model, X_train, y_train,
            train_sizes=np.linspace(0.1, 1.0, 10),
            cv=cv_folds,
            scoring='neg_root_mean_squared_error',
            n_jobs=-1,
            shuffle=True,
            random_state=RANDOM_STATE,
        )

        train_rmse = -train_scores.mean(axis=1)
        val_rmse = -val_scores.mean(axis=1)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(train_sizes, train_rmse, 'o-', color='steelblue', label='Training RMSE')
        ax.plot(train_sizes, val_rmse, 'o-', color='darkorange', label='Validation RMSE')
        ax.fill_between(train_sizes, train_rmse - train_scores.std(axis=1),
                        train_rmse + train_scores.std(axis=1), alpha=0.1, color='steelblue')
        ax.fill_between(train_sizes, val_rmse - val_scores.std(axis=1),
                        val_rmse + val_scores.std(axis=1), alpha=0.1, color='darkorange')
        ax.set_xlabel('Training Set Size')
        ax.set_ylabel('RMSE (log-space)')
        ax.set_title('Learning Curves')
        ax.legend(loc='best')
        plt.tight_layout()
        plt.savefig(path, bbox_inches='tight')
        plt.close()
    except Exception as e:
        logger.warning(f"Could not generate learning curves: {e}")
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, f'Learning curves unavailable: {e}',
                ha='center', va='center', transform=ax.transAxes, fontsize=12)
        plt.savefig(path, bbox_inches='tight')
        plt.close()


def plot_06_prediction_intervals(
    y_true: np.ndarray, y_pred: np.ndarray,
    lower: np.ndarray, upper: np.ndarray, path: str,
):
    """Chart 6: Prediction interval plot."""
    fig, ax = plt.subplots(figsize=(12, 6))
    n_show = min(200, len(y_true))
    idx = np.random.RandomState(RANDOM_STATE).choice(len(y_true), n_show, replace=False)
    idx = np.sort(idx)

    y_true_orig = np.expm1(y_true[idx])
    y_pred_orig = expm1_to_original(y_pred[idx])
    lower_orig = expm1_to_original(lower[idx])
    upper_orig = expm1_to_original(upper[idx])

    x = np.arange(n_show)
    ax.fill_between(x, lower_orig, upper_orig, alpha=0.3, color='steelblue', label='95% CI')
    ax.plot(x, y_true_orig, 'o', color='black', markersize=3, alpha=0.5, label='Actual')
    ax.plot(x, y_pred_orig, '-', color='darkorange', linewidth=1, alpha=0.8, label='Predicted')
    ax.set_xlabel('Sample Index')
    ax.set_ylabel('Price (TND)')
    ax.set_title('Prediction Intervals (95% Confidence)')
    ax.legend(loc='best')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_07_mae_by_gouvernorat(
    df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, path: str,
):
    """Chart 7: MAE by gouvernorat bar chart."""
    df_plot = df.copy()
    df_plot['y_true'] = np.expm1(y_true)
    df_plot['y_pred'] = expm1_to_original(y_pred)
    df_plot['error'] = abs(df_plot['y_true'] - df_plot['y_pred'])

    if 'localisation.gouvernorat' not in df_plot.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'gouvernorat column not available',
                ha='center', va='center', transform=ax.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    gouv_mae = df_plot.groupby('localisation.gouvernorat')['error'].mean().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#e74c3c' if v > 50000 else '#f39c12' if v > 35000 else '#27ae60' for v in gouv_mae.values]
    ax.barh(range(len(gouv_mae)), gouv_mae.values, color=colors, edgecolor='white')
    ax.set_yticks(range(len(gouv_mae)))
    ax.set_yticklabels(gouv_mae.index, fontsize=9)
    ax.set_xlabel('Mean Absolute Error (TND)')
    ax.set_title('MAE by Gouvernorat')
    ax.axvline(x=50000, color='red', linestyle='--', alpha=0.7, label='Target (50,000 TND)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_08_mae_by_bien_type(
    df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, path: str,
):
    """Chart 8: MAE by bien.type bar chart."""
    df_plot = df.copy()
    df_plot['y_true'] = np.expm1(y_true)
    df_plot['y_pred'] = expm1_to_original(y_pred)
    df_plot['error'] = abs(df_plot['y_true'] - df_plot['y_pred'])

    if 'bien.type' not in df_plot.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'bien.type column not available',
                ha='center', va='center', transform=ax.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    type_mae = df_plot.groupby('bien.type')['error'].mean().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#e74c3c' if v > 50000 else '#f39c12' if v > 35000 else '#27ae60' for v in type_mae.values]
    ax.barh(range(len(type_mae)), type_mae.values, color=colors, edgecolor='white')
    ax.set_yticks(range(len(type_mae)))
    ax.set_yticklabels(type_mae.index, fontsize=9)
    ax.set_xlabel('Mean Absolute Error (TND)')
    ax.set_title('MAE by Property Type')
    ax.axvline(x=50000, color='red', linestyle='--', alpha=0.7, label='Target (50,000 TND)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_09_price_distribution_kde(y_true: np.ndarray, y_pred: np.ndarray, path: str):
    """Chart 9: Price distribution (actual vs predicted KDE)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    y_true_orig = np.expm1(y_true)
    y_pred_orig = expm1_to_original(y_pred)

    # Clip for visualization
    max_val = np.percentile(y_true_orig, 98)
    sns.kdeplot(y_true_orig[y_true_orig < max_val], ax=ax, label='Actual', color='steelblue', linewidth=2)
    sns.kdeplot(y_pred_orig[y_pred_orig < max_val], ax=ax, label='Predicted', color='darkorange', linewidth=2, linestyle='--')
    ax.set_xlabel('Price (TND)')
    ax.set_ylabel('Density')
    ax.set_title('Price Distribution: Actual vs Predicted')
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_10_qq_residuals(residuals: np.ndarray, path: str):
    """Chart 10: Q-Q plot of residuals."""
    fig, ax = plt.subplots(figsize=(8, 8))
    stats.probplot(residuals, dist='norm', plot=ax)
    ax.set_title('Q-Q Plot of Residuals (log-space)')
    ax.get_lines()[0].set_markerfacecolor('steelblue')
    ax.get_lines()[0].set_markeredgecolor('steelblue')
    ax.get_lines()[0].set_markersize(3)
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_11_cv_scores_boxplot(cv_results: Dict[str, Any], path: str):
    """Chart 11: Cross-validation scores boxplot."""
    fig, ax = plt.subplots(figsize=(10, 6))

    model_names = []
    all_scores = []

    for name, result in cv_results.items():
        if result.get('search') and hasattr(result['search'], 'cv_results_'):
            cv_res = result['search'].cv_results_
            # Extract all fold scores
            test_scores = []
            for key in cv_res:
                if 'split' in key and '_test_score' in key:
                    test_scores.extend(cv_res[key])
            if test_scores:
                model_names.append(name)
                all_scores.append([-s for s in test_scores])  # Convert back from neg

    if not model_names:
        ax.text(0.5, 0.5, 'No CV score data available',
                ha='center', va='center', transform=ax.transAxes)
    else:
        bp = ax.boxplot(all_scores, labels=model_names, patch_artist=True)
        colors = sns.color_palette('husl', len(model_names))
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
    ax.set_ylabel('RMSE (log-space)')
    ax.set_title('Cross-Validation Scores by Model')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_12_hyperparameter_sensitivity(phase1_results: Dict[str, Any], path: str):
    """Chart 12: Hyperparameter sensitivity heatmap."""
    fig, axes = plt.subplots(1, 1, figsize=(12, 6))

    data_rows = []
    for name, result in phase1_results.items():
        if result.get('search') and hasattr(result['search'], 'cv_results_'):
            cv_res = result['search'].cv_results_
            if 'mean_test_score' in cv_res:
                best_idx = result['search'].best_index_
                best_rmse = -cv_res['mean_test_score'][best_idx]
                std_rmse = cv_res['std_test_score'][best_idx]
                data_rows.append({
                    'Model': name,
                    'Best RMSE': best_rmse,
                    'Std': std_rmse,
                    'Params Tested': len(cv_res['params']),
                })

    if not data_rows:
        axes.text(0.5, 0.5, 'No hyperparameter search data available',
                  ha='center', va='center', transform=axes.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    df_hp = pd.DataFrame(data_rows).set_index('Model')
    sns.heatmap(df_hp, annot=True, fmt='.4f', cmap='YlOrRd_r', ax=axes, linewidths=0.5)
    axes.set_title('Hyperparameter Search Summary')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def plot_13_external_validation(external_results: Dict[str, Any], path: str):
    """Chart 13: External validation comparison (model vs Mubawab)."""
    fig, ax = plt.subplots(figsize=(12, 8))

    # Extract comparable results
    zones = []
    model_prices = []
    mubawab_prices = []

    for key, val in external_results.items():
        if isinstance(val, dict) and 'model_prix_m2' in val:
            zones.append(key)
            model_prices.append(val['model_prix_m2'])
            mubawab_prices.append(val['mubawab_prix_m2'])

    if not zones:
        ax.text(0.5, 0.5, 'No external benchmark comparison data available',
                ha='center', va='center', transform=ax.transAxes)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        return

    x = np.arange(len(zones))
    width = 0.35

    ax.bar(x - width/2, model_prices, width, label='Model (median prix/m²)', color='steelblue', alpha=0.8)
    ax.bar(x + width/2, mubawab_prices, width, label='Mubawab Reference', color='darkorange', alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(zones, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Price per m² (TND)')
    ax.set_title('Model Predictions vs Mubawab Benchmarks')
    ax.legend(loc='best')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight')
    plt.close()


def generate_all_visualizations(
    best_model: BaseEstimator,
    eval_results: Dict,
    X_train: np.ndarray, y_train: pd.Series,
    X_test: np.ndarray, y_test: pd.Series,
    df_test: pd.DataFrame,
    df_full: pd.DataFrame,
    phase1_results: Dict,
    validation_results: Dict,
    feature_names: List[str],
    cv_folds: int,
    vis_dir: str,
):
    """Generate all 13 visualization charts."""
    logger.info(f"\n{'='*60}")
    logger.info("GENERATING VISUALIZATIONS")
    logger.info(f"{'='*60}")

    os.makedirs(vis_dir, exist_ok=True)
    setup_plotting()

    y_pred_test = eval_results['test']['y_pred']
    residuals = y_test.values - y_pred_test
    pi_data = validation_results.get('step4_prediction_intervals', {})

    charts = [
        ('01_actual_vs_predicted.png', lambda p: plot_01_actual_vs_predicted(y_test.values, y_pred_test, p)),
        ('02_residual_distribution.png', lambda p: plot_02_residual_distribution(residuals, p)),
        ('03_residual_vs_predicted.png', lambda p: plot_03_residual_vs_predicted(y_pred_test, residuals, p)),
        ('04_feature_importance.png', lambda p: plot_04_feature_importance(best_model, feature_names, p)),
        ('05_learning_curves.png', lambda p: plot_05_learning_curves(best_model, X_train, y_train, cv_folds, p)),
        ('06_prediction_intervals.png', lambda p: plot_06_prediction_intervals(
            y_test.values, y_pred_test,
            pi_data.get('lower', np.zeros(len(y_test))),
            pi_data.get('upper', np.ones(len(y_test))),
            p,
        )),
        ('07_mae_by_gouvernorat.png', lambda p: plot_07_mae_by_gouvernorat(df_test, y_test.values, y_pred_test, p)),
        ('08_mae_by_bien_type.png', lambda p: plot_08_mae_by_bien_type(df_test, y_test.values, y_pred_test, p)),
        ('09_price_distribution_kde.png', lambda p: plot_09_price_distribution_kde(y_test.values, y_pred_test, p)),
        ('10_qq_residuals.png', lambda p: plot_10_qq_residuals(residuals, p)),
        ('11_cv_scores_boxplot.png', lambda p: plot_11_cv_scores_boxplot(phase1_results, p)),
        ('12_hyperparameter_sensitivity.png', lambda p: plot_12_hyperparameter_sensitivity(phase1_results, p)),
        ('13_external_validation.png', lambda p: plot_13_external_validation(
            validation_results.get('step5_external_benchmark', {}), p
        )),
    ]

    for filename, plot_func in charts:
        filepath = os.path.join(vis_dir, filename)
        try:
            plot_func(filepath)
            logger.info(f"  Saved: {filepath}")
        except Exception as e:
            logger.error(f"  Failed to generate {filename}: {e}")
