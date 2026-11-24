"""
Voice hyperparameter sensitivity study: HistGradientBoosting on the 36 acoustic
features (CREMA-D + EMO-DB + RAVDESS + URDU), speaker-independent.

Question: the deployed voice model uses HGB(max_iter=300, learning_rate=0.1) with
every other hyperparameter at its sklearn default, set by hand rather than searched.
Did leaving it untuned cost accuracy?

PROTOCOL (nested; model selection never sees the test set)
  0. Data and split are the ablation protocol's, REUSED rather than re-implemented:
     collect_files / build_dataset / balance from ml/train_voice_real.py, and boot_ci /
     SEED / DATA from ml/ablation_studies.py. Rows = every labelled clip plus one
     augmented copy (the deployed "full" config). Speakers are split ONCE by
     GroupShuffleSplit(test_size=0.2, random_state=42) on the un-augmented rows. The
     FIXED test set is the un-augmented clips of the held-out speakers. The training
     side is class-balanced by downsampling (rng seed 42), exactly as in ablate_voice.
  1. REPLICATION GATE. The UNMODIFIED ablation_studies.ablate_voice() is run (its
     features come from the cache through a patched build_dataset, and its estimator
     is wrapped only to record what it fits and predicts). Then the deployed config is
     refit on this script's re-derived split. Both must reproduce the
     docs/ablation_results.json voice "full" accuracy (0.5622) within 0.002, on a
     bit-identical training matrix. If they do not, the script stops and writes
     replication.match = false.
  2. SEARCH on the training speakers only, with GroupKFold(5) over training speakers
     (augmented copies stay with their speaker). Each fold re-applies the deployed
     training recipe to the fold-train speakers (class-balance by downsampling with
     rng seed 42+k, then fit). The fold is scored on the UN-AUGMENTED clips of the
     fold-validation speakers, a small copy of the test condition. Every config sees
     the same folds (a paired comparison). The selection metric is macro-F1; accuracy
     is also recorded. Grid: learning_rate {0.03, 0.1, 0.3} x max_iter {150, 300, 600}
     x max_leaf_nodes {15, 31, 63} x l2_regularization {0, 1} = 54 configs. Ties are
     broken by accuracy, then in favour of the deployed config, then by grid order.
  3. TEST, touched once, for two models: the deployed config and the CV-best config,
     each refit on the full balanced training set. A paired bootstrap of
     accuracy(best) - accuracy(deployed) uses 1,000 resamples of the test set with
     seed 42 (ablation_studies.boot_ci, recording the per-resample differences).

  Early stopping. The deployed estimator leaves early_stopping='auto', which sklearn
  turns ON only when the fit set has more than 10,000 rows. The full balanced training
  set has 10,528 rows, so it is ON. A CV fold-train set has about 8,400 rows, where it
  would silently turn OFF, and CV would then score a different procedure from the one
  the final fit runs. Every CV fit therefore fixes early_stopping to the value 'auto'
  takes on the full training set (True). The final fits keep the deployed spec
  ('auto'), and the script asserts that it resolved to ON. Under early stopping
  max_iter is only a cap, so the iterations actually used (n_iter_) are reported too.
  One extra row (CV only, never a selection candidate) shows the deployed config with
  early stopping OFF.

Features are cached in data/voice/_cache/ (gitignored with data/voice/). The cache is
keyed on the clip list and the feature and augmentation code, so a re-run takes
minutes. Writes docs/hparam_voice.json. It never touches backend/models, so the
deployed model is unchanged. Run from the project root:
    python ml/hparam_voice.py [--jobs N]
"""
import argparse
import hashlib
import itertools
import json
import os
import sys
import time

import numpy as np

ML_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ML_DIR)

import ablation_studies as abl      # noqa: E402  (also puts backend/ on sys.path)
import train_voice_real as tvr      # noqa: E402

from sklearn.ensemble import HistGradientBoostingClassifier         # noqa: E402
from sklearn.metrics import accuracy_score, f1_score                 # noqa: E402
from sklearn.model_selection import GroupKFold, GroupShuffleSplit    # noqa: E402

