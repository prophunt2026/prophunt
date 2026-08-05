"""
Optional third-party dependency detection.
=============================================================
Centralizes the try/except imports for optional ML libraries so the
rest of the codebase can simply check the HAS_* flags instead of
repeating try/except ImportError blocks everywhere.
"""

try:
    from category_encoders import TargetEncoder
    HAS_CATEGORY_ENCODERS = True
except ImportError:
    TargetEncoder = None
    HAS_CATEGORY_ENCODERS = False
    print("WARNING: category_encoders not installed. TargetEncoder will be skipped.")

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    XGBRegressor = None
    HAS_XGBOOST = False
    print("WARNING: xgboost not installed. XGBoost model will be skipped.")

try:
    from lightgbm import LGBMRegressor
    HAS_LIGHTGBM = True
except ImportError:
    LGBMRegressor = None
    HAS_LIGHTGBM = False
    print("WARNING: lightgbm not installed. LightGBM model will be skipped.")
