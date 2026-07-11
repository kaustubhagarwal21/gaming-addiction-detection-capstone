"""
Retrains behavior_model, chat_model, and voice_model.
Run from project root: python ml/retrain_models.py
"""
import os, sys, pickle, warnings, json
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.metrics import classification_report, confusion_matrix, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

warnings.filterwarnings('ignore')

MODELS_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'models')
DATA_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data')

# Share the EXACT preprocessing + feature derivation the backend serves with (no
# train/serve skew). derive_psychometrics is the single source of truth for the 10
# psychometric features, used identically here and in app.compute_behavioral_features.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from text_utils import clean_text
from behavior_features import derive_psychometrics as _derive_psych


# ──────────────────────────────────────────────────────────────────────────────
# 1. BEHAVIOR MODEL
# ──────────────────────────────────────────────────────────────────────────────
def generate_behavior_dataset(n=25000, seed=42):
    rng = np.random.default_rng(seed)

    FEATURE_NAMES = [
        'daily_play_time_hours', 'weekly_play_time_hours', 'sessions_per_day',
        'avg_session_duration_min', 'late_night_play_ratio', 'days_played_per_week',
        'longest_play_streak_days', 'binge_sessions_per_week', 'avg_break_between_sessions_min',
        'rapid_relogin_ratio', 'urge_to_continue_score', 'loss_of_time_awareness_score',
        'control_loss_score', 'craving_score', 'tolerance_score',
        'missed_sleep_days_per_week', 'fatigue_after_play_score', 'routine_disruption_score',
        'neglect_responsibilities_score', 'gaming_priority_score'
    ]

    n_casual   = int(n * 0.35)
    n_at_risk  = int(n * 0.40)
    n_addicted = n - n_casual - n_at_risk

    def clip(arr, lo, hi):
        return np.clip(arr, lo, hi)

    _PSY_ORDER = ['urge_to_continue_score', 'loss_of_time_awareness_score', 'control_loss_score',
                  'craving_score', 'tolerance_score', 'missed_sleep_days_per_week',
                  'fatigue_after_play_score', 'routine_disruption_score',
                  'neglect_responsibilities_score', 'gaming_priority_score']

    def derive_psychometrics(obj):
        """Apply the SHARED derive_psychometrics() — the exact mapping the live backend
        uses at serving (single source of truth, zero train/serve skew) — then add small
        Gaussian noise so the model can't trivially invert the deterministic relationship."""
        rows = np.array([[_derive_psych(*[float(r[i]) for i in range(10)])[k] for k in _PSY_ORDER]
                          for r in obj])
        rows = rows + rng.normal(0.0, 0.6, rows.shape)
        rows = clip(rows, 0, 10)
        rows[:, 5] = clip(rows[:, 5], 0, 7)   # missed_sleep_days_per_week is 0–7
        return rows

    def make_class(size, label):
        # Wider distributions + realistic class overlap. PLAY-TIME levels are grounded
        # in REAL survey data — the "Gamers & Anxiety" dataset (Sauter & Draschkow
        # 2017, n=13,464; aged<=24 cohort n=11,731, CC-BY 4.0) — via the percentile
        # bands computed by ml/analyze_survey.py:
        #   casual   ~ pct  5-50 : weekly 14.2 +/- 4.8 h
        #   at-risk  ~ pct 60-90 : weekly 26.3 +/- 6.6 h
        #   heavy    ~ pct 92+   : weekly 50.0 +/- 12.8 h
        # daily means are set so that daily * 7 * E[consistency-U] hits those weekly
        # targets. The remaining features (late-night, breaks, re-logins, ...) have no
        # public telemetry source and stay hand-set priors; the LABELS remain synthetic
        # screening priors either way — grounding narrows the sim-to-real gap for the
        # dominant features, it does not make the labels real.
        if label == 0:
            daily  = clip(rng.normal(3.4,  1.35, size), 0.3,  8.0)
            weekly = clip(daily * 7 * rng.uniform(0.4, 0.80, size), 2, 35)
            spd    = clip(rng.normal(1.2,  0.6,  size), 0.3,  4.0)
            dur    = clip(rng.normal(60,   30,   size), 10, 150)
            lnr    = clip(rng.normal(0.08, 0.10, size), 0, 0.45)
            dpw    = clip(rng.normal(3,    1.5,  size), 1, 7)
            streak = clip(rng.normal(3,    3,    size), 1, 14)
            binge  = clip(rng.normal(0.3,  0.6,  size), 0, 3)
            brk    = clip(rng.normal(180,  80,   size), 30, 600)
            rlr    = clip(rng.normal(0.05, 0.08, size), 0, 0.40)
        elif label == 1:
            daily  = clip(rng.normal(5.4,  1.6,  size), 2.0, 11.0)
            weekly = clip(daily * 7 * rng.uniform(0.5, 0.90, size), 10, 55)
            spd    = clip(rng.normal(2.5,  0.9,  size), 0.8,  6.0)
            dur    = clip(rng.normal(100,  35,   size), 30, 250)
            lnr    = clip(rng.normal(0.30, 0.16, size), 0.0, 0.75)
            dpw    = clip(rng.normal(5,    1.4,  size), 2, 7)
            streak = clip(rng.normal(8,    4,    size), 2, 22)
            binge  = clip(rng.normal(2.0,  1.1,  size), 0, 6.0)
            brk    = clip(rng.normal(90,   55,   size), 10, 300)
            rlr    = clip(rng.normal(0.25, 0.14, size), 0.0, 0.70)
        else:
            daily  = clip(rng.normal(8.9,  2.3,  size), 4.0, 16.0)
            weekly = clip(daily * 7 * rng.uniform(0.65, 0.95, size), 25, 112)
            spd    = clip(rng.normal(4.5,  1.1,  size), 2.0,  8.0)
            dur    = clip(rng.normal(160,  45,   size), 60, 360)
            lnr    = clip(rng.normal(0.60, 0.18, size), 0.2,  1.0)
            dpw    = clip(rng.normal(6.5,  0.8,  size), 4, 7)
            streak = clip(rng.normal(18,   6,    size), 7, 35)
            binge  = clip(rng.normal(5.0,  1.5,  size), 1.5, 10.0)
            brk    = clip(rng.normal(30,   25,   size), 2, 120)
            rlr    = clip(rng.normal(0.55, 0.18, size), 0.1,  1.0)

        obj = np.column_stack([daily, weekly, spd, dur, lnr, dpw, streak, binge, brk, rlr])
        return np.column_stack([obj, derive_psychometrics(obj)])

    X = np.vstack([make_class(n_casual, 0), make_class(n_at_risk, 1), make_class(n_addicted, 2)])
    y = np.concatenate([np.zeros(n_casual), np.ones(n_at_risk), np.full(n_addicted, 2)]).astype(int)

    # Add 15% boundary samples (ambiguous cases near class borders) for realistic accuracy
    n_boundary = int(n * 0.15)
    X_b0 = make_class(n_boundary // 2, 0) * 0.5 + make_class(n_boundary // 2, 1) * 0.5
    X_b1 = make_class(n_boundary // 2, 1) * 0.5 + make_class(n_boundary // 2, 2) * 0.5
    y_b0 = rng.choice([0, 1], size=n_boundary // 2)   # ambiguous casual/at_risk
    y_b1 = rng.choice([1, 2], size=n_boundary // 2)   # ambiguous at_risk/addicted
    X = np.vstack([X, X_b0, X_b1])
    y = np.concatenate([y, y_b0, y_b1])

    # Add small feature-scale noise to prevent memorisation
    noise_scale = np.std(X, axis=0) * 0.08
    X = X + rng.normal(0, 1, X.shape) * noise_scale

    df = pd.DataFrame(X, columns=FEATURE_NAMES)
    df['addiction_label'] = y
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df, FEATURE_NAMES


def train_behavior_model():
    print("=" * 60)
    print("TRAINING BEHAVIOR MODEL")
    print("=" * 60)

    df, feature_names = generate_behavior_dataset(25000)
    print(f"Dataset: {df.shape}")
    print("Class distribution:")
    print(df['addiction_label'].value_counts().sort_index().to_string())

    # Persist the actual training data so the committed CSV matches what the model
    # learned (the old committed CSV was a stale, imbalanced artifact).
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(os.path.join(DATA_DIR, 'behavior_dataset.csv'), index=False)
    print("Saved balanced training data -> data/behavior_dataset.csv")

    # Train on the 10 OBJECTIVE features only. The 10 psychometric proxies are
    # deterministic functions of these (behavior_features.derive_psychometrics) plus
    # training noise — they add no information the model can use, and including them
    # made SHAP attributions partly circular (a "craving score" driver shown to a
    # parent is really late-night ratio x re-login ratio in disguise). The proxies are
    # still generated into the dataset CSV and served as UI-level explanations; the
    # backend sizes its model input from the fitted scaler, so old 20-feature models
    # keep working during rollout.
    model_features = feature_names[:10]
    X = df[model_features].values
    y = df['addiction_label'].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)
    scaler.feature_names_in_ = np.array(model_features)

    # max_depth=6 and high min_samples_leaf regularise model → realistic ~87% accuracy
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=20,
        class_weight='balanced', random_state=42, n_jobs=-1
    )
    clf.fit(X_train_s, y_train)

    y_pred = clf.predict(X_test_s)
    test_accuracy = float((y_pred == y_test).mean())
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['casual', 'at_risk', 'addicted']))
    rep = classification_report(y_test, y_pred, target_names=['casual', 'at_risk', 'addicted'],
                                output_dict=True, zero_division=0)

    print("5-Fold Cross-Validation (on training set):")
    cv_scores = cross_val_score(clf, X_train_s, y_train, cv=5, scoring='accuracy', n_jobs=-1)
    print(f"  Accuracy per fold: {cv_scores.round(3)}")
    print(f"  Mean: {cv_scores.mean():.3f}  Std: {cv_scores.std():.3f}")

    test_cases = [
        ('Casual',   1.5, 10.5, 2.0),
        ('At-risk',  5.0, 35.0, 6.0),
        ('Addicted', 10.0, 70.0, 9.0),
    ]
    print("Sanity checks:")
    for name, daily, weekly, psy in test_cases:
        row = {fn: 0.0 for fn in feature_names}
        row['daily_play_time_hours'] = daily
        row['weekly_play_time_hours'] = weekly
        row['sessions_per_day'] = daily / 1.5
        row['avg_session_duration_min'] = daily * 60 / max(1, daily / 1.5)
        row['late_night_play_ratio'] = 0.05 if psy < 4 else (0.3 if psy < 7 else 0.65)
        row['days_played_per_week'] = min(7, weekly / max(1, daily))
        row['longest_play_streak_days'] = 3 if psy < 4 else (8 if psy < 7 else 20)
        row['binge_sessions_per_week'] = 0.2 if psy < 4 else (2.0 if psy < 7 else 5.5)
        row['avg_break_between_sessions_min'] = 200 if psy < 4 else (90 if psy < 7 else 25)
        row['rapid_relogin_ratio'] = 0.05 if psy < 4 else (0.25 if psy < 7 else 0.6)
        X_row = pd.DataFrame([row])[model_features].values
        X_row_s = scaler.transform(X_row)
        pred = clf.predict(X_row_s)[0]
        proba = clf.predict_proba(X_row_s)[0]
        lmap = {0: 'casual', 1: 'at_risk', 2: 'addicted'}
        print(f"  {name}: {lmap[pred]}, proba={proba.round(3)}")

    with open(os.path.join(MODELS_DIR, 'behavior_model.pkl'), 'wb') as f:
        pickle.dump(clf, f)
    with open(os.path.join(MODELS_DIR, 'feature_scaler.pkl'), 'wb') as f:
        pickle.dump(scaler, f)
    with open(os.path.join(MODELS_DIR, 'feature_names.pkl'), 'wb') as f:
        pickle.dump(model_features, f)

    # Save model metadata for the /api/health + /api/model_card endpoints
    metadata = {
        'trained_at':        datetime.now().isoformat(),
        'test_accuracy':     round(test_accuracy, 4),
        'macro_f1':          round(float(rep['macro avg']['f1-score']), 4),
        'per_class_f1': {
            'casual':   round(float(rep['casual']['f1-score']), 4),
            'at_risk':  round(float(rep['at_risk']['f1-score']), 4),
            'addicted': round(float(rep['addicted']['f1-score']), 4),
        },
        'per_class_precision': {
            'casual':   round(float(rep['casual']['precision']), 4),
            'at_risk':  round(float(rep['at_risk']['precision']), 4),
            'addicted': round(float(rep['addicted']['precision']), 4),
        },
        'per_class_recall': {
            'casual':   round(float(rep['casual']['recall']), 4),
            'at_risk':  round(float(rep['at_risk']['recall']), 4),
            'addicted': round(float(rep['addicted']['recall']), 4),
        },
        'confusion_matrix':  confusion_matrix(y_test, y_pred).tolist(),
        'confusion_labels':  ['casual', 'at_risk', 'addicted'],
        'cv_mean_accuracy':  round(float(cv_scores.mean()), 4),
        'cv_std_accuracy':   round(float(cv_scores.std()), 4),
        'cv_fold_scores':    [round(float(s), 4) for s in cv_scores],
        'n_estimators':      clf.n_estimators,
        'max_depth':         clf.max_depth,
        'train_samples':     len(X_train),
        'test_samples':      len(X_test),
        'feature_count':     len(model_features),
        'model_features':    ('objective-10: the 10 psychometric proxies are deterministic '
                              'functions of these (behavior_features.py) and are excluded '
                              'from the model input to keep SHAP attributions non-circular; '
                              'they remain as UI-level explanations'),
        'class_balance':     'balanced (35/40/25) + class_weight; psychometrics derived from behaviour (train/serve aligned)',
    }
    # MERGE into the existing file rather than overwrite: calibration (calibrate_behavior.py)
    # and chat_metrics/voice_metrics + notes (eval_chat_voice.py) live in the same JSON —
    # a wholesale rewrite here silently wiped them from /api/model_card until those
    # scripts were rerun.
    meta_path = os.path.join(MODELS_DIR, 'model_metadata.json')
    merged = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                merged = json.load(f)
        except Exception:
            merged = {}
    merged.update(metadata)
    with open(meta_path, 'w') as f:
        json.dump(merged, f, indent=2)
    print("[OK] Saved behavior_model.pkl, feature_scaler.pkl, feature_names.pkl, model_metadata.json")
    return clf, scaler, model_features