ROOT      = abl.ROOT
SEED      = abl.SEED
OUT       = os.path.join(abl.DOCS, 'hparam_voice.json')
CACHE_DIR = os.path.join(abl.DATA, 'voice', '_cache')   # data/voice/ is gitignored
TOL       = 0.002
N_FOLDS   = 5
FULL_ROW  = 'full (36 feats, 4 corpora, aug x1)'
GRID = {
    'learning_rate':     [0.03, 0.1, 0.3],
    'max_iter':          [150, 300, 600],
    'max_leaf_nodes':    [15, 31, 63],
    'l2_regularization': [0.0, 1.0],
}
DEPLOYED = {'learning_rate': 0.1, 'max_iter': 300, 'max_leaf_nodes': 31, 'l2_regularization': 0.0}
JOBS = 8
CACHE_LOG = []


def _r(x, n=4):
    return round(float(x), n)


def _rel(p):
    return os.path.relpath(p, ROOT).replace('\\', '/')


def _sha(a):
    a = np.ascontiguousarray(a)
    return hashlib.sha1(a.tobytes() + repr((a.dtype.str, a.shape)).encode(),
                        usedforsecurity=False).hexdigest()      # identity digest only


# ── feature cache around the trainer's own build_dataset ─────────────────────────
_ORIG_BUILD = tvr.build_dataset


def _cache_key(labelled, n_aug, seed):
    h = hashlib.sha1(usedforsecurity=False)     # cache key, not a security use
    for src in (os.path.join(ROOT, 'backend', 'audio_features.py'), tvr.__file__):
        with open(src, 'rb') as f:              # feature / augmentation code
            h.update(hashlib.sha1(f.read(), usedforsecurity=False).digest())
    h.update(f'{n_aug}|{seed}'.encode())
    for path, lab in labelled:                  # the clip list itself
        h.update(f'{_rel(path)}|{lab}|{os.path.getsize(path)}\n'.encode())
    return h.hexdigest()[:16]


def cached_build_dataset(labelled, n_aug, seed=42, jobs=1):
    """train_voice_real.build_dataset, memoised to disk. Output does not depend on
    `jobs` (each clip's augmentation is seeded seed+i), so more workers are used."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'voice36_aug{n_aug}_seed{seed}_'
                                   f'{_cache_key(labelled, n_aug, seed)}.npz')
    if os.path.exists(path):
        with np.load(path, allow_pickle=False) as z:
            X, y, g, sk = z['X'], z['y'], z['groups'], int(z['skipped'])
        CACHE_LOG.append({'n_aug': n_aug, 'hit': True, 'path': _rel(path)})
        return X, y, g, sk
    t = time.time()
    X, y, g, sk = _ORIG_BUILD(labelled, n_aug, seed=seed, jobs=max(jobs, JOBS))
    np.savez_compressed(path, X=X, y=y, groups=g, skipped=np.int64(sk))
    CACHE_LOG.append({'n_aug': n_aug, 'hit': False, 'path': _rel(path),
                      'extract_s': _r(time.time() - t, 1)})
    return X, y, g, sk


class _RecordingHGB(HistGradientBoostingClassifier):
    """ablate_voice's own estimator, unchanged except that it logs what it saw."""
    log = []

    def fit(self, X, y, *args, **kwargs):
        type(self).log.append({'X_sha': _sha(X), 'y_sha': _sha(y), 'n': int(len(y))})
        return super().fit(X, y, *args, **kwargs)

    def predict(self, X):
        p = super().predict(X)
        type(self).log[-1]['pred'] = np.asarray(p).copy()
        return p


