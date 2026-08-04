# -*- coding: utf-8 -*-
"""Voice embedding-headroom experiment. Three configs, ONE speaker-independent
split (GroupShuffleSplit test 20%, seed 42 — the deployed protocol), identical
balancing, identical classifier family:

  A. 36 deployed acoustic features -> HistGB          (protocol baseline)
  B. w2v2 1024-d emotion embedding -> HistGB          (representation headroom)
  C. as B but trained on the corpora's FINE labels (9 classes), merged to the
     serving 4 classes at inference by summing grouped probabilities
     (label-mapping headroom on top of B)

Honest protocol notes: original clips only (the deployed trainer also used one
augmented variant per clip — a small advantage NOT given to any config here);
same undersample-balance on the train side (seed 42); accuracy + macro-F1 on the
untouched test speakers.
"""
import glob
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Embedding chunks produced by the extraction step (gitignored, ~1 GB).
CHUNKS = os.environ.get('VOICE_EMB_DIR', os.path.join(ROOT, 'data', 'voice_emb_chunks'))

FINE_TO_4 = {'angry': 'angry', 'happy': 'excited', 'surprised': 'excited',
             'sad': 'frustrated', 'fear': 'frustrated', 'disgust': 'frustrated',
             'neutral': 'neutral', 'calm': 'neutral', 'boredom': 'neutral'}
CLASSES4 = ['angry', 'excited', 'frustrated', 'neutral']


def load_all():
    f36, emb, y4, yf, spk = [], [], [], [], []
    for p in sorted(glob.glob(os.path.join(CHUNKS, 'chunk_*.npz'))):
        z = np.load(p, allow_pickle=True)
        f36.append(z['f36']); emb.append(z['emb'])
        y4.append(z['y4']); yf.append(z['yf']); spk.append(z['spk'])
    return (np.vstack(f36), np.vstack(emb), np.concatenate(y4),
            np.concatenate(yf), np.concatenate(spk))


def balance(X, y, rng):
    classes, counts = np.unique(y, return_counts=True)
    m = counts.min()
    keep = np.concatenate([rng.choice(np.where(y == c)[0], m, replace=False)
                           for c in classes])
    rng.shuffle(keep)
    return X[keep], y[keep]


def main():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import GroupShuffleSplit

    f36, emb, y4, yf, spk = load_all()
    print(f'{len(y4)} clips, {len(set(spk))} speakers', flush=True)
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
                  .split(f36, y4, groups=spk))
    print(f'test side: {len(te)} clips, {len(set(spk[te]))} unseen speakers', flush=True)
    rng = np.random.default_rng(42)
    results = {}

    # A: 36 features, 4-class
    Xa, ya = balance(f36[tr], y4[tr], rng)
    clf = HistGradientBoostingClassifier(random_state=42).fit(Xa, ya)
    pa = clf.predict(f36[te])
    results['A_36feat_4class'] = {
        'acc': round(float(accuracy_score(y4[te], pa)), 4),
        'macro_f1': round(float(f1_score(y4[te], pa, average='macro')), 4)}
    print('A (36-feat baseline):', results['A_36feat_4class'], flush=True)

    # B: embeddings, 4-class
    Xb, yb = balance(emb[tr], y4[tr], rng)
    clf_b = HistGradientBoostingClassifier(random_state=42).fit(Xb, yb)
    pb = clf_b.predict(emb[te])
    results['B_emb_4class'] = {
        'acc': round(float(accuracy_score(y4[te], pb)), 4),
        'macro_f1': round(float(f1_score(y4[te], pb, average='macro')), 4)}
    print('B (w2v2 embeddings):', results['B_emb_4class'], flush=True)

    # C: embeddings, fine labels -> grouped probabilities
    Xc, yc = balance(emb[tr], yf[tr], rng)
    clf_c = HistGradientBoostingClassifier(random_state=42).fit(Xc, yc)
    proba = clf_c.predict_proba(emb[te])
    grouped = np.zeros((len(te), len(CLASSES4)))
    for j, fine in enumerate(clf_c.classes_):
        grouped[:, CLASSES4.index(FINE_TO_4[fine])] += proba[:, j]
    pc = np.array(CLASSES4)[grouped.argmax(axis=1)]
    results['C_emb_fine_grouped'] = {
        'acc': round(float(accuracy_score(y4[te], pc)), 4),
        'macro_f1': round(float(f1_score(y4[te], pc, average='macro')), 4)}
    print('C (emb + fine-label training):', results['C_emb_fine_grouped'], flush=True)

    results['protocol'] = ('GroupShuffleSplit 20% test seed 42 on speaker ids; '
                           'original clips only (no augmentation for ANY config); '
                           'undersample-balanced train; HistGB default, seed 42. '
                           'Deployed reference on ITS split (with augmentation): 0.574.')
    with open(os.path.join(ROOT, "docs", 'voice_headroom.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print('[OK] wrote voice_headroom.json', flush=True)


if __name__ == '__main__':
    main()