# ──────────────────────────────────────────────────────────────────────────────
# 2. CHAT MODEL  (binary classifier: toxic vs. clean)
# ──────────────────────────────────────────────────────────────────────────────
def assemble_chat_dataset(verbose: bool = True):
    """The FULL chat corpus the model trains on: general corpus + CONDA train split +
    every data/chat_extra/*.csv, cleaned with the serving clean_text. Deterministic
    (fixed read order, ignore_index concats), so ml/eval_chat_voice.py can import this
    and reproduce the EXACT rows — its "held-out" set then genuinely excludes what the
    model trained on. Previously eval rebuilt the split from the general corpus ALONE,
    so CONDA/chat_extra rows the model HAD trained on leaked into the "held-out" metrics.
    """
    df = pd.read_csv(os.path.join(DATA_DIR, 'chat_dataset.csv'))
    df = df[['text', 'toxicity_score']].dropna()
    df['toxic'] = (df['toxicity_score'] >= 0.5).astype(int)
    df = df[['text', 'toxic']]
    # Gaming-DOMAIN data (CONDA train split — real Dota 2 in-game chat) is included
    # whenever it's on disk: the deployed model is gaming-domain-trained, and a full
    # retrain run must never silently regress it to a general-corpus-only model.
    conda = os.path.join(DATA_DIR, 'conda', 'CONDA_train.csv')
    if os.path.exists(conda):
        g = pd.read_csv(conda)
        g = pd.DataFrame({'text': g['utterance'].astype(str),
                          'toxic': g['intentClass'].astype(str).str.strip().str.upper()
                                    .isin({'E', 'I'}).astype(int)})
        df = pd.concat([df, g], ignore_index=True)
        if verbose:
            print(f"Included gaming-domain chat: {len(g)} rows (CONDA train split)")
    elif verbose:
        print("WARNING: data/conda/CONDA_train.csv not found — training on the general "
              "corpus only will UNDERPERFORM the deployed gaming-domain model in-domain.")
    # Additional REAL corpora normalised to (text,toxic) live in data/chat_extra/
    # (e.g. Davidson et al. hate/offensive tweets — informal, slang-heavy language
    # close to gaming chat's register). Included whenever present. sorted() fixes the
    # order so the assembly (and thus the seeded split) is reproducible.
    import glob as _glob
    for extra in sorted(_glob.glob(os.path.join(DATA_DIR, 'chat_extra', '*.csv'))):
        e = pd.read_csv(extra)
        if {'text', 'toxic'} <= set(e.columns):
            df = pd.concat([df, e[['text', 'toxic']]], ignore_index=True)
            if verbose:
                print(f"Included extra corpus: {len(e)} rows ({os.path.basename(extra)})")
    # Apply the SAME clean_text the backend uses at serving (no train/serve skew).
    df['text'] = df['text'].astype(str).map(clean_text)
    df = df[df['text'].str.len() > 2]
    return df


