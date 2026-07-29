"""
Standalone SHAP sanity check against the real behaviour model — run where numpy 1.x
+ shap 0.45.1 are installed (the Docker/Render env), e.g.:

    docker run --rm -v "%cd%:/app" -w /app python:3.11-slim sh -c \
      "pip install -q numpy==1.26.4 scikit-learn==1.5.1 pandas==2.2.2 joblib==1.4.2 shap==0.45.1 && python scripts/shap_check.py"

Confirms shap.TreeExplainer runs on the saved RandomForest and that our per-class
normalization yields sensible signed top factors.
"""
import os
import joblib
import numpy as np
import pandas as pd
import shap

HERE      = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, '..', 'models')

DEFAULT_FEATURES = [
    'daily_play_time_hours', 'weekly_play_time_hours', 'sessions_per_day',
    'avg_session_duration_min', 'late_night_play_ratio', 'days_played_per_week',
    'longest_play_streak_days', 'binge_sessions_per_week',
    'avg_break_between_sessions_min', 'rapid_relogin_ratio',
]


def per_class(sv):
    if isinstance(sv, list):
        return [np.asarray(a)[0] for a in sv]
    arr = np.asarray(sv)
    if arr.ndim == 3:
        return [arr[0, :, k] for k in range(arr.shape[2])]
    if arr.ndim == 2:
        return [arr[0]]
    return [arr]


model  = joblib.load(os.path.join(MODEL_DIR, 'behavior_model.pkl'))
scaler = joblib.load(os.path.join(MODEL_DIR, 'feature_scaler.pkl'))
feature_path = os.path.join(MODEL_DIR, 'feature_names.pkl')
FEATURES = joblib.load(feature_path) if os.path.exists(feature_path) else DEFAULT_FEATURES
FEATURES = list(FEATURES)
print("Loaded:", type(model).__name__, "| classes:", getattr(model, 'classes_', None))

expected = int(getattr(model, 'n_features_in_', len(FEATURES)))
if len(FEATURES) != expected:
    raise RuntimeError(
        f"feature_names.pkl has {len(FEATURES)} entries but the model expects {expected}"
    )

# A high-risk-ish sample
sample = {f: 0.0 for f in FEATURES}
sample.update({'daily_play_time_hours': 6.0, 'weekly_play_time_hours': 40.0,
               'late_night_play_ratio': 0.6,
               'binge_sessions_per_week': 3.0,
               'rapid_relogin_ratio': 0.7})

X = scaler.transform(pd.DataFrame([sample])[FEATURES])
explainer = shap.TreeExplainer(model)
arrs = per_class(explainer.shap_values(X))
print("shap_values -> %d class arrays of %d features" % (len(arrs), len(arrs[0])))

contrib = (arrs[1] * 0.5 + arrs[2] * 1.0) if len(arrs) >= 3 else arrs[-1]
order = np.argsort(np.abs(contrib))[::-1][:5]
print("\nTop SHAP factors (signed, + raises risk):")
for i in order:
    print(f"  {FEATURES[i]:<32} {contrib[i]:+.4f}  (value={sample[FEATURES[i]]})")

assert len(arrs[0]) == len(FEATURES), "feature count mismatch"
print("\nSHAP_CHECK_OK")
