"""
Retrain the voice-emotion model on REAL labelled speech (RAVDESS / CREMA-D) instead of
synthetic features — the single change that most strengthens the system's credibility
(voice is the only modality still trained on synthetic data; see PROJECT_PAPER Tier 1).

Train/serve alignment: every clip is run through backend/audio_features.py — the SAME
extraction the live backend serves with (silence floor -> gain normalisation -> 17
features) — so the model can never see features the server doesn't produce.

Datasets (both free):
  RAVDESS speech  https://zenodo.org/records/1188976
                  (Audio_Speech_Actors_01-24.zip -> unzip under data/voice/RAVDESS/)
  CREMA-D         https://github.com/CheyneyComputerScience/CREMA-D
                  (AudioWAV/*.wav -> put under data/voice/CREMA-D/)

Label mapping to the system's 4 classes (angry / excited / frustrated / neutral):
  RAVDESS code:  01,02 neutral|calm -> neutral   03 happy -> excited     04 sad -> frustrated
                 05 angry -> angry               06 fearful -> frustrated
                 07 disgust -> frustrated        08 surprised -> excited
  CREMA-D code:  NEU -> neutral   HAP -> excited   SAD/FEA/DIS -> frustrated   ANG -> angry

Augmentation (per clip, --augment N extra variants): additive noise at a random SNR
(10-25 dB) and phone-mic band-limiting — the two realistic corruptions of a game-time
phone recording. Gain augmentation is deliberately NOT used: the shared pipeline is
gain-invariant by design (fixed-RMS normalisation), so it would be a no-op.

Usage (from the project root):
  python ml/train_voice_real.py                     # scan default data/voice/ dirs
  python ml/train_voice_real.py --limit 200         # quick pass on a subset
  python ml/train_voice_real.py --augment 2         # 2 augmented variants per clip
  python ml/train_voice_real.py --smoke             # self-test on generated WAVs (no data needed)
Then re-run ml/eval_chat_voice.py? No — this script writes voice_metrics itself (real).
"""
import argparse
import glob
import json
import os
import pickle
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from audio_features import SAMPLE_RATE, LIBROSA_AVAILABLE  # noqa: E402

MODELS_DIR = os.path.join(ROOT, 'backend', 'models')
DATA_DIR   = os.path.join(ROOT, 'data')

RAVDESS_MAP = {'01': 'neutral', '02': 'neutral', '03': 'excited', '04': 'frustrated',
               '05': 'angry', '06': 'frustrated', '07': 'frustrated', '08': 'excited'}
CREMAD_MAP  = {'NEU': 'neutral', 'HAP': 'excited', 'SAD': 'frustrated',
               'FEA': 'frustrated', 'DIS': 'frustrated', 'ANG': 'angry'}
# EMO-DB (Berlin, German): emotion letter at stem position 5 (e.g. 03a01Wa.wav).
# W=Wut/anger, F=Freude/happiness, T=Trauer/sadness, A=Angst/fear, E=Ekel/disgust,
# L=Langeweile/boredom (low arousal -> neutral), N=neutral.
EMODB_MAP   = {'W': 'angry', 'F': 'excited', 'T': 'frustrated', 'A': 'frustrated',
               'E': 'frustrated', 'L': 'neutral', 'N': 'neutral'}
# Folder-per-emotion corpora (URDU and similar): parent directory names the emotion.
FOLDER_MAP  = {'angry': 'angry', 'happy': 'excited', 'sad': 'frustrated',
               'neutral': 'neutral', 'fear': 'frustrated', 'disgust': 'frustrated'}
CLASSES = ['angry', 'excited', 'frustrated', 'neutral']


def label_for(path: str):
    """Emotion label from a RAVDESS / CREMA-D / EMO-DB filename or a
    folder-per-emotion layout (URDU); None when unrecognised."""
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    parts = name.split('-')
    if len(parts) >= 3 and parts[0].isdigit():          # RAVDESS: 03-01-05-01-...
        return RAVDESS_MAP.get(parts[2])
    parts = stem.split('_')
    if len(parts) >= 3 and parts[2].upper() in CREMAD_MAP:   # CREMA-D: 1001_DFA_ANG_XX
        return CREMAD_MAP[parts[2].upper()]
    if len(stem) == 7 and stem[:2].isdigit() and stem[5] in EMODB_MAP:  # EMO-DB: 03a01Wa
        return EMODB_MAP[stem[5]]
    parent = os.path.basename(os.path.dirname(path)).lower()           # URDU: Angry/...
    return FOLDER_MAP.get(parent)