# ── data + the ablation split ──────────────────────────────────────────────────
def load_split():
    class A:   # ablate_voice's corpus dirs (it builds this same class internally)
        ravdess = os.path.join(abl.DATA, 'voice', 'RAVDESS')
        cremad  = os.path.join(abl.DATA, 'voice', 'CREMA-D')
        extra   = [os.path.join(abl.DATA, 'voice', 'EMO-DB'), os.path.join(abl.DATA, 'voice', 'URDU')]
        limit   = 0
    labelled = tvr.collect_files(A)
    X1, y1, g1, sk1 = tvr.build_dataset(labelled, n_aug=1, jobs=JOBS)   # originals + aug
    X0, y0, g0, sk0 = tvr.build_dataset(labelled, n_aug=0, jobs=JOBS)   # originals only
    _, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2,
                                       random_state=SEED).split(X0, y0, g0))
    te_speakers = sorted(set(g0[te_idx]))
    te0 = np.isin(g0, te_speakers)
    pool = ~np.isin(g1, te_speakers)                 # training side, orig + aug
    Xp, yp, gp = X1[pool], y1[pool], g1[pool]
    X_tr, y_tr, g_tr = tvr.balance(Xp, yp, gp, np.random.default_rng(SEED))
    return dict(labelled=labelled, X0=X0, y0=y0, g0=g0, Xp=Xp, yp=yp, gp=gp,
                X_tr=X_tr, y_tr=y_tr, X_test=X0[te0], y_test=y0[te0],
                te_speakers=te_speakers, n_rows_aug=len(X1), n_rows_orig=len(X0),
                skipped=int(sk1 + sk0))


def replicate(d):
    with open(os.path.join(abl.DOCS, 'ablation_results.json'), encoding='utf-8') as f:
        ref_rows = {r['config']: r for r in json.load(f)['voice']}
    ref = ref_rows[FULL_ROW]

    # (a) the unmodified ablation function, estimator wrapped only to record
    _RecordingHGB.log.clear()
    real_cls, abl.HistGradientBoostingClassifier = abl.HistGradientBoostingClassifier, _RecordingHGB
    try:
        rows = abl.ablate_voice(jobs=JOBS)
    finally:
        abl.HistGradientBoostingClassifier = real_cls
    rec = _RecordingHGB.log[0]                       # the 'full' row's fit
    rerun = {r['config']: r for r in rows}

    # (b) the deployed config on this script's re-derived split
    dep = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=SEED)
    dep.fit(d['X_tr'], d['y_tr'])
    yh = dep.predict(d['X_test'])
    acc = accuracy_score(d['y_test'], yh)
    ci = abl.boot_ci(lambda a, b: accuracy_score(a, b), d['y_test'], yh)

    split_identical = (rec['X_sha'] == _sha(d['X_tr']) and rec['y_sha'] == _sha(d['y_tr']))
    rerun_full = rerun[FULL_ROW]['accuracy']
    match = bool(split_identical and abs(acc - ref['accuracy']) <= TOL
                 and abs(rerun_full - ref['accuracy']) <= TOL)
    out = {
        'deployed_test': _r(acc), 'ablation_json': ref['accuracy'], 'match': match,
        'tolerance': TOL, 'abs_diff': _r(abs(acc - ref['accuracy']), 6),
        'deployed_test_ci95': list(ci), 'ablation_json_ci95': ref['acc_ci95'],
        'deployed_test_macro_f1': _r(f1_score(d['y_test'], yh, average='macro')),
        'unmodified_ablate_voice_rerun': rerun_full,
        'split_identical_to_ablate_voice': bool(split_identical),
        'predictions_identical_to_ablate_voice': bool(np.array_equal(rec['pred'], yh)),
        'deployed_early_stopping_active': bool(dep.do_early_stopping_),
        'deployed_n_iter_used': int(dep.n_iter_),
        'all_voice_rows': [{'config': c, 'json': ref_rows[c]['accuracy'],
                            'rerun': rerun[c]['accuracy'],
                            'abs_diff': _r(abs(rerun[c]['accuracy'] - ref_rows[c]['accuracy']), 6)}
                           for c in ref_rows if c in rerun],
    }
    return out, dep, yh


