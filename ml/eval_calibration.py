# -*- coding: utf-8 -*-
"""Expected Calibration Error (ECE) + reliability diagrams for the two calibrated
channels — the direct calibration evidence the paper's Brier figures only imply.

Why this exists: Brier score is a *proper score* that decomposes (Murphy) into
calibration AND refinement terms, so a Brier improvement does not by itself prove
the probabilities are calibrated — a sharper-but-biased model can win on Brier.
ECE measures calibration directly: bin predictions by confidence and average
|confidence - accuracy| over bins. Reliability diagrams show the same thing
visually (the diagonal is perfect calibration).

Protocol: reuses the EXACT splits the deployed calibrators were fitted with, so
these numbers sit alongside the existing Brier figures rather than beside them:
  behaviour — generate_behavior_dataset(25000), 80/20 seed 42, then the held-out
              half-split seed 7 (calibrate_behavior.py's eval half; the RF never
              saw it and neither did the isotonic layer)
  chat      — assemble_chat_dataset(dedupe=True), balanced, 80/20 seed 42
              (retrain_models.py's held-out split)

Outputs: `calibration_eval` in backend/models/model_metadata.json and
docs/figures/reliability.pdf.

Usage: python ml/eval_calibration.py
"""
import json
import os
import pickle
import sys