def speaker_for(path: str) -> str:
    """Speaker id (corpus-prefixed) — evaluation splits GROUP by this so no speaker
    appears on both sides. A random clip split leaks speaker identity: the model
    partly recognises the *person*, not the emotion, and the reported accuracy
    inflates. Speaker-independent evaluation is the honest protocol."""
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    parts = stem.split('-')
    if len(parts) >= 7 and parts[0].isdigit():          # RAVDESS: ...-ACTOR
        return 'RAV' + parts[-1]
    parts = stem.split('_')
    if len(parts) >= 3 and parts[2].upper() in CREMAD_MAP:   # CREMA-D: 1001_...
        return 'CRE' + parts[0]
    if len(stem) == 7 and stem[:2].isdigit() and stem[5] in EMODB_MAP:  # EMO-DB
        return 'EMO' + stem[:2]
    parent = os.path.basename(os.path.dirname(path)).lower()
    if parent in FOLDER_MAP:                                  # URDU: SM1_F10_A010
        return 'URD' + parts[0]
    return 'UNK'


def augment(y: np.ndarray, sr: int, rng: np.random.Generator):
    """One augmented variant: additive noise at a random SNR + optional band-limiting."""
    out = y.copy()
    # Additive noise, SNR 10-25 dB
    snr_db = rng.uniform(10, 25)
    sig_p  = np.mean(out ** 2) or 1e-9
    noise  = rng.normal(0, 1, len(out)) * np.sqrt(sig_p / (10 ** (snr_db / 10)))
    out = out + noise
    # Half the variants also get phone-mic band-limiting (~300 Hz-4 kHz)
    if rng.random() < 0.5:
        from scipy.signal import butter, sosfilt
        sos = butter(4, [300, 4000], btype='bandpass', fs=sr, output='sos')
        out = sosfilt(sos, out).astype(np.float32)
    return out


def collect_files(args):
    files = []
    for d in [args.ravdess, args.cremad] + list(args.extra or []):
        if d and os.path.isdir(d):
            files += glob.glob(os.path.join(d, '**', '*.wav'), recursive=True)
    labelled = [(f, label_for(f)) for f in sorted(files)]
    labelled = [(f, l) for f, l in labelled if l]
    if args.limit:
        labelled = labelled[:args.limit]
    return labelled


def _process_clip(path: str, lab: str, spk: str, n_aug: int, seed: int, root: str):
    """Load one clip, build its augmented variants, extract features for each.
    Self-contained (imports inside) so it runs cleanly in a joblib worker process."""
    import os
    import sys
    sys.path.insert(0, os.path.join(root, 'backend'))
    import librosa
    import numpy as np
    from audio_features import extract_features_from_array, SAMPLE_RATE
    rng = np.random.default_rng(seed)
    try:
        y, sr = librosa.load(path, sr=SAMPLE_RATE, duration=10)
    except Exception:
        return [], 1
    variants = [y] + [augment(y, sr, rng) for _ in range(n_aug)]
    rows, skipped = [], 0
    for v in variants:
        # apply_vad=False: curated corpora are known speech; skipping VAD keeps the
        # pass fast and avoids rejecting soft acted clips. The silence floor and
        # gain normalisation still run — identical to serving.
        feats, _ = extract_features_from_array(v, sr, apply_vad=False)
        if feats is not None:
            rows.append((feats, lab, spk))
        else:
            skipped += 1
    return rows, skipped


def build_dataset(labelled, n_aug: int, seed: int = 42, jobs: int = 1):
    """Returns (X, y, groups, skipped) — groups carry the speaker id per row so
    splits can be made speaker-independent (augmented variants of a clip inherit
    the clip's speaker, so they can never straddle a split either)."""
    if jobs > 1:
        from joblib import Parallel, delayed
        results = Parallel(n_jobs=jobs, verbose=5)(
            delayed(_process_clip)(path, lab, speaker_for(path), n_aug, seed + i, ROOT)
            for i, (path, lab) in enumerate(labelled))
    else:
        results = [_process_clip(path, lab, speaker_for(path), n_aug, seed + i, ROOT)
                   for i, (path, lab) in enumerate(labelled)]
    X, y_lab, groups, skipped = [], [], [], 0
    for rows, sk in results:
        skipped += sk
        for feats, lab, spk in rows:
            X.append(feats)
            y_lab.append(lab)
            groups.append(spk)
    return np.array(X), np.array(y_lab), np.array(groups), skipped