# ── CV search ─────────────────────────────────────────────────────────────────
def _fit_score(params, es, X_tr, y_tr, X_va, y_va, labels):
    clf = HistGradientBoostingClassifier(**params, early_stopping=es, random_state=SEED)
    clf.fit(X_tr, y_tr)
    yh = clf.predict(X_va)
    return (float(f1_score(y_va, yh, average='macro', labels=labels)),
            float(accuracy_score(y_va, yh)), int(clf.n_iter_))


def make_folds(d):
    folds, sizes = [], []
    te = set(d['te_speakers'])
    for k, (tr, va) in enumerate(GroupKFold(n_splits=N_FOLDS).split(d['Xp'], d['yp'], d['gp'])):
        va_spk, tr_spk = set(d['gp'][va]), set(d['gp'][tr])
        assert not (va_spk & tr_spk) and not (va_spk & te) and not (tr_spk & te)
        Xf, yf, _ = tvr.balance(d['Xp'][tr], d['yp'][tr], d['gp'][tr],
                                np.random.default_rng(SEED + k))
        vm = np.isin(d['g0'], sorted(va_spk))        # un-augmented clips only
        folds.append((Xf, yf, d['X0'][vm], d['y0'][vm]))
        sizes.append({'fold': k, 'train_speakers': len(tr_spk), 'val_speakers': len(va_spk),
                      'train_rows_balanced': int(len(yf)), 'val_rows_original': int(vm.sum())})
    return folds, sizes


def run_cv(folds, labels, configs):
    from joblib import Parallel, delayed
    cands = [(i, True) for i in range(len(configs))] + [(-1, False)]   # -1: deployed, ES off
    tasks = [(i, es, k) for i, es in cands for k in range(N_FOLDS)]
    cfg = lambda i: configs[i] if i >= 0 else DEPLOYED                  # noqa: E731
    tasks.sort(key=lambda t: (cfg(t[0])['learning_rate'], -cfg(t[0])['max_iter'],
                              -cfg(t[0])['max_leaf_nodes']))           # slowest first
    out = Parallel(n_jobs=JOBS)(delayed(_fit_score)(cfg(i), es, *folds[k], labels)
                                for i, es, k in tasks)
    res = {}
    for (i, es, k), (f1, acc, it) in zip(tasks, out):
        res.setdefault((i, es), {})[k] = (f1, acc, it)

    def summary(i, es):
        a = np.array([res[(i, es)][k] for k in range(N_FOLDS)])
        return {'f1_folds': a[:, 0], 'mean': a[:, 0].mean(), 'std': a[:, 0].std(),
                'acc_mean': a[:, 1].mean(), 'acc_std': a[:, 1].std(), 'n_iter_mean': a[:, 2].mean()}
    return [summary(i, True) for i in range(len(configs))], summary(-1, False)


def pub(s, params=None, rank=None):
    o = {} if params is None else {'params': params}
    o.update({'mean': _r(s['mean']), 'std': _r(s['std']), 'acc_mean': _r(s['acc_mean']),
              'acc_std': _r(s['acc_std']), 'n_iter_mean': _r(s['n_iter_mean'], 1)})
    if rank is not None:
        o['rank'] = rank
    return o


