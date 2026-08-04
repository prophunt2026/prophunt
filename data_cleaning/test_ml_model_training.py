import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from ml_model_training import (
    BinaryImputer,
    build_preprocessing_pipeline,
    load_and_prepare_data,
    load_metadata,
    phase1_random_search,
    stratified_train_val_test_split,
    create_composite_stratifier,
    get_models,
    expm1_to_original,
    validation_step3_segment_analysis,
)

DATA_DIR = Path(__file__).resolve().parent


def test_expm1_to_original_clips_negative_numpy_predictions():
    y_log = np.array([13.0, 0.0, -0.5])
    y_orig = expm1_to_original(y_log)

    assert y_orig[0] == pytest.approx(442412.39, rel=1e-4)
    assert y_orig[1:].tolist() == [0.0, 0.0]
    assert (y_orig >= 0).all()


def test_numpy_clip_lower_kwarg_is_invalid_for_expm1_back_transform():
    y_log = np.array([13.0, -0.5])
    with pytest.raises(TypeError, match="lower"):
        np.expm1(y_log).clip(lower=0)


def test_validation_step3_segment_analysis_back_transforms_log_predictions():
    df_test = pd.DataFrame({
        "localisation.gouvernorat": ["Tunis", "Ariana", "Tunis"],
        "bien.type": ["Appartement", "Villa", "Appartement"],
        "bien.superficie_totale": [100.0, 200.0, 120.0],
    })
    y_test = np.array([13.0, 12.5, 13.2])
    y_pred_test = np.array([13.1, 12.4, -0.5])

    results = validation_step3_segment_analysis(df_test, y_test, y_pred_test)

    assert "by_gouvernorat" in results
    assert "by_bien_type" in results
    assert "by_price_range" in results
    assert results["by_gouvernorat"]["Tunis"]["n"] == 2
    assert results["by_bien_type"]["Appartement"]["n"] == 2


def test_binary_imputer_coerces_text_boolean_values_to_numeric_binary():
    X = pd.DataFrame({
        "equipements.climatisation": ["True", "False", None, "1", "0"],
        "equipements.garage": ["TRUE", "FALSE", pd.NA, "yes", "no"],
    })

    transformed = BinaryImputer().fit_transform(X)

    assert transformed["equipements.climatisation"].tolist() == [1, 0, 0, 1, 0]
    assert transformed["equipements.garage"].tolist() == [1, 0, 0, 1, 0]
    assert transformed.isin([0, 1]).all().all()


def test_binary_imputer_coerces_heating_type_labels_to_binary():
    X = pd.DataFrame({
        "equipements.chauffage": ["True", "False", "Central", "Sans chauffage", None],
    })

    transformed = BinaryImputer().fit_transform(X)

    assert transformed["equipements.chauffage"].tolist() == [1, 0, 1, 0, 0]


def test_preprocessed_training_matrix_is_numeric_for_linear_regression():
    data_path = DATA_DIR / "cleaned_vente.csv"
    metadata_path = DATA_DIR / "feature_metadata.json"
    if not data_path.exists() or not metadata_path.exists():
        pytest.skip("Local training data files are not available.")

    metadata = load_metadata(str(metadata_path))
    df, y, features_config = load_and_prepare_data(str(data_path), metadata)
    feature_cols = (
        features_config["numeric"]
        + features_config["categorical_high_card"]
        + features_config["categorical_low_card"]
        + features_config["binary"]
    )
    available_features = [c for c in feature_cols if c in df.columns]
    X = df[available_features].copy()

    stratify_col = create_composite_stratifier(df)
    X_train, _, _, y_train, _, _ = stratified_train_val_test_split(X, y, stratify_col)
    X_train = X_train.reset_index(drop=True)
    y_train = y_train.reset_index(drop=True)

    preprocessor = build_preprocessing_pipeline(features_config)
    X_train_processed = preprocessor.fit_transform(X_train, y_train)

    X_numeric = pd.DataFrame(X_train_processed).apply(pd.to_numeric, errors="raise")
    LinearRegression().fit(X_numeric, y_train)


def test_phase1_linear_regression_fits_without_string_boolean_error():
    data_path = DATA_DIR / "cleaned_vente.csv"
    metadata_path = DATA_DIR / "feature_metadata.json"
    if not data_path.exists() or not metadata_path.exists():
        pytest.skip("Local training data files are not available.")

    metadata = load_metadata(str(metadata_path))
    df, y, features_config = load_and_prepare_data(str(data_path), metadata)
    feature_cols = (
        features_config["numeric"]
        + features_config["categorical_high_card"]
        + features_config["categorical_low_card"]
        + features_config["binary"]
    )
    available_features = [c for c in feature_cols if c in df.columns]
    X = df[available_features].copy()

    stratify_col = create_composite_stratifier(df)
    X_train, _, _, y_train, _, _ = stratified_train_val_test_split(X, y, stratify_col)
    X_train = X_train.reset_index(drop=True)
    y_train = y_train.reset_index(drop=True)

    preprocessor = build_preprocessing_pipeline(features_config)
    X_train_processed = preprocessor.fit_transform(X_train, y_train)

    models = {"LinearRegression": get_models()["LinearRegression"]}
    results = phase1_random_search(models, X_train_processed, y_train, cv_folds=2, n_iter=5)

    assert "LinearRegression" in results
    assert results["LinearRegression"]["model"] is not None
