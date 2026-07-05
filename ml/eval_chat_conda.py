"""
Evaluate (and optionally retrain) the chat-toxicity pipeline on REAL in-game chat.

Why: the deployed model is trained on a general toxicity corpus, and on a realistic
gaming stream its toxic precision collapses (documented in the model card). The fix is
gaming-DOMAIN data. The best free option is CONDA — ~45k utterances of real Dota 2
in-game chat with utterance-level labels (https://github.com/usydnlp/CONDA); any CSV of
game chat with a toxic/clean label works via the column flags below.

What it measures — the pipeline AS SERVED (clean_text -> TF-IDF -> LogReg [+ isotonic
calibration] fused with the keyword lexicon via noisy-OR, exactly like app.py):
  precision / recall / F1 at 0.5 and at the live alert threshold, PR-AUC, Brier,
  and a threshold sweep so the alert cut-off can be chosen from in-domain data.
Results land in model_metadata.json as `chat_metrics_gaming` (served by /api/model_card).

--retrain refits vectorizer + LogReg (+ a fresh isotonic calibration layer) on the
general corpus + the gaming TRAIN csv combined (balanced), and compares before/after
on a HELD-OUT gaming eval csv (--eval-csv) the new model never saw — never on the
training file itself. Saves the three pkls only with --save; re-run
ml/eval_chat_voice.py afterwards so the general-corpus metrics reflect the new model.

Usage (from the project root):
  python ml/eval_chat_conda.py --csv data/conda/CONDA_train.csv
  python ml/eval_chat_conda.py --csv data/conda/CONDA_train.csv \
         --retrain --eval-csv data/conda/CONDA_test.csv [--save]
  python ml/eval_chat_conda.py --csv my_gaming_chat.csv --text-col text --label-col toxic
  python ml/eval_chat_conda.py --smoke        # self-test on a tiny built-in sample
"""
import argparse
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import (precision_score, recall_score, f1_score,
                             average_precision_score, brier_score_loss,
                             matthews_corrcoef, roc_auc_score)

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(ROOT, 'data')
MODELS_DIR = os.path.join(ROOT, 'backend', 'models')
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from text_utils import clean_text, keyword_toxicity  # noqa: E402  (serving preprocessing)

ALERT_T = float(os.environ.get('CHAT_ALERT_T', '0.90'))   # must match backend/app.py's default


def _load(name):
    p = os.path.join(MODELS_DIR, name)
    if not os.path.exists(p):
        return None
    with open(p, 'rb') as f:
        return pickle.load(f)


def served_scores(texts, clf, vec, cal):
    """Toxicity exactly as app.py serves it: calibrated P(toxic) when available,
    fused with the keyword lexicon via noisy-OR."""
    model = cal if cal is not None else clf
    ml = model.predict_proba(vec.transform([clean_text(t) for t in texts]))[:, 1]
    kw = np.array([keyword_toxicity(t) for t in texts])
    return 1.0 - (1.0 - np.clip(kw, 0, 1)) * (1.0 - np.clip(ml, 0, 1))


def metrics_at(scores, y, thr):
    y_hat = (scores >= thr).astype(int)
    return {
        'threshold':       thr,
        'precision_toxic': round(float(precision_score(y, y_hat, zero_division=0)), 4),
        'recall_toxic':    round(float(recall_score(y, y_hat, zero_division=0)), 4),
        'f1_toxic':        round(float(f1_score(y, y_hat, zero_division=0)), 4),
        # MCC: a single balanced summary robust to class imbalance (uses all four
        # confusion cells), reported alongside the P/R pair rather than instead of it.
        'mcc':             round(float(matthews_corrcoef(y, y_hat)), 4),
    }


def load_csv(path, text_col, label_col, toxic_values):
    df = pd.read_csv(path)
    if text_col not in df.columns or label_col not in df.columns:
        sys.exit(f"Columns not found in {path}: {text_col!r}/{label_col!r}. "
                 f"Available: {list(df.columns)}")
    toxic_vals = {v.strip().lower() for v in toxic_values.split(',')}
    out = pd.DataFrame({
        'text':  df[text_col].astype(str),
        'toxic': df[label_col].astype(str).str.strip().str.lower()
                   .isin(toxic_vals).astype(int),
    })
    return out[out['text'].str.len() > 2].reset_index(drop=True)