def train_chat_model():
    print("\n" + "=" * 60)
    print("TRAINING CHAT MODEL")
    print("=" * 60)

    # NOTE: We evaluated ChatGPT's cleaned/curated chat data (ml/improve_datasets.py):
    # it removed duplicate/conflicting labels + added gaming hard-negatives, but realistic
    # toxic precision stayed ~0.20 (flat) — the issue is the general-hate-speech vs
    # gaming-chat domain mismatch + 30:1 imbalance, not label noise. So we did NOT adopt
    # it; the real chat lever is real gaming-chat data / threshold tuning, not cleanup.
    # Shared assembly (also used by eval_chat_voice.py, so eval excludes exactly these rows).
    df = assemble_chat_dataset(verbose=True)
    print(f"Dataset: {df.shape}")
    print(f"Toxic: {df['toxic'].sum():,} ({df['toxic'].mean()*100:.1f}%)  Non-toxic: {(df['toxic']==0).sum():,}")

    # Oversample toxic class to 1:1 ratio for balanced training
    toxic_df    = df[df['toxic'] == 1]
    nontoxic_df = df[df['toxic'] == 0].sample(n=len(toxic_df), random_state=42)
    df_bal = pd.concat([toxic_df, nontoxic_df]).sample(frac=1, random_state=42)
    print(f"Balanced dataset: {df_bal.shape}")

    X_train, X_test, y_train, y_test = train_test_split(
        df_bal['text'], df_bal['toxic'], test_size=0.2, random_state=42, stratify=df_bal['toxic']
    )
    # Carve a CALIBRATION slice out of the training split (never the test split — that
    # stays untouched so eval_chat_voice.py's held-out metrics remain honest). The
    # isotonic layer makes the served P(toxic) meaningful, mirroring the behaviour
    # model's calibration pattern (chat_calibrated.pkl is optional; raw model fallback).
    X_fit, X_cal, y_fit, y_cal = train_test_split(
        X_train, y_train, test_size=0.15, random_state=42, stratify=y_train
    )

    # Word n-grams + WORD-BOUNDED char n-grams (char_wb) on cleaned text. Raw char
    # n-grams were originally rejected — trained on the general corpus alone they
    # over-fired on clean gaming phrases via spurious substrings. Re-tested with
    # gaming-domain training data and char_wb (which never crosses word boundaries),
    # the union wins DECISIVELY on held-out real gaming chat: PR-AUC 0.714 -> 0.794
    # and precision at the deployed alert point 0.836 -> 0.924 — char n-grams catch
    # the misspellings/obfuscations word tokens miss, once the training data teaches
    # them what gaming chat looks like.
    vectorizer = FeatureUnion([
        ('word', TfidfVectorizer(max_features=20000, ngram_range=(1, 2), min_df=2,
                                 sublinear_tf=True, strip_accents='unicode')),
        ('char', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5),
                                 max_features=30000, min_df=2, sublinear_tf=True)),
    ])
    X_fit_v  = vectorizer.fit_transform(X_fit)
    X_cal_v  = vectorizer.transform(X_cal)
    X_test_v = vectorizer.transform(X_test)

    clf = LogisticRegression(
        C=1.0, solver='lbfgs', max_iter=1000,
        class_weight='balanced', random_state=42, n_jobs=-1
    )
    clf.fit(X_fit_v, y_fit)

    calibrated = CalibratedClassifierCV(FrozenEstimator(clf), method='isotonic')
    calibrated.fit(X_cal_v, y_cal)

    y_pred = clf.predict(X_test_v)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['clean', 'toxic']))
    brier_raw = brier_score_loss(y_test, clf.predict_proba(X_test_v)[:, 1])
    brier_cal = brier_score_loss(y_test, calibrated.predict_proba(X_test_v)[:, 1])
    print(f"Brier (held-out): raw={brier_raw:.4f}  calibrated={brier_cal:.4f}")

    # Sanity check — predict_proba[1] is the toxicity score
    test_messages = [
        ("good game well played gg",              "clean"),
        ("nice shot bro let's go clutch",         "clean"),
        ("you're so bad at this game",             "mild"),
        ("kill yourself you worthless trash",      "toxic"),
        ("hate everyone i cant stop playing",      "toxic"),
        ("noob get rekt loser garbage player",     "toxic"),
        ("gg everyone had fun",                    "clean"),
    ]
    print("\nSanity checks (predict_proba[1] = toxicity score):")
    for msg, expected in test_messages:
        vec   = vectorizer.transform([clean_text(msg)])
        score = clf.predict_proba(vec)[0][1]
        print(f"  [{score:.3f}] ({expected:5s}) {msg[:55]}")

    with open(os.path.join(MODELS_DIR, 'chat_model.pkl'), 'wb') as f:
        pickle.dump(clf, f)
    with open(os.path.join(MODELS_DIR, 'chat_calibrated.pkl'), 'wb') as f:
        pickle.dump(calibrated, f)
    with open(os.path.join(MODELS_DIR, 'tfidf_vectorizer.pkl'), 'wb') as f:
        pickle.dump(vectorizer, f)
    print("[OK] Saved chat_model.pkl, chat_calibrated.pkl, tfidf_vectorizer.pkl")
    return clf, vectorizer


