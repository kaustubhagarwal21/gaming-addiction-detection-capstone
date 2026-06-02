"""
Honest per-model evaluation for the CHAT and VOICE models, written into
backend/models/model_metadata.json (chat_metrics / voice_metrics) so /api/model_card
can report them. Only the behaviour model had stored metrics before; this closes the
gap the review flagged.

Key honesty points:
- Chat is reported on TWO sets: (a) the balanced held-out split it was tested on
  (optimistic), and (b) a REALISTIC, naturally-imbalanced held-out set the model never
  trained on (the truthful view — this is where toxic precision is low). Both at the
  default 0.5 cut and at the live alert threshold (0.75).
- Voice is reported on a held-out split of SYNTHETIC features — clearly labelled as such,
  because the model is not trained on real audio.

Splits are reproduced with the SAME seeds as ml/retrain_models.py, so the test rows are
genuinely held out from the deployed models (no train leakage).
"""
import os, sys, json, pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (precision_score, recall_score, f1_score,
                             accuracy_score, confusion_matrix)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(ROOT, 'data')
MODELS_DIR = os.path.join(ROOT, 'backend', 'models')
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from text_utils import clean_text   # the exact serving preprocessing

ALERT_T = 0.75   # must match CHAT_ALERT_T in backend/app.py


def _load(name):
    with open(os.path.join(MODELS_DIR, name), 'rb') as f:
        return pickle.load(f)