import joblib
import numpy as np
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, 'backend', 'models')
FIGS = os.path.join(ROOT, 'docs', 'figures')
sys.path.insert(0, os.path.join(ROOT, 'ml'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

N_BINS = 10


def ece_mce(confidences, correct, n_bins=N_BINS):
    """Expected and Maximum Calibration Error over equal-width confidence bins.

    confidences: predicted probability of the PREDICTED class (top-label ECE for
    multiclass; the positive-class probability for binary).
    correct:     1 when that prediction was right.
    Returns (ece, mce, per-bin rows) — bins with no samples are skipped, and each
    bin is weighted by its share of the data, which is what makes ECE an average
    miscalibration rather than a worst case.
    """
    confidences = np.asarray(confidences, dtype=float)
    correct = np.asarray(correct, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece, mce, rows = 0.0, 0.0, []
    n = len(confidences)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (confidences > lo) & (confidences <= hi) if lo > 0 else (confidences >= lo) & (confidences <= hi)
        if not m.any():
            continue
        conf, acc, w = confidences[m].mean(), correct[m].mean(), m.sum() / n
        gap = abs(conf - acc)
        ece += w * gap
        mce = max(mce, gap)
        rows.append({'bin': [round(float(lo), 2), round(float(hi), 2)],
                     'n': int(m.sum()), 'confidence': round(float(conf), 4),
                     'accuracy': round(float(acc), 4), 'gap': round(float(gap), 4)})
    return float(ece), float(mce), rows


def behaviour_arrays():
    """(raw_proba, cal_proba, y) on the calibrator's own eval half."""
    from retrain_models import generate_behavior_dataset
    rf = joblib.load(os.path.join(MODELS, 'behavior_model.pkl'))
    scaler = joblib.load(os.path.join(MODELS, 'feature_scaler.pkl'))
    cal = joblib.load(os.path.join(MODELS, 'behavior_calibrated.pkl'))
    df, names = generate_behavior_dataset(25000)
    feats = names[:int(rf.n_features_in_)]
    X, y = df[feats].values, df['addiction_label'].values
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    _, X_eval, _, y_eval = train_test_split(X_test, y_test, test_size=0.5,
                                            random_state=7, stratify=y_test)
    Xe = scaler.transform(X_eval)
    return rf.predict_proba(Xe), cal.predict_proba(Xe), y_eval, rf.classes_


def chat_arrays():
    """(raw_proba, cal_proba, y) on the trainer's held-out split."""
    from retrain_models import assemble_chat_dataset
    with open(os.path.join(MODELS, 'chat_model.pkl'), 'rb') as f:
        clf = pickle.load(f)
    with open(os.path.join(MODELS, 'chat_calibrated.pkl'), 'rb') as f:
        cal = pickle.load(f)
    with open(os.path.join(MODELS, 'tfidf_vectorizer.pkl'), 'rb') as f:
        vec = pickle.load(f)
    df = assemble_chat_dataset(verbose=False, dedupe=True)
    tox = df[df['toxic'] == 1]
    cln = df[df['toxic'] == 0].sample(n=len(tox), random_state=42)
    bal = __import__('pandas').concat([tox, cln]).sample(frac=1, random_state=42)
    _, X_te, _, y_te = train_test_split(bal['text'], bal['toxic'], test_size=0.2,
                                        random_state=42, stratify=bal['toxic'])
    Xv = vec.transform(X_te)
    return clf.predict_proba(Xv), cal.predict_proba(Xv), y_te.values, clf.classes_


def summarise(name, raw, calp, y, classes):
    out = {}
    for tag, proba in (('uncalibrated', raw), ('calibrated', calp)):
        idx = proba.argmax(axis=1)
        conf = proba[np.arange(len(idx)), idx]
        correct = (np.asarray(classes)[idx] == y).astype(float)
        ece, mce, rows = ece_mce(conf, correct)
        out[tag] = {'ece': round(ece, 4), 'mce': round(mce, 4), 'bins': rows}
        print(f"  {name:9s} {tag:12s} ECE {ece:.4f}   MCE {mce:.4f}")
    out['ece_improvement'] = round(out['uncalibrated']['ece'] - out['calibrated']['ece'], 4)
    out['n_eval'] = int(len(y))
    out['n_bins'] = N_BINS
    return out


def reliability_figure(panels):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(panels), figsize=(4.4 * len(panels), 3.5))
    if len(panels) == 1:
        axes = [axes]
    for ax, (title, res) in zip(axes, panels):
        ax.plot([0, 1], [0, 1], ls=':', color='#6b7280', lw=1, label='perfect')
        for tag, colour, mark in (('uncalibrated', '#b45309', 's'), ('calibrated', '#1d4ed8', 'o')):
            rows = res[tag]['bins']
            if not rows:
                continue
            ax.plot([r['confidence'] for r in rows], [r['accuracy'] for r in rows],
                    marker=mark, color=colour, lw=1.6, ms=4,
                    label=f"{tag} (ECE {res[tag]['ece']:.3f})")
        ax.set_title(title, fontsize=9)
        ax.set_xlabel('Predicted confidence')
        ax.set_ylabel('Observed accuracy')
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.grid(True, color='#e5e7eb', lw=0.6)
        ax.set_axisbelow(True)
        ax.legend(loc='upper left', frameon=False, fontsize=7)
    fig.tight_layout()
    os.makedirs(FIGS, exist_ok=True)
    fig.savefig(os.path.join(FIGS, 'reliability.pdf'))
    plt.close(fig)
    print('[OK] docs/figures/reliability.pdf')


def main():
    print('Expected Calibration Error (10 equal-width bins, top-label)')
    result = {}
    b_raw, b_cal, b_y, b_cls = behaviour_arrays()
    result['behaviour'] = summarise('behaviour', b_raw, b_cal, b_y, b_cls)
    c_raw, c_cal, c_y, c_cls = chat_arrays()
    result['chat'] = summarise('chat', c_raw, c_cal, c_y, c_cls)
    result['note'] = ('Top-label ECE/MCE on the same held-out splits the deployed '
                      'calibrators were fitted against. ECE measures calibration '
                      'directly; the Brier figures elsewhere mix calibration with '
                      'refinement.')
    reliability_figure([('Behaviour (3-class)', result['behaviour']),
                        ('Chat (binary)', result['chat'])])
    path = os.path.join(MODELS, 'model_metadata.json')
    meta = json.load(open(path)) if os.path.exists(path) else {}
    meta['calibration_eval'] = result
    with open(path, 'w') as f:
        json.dump(meta, f, indent=2)
    print('[OK] calibration_eval written into model_metadata.json')


if __name__ == '__main__':
    main()