SMOKE_ROWS = [
    ("gg well played everyone", 0), ("nice kill bro", 0), ("push mid now", 0),
    ("lets go team win this", 0), ("one more game then dinner", 0),
    ("care top missing", 0), ("wow what a clutch", 0), ("report this feeder noob", 1),
    ("you are trash uninstall the game idiot", 1), ("kys worthless player", 1),
    ("stupid team all garbage", 1), ("shut the fuck up and play", 1),
]


def load_dataset(args):
    if args.smoke:
        return pd.DataFrame(SMOKE_ROWS, columns=['text', 'toxic'])
    if not args.csv or not os.path.exists(args.csv):
        sys.exit("Dataset CSV not found. Get CONDA (real Dota 2 in-game chat, free):\n"
                 "  https://github.com/usydnlp/CONDA  -> save under data/conda/\n"
                 "then run with --csv data/conda/<file>.csv --text-col utterance "
                 "--label-col intentClass --toxic-values E,I\n"
                 "(Any gaming-chat CSV works — point --text-col/--label-col at it.)")
    return load_csv(args.csv, args.text_col, args.label_col, args.toxic_values)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', default=os.path.join(DATA_DIR, 'conda', 'conda_train.csv'))
    ap.add_argument('--text-col', default='utterance')
    ap.add_argument('--label-col', default='intentClass')
    ap.add_argument('--toxic-values', default='E,I',
                    help='label values that count as toxic (comma-separated, case-insensitive)')
    ap.add_argument('--retrain', action='store_true',
                    help='refit on general+gaming data combined and print before/after')
    ap.add_argument('--eval-csv', default=os.path.join(DATA_DIR, 'conda', 'CONDA_test.csv'),
                    help='held-out gaming set for the retrain before/after comparison')
    ap.add_argument('--save', action='store_true', help='with --retrain: overwrite the model pkls')
    ap.add_argument('--smoke', action='store_true', help='self-test on a tiny built-in sample')
    args = ap.parse_args()

    clf = _load('chat_model.pkl')
    vec = _load('tfidf_vectorizer.pkl')
    cal = _load('chat_calibrated.pkl')
    if clf is None or vec is None:
        sys.exit("chat_model.pkl / tfidf_vectorizer.pkl missing — run ml/retrain_models.py first")

    df = load_dataset(args)
    rate = float(df['toxic'].mean())
    print(f"Gaming-chat rows: {len(df)}  toxic base rate: {rate:.3f}")

    scores = served_scores(df['text'].tolist(), clf, vec, cal)
    y = df['toxic'].values

    sweep = [metrics_at(scores, y, t) for t in (0.3, 0.5, 0.6, 0.7, 0.85, 0.9, ALERT_T, 0.97)]
    best = max(sweep, key=lambda m: m['f1_toxic'])
    out = {
        'dataset': 'built-in smoke sample' if args.smoke else os.path.basename(args.csv),
        'rows': int(len(df)),
        'toxic_base_rate': round(rate, 4),
        'pr_auc': round(float(average_precision_score(y, scores)), 4),
        'roc_auc': round(float(roc_auc_score(y, scores)), 4),   # secondary: PR-AUC is
        'brier':  round(float(brier_score_loss(y, scores)), 4),  # primary under imbalance
        'at_threshold_0.5':  metrics_at(scores, y, 0.5),
        'at_alert_threshold': metrics_at(scores, y, ALERT_T),
        'threshold_sweep': sweep,
        'best_f1_threshold': best,
        'scoring': 'as served: clean_text -> TF-IDF -> LogReg'
                   + (' + isotonic' if cal is not None else '')
                   + ' fused with keyword lexicon (noisy-OR)',
        'note': ('In-DOMAIN evaluation on real in-game chat — the honest complement to '
                 'the general-corpus metrics in chat_metrics. Use best_f1_threshold to '
                 'inform CHAT_ALERT_T (env-overridable), alongside the false-alarm '
                 'evidence from ml/tune_from_feedback.py.'),
    }
    print(json.dumps(out, indent=2))

    if args.retrain:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.frozen import FrozenEstimator

        # NEVER score the retrained model on its own training file — require a
        # separate held-out gaming eval set for the before/after comparison.
        if not args.eval_csv or not os.path.exists(args.eval_csv):
            sys.exit("--retrain requires --eval-csv (a held-out gaming set, e.g. "
                     "data/conda/CONDA_test.csv) so the comparison isn't scored on "
                     "the training data.")
        eval_df = load_csv(args.eval_csv, args.text_col, args.label_col, args.toxic_values)
        y_eval  = eval_df['toxic'].values
        print(f"\nRETRAIN: general corpus + {os.path.basename(args.csv)} (train) "
              f"-> evaluate on {os.path.basename(args.eval_csv)} "
              f"({len(eval_df)} rows, base rate {y_eval.mean():.3f})")

        gen = pd.read_csv(os.path.join(DATA_DIR, 'chat_dataset.csv'))[['text', 'toxicity_score']].dropna()
        gen = pd.DataFrame({'text': gen['text'].astype(str),
                            'toxic': (gen['toxicity_score'] >= 0.5).astype(int)})
        pieces = [gen, df[['text', 'toxic']]]
        # Additional REAL corpora normalised to (text,toxic) — same sources the full
        # retrain pipeline (ml/retrain_models.py) includes, so the two paths agree.
        import glob as _glob
        for extra in sorted(_glob.glob(os.path.join(DATA_DIR, 'chat_extra', '*.csv'))):
            e = pd.read_csv(extra)
            if {'text', 'toxic'} <= set(e.columns):
                pieces.append(e[['text', 'toxic']])
                print(f"  including extra corpus: {len(e)} rows ({os.path.basename(extra)})")
        combo = pd.concat(pieces, ignore_index=True)
        combo['clean'] = combo['text'].map(clean_text)
        combo = combo[combo['clean'].str.len() > 2]
        tox = combo[combo['toxic'] == 1]
        cln = combo[combo['toxic'] == 0].sample(n=len(tox), random_state=42)
        bal = pd.concat([tox, cln]).sample(frac=1, random_state=42)
        # Same fit/calibration scheme as retrain_models.py: the isotonic layer is
        # fitted on a slice the LogReg never trained on.
        X_fit, X_cal, y_fit, y_cal = train_test_split(
            bal['clean'], bal['toxic'], test_size=0.15, random_state=42,
            stratify=bal['toxic'])
        # word + char_wb union — selected by held-out bake-off (see retrain_models.py)
        from sklearn.pipeline import FeatureUnion
        v2 = FeatureUnion([
            ('word', TfidfVectorizer(max_features=20000, ngram_range=(1, 2), min_df=2,
                                     sublinear_tf=True, strip_accents='unicode')),
            ('char', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5),
                                     max_features=30000, min_df=2, sublinear_tf=True)),
        ])
        c2 = LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000,
                                class_weight='balanced', random_state=42, n_jobs=-1)
        c2.fit(v2.fit_transform(X_fit), y_fit)
        cal2 = CalibratedClassifierCV(FrozenEstimator(c2), method='isotonic')
        cal2.fit(v2.transform(X_cal), y_cal)

        before = served_scores(eval_df['text'].tolist(), clf, vec, cal)
        after  = served_scores(eval_df['text'].tolist(), c2, v2, cal2)
        comp = {
            'eval_set': os.path.basename(args.eval_csv),
            'rows': int(len(eval_df)),
            'pr_auc':  {'before': round(float(average_precision_score(y_eval, before)), 4),
                        'after':  round(float(average_precision_score(y_eval, after)), 4)},
            'at_alert_threshold': {'before': metrics_at(before, y_eval, ALERT_T),
                                   'after':  metrics_at(after, y_eval, ALERT_T)},
            'after_sweep': [metrics_at(after, y_eval, t)
                            for t in (0.5, 0.6, 0.7, 0.75, ALERT_T, 0.9)],
        }
        print(json.dumps(comp, indent=2))

        if args.save:
            with open(os.path.join(MODELS_DIR, 'chat_model.pkl'), 'wb') as f:
                pickle.dump(c2, f)
            with open(os.path.join(MODELS_DIR, 'tfidf_vectorizer.pkl'), 'wb') as f:
                pickle.dump(v2, f)
            with open(os.path.join(MODELS_DIR, 'chat_calibrated.pkl'), 'wb') as f:
                pickle.dump(cal2, f)
            print("[OK] saved retrained chat model + vectorizer + calibration.\n"
                  "     Re-run ml/eval_chat_voice.py (general metrics) and this script's "
                  "eval mode on the eval csv (chat_metrics_gaming) so the model card "
                  "reflects the new model.")
        else:
            print("(dry run — pass --save to overwrite the deployed pkls)")

    if not args.smoke:
        meta_path = os.path.join(MODELS_DIR, 'model_metadata.json')
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
        meta['chat_metrics_gaming'] = out
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
        print("\n[OK] chat_metrics_gaming written into model_metadata.json")


if __name__ == '__main__':
    main()