def eval_chat():
    print("=" * 60, "\nCHAT MODEL EVAL\n", "=" * 60)
    df = pd.read_csv(os.path.join(DATA_DIR, 'chat_dataset.csv'))
    df = df[['text', 'toxicity_score']].dropna()
    df['text'] = df['text'].astype(str).map(clean_text)
    df = df[df['text'].str.len() > 2]
    df['toxic'] = (df['toxicity_score'] >= 0.5).astype(int)

    # Reproduce the balanced training subset + split EXACTLY (retrain_models.py seeds).
    toxic_df    = df[df['toxic'] == 1]
    nontoxic_df = df[df['toxic'] == 0].sample(n=len(toxic_df), random_state=42)
    df_bal = pd.concat([toxic_df, nontoxic_df]).sample(frac=1, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(
        df_bal['text'], df_bal['toxic'], test_size=0.2, random_state=42, stratify=df_bal['toxic'])

    clf = _load('chat_model.pkl')
    vec = _load('tfidf_vectorizer.pkl')

    def metrics(texts, y_true, thr):
        proba = clf.predict_proba(vec.transform(texts))[:, 1]
        y_hat = (proba >= thr).astype(int)
        return {
            'precision_toxic': round(float(precision_score(y_true, y_hat, zero_division=0)), 4),
            'recall_toxic':    round(float(recall_score(y_true, y_hat, zero_division=0)), 4),
            'f1_toxic':        round(float(f1_score(y_true, y_hat, zero_division=0)), 4),
            'accuracy':        round(float(accuracy_score(y_true, y_hat)), 4),
            'confusion':       confusion_matrix(y_true, y_hat).tolist(),  # [[TN,FP],[FN,TP]]
        }

    # (a) balanced held-out split (optimistic, what it was tested on)
    bal = metrics(X_test, y_test, 0.5)

    # (b) realistic held-out: every row NOT used in training, at natural imbalance
    realistic = df.drop(index=X_train.index)
    rate = round(float(realistic['toxic'].mean()), 4)
    real_05 = metrics(realistic['text'], realistic['toxic'], 0.5)
    real_75 = metrics(realistic['text'], realistic['toxic'], ALERT_T)

    out = {
        'model': 'LogisticRegression + TF-IDF (1-2gram)',
        'balanced_holdout': bal,
        'realistic_holdout': {
            'toxic_base_rate': rate,
            'at_threshold_0.5':       real_05,
            'at_alert_threshold_0.75': real_75,
        },
        'note': ('Balanced split flatters the model; the realistic set reflects the true '
                 '~imbalanced stream. Toxic precision is low at 0.5 (the model over-flags '
                 'gaming language), which is exactly why the live alert threshold is 0.75 '
                 '(higher precision, lower recall). The real fix is real gaming-chat data.'),
        'confusion_labels': ['clean', 'toxic'],
        'eval': 'Held-out rows the deployed model never trained on (seeds match retrain).',
    }
    print(json.dumps(out, indent=2))
    return out


def generate_voice_dataset(n=8000, seed=42):
    """Identical to ml/retrain_models.generate_voice_dataset (same seed => same data)."""
    rng = np.random.default_rng(seed)
    classes = ['neutral', 'excited', 'frustrated', 'angry']
    params = {
        'neutral':    dict(m0=(-20, 5), pitch=(120, 20), energy=(0.04, 0.01)),
        'excited':    dict(m0=(-15, 5), pitch=(200, 40), energy=(0.10, 0.03)),
        'frustrated': dict(m0=(-25, 5), pitch=(150, 30), energy=(0.08, 0.02)),
        'angry':      dict(m0=(-30, 5), pitch=(180, 50), energy=(0.15, 0.04)),
    }
    rows, labels = [], []
    per_class = n // len(classes)
    for cls in classes:
        p = params[cls]
        mfcc0 = rng.normal(p['m0'][0], p['m0'][1], per_class)
        mfccs = rng.normal(0, 8, (per_class, 12))
        pitch_mean = rng.normal(p['pitch'][0], p['pitch'][1] / 2, per_class)
        pitch_std  = rng.normal(p['pitch'][1], 5, per_class)
        e_mean     = rng.normal(p['energy'][0], p['energy'][1] / 2, per_class)
        e_std      = rng.normal(p['energy'][1], 0.005, per_class)
        feats = np.column_stack([mfcc0.reshape(-1, 1), mfccs, pitch_mean, pitch_std, e_mean, e_std])
        rows.append(feats)
        labels.extend([cls] * per_class)
    return np.vstack(rows), np.array(labels)


def eval_voice():
    print("=" * 60, "\nVOICE MODEL EVAL\n", "=" * 60)
    X, y = generate_voice_dataset(8000, seed=42)
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    clf = _load('voice_model.pkl')
    y_hat = clf.predict(X_test)
    labels = ['neutral', 'excited', 'frustrated', 'angry']
    out = {
        'model': 'GradientBoosting on 17 acoustic features (synthetic)',
        'accuracy':  round(float(accuracy_score(y_test, y_hat)), 4),
        'macro_f1':  round(float(f1_score(y_test, y_hat, average='macro')), 4),
        'per_class_precision': {l: round(float(precision_score(y_test, y_hat, labels=[l], average='micro', zero_division=0)), 4) for l in labels},
        'per_class_recall':    {l: round(float(recall_score(y_test, y_hat, labels=[l], average='micro', zero_division=0)), 4) for l in labels},
        'confusion': confusion_matrix(y_test, y_hat, labels=labels).tolist(),
        'confusion_labels': labels,
        'eval': 'Held-out 20% split (seed=42).',
        'note': ('Trained and evaluated on SYNTHETIC acoustic features, not real microphone '
                 'audio — so this high accuracy is internal validity only; real-world voice '
                 'accuracy is unproven. Lowest ensemble weight for this reason.'),
    }
    print(json.dumps(out, indent=2))
    return out


def main():
    chat = eval_chat()
    voice = eval_voice()
    meta_path = os.path.join(MODELS_DIR, 'model_metadata.json')
    with open(meta_path) as f:
        meta = json.load(f)
    meta['chat_metrics'] = chat
    meta['voice_metrics'] = voice
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print("\n[OK] Wrote chat_metrics + voice_metrics into model_metadata.json")


if __name__ == '__main__':
    main()
