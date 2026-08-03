"""Held-out Devanagari/Hindi abuse evaluation for the SERVED chat pipeline.

The HASOC 2019 Hindi corpus (Mandl et al., FIRE 2019; HOF/NOT labels) was adopted
into the training assembly as data/chat_extra/hasoc2019_hindi.csv — an 80% split
(stratified, seed 42). The remaining 20% lives OUTSIDE chat_extra (so the trainer
can never ingest it) at data/hasoc2019_hindi_heldout.csv and is scored here with
the exact serving formula (calibrated model noisy-OR keyword lexicon).
Both files are rebuilt deterministically by ml/fetch_hasoc_hindi.py (the corpus is
registration-gated upstream, so this public repo does not redistribute the rows).

Adoption experiment (2026-08-04, pre-adoption deployed model vs candidate):
  deployed  — HASOC held-out PR-AUC 0.579, precision/recall @0.95 = 0.000/0.000
  candidate — HASOC held-out PR-AUC 0.875, precision/recall @0.95 = 0.948/0.439
  CONDA in-domain held within CI (0.826 vs 0.833) with recall UP (+0.089).
Writes chat_metrics_hindi into backend/models/model_metadata.json.
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_score, recall_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, 'backend', 'models')
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from text_utils import clean_text, keyword_toxicity  # noqa: E402

ALERT_T = float(os.environ.get('CHAT_ALERT_T', '0.95'))


def _load(name):
    with open(os.path.join(MODELS_DIR, name), 'rb') as f:
        return pickle.load(f)


def main():
    df = pd.read_csv(os.path.join(ROOT, 'data', 'hasoc2019_hindi_heldout.csv'))
    texts, y = df['text'].astype(str).tolist(), df['toxic'].values
    vec = _load('tfidf_vectorizer.pkl')
    cal_path = os.path.join(MODELS_DIR, 'chat_calibrated.pkl')
    served = _load('chat_calibrated.pkl') if os.path.exists(cal_path) else _load('chat_model.pkl')

    ml = served.predict_proba(vec.transform([clean_text(t) for t in texts]))[:, 1]
    kw = np.array([keyword_toxicity(t) for t in texts])
    s = 1.0 - (1.0 - ml) * (1.0 - kw)          # noisy-OR, exactly as app.py serves
    yh = (s >= ALERT_T).astype(int)

    res = {
        'eval_set': 'HASOC 2019 Hindi held-out 20% (933 rows, never trained on)',
        'n': len(y), 'toxic_rate': round(float(np.mean(y)), 4),
        'pr_auc': round(float(average_precision_score(y, s)), 4),
        'precision@alert': round(float(precision_score(y, yh, zero_division=0)), 4),
        'recall@alert': round(float(recall_score(y, yh, zero_division=0)), 4),
        'alert_threshold': ALERT_T,
        'scoring': 'as served: clean_text -> TF-IDF -> LogReg + isotonic, noisy-OR keyword fusion',
    }
    print(json.dumps(res, indent=2))
    meta_path = os.path.join(MODELS_DIR, 'model_metadata.json')
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    meta['chat_metrics_hindi'] = res
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print('[OK] chat_metrics_hindi written into model_metadata.json')


if __name__ == '__main__':
    main()
