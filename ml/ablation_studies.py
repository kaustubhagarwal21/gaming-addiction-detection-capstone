"""
Ablation studies for all three channels — what does each design choice actually buy?

Every row removes ONE component from the deployed recipe (or swaps the dataset it
depends on) and re-measures on the same held-out data, so the delta is attributable.
Headline metrics carry bootstrap 95% confidence intervals (1,000 resamples of the
test set), and the chat table adds ROC-AUC and MCC at the operating point alongside
PR-AUC — PR-AUC remains primary because the serving stream is imbalanced.

  CHAT   (held-out CONDA_valid, served fusion unless ablated):
    full recipe / -keyword fusion / -calibration / -char_wb n-grams /
    -Davidson / -CONDA (domain data) / original (general corpus, word-only)
  VOICE  (speaker-independent split, HistGradientBoosting):
    36 features / 17-feature prefix / -augmentation / English-only corpora
  BEHAVIOUR (synthetic, survey-grounded generator):
    objective-10 / all-20 / volume-features-only / pattern-features-only

Writes docs/ablation_results.json and caches per-example chat scores for the PR-curve
figure (ml/make_figures.py). Run from the project root (~10-15 min, mostly chat
retrains):  python ml/ablation_studies.py
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from text_utils import clean_text, keyword_toxicity  # noqa: E402

from sklearn.calibration import CalibratedClassifierCV                     # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer                # noqa: E402
from sklearn.frozen import FrozenEstimator                                 # noqa: E402
from sklearn.linear_model import LogisticRegression                        # noqa: E402
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score,  # noqa: E402
                             matthews_corrcoef, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, train_test_split    # noqa: E402
from sklearn.pipeline import FeatureUnion                                  # noqa: E402
from sklearn.preprocessing import StandardScaler                           # noqa: E402

DATA    = os.path.join(ROOT, 'data')
DOCS    = os.path.join(ROOT, 'docs')
ALERT_T = float(os.environ.get('CHAT_ALERT_T', '0.90'))
SEED    = 42


def boot_ci(metric_fn, y, s, n=1000, seed=SEED):
    """Bootstrap 95% CI for metric_fn(y, s) over test-set resamples."""
    rng = np.random.default_rng(seed)
    y, s = np.asarray(y), np.asarray(s)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) < 2:
            continue
        vals.append(metric_fn(y[idx], s[idx]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


# ══════════════════════════ CHAT ═══════════════════════════════════

def load_norm(path, text_col='utterance', label_col='intentClass', toxic_vals=('E', 'I')):
    df = pd.read_csv(path)
    if 'text' in df.columns and 'toxic' in df.columns:
        out = df[['text', 'toxic']].copy()
    else:
        out = pd.DataFrame({'text': df[text_col].astype(str),
                            'toxic': df[label_col].astype(str).str.strip().str.upper()
                                       .isin(set(toxic_vals)).astype(int)})
    out['text'] = out['text'].astype(str)
    return out[out['text'].str.len() > 2].reset_index(drop=True)


def chat_sources():
    gen = pd.read_csv(os.path.join(DATA, 'chat_dataset.csv'))[['text', 'toxicity_score']].dropna()
    gen = pd.DataFrame({'text': gen['text'].astype(str),
                        'toxic': (gen['toxicity_score'] >= 0.5).astype(int)})
    conda = load_norm(os.path.join(DATA, 'conda', 'CONDA_train.csv'))
    dav   = load_norm(os.path.join(DATA, 'chat_extra', 'davidson_offensive.csv'))
    return {'gen': gen, 'conda': conda, 'davidson': dav}


def make_vec(char_ngrams=True):
    word = TfidfVectorizer(max_features=20000, ngram_range=(1, 2), min_df=2,
                           sublinear_tf=True, strip_accents='unicode')
    if not char_ngrams:
        return word
    return FeatureUnion([('word', word),
                         ('char', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5),
                                                  max_features=30000, min_df=2,
                                                  sublinear_tf=True))])


def train_chat(sources, use, char_ngrams=True, calibrated=True):
    """Deployed training recipe on the chosen source subset."""
    combo = pd.concat([sources[k][['text', 'toxic']] for k in use], ignore_index=True)
    combo['clean'] = combo['text'].map(clean_text)
    combo = combo[combo['clean'].str.len() > 2]
    tox = combo[combo['toxic'] == 1]
    cln = combo[combo['toxic'] == 0].sample(n=len(tox), random_state=SEED)
    bal = pd.concat([tox, cln]).sample(frac=1, random_state=SEED)
    X_fit, X_cal, y_fit, y_cal = train_test_split(bal['clean'], bal['toxic'],
                                                  test_size=0.15, random_state=SEED,
                                                  stratify=bal['toxic'])
    vec = make_vec(char_ngrams)
    clf = LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced',
                             random_state=SEED, n_jobs=-1)
    clf.fit(vec.fit_transform(X_fit), y_fit)
    cal = None
    if calibrated:
        cal = CalibratedClassifierCV(FrozenEstimator(clf), method='isotonic')
        cal.fit(vec.transform(X_cal), y_cal)
    return clf, vec, cal


def chat_scores(texts, clf, vec, cal, kw_fusion=True):
    model = cal if cal is not None else clf
    ml = model.predict_proba(vec.transform([clean_text(t) for t in texts]))[:, 1]
    if not kw_fusion:
        return ml
    kw = np.array([keyword_toxicity(t) for t in texts])
    return 1.0 - (1.0 - np.clip(kw, 0, 1)) * (1.0 - np.clip(ml, 0, 1))


def chat_row(name, y, s):
    yh = (s >= ALERT_T).astype(int)
    lo, hi = boot_ci(average_precision_score, y, s)
    return {'config': name,
            'pr_auc': round(float(average_precision_score(y, s)), 4),
            'pr_auc_ci95': [lo, hi],
            'roc_auc': round(float(roc_auc_score(y, s)), 4),
            'precision@alert': round(float(precision_score(y, yh, zero_division=0)), 4),
            'recall@alert': round(float(recall_score(y, yh, zero_division=0)), 4),
            'f1@alert': round(float(f1_score(y, yh, zero_division=0)), 4),
            'mcc@alert': round(float(matthews_corrcoef(y, yh)), 4)}


def ablate_chat():
    print('=' * 66, '\nCHAT ABLATIONS  (held-out CONDA_valid)\n', '=' * 66)
    src = chat_sources()
    evald = load_norm(os.path.join(DATA, 'conda', 'CONDA_valid.csv'))
    y = evald['toxic'].values
    texts = evald['text'].tolist()

    full_clf, full_vec, full_cal = train_chat(src, ('gen', 'conda', 'davidson'))
    configs, score_cache = [], {}

    def add(name, s):
        configs.append(chat_row(name, y, s))
        score_cache[name] = s
        print(f"  {name:<34} PR-AUC {configs[-1]['pr_auc']:.4f} "
              f"CI {configs[-1]['pr_auc_ci95']}  P@{ALERT_T} {configs[-1]['precision@alert']:.3f}")

    add('full recipe (deployed)', chat_scores(texts, full_clf, full_vec, full_cal))
    add('- keyword fusion', chat_scores(texts, full_clf, full_vec, full_cal, kw_fusion=False))
    add('- calibration', chat_scores(texts, full_clf, full_vec, None))
    c, v, k = train_chat(src, ('gen', 'conda', 'davidson'), char_ngrams=False)
    add('- char_wb n-grams', chat_scores(texts, c, v, k))
    c, v, k = train_chat(src, ('gen', 'conda'))
    add('- Davidson corpus', chat_scores(texts, c, v, k))
    c, v, k = train_chat(src, ('gen', 'davidson'))
    add('- CONDA corpus (domain data)', chat_scores(texts, c, v, k))
    c, v, k = train_chat(src, ('gen',), char_ngrams=False)
    add('original (general-only, word-only)', chat_scores(texts, c, v, k))

    np.savez_compressed(os.path.join(DOCS, 'figures', 'chat_scores_cache.npz'),
                        y=y, **{k.replace(' ', '_'): v for k, v in score_cache.items()})
    return configs


# ══════════════════════════ VOICE ══════════════════════════════════

def ablate_voice(jobs=8):
    """One FIXED test set — the un-augmented clips of held-out speakers — and one
    variable changed per row on the TRAINING side only. (A first draft compared
    configs on different test sets, which confounds every delta; and training sets
    are class-balanced exactly like the deployed trainer.)"""
    print('=' * 66, '\nVOICE ABLATIONS  (speaker-independent, fixed original-clip test set)\n', '=' * 66)
    from train_voice_real import build_dataset, collect_files

    class A:   # mirror the trainer's default corpus dirs
        ravdess = os.path.join(DATA, 'voice', 'RAVDESS')
        cremad  = os.path.join(DATA, 'voice', 'CREMA-D')
        extra   = [os.path.join(DATA, 'voice', 'EMO-DB'), os.path.join(DATA, 'voice', 'URDU')]
        limit   = 0
    labelled = collect_files(A)
    X1, y1, g1, _ = build_dataset(labelled, n_aug=1, jobs=jobs)   # originals + augmented
    X0, y0, g0, _ = build_dataset(labelled, n_aug=0, jobs=jobs)   # originals only

    # Split SPEAKERS once; every row derives its side from its speaker.
    tr_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2,
                                            random_state=SEED).split(X0, y0, g0))
    te_speakers = set(g0[te_idx])
    te0 = np.isin(g0, list(te_speakers))
    X_test, y_test = X0[te0], y0[te0]              # fixed: original clips, unseen speakers
    print(f"  fixed test set: {len(y_test)} original clips from {len(te_speakers)} unseen speakers")

    rng = np.random.default_rng(SEED)

    def bal_idx(y):
        n_min = min(int((y == c).sum()) for c in np.unique(y))
        idx = []
        for c in np.unique(y):
            rows = np.where(y == c)[0]
            idx.extend(rng.choice(rows, size=n_min, replace=False))
        return np.array(sorted(idx))

    def run(name, X_pool, y_pool, g_pool, feat_slice=None, corpus_prefixes=None):
        m = ~np.isin(g_pool, list(te_speakers))    # training side only
        if corpus_prefixes is not None:
            m &= np.isin([g[:3] for g in g_pool], corpus_prefixes)
        X_tr, y_tr = X_pool[m], y_pool[m]
        bi = bal_idx(y_tr)
        X_tr, y_tr = X_tr[bi], y_tr[bi]
        X_te = X_test
        if feat_slice is not None:
            X_tr, X_te = X_tr[:, feat_slice], X_test[:, feat_slice]
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1,
                                             random_state=SEED)
        clf.fit(X_tr, y_tr)
        y_hat = clf.predict(X_te)
        acc = accuracy_score(y_test, y_hat)
        lo, hi = boot_ci(lambda a, b: accuracy_score(a, b), y_test, y_hat)
        row = {'config': name, 'accuracy': round(float(acc), 4), 'acc_ci95': [lo, hi],
               'macro_f1': round(float(f1_score(y_test, y_hat, average='macro')), 4),
               'train_rows': int(len(y_tr)), 'test_rows': int(len(y_test))}
        print(f"  {name:<38} acc {row['accuracy']:.4f} CI {row['acc_ci95']} "
              f"macroF1 {row['macro_f1']:.4f}")
        return row

    return [
        run('full (36 feats, 4 corpora, aug x1)', X1, y1, g1),
        run('17-feature prefix', X1, y1, g1, feat_slice=slice(0, 17)),
        run('- augmentation', X0, y0, g0),
        run('English-only training corpora', X1, y1, g1, corpus_prefixes=['RAV', 'CRE']),
    ]


# ═══════════════════════ BEHAVIOUR ═════════════════════════════════

def ablate_behavior():
    print('=' * 66, '\nBEHAVIOUR ABLATIONS  (synthetic, survey-grounded generator)\n', '=' * 66)
    from retrain_models import generate_behavior_dataset
    df, names = generate_behavior_dataset(25000)
    groupsets = {
        # THE THESIS BASELINE. The project's core claim is "multimodal behaviour
        # patterns beat screen-time alone" — so the table must contain screen-time
        # alone. Deliberately given its best shot (both hours features + the same
        # model family and protocol as every other row): if the full feature set
        # still wins against a well-fit hours model, the claim is measured, not
        # asserted.
        'screen-time only (hours, the baseline)': ['daily_play_time_hours',
                                                   'weekly_play_time_hours'],
        'objective-10 (deployed)': names[:10],
        'all-20 (incl. derived proxies)': names,
        'volume features only (5)': ['daily_play_time_hours', 'weekly_play_time_hours',
                                     'sessions_per_day', 'avg_session_duration_min',
                                     'days_played_per_week'],
        'pattern features only (5)': ['late_night_play_ratio', 'longest_play_streak_days',
                                      'binge_sessions_per_week',
                                      'avg_break_between_sessions_min', 'rapid_relogin_ratio'],
    }
    y = df['addiction_label'].values
    out = []
    for name, feats in groupsets.items():
        X = df[feats].values
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                                  random_state=SEED, stratify=y)
        sc = StandardScaler().fit(X_tr)
        clf = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=20,
                                     class_weight='balanced', random_state=SEED, n_jobs=-1)
        clf.fit(sc.transform(X_tr), y_tr)
        y_hat = clf.predict(sc.transform(X_te))
        acc = accuracy_score(y_te, y_hat)
        lo, hi = boot_ci(lambda a, b: accuracy_score(a, b), y_te, y_hat)
        out.append({'config': name, 'accuracy': round(float(acc), 4), 'acc_ci95': [lo, hi],
                    'macro_f1': round(float(f1_score(y_te, y_hat, average='macro')), 4)})
        print(f"  {name:<34} acc {out[-1]['accuracy']:.4f} CI {out[-1]['acc_ci95']}")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=['chat', 'voice', 'behaviour', 'all'], default='all')
    args = ap.parse_args()
    os.makedirs(os.path.join(DOCS, 'figures'), exist_ok=True)
    t0 = time.time()
    path = os.path.join(DOCS, 'ablation_results.json')
    results = {}
    if os.path.exists(path):                 # merge: re-run one section without losing others
        with open(path) as f:
            results = json.load(f)
    results['alert_threshold'] = ALERT_T
    if args.only in ('chat', 'all'):
        results['chat'] = ablate_chat()
    if args.only in ('voice', 'all'):
        results['voice'] = ablate_voice()
    if args.only in ('behaviour', 'all'):
        results['behaviour'] = ablate_behavior()
    results['protocol'] = ('One component removed per row from the deployed recipe; '
                           'fixed held-out data per table; bootstrap 95% CIs over 1,000 '
                           'test-set resamples. Voice rows use speaker-independent '
                           'splits with a FIXED test set of un-augmented clips from '
                           'unseen speakers; chat rows evaluate on CONDA_valid, which '
                           'no config trains on.')
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] wrote {path}  ({time.time() - t0:.0f}s)")


if __name__ == '__main__':
    main()