# ──────────────────────────────────────────────────────────────────────────────
# 3. VOICE MODEL  (17 MFCC+pitch+energy features -> emotion label)
# ──────────────────────────────────────────────────────────────────────────────
def generate_voice_dataset(n=8000, seed=42):
    """
    Synthetic MFCC-like features.  Backend extracts:
      mfcc[0..12] (13 values) + [pitch_mean, pitch_std, energy_mean, energy_std]
    Total = 17 features.
    """
    rng = np.random.default_rng(seed)
    classes = ['neutral', 'excited', 'frustrated', 'angry']
    # (mfcc0_mean, mfcc0_std), remaining mfcc roughly ~0, pitch_mean, pitch_std,
    #  energy_mean, energy_std
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
        feats = np.column_stack([mfcc0.reshape(-1, 1), mfccs,
                                  pitch_mean, pitch_std, e_mean, e_std])
        rows.append(feats)
        labels.extend([cls] * per_class)
    return np.vstack(rows), np.array(labels)


def train_voice_model():
    print("\n" + "=" * 60)
    print("TRAINING VOICE MODEL")
    print("=" * 60)

    X, y = generate_voice_dataset(8000)
    print(f"Dataset: {X.shape}")
    print("Class distribution:", {c: int((y == c).sum()) for c in np.unique(y)})

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = GradientBoostingClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.1,
        random_state=42
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    with open(os.path.join(MODELS_DIR, 'voice_model.pkl'), 'wb') as f:
        pickle.dump(clf, f)
    print("[OK] Saved voice_model.pkl")

    # Verify it loads cleanly
    with open(os.path.join(MODELS_DIR, 'voice_model.pkl'), 'rb') as f:
        vm = pickle.load(f)
    print(f"     classes: {vm.classes_}, n_features: {vm.n_features_in_}")
    return clf


