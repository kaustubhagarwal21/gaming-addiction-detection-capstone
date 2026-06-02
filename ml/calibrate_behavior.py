"""
Post-training probability calibration for the behaviour model.

The RandomForest is trained by retrain_models.py. Run this AFTER it: it fits an
ISOTONIC calibrator on a held-out split so the served 0-1 risk probabilities are
better calibrated — WITHOUT retraining or modifying the RF. The RF stays the exact
model that SHAP and feature-importances explain (behavior_model.pkl is untouched);
the calibrator (behavior_calibrated.pkl) is an additive layer the backend applies
for the probability/score only, falling back to the raw RF if it's missing.

Reports the multiclass Brier-score change on a separate evaluation split.

Run from the project root:  python ml/calibrate_behavior.py
"""
import os, sys, json, pickle, joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator  # sklearn >= 1.6: marks an estimator as prefit

MODELS = os.path.join(os.path.dirname(__file__), '..', 'backend', 'models')
sys.path.insert(0, os.path.dirname(__file__))
from retrain_models import generate_behavior_dataset


def multiclass_brier(proba, y, n_classes):
    """Standard multiclass Brier score: mean over samples of sum_k (p_k - 1[y=k])^2.
    Lower is better; 0 = perfect."""
    onehot = np.eye(n_classes)[y]
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


def main():
    rf     = joblib.load(os.path.join(MODELS, 'behavior_model.pkl'))
    scaler = joblib.load(os.path.join(MODELS, 'feature_scaler.pkl'))

    # Reproduce the EXACT train/test split (seed=42) so the RF never saw X_test.
    df, feature_names = generate_behavior_dataset(25000)
    X = df[feature_names].values
    y = df['addiction_label'].values
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # Split the held-out test set: half to fit the calibrator, half to evaluate it.
    X_cal, X_eval, y_cal, y_eval = train_test_split(
        X_test, y_test, test_size=0.5, random_state=7, stratify=y_test)

    Xc, Xe = scaler.transform(X_cal), scaler.transform(X_eval)

    # Calibrate the already-fitted RF (FrozenEstimator => not refit) on the calib half.
    calibrated = CalibratedClassifierCV(FrozenEstimator(rf), method='isotonic')
    calibrated.fit(Xc, y_cal)

    n = len(rf.classes_)
    brier_raw = multiclass_brier(rf.predict_proba(Xe), y_eval, n)
    brier_cal = multiclass_brier(calibrated.predict_proba(Xe), y_eval, n)
    acc_raw = float((rf.predict(Xe) == y_eval).mean())
    acc_cal = float((calibrated.predict(Xe) == y_eval).mean())
    print(f"Eval samples: {len(y_eval)}")
    print(f"Brier (multiclass)  raw={brier_raw:.4f}  calibrated={brier_cal:.4f}  "
          f"({(brier_raw - brier_cal) / brier_raw * 100:+.1f}%)")
    print(f"Accuracy            raw={acc_raw:.4f}  calibrated={acc_cal:.4f}")

    with open(os.path.join(MODELS, 'behavior_calibrated.pkl'), 'wb') as f:
        pickle.dump(calibrated, f)
    print("[OK] saved behavior_calibrated.pkl")

    meta_path = os.path.join(MODELS, 'model_metadata.json')
    with open(meta_path) as f:
        meta = json.load(f)
    meta['calibration'] = {
        'method': 'isotonic',
        'fit': 'held-out split the RF never trained on (FrozenEstimator, prefit)',
        'brier_uncalibrated': round(brier_raw, 4),
        'brier_calibrated':   round(brier_cal, 4),
        'eval_samples':       int(len(y_eval)),
        'note': 'Calibrates the served probability only; the RF used for SHAP/'
                'feature-importances is unchanged.',
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print("[OK] metadata updated with calibration block")


if __name__ == '__main__':
    main()