# ── conclusion ──────────────────────────────────────────────────────────────────
def conclude(rep, spread, dep_cv, dep_rank, n_cfg, marg_range, best_params, best_n_iter, test,
             es_off=None):
    lo, hi = test['diff_ci95']
    top_param = max(marg_range, key=marg_range.get)
    flat = [p for p, v in marg_range.items() if v < dep_cv['std']]
    others = [p for p in flat if p != top_param]
    fmt = ', '.join(f'{k}={v}' for k, v in best_params.items())
    s = (f"Replication passed: the deployed config refit on the ablation split scores "
         f"{rep['deployed_test']:.4f} against {rep['ablation_json']:.4f} in "
         f"ablation_results.json, on a training matrix bit-identical to ablate_voice's. "
         f"Across the {n_cfg}-config grid (GroupKFold(5) over training speakers only), CV "
         f"macro-F1 runs from {spread['min']:.4f} to {spread['max']:.4f} (median "
         f"{spread['median']:.4f}). The deployed config scores {dep_cv['mean']:.4f} +/- "
         f"{dep_cv['std']:.4f} and ranks {dep_rank}/{n_cfg}. {top_param} moves the marginal "
         f"mean most ({marg_range[top_param]:.4f})")
    if len(flat) == len(marg_range):
        s += (f", yet every hyperparameter's marginal range, that one included, is smaller than "
              f"one fold-std of the deployed config ({dep_cv['std']:.4f}). ")
    elif others:
        s += (f", while {', '.join(others)} move it by less than one fold-std "
              f"({dep_cv['std']:.4f}). ")
    else:
        s += ". "
    s += (f"Early stopping is active, so the deployed model uses {rep['deployed_n_iter_used']} "
          f"of its 300-iteration cap and max_iter is not the binding setting. ")
    if es_off is not None:
        s += (f"Early stopping itself was held at its deployed value (ON); a CV-only row with it "
              f"OFF scores {es_off['mean']:.4f} +/- {es_off['std']:.4f}, "
              f"{'above' if es_off['mean'] > spread['max'] else 'below'} the CV-best "
              f"{spread['max']:.4f}, but it was never a selection candidate, so the test set "
              f"says nothing about it. ")
    if best_params == DEPLOYED:
        s += ("The deployed config is itself the CV-best, so there is nothing to switch to; its "
              "hand-set hyperparameters cost no measurable accuracy.")
        return s
    s += (f"On the fixed test set, the CV-best config ({fmt}; {best_n_iter} iterations) scores "
          f"{test['best']:.4f} against {test['deployed']:.4f} for the deployed config: a paired "
          f"difference of {test['diff']:+.4f}, 95% CI [{lo:+.4f}, {hi:+.4f}], with the best config "
          f"ahead in {test['p_best_better'] * 100:.1f}% of resamples. ")
    if lo > 0:
        s += ("That is a real gain (the CI excludes 0). It is NOT adopted here: switching needs "
              "full re-validation (ablation table, calibration of the served probabilities), a "
              "per-corpus/language fairness re-audit and an on-device latency and size check. "
              "The deployed model is unchanged.")
    elif hi < 0:
        s += ("The CV-best config is significantly worse on test, so its CV advantage did not "
              "transfer. The deployed config stands.")
    else:
        s += ("No detectable gain: the CI includes 0, so the hand-set values of the searched "
              "hyperparameters cost no measurable accuracy and the deployed model stays as it is.")
    return s


def write(obj):
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
    print(f'[OK] wrote {_rel(OUT)}')