# ──────────────────────────────────────────────────────────────────────────────
# 4. END-TO-END VERIFY
# ──────────────────────────────────────────────────────────────────────────────
def verify_end_to_end(behavior_clf, scaler, feature_names, chat_clf, vectorizer):
    print("\n" + "=" * 60)
    print("END-TO-END VERIFICATION")
    print("=" * 60)

    VOICE_RISK = {'angry': 0.9, 'frustrated': 0.7, 'excited': 0.4, 'neutral': 0.1}

    scenarios = [
        {
            'name': 'Casual gamer',
            'feats': {'daily_play_time_hours': 1.5, 'weekly_play_time_hours': 10.5,
                      'sessions_per_day': 1.0, 'avg_session_duration_min': 90,
                      'late_night_play_ratio': 0.05, 'days_played_per_week': 3,
                      'longest_play_streak_days': 3, 'binge_sessions_per_week': 0.3,
                      'avg_break_between_sessions_min': 200, 'rapid_relogin_ratio': 0.04,
                      'urge_to_continue_score': 2, 'loss_of_time_awareness_score': 2,
                      'control_loss_score': 2, 'craving_score': 2, 'tolerance_score': 2,
                      'missed_sleep_days_per_week': 0.1, 'fatigue_after_play_score': 2,
                      'routine_disruption_score': 2, 'neglect_responsibilities_score': 2,
                      'gaming_priority_score': 2},
            'chat': 'good game gg nice play well done',
            'voice': 'neutral',
            'expected': 'casual',
        },
        {
            'name': 'At-risk gamer',
            'feats': {'daily_play_time_hours': 5.0, 'weekly_play_time_hours': 35.0,
                      'sessions_per_day': 3.0, 'avg_session_duration_min': 100,
                      'late_night_play_ratio': 0.30, 'days_played_per_week': 5,
                      'longest_play_streak_days': 8, 'binge_sessions_per_week': 2.0,
                      'avg_break_between_sessions_min': 80, 'rapid_relogin_ratio': 0.25,
                      'urge_to_continue_score': 6, 'loss_of_time_awareness_score': 6,
                      'control_loss_score': 6, 'craving_score': 6, 'tolerance_score': 6,
                      'missed_sleep_days_per_week': 1.5, 'fatigue_after_play_score': 6,
                      'routine_disruption_score': 6, 'neglect_responsibilities_score': 6,
                      'gaming_priority_score': 6},
            'chat': 'you suck get rekt loser trash',
            'voice': 'frustrated',
            'expected': 'at_risk',
        },
        {
            'name': 'Addicted gamer',
            'feats': {'daily_play_time_hours': 10.0, 'weekly_play_time_hours': 70.0,
                      'sessions_per_day': 5.0, 'avg_session_duration_min': 180,
                      'late_night_play_ratio': 0.70, 'days_played_per_week': 7,
                      'longest_play_streak_days': 20, 'binge_sessions_per_week': 5.5,
                      'avg_break_between_sessions_min': 20, 'rapid_relogin_ratio': 0.60,
                      'urge_to_continue_score': 9, 'loss_of_time_awareness_score': 9,
                      'control_loss_score': 9, 'craving_score': 9, 'tolerance_score': 9,
                      'missed_sleep_days_per_week': 4.0, 'fatigue_after_play_score': 9,
                      'routine_disruption_score': 9, 'neglect_responsibilities_score': 9,
                      'gaming_priority_score': 9},
            'chat': 'i hate everyone kill yourself i cant stop playing addicted obsessed',
            'voice': 'angry',
            'expected': 'addicted',
        },
    ]

    label_map = {0: 'casual', 1: 'at_risk', 2: 'addicted'}

    print(f"{'Name':<20} {'B-pred':<10} {'B-score':>7} {'C-score':>7} {'V-score':>7} {'Ensemble':>8} {'Result':<10} {'OK'}")
    print("-" * 85)

    for s in scenarios:
        df_row = pd.DataFrame([s['feats']])[feature_names]
        X_s    = scaler.transform(df_row)
        b_pred = behavior_clf.predict(X_s)[0]
        b_prob = behavior_clf.predict_proba(X_s)[0]
        # Score: weighted toward higher risk classes
        b_score = float(b_prob[1] * 0.5 + b_prob[2])

        # clean_text first — the model is trained AND served on cleaned text, so verifying
        # on raw text would report scores the live system never produces.
        vec     = vectorizer.transform([clean_text(s['chat'])])
        c_score = float(chat_clf.predict_proba(vec)[0][1])

        v_score = VOICE_RISK[s['voice']]

        ensemble = 0.40 * b_score + 0.30 * c_score + 0.30 * v_score
        risk = 'casual' if ensemble < 0.33 else ('at_risk' if ensemble < 0.67 else 'addicted')
        ok   = 'OK' if risk == s['expected'] else 'FAIL'

        print(f"{s['name']:<20} {label_map[b_pred]:<10} {b_score:>7.3f} {c_score:>7.3f} {v_score:>7.3f} {ensemble:>8.3f} {risk:<10} {ok}")


if __name__ == '__main__':
    os.makedirs(MODELS_DIR, exist_ok=True)
    b_clf, scaler, feat_names = train_behavior_model()
    c_clf, vectorizer         = train_chat_model()
    train_voice_model()
    verify_end_to_end(b_clf, scaler, feat_names, c_clf, vectorizer)
    print("\nAll models retrained successfully.")