def balance(X, y, groups, rng):
    """Downsample every class to the smallest class count (keeps groups aligned)."""
    idx = []
    n_min = min(int((y == c).sum()) for c in np.unique(y))
    for c in np.unique(y):
        rows = np.where(y == c)[0]
        idx.extend(rng.choice(rows, size=n_min, replace=False))
    idx = np.array(sorted(idx))
    return X[idx], y[idx], groups[idx]


def smoke_files(tmpdir: str) -> list:
    """Generate a tiny synthetic WAV set so the whole pipeline can be exercised
    end-to-end with no downloads (CI / sanity checks)."""
    import soundfile as sf
    rng = np.random.default_rng(0)
    os.makedirs(tmpdir, exist_ok=True)
    out = []
    profiles = {'NEU': (120, 0.05), 'HAP': (250, 0.12), 'SAD': (140, 0.07), 'ANG': (200, 0.2)}
    for code, (f0, amp) in profiles.items():
        for i in range(8):
            t = np.linspace(0, 1.5, int(SAMPLE_RATE * 1.5))
            f = f0 * (1 + 0.1 * rng.standard_normal())
            y = amp * np.sin(2 * np.pi * f * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
            y += 0.01 * rng.standard_normal(len(t))
            p = os.path.join(tmpdir, f"100{i}_XXX_{code}_XX.wav")
            sf.write(p, y.astype(np.float32), SAMPLE_RATE)
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ravdess', default=os.path.join(DATA_DIR, 'voice', 'RAVDESS'))
    ap.add_argument('--cremad',  default=os.path.join(DATA_DIR, 'voice', 'CREMA-D'))
    ap.add_argument('--extra', nargs='*', default=[os.path.join(DATA_DIR, 'voice', 'EMO-DB'),
                                                   os.path.join(DATA_DIR, 'voice', 'URDU')],
                    help='additional corpora dirs (EMO-DB letter codes and '
                         'folder-per-emotion layouts are auto-labelled)')
    ap.add_argument('--augment', type=int, default=1, help='augmented variants per clip')
    ap.add_argument('--jobs',    type=int, default=1, help='parallel extraction workers')
    ap.add_argument('--limit',   type=int, default=0, help='cap clips (quick runs)')
    ap.add_argument('--smoke',   action='store_true',
                    help='self-test on generated WAVs; does NOT overwrite the model')
    args = ap.parse_args()

    if not LIBROSA_AVAILABLE:
        sys.exit("librosa is required (pip install -r backend/requirements.txt)")

    if args.smoke:
        import tempfile
        tmp = tempfile.mkdtemp(prefix='voice_smoke_')
        labelled = [(f, label_for(f)) for f in smoke_files(tmp)]
        labelled = [(f, l) for f, l in labelled if l]
        corpora = 'smoke'
    else:
        labelled = collect_files(args)
        dirs = [('RAVDESS', args.ravdess), ('CREMA-D', args.cremad)] + \
               [(os.path.basename(os.path.normpath(d)), d) for d in (args.extra or [])]
        corpora = '/'.join(n for n, d in dirs
                           if d and os.path.isdir(d) and glob.glob(os.path.join(d, '**', '*.wav'),
                                                                   recursive=True))
        if not labelled:
            sys.exit("No labelled WAVs found.\n"
                     f"  RAVDESS -> {args.ravdess}\n  CREMA-D -> {args.cremad}\n"
                     "Download links are in this script's docstring. "
                     "(Or run with --smoke to self-test the pipeline.)")

    print(f"Clips: {len(labelled)}  (augment x{args.augment}, jobs {args.jobs})")
    X, y, groups, skipped = build_dataset(labelled, args.augment, jobs=args.jobs)
    print(f"Feature rows: {len(X)}  (skipped {skipped})")
    print("Class counts:", {c: int((y == c).sum()) for c in np.unique(y)})

    rng = np.random.default_rng(42)
    X, y, groups = balance(X, y, groups, rng)
    print("Balanced to:", {c: int((y == c).sum()) for c in np.unique(y)})

    from sklearn.ensemble import (GradientBoostingClassifier, HistGradientBoostingClassifier,
                                  RandomForestClassifier, ExtraTreesClassifier)
    from sklearn.metrics import classification_report, accuracy_score, f1_score, confusion_matrix
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    # SPEAKER-INDEPENDENT splits (GroupShuffleSplit on speaker id): a random clip
    # split puts the same speaker on both sides, so the model partly recognises the
    # PERSON rather than the emotion and the reported accuracy inflates. Grouping by
    # speaker is the honest protocol; augmented variants inherit their clip's
    # speaker, so they can never straddle a split either.
    from sklearn.model_selection import GroupShuffleSplit
    tr_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2,
                                            random_state=42).split(X, y, groups))
    X_tr, y_tr, g_tr = X[tr_idx], y[tr_idx], groups[tr_idx]
    X_te, y_te = X[te_idx], y[te_idx]
    print(f"Speaker-independent split: {len(set(g_tr))} train speakers / "
          f"{len(set(groups[te_idx]))} test speakers")
    # Model selection done PROPERLY: candidates are compared on a validation slice
    # carved from the training split (also speaker-grouped); the untouched test split
    # scores only the winner (selecting on the test set would leak selection bias).
    # The field spans the classical families that make sense for a small dense feature
    # space: boosted trees, bagged trees, kernel SVM and a small MLP (the latter two
    # scaled — they are not scale-invariant like trees).
    fit_idx, val_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.15,
                                              random_state=42).split(X_tr, y_tr, g_tr))
    X_fit, y_fit = X_tr[fit_idx], y_tr[fit_idx]
    X_val, y_val = X_tr[val_idx], y_tr[val_idx]
    candidates = {
        'GradientBoosting':     GradientBoostingClassifier(
            n_estimators=150, max_depth=5, learning_rate=0.1, random_state=42),
        'HistGradientBoosting': HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, random_state=42),
        'RandomForest':         RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1),
        'ExtraTrees':           ExtraTreesClassifier(
            n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1),
        # probability=False during SELECTION: Platt scaling runs an internal 5-fold CV
        # that quintuples the fit cost, and predict-accuracy selection doesn't need it.
        # The final refit below rebuilds the winner WITH probabilities for serving.
        'SVM-RBF (scaled)':     make_pipeline(
            StandardScaler(), SVC(C=10, gamma='scale', probability=False, random_state=42)),
        # early_stopping=False: sklearn's early-stopping scorer calls np.isnan on the
        # predicted labels, which crashes on STRING classes (and the emotion labels
        # must stay strings — serving maps voice_model.classes_ into VOICE_RISK).
        'MLP (scaled)':         make_pipeline(
            StandardScaler(), MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=300,
                                            early_stopping=False, random_state=42)),
    }
    best_name, best_val = None, -1.0
    for name, cand in candidates.items():
        cand.fit(X_fit, y_fit)
        val_acc = accuracy_score(y_val, cand.predict(X_val))
        print(f"  candidate {name}: validation accuracy {val_acc:.4f}")
        if val_acc > best_val:
            best_name, best_val = name, val_acc
    clf = candidates[best_name]
    if 'SVM' in best_name:   # serving needs predict_proba — rebuild with probabilities
        clf = make_pipeline(StandardScaler(),
                            SVC(C=10, gamma='scale', probability=True, random_state=42))
    clf.fit(X_tr, y_tr)                            # refit the winner on the full train split
    print(f"Selected: {best_name}")
    y_hat = clf.predict(X_te)
    print("\nClassification Report (REAL audio held-out):")
    print(classification_report(y_te, y_hat))

    if args.smoke:
        print("[SMOKE OK] pipeline ran end-to-end — model NOT saved (synthetic tones).")
        return

    with open(os.path.join(MODELS_DIR, 'voice_model.pkl'), 'wb') as f:
        pickle.dump(clf, f)
    print("[OK] Saved voice_model.pkl (trained on real audio)")

    labels = [c for c in CLASSES if c in set(y)]
    metrics = {
        'model': f'{best_name} on {X.shape[1]} acoustic features (REAL audio: {corpora})',
        'accuracy': round(float(accuracy_score(y_te, y_hat)), 4),
        'macro_f1': round(float(f1_score(y_te, y_hat, average='macro')), 4),
        'confusion': confusion_matrix(y_te, y_hat, labels=labels).tolist(),
        'confusion_labels': labels,
        'train_rows': int(len(X_tr)), 'test_rows': int(len(X_te)),
        'augment_per_clip': args.augment,
        'eval': ('Held-out 20% of real labelled speech, SPEAKER-INDEPENDENT split '
                 '(no speaker appears in both train and test), features via the '
                 'SERVING extractor.'),
        'note': ('Acted-emotion corpora (adult, studio conditions) — closer to reality than '
                 'synthetic features, but child gaming speech remains the validation target.'),
    }
    meta_path = os.path.join(MODELS_DIR, 'model_metadata.json')
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    meta['voice_metrics'] = metrics
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print("[OK] voice_metrics (real-audio) written into model_metadata.json")


if __name__ == '__main__':
    main()