def main():
    global JOBS
    ap = argparse.ArgumentParser(description='Voice HGB hyperparameter sensitivity study')
    ap.add_argument('--jobs', type=int, default=max(1, min(20, (os.cpu_count() or 2) - 4)))
    JOBS = ap.parse_args().jobs
    t0 = time.time()

    defaults = HistGradientBoostingClassifier().get_params()
    assert all(defaults[p] == DEPLOYED[p] for p in ('max_leaf_nodes', 'l2_regularization')), \
        'sklearn defaults changed: the deployed spec no longer equals DEPLOYED'
    tvr.build_dataset = cached_build_dataset     # ablate_voice imports it at call time

    configs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    base = {
        'model': ('voice: HistGradientBoostingClassifier on 36 acoustic features '
                  '(CREMA-D, EMO-DB, RAVDESS, URDU; originals + 1 augmented copy per clip)'),
        'protocol': ('Nested and speaker-independent. The ablation split is reused exactly '
                     '(GroupShuffleSplit test_size=0.2, seed 42; fixed test set = un-augmented '
                     'clips of unseen speakers). A replication gate comes first. Hyperparameters '
                     'are searched by GroupKFold(5) over TRAINING speakers only, re-applying the '
                     'balance-then-fit recipe inside each fold and scoring on fold-validation '
                     'un-augmented clips, selecting on macro-F1. The test set is used once, for the '
                     'deployed and the CV-best configs, with a paired bootstrap (1,000 resamples, '
                     'seed 42).'),
        'search_space': GRID,
        'fixed_params': {'early_stopping': True, 'early_stopping_note':
                         "'auto' in the deployed spec, which sklearn resolves to ON for the 10,528-"
                         "row training set; fixed to True in CV so the ~8,400-row folds run the "
                         "same procedure", 'validation_fraction': 0.1, 'n_iter_no_change': 10,
                         'min_samples_leaf': defaults['min_samples_leaf'],
                         'max_depth': defaults['max_depth'], 'max_bins': defaults['max_bins'],
                         'random_state': SEED},
        'deployed_params': DEPLOYED,
        'n_configs': len(configs),
        'cv': {'scheme': ('GroupKFold over training speakers (augmented copies stay with their '
                          'speaker). Fold-train = original + augmented rows of the fold-train '
                          'speakers, class-balanced by downsampling (rng seed 42+k). Fold-validation '
                          '= un-augmented clips of the fold-validation speakers. All configs see the '
                          'same folds. std = population std over folds.'),
               'folds': N_FOLDS, 'metric': 'macro_f1 (selection); accuracy also recorded'},
    }

    print(f'[1/4] features + ablation split  (jobs {JOBS})')
    d = load_split()
    print(f'      {len(d["labelled"])} clips, train {len(d["y_tr"])} balanced rows, '
          f'test {len(d["y_test"])} original clips / {len(d["te_speakers"])} speakers')
    print('[2/4] replication gate (unmodified ablate_voice + deployed refit)')
    rep, dep_model, yh_dep = replicate(d)
    base['data'] = {'clips': len(d['labelled']), 'rows_original_plus_aug': d['n_rows_aug'],
                    'rows_original': d['n_rows_orig'], 'skipped': d['skipped'],
                    'train_rows_balanced': int(len(d['y_tr'])), 'test_rows': int(len(d['y_test'])),
                    'test_speakers': len(d['te_speakers']),
                    'train_speakers': len(set(d['gp'])), 'feature_cache': CACHE_LOG}
    print(f"      deployed {rep['deployed_test']} vs json {rep['ablation_json']}  "
          f"rerun {rep['unmodified_ablate_voice_rerun']}  split identical "
          f"{rep['split_identical_to_ablate_voice']}  match {rep['match']}")
    if not rep['match']:
        base.update({'replication': rep, 'conclusion': (
            'STOPPED at the replication gate: the deployed config did not reproduce the ablation '
            'number on an identical split, so no search was run. See replication.'),
            'runtime_s': _r(time.time() - t0, 1)})
        write(base)
        sys.exit(2)

    print(f'[3/4] CV search: {len(configs)} configs x {N_FOLDS} folds (+1 CV-only row)')
    folds, sizes = make_folds(d)
    base['cv']['fold_sizes'] = sizes
    labels = sorted(np.unique(d['y_tr']).tolist())
    stats, es_off = run_cv(folds, labels, configs)
    dep_i = configs.index(DEPLOYED)
    order = sorted(range(len(configs)),
                   key=lambda i: (-stats[i]['mean'], -stats[i]['acc_mean'], i != dep_i, i))
    best_i = order[0]
    best_params = configs[best_i]
    means = np.array([s['mean'] for s in stats])
    accs = np.array([s['acc_mean'] for s in stats])
    dep_rank = int(1 + (means > stats[dep_i]['mean']).sum())
    marginal = {p: {str(v): _r(np.mean([stats[i]['mean'] for i, c in enumerate(configs) if c[p] == v]))
                    for v in vals} for p, vals in GRID.items()}
    marginal_acc = {p: {str(v): _r(np.mean([stats[i]['acc_mean'] for i, c in enumerate(configs)
                                            if c[p] == v])) for v in vals} for p, vals in GRID.items()}
    marg_range = {p: _r(max(m.values()) - min(m.values())) for p, m in marginal.items()}
    spread = {'min': _r(means.min()), 'median': _r(np.median(means)), 'max': _r(means.max())}
    gap = stats[best_i]['f1_folds'] - stats[dep_i]['f1_folds']

    print('[4/4] test set: deployed vs CV-best (paired bootstrap)')
    if best_i == dep_i:
        yh_best, best_n_iter = yh_dep, int(dep_model.n_iter_)
    else:
        bm = HistGradientBoostingClassifier(**best_params, random_state=SEED)   # deployed spec
        bm.fit(d['X_tr'], d['y_tr'])
        assert bm.do_early_stopping_, "'auto' should resolve to early stopping ON at this size"
        yh_best, best_n_iter = bm.predict(d['X_test']), int(bm.n_iter_)
    y_test = d['y_test']
    diffs = []

    def diff_fn(y, s):                       # boot_ci's resamples, differences recorded
        v = accuracy_score(y, s[:, 0]) - accuracy_score(y, s[:, 1])
        diffs.append(v)
        return v
    lo, hi = abl.boot_ci(diff_fn, y_test, np.column_stack([yh_best, yh_dep]))
    diffs = np.array(diffs)
    ok_b, ok_d = yh_best == y_test, yh_dep == y_test
    acc_b, acc_d = accuracy_score(y_test, yh_best), accuracy_score(y_test, yh_dep)
    test = {'metric': 'accuracy (fixed speaker-independent test set: un-augmented clips, unseen speakers)',
            'deployed': _r(acc_d), 'best': _r(acc_b), 'diff': _r(acc_b - acc_d),
            'diff_ci95': [lo, hi], 'p_best_better': _r((diffs > 0).mean(), 3),
            'p_best_worse': _r((diffs < 0).mean(), 3), 'n_resamples': int(len(diffs)),
            'deployed_ci95': list(abl.boot_ci(lambda a, b: accuracy_score(a, b), y_test, yh_dep)),
            'best_ci95': list(abl.boot_ci(lambda a, b: accuracy_score(a, b), y_test, yh_best)),
            'deployed_macro_f1': _r(f1_score(y_test, yh_dep, average='macro')),
            'best_macro_f1': _r(f1_score(y_test, yh_best, average='macro')),
            'discordant': {'best_only_correct': int((ok_b & ~ok_d).sum()),
                           'deployed_only_correct': int((~ok_b & ok_d).sum())},
            'n_iter_used': {'deployed': int(dep_model.n_iter_), 'best': best_n_iter}}

    base.update({
        'replication': rep,
        'cv_deployed': pub(stats[dep_i], rank=dep_rank),
        'cv_top10': [pub(stats[i], configs[i], rank=int(1 + (means > stats[i]['mean']).sum()))
                     for i in order[:10]],
        'cv_spread': spread,
        'cv_spread_accuracy': {'min': _r(accs.min()), 'median': _r(np.median(accs)),
                               'max': _r(accs.max())},
        'cv_best_minus_deployed': {'mean': _r(gap.mean()), 'per_fold': [_r(g) for g in gap],
                                   'folds_best_ahead': int((gap > 0).sum())},
        'cv_supplementary': {'deployed_early_stopping_off': pub(es_off),
                             'note': 'CV only, never a selection candidate or tested'},
        'marginal': marginal,
        'marginal_accuracy': marginal_acc,
        'marginal_range': marg_range,
        'best_params': best_params,
        'test': test,
        'cv_all': [pub(stats[i], configs[i], rank=int(1 + (means > stats[i]['mean']).sum()))
                   for i in order],
    })
    base['conclusion'] = conclude(rep, spread, base['cv_deployed'], dep_rank, len(configs),
                                  marg_range, best_params, best_n_iter, test,
                                  es_off=base['cv_supplementary']['deployed_early_stopping_off'])
    base['env'] = {'sklearn': __import__('sklearn').__version__, 'numpy': np.__version__}
    base['runtime_s'] = _r(time.time() - t0, 1)
    write(base)
    print(f"best {best_params}  CV {spread}  test dep {test['deployed']} best {test['best']} "
          f"diff {test['diff']} CI {test['diff_ci95']} p {test['p_best_better']}  "
          f"{base['runtime_s']}s")
    print(base['conclusion'])


if __name__ == '__main__':
    main()
