"""
Hyperparameter sensitivity study: CHAT channel (TF-IDF + LogisticRegression recipe).

Question: the deployed recipe hand-sets LogisticRegression(C=1.0, class_weight='balanced').
Was that a lucky or a costly choice, and would a proper search have changed it?

PROTOCOL (fixed before running; CONDA_valid is the test set and is scored exactly once,
for two models: the deployed config and the validation-best config)

  Reuse.  Everything comes unchanged from ml/ablation_studies.py: chat_sources() and
    load_norm() (training corpora, CONDA_valid), train_chat() (dedupe by cleaned text ->
    1:1 class balance by downsampling -> stratified 85/15 fit/calibration split -> TF-IDF
    word 1-2 + char_wb 3-5 -> LogisticRegression -> isotonic calibration), chat_scores()
    (calibrated ML score noisy-OR keyword score = the served score), chat_row(), boot_ci()
    and ALERT_T. Only the LogisticRegression constructor's C and class_weight are
    overridden, by swapping that module-level name for the duration of one train_chat()
    call (recipe_with()). The rest of the recipe, seeds included, is untouched.

  0. Replication gate.  The deployed config is retrained on all training corpora through
     exactly that path and scored on CONDA_valid. It must reproduce the "full recipe
     (deployed)" PR-AUC in docs/ablation_results.json within 0.002. If it does not, the
     study stops and writes replication.match = false.

  1. Validation slice (training data only).  The pooled training corpora are
     de-duplicated by cleaned text with train_chat()'s own rule (majority label, ties ->
     toxic) and a stratified 15% slice is carved off (seed 42). Every raw row whose
     cleaned text lands in the slice is dropped from every source, so no validation text,
     and no duplicate of one, is ever trained on. CONDA_valid plays no part.

  2. Search.  C in {0.125, 0.25, 0.5, 1, 2, 4, 8} x class_weight in {balanced, None} gives
     14 configs. Each runs through the unchanged recipe on the remaining rows. The TF-IDF
     vectoriser is fitted ONCE on those rows and shared by all 14 configs (SharedVec,
     keyed by a content hash of the rows). TF-IDF never sees labels, so sharing it leaks
     nothing. Selection metric: PR-AUC (average precision) of the served score on the
     slice. Ties at the reported precision (4 decimals) go to the deployed value of each
     hyperparameter. 'std' = bootstrap SD over 1,000 resamples of the slice; the
     resamples are the same for every config, so between-config differences are paired.

  3. Test.  The deployed and the validation-best configs are each refitted on all
     training corpora and scored on CONDA_valid: PR-AUC with a bootstrap CI, precision
     and recall at ALERT_T, and a PAIRED bootstrap of the PR-AUC difference (best minus
     deployed; 1,000 test-set resamples, seed 42). A difference whose 95% CI includes 0
     is reported as no detectable gain. This script never changes the deployed model.

  4. In-domain selection (robustness variant, stored under "in_domain_selection").  The
     step-1 slice is mostly general-corpus text, which may be why its pick did worse on
     gaming chat. The variant repeats steps 1-3 with the slice drawn from CONDA_train ONLY:
     its de-duplicated texts (CONDA_train's own majority label, ties -> toxic), a
     stratified 15% slice (seed 42), and every raw row in ANY corpus whose cleaned text is
     in the slice removed from training. The same 14 configs are selected on that slice by
     the same rule; CONDA_valid takes no part in selection. The pick is then scored once on
     CONDA_valid against the deployed config with the same paired bootstrap.

Writes docs/hparam_chat.json. Run from the project root (~20 min):
    python ml/hparam_chat.py
Only step 4, merged into the existing JSON after a fresh replication gate (~10 min):
    python ml/hparam_chat.py --in-domain-only
"""
import argparse
import contextlib
import hashlib
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ablation_studies as ab  # noqa: E402  (also puts backend/ on sys.path)

from sklearn.exceptions import ConvergenceWarning               # noqa: E402
from sklearn.metrics import average_precision_score as AP       # noqa: E402
from sklearn.model_selection import train_test_split            # noqa: E402

OUT      = os.path.join(ab.DOCS, 'hparam_chat.json')
USE      = ('gen', 'conda', 'davidson', 'hasoc', 'wiki')   # deployed source set (ablate_chat)
GRID_C   = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
GRID_CW  = ['balanced', None]
DEPLOYED = {'C': 1.0, 'class_weight': 'balanced'}           # as hard-coded in ab.train_chat
VAL_FRAC = 0.15
TOL      = 0.002

_LR, _MAKE_VEC = ab.LogisticRegression, ab.make_vec        # originals, captured before patching


def r4(x):
    return round(float(x), 4)


def label(p):
    return f"C={p['C']:g}, class_weight={p['class_weight']}"


# ── the only intervention: LR's C / class_weight, plus one shared vectoriser fit ──

def _digest(texts):
    h = hashlib.sha1(usedforsecurity=False)     # identity digest, not a security use
    for t in texts:
        h.update(str(t).encode('utf-8', 'surrogatepass'))
        h.update(b'\x00')
    return h.hexdigest()


class SharedVec:
    """Stands in for ab.make_vec()'s vectoriser. The real one (from the original
    make_vec) is fitted once per distinct training input, keyed by a content hash, and
    every transform is memoised in `store`. Same rows give the same fit, computed once."""

    def __init__(self, store, char_ngrams):
        self.store, self.char_ngrams, self.fit_key = store, char_ngrams, None

    def fit_transform(self, texts):
        self.fit_key = ('fit', self.char_ngrams, _digest(texts))
        if self.fit_key not in self.store:
            vec = _MAKE_VEC(self.char_ngrams)
            self.store[self.fit_key] = (vec, vec.fit_transform(texts))
            self.store['n_vectoriser_fits'] = self.store.get('n_vectoriser_fits', 0) + 1
        return self.store[self.fit_key][1]

    def transform(self, texts):
        key = (self.fit_key, _digest(texts))
        if key not in self.store:
            self.store[key] = self.store[self.fit_key][0].transform(texts)
        return self.store[key]


@contextlib.contextmanager
def recipe_with(C, class_weight, store):
    """ab.train_chat() with only LogisticRegression(C=, class_weight=) overridden and the
    vectoriser shared through `store`; every other argument and step is unchanged."""
    def lr(**kw):
        kw.update(C=C, class_weight=class_weight)
        return _LR(**kw)
    ab.LogisticRegression = lr
    ab.make_vec = lambda char_ngrams=True: SharedVec(store, char_ngrams)
    try:
        yield
    finally:
        ab.LogisticRegression, ab.make_vec = _LR, _MAKE_VEC


def fit_and_score(sources, params, store, texts):
    """Full deployed recipe on `sources` with `params`; served scores for `texts`."""
    with recipe_with(params['C'], params['class_weight'], store), warnings.catch_warnings():
        warnings.simplefilter('ignore', ConvergenceWarning)
        clf, vec, cal = ab.train_chat(sources, USE)
    n_iter = int(np.max(clf.n_iter_))
    return ab.chat_scores(texts, clf, vec, cal), n_iter, n_iter < clf.max_iter


def boot_values(metric_fn, y, s):
    """ab.boot_ci() unchanged, also keeping every resample value (same seed => the same
    resample indices on every call, so values from different calls are paired)."""
    vals = []

    def rec(yy, ss):
        v = metric_fn(yy, ss)
        vals.append(v)
        return v
    ci = ab.boot_ci(rec, y, s)
    return np.array(vals), ci


# ── validation slice carved from the training corpora ──

def carve_validation(src, from_sources=USE):
    """Stratified 15% slice of the de-duplicated texts of `from_sources` (default: every
    training corpus, the main study; ('conda',) for the in-domain variant, where each
    text's label is then CONDA_train's own majority label). Rows whose cleaned text is in
    the slice are removed from EVERY source, so no slice text is trained on."""
    pool = pd.concat([src[k][['text', 'toxic']].assign(source=k) for k in from_sources],
                     ignore_index=True)
    pool['clean'] = pool['text'].map(ab.clean_text)
    pool = pool[pool['clean'].str.len() > 2]
    # train_chat()'s de-duplication rule: one row per cleaned text, majority label, ties -> toxic
    lab = pool.groupby('clean')['toxic'].mean().ge(0.5).astype(int)
    first = pool.drop_duplicates('clean').set_index('clean')['text']
    uniq = pd.DataFrame({'clean': lab.index, 'toxic': lab.values,
                         'text': first.reindex(lab.index).values})
    uniq['in_conda'] = uniq['clean'].isin(set(pool.loc[pool['source'] == 'conda', 'clean']))
    _, val = train_test_split(uniq, test_size=VAL_FRAC, random_state=ab.SEED,
                              stratify=uniq['toxic'])
    held = set(val['clean'])
    src_tr = {k: df[~df['text'].map(ab.clean_text).isin(held)].reset_index(drop=True)
              for k, df in src.items()}
    dropped = sum(len(src[k]) - len(src_tr[k]) for k in src)
    return src_tr, val.reset_index(drop=True), len(uniq), dropped


# ── conclusion text, written from the numbers ──

def conclude(rows, dep_row, best_row, test, abl, cw_gap):
    means = [r['mean'] for r in rows]
    rank = 1 + sum(m > dep_row['mean'] for m in means)
    txt = (f"On the training-only validation slice the 14 configs span PR-AUC "
           f"{min(means):.4f} to {max(means):.4f} (range {max(means) - min(means):.4f}). "
           f"The deployed C=1, class_weight=balanced scores {dep_row['mean']:.4f} "
           f"+/- {dep_row['std']:.4f} and ranks {rank} of 14. ")
    if cw_gap < 0.0005:
        txt += (f"class_weight has no effect here (largest gap at any C: {cw_gap:.4f}), "
                "because train_chat() already balances the classes 1:1 by downsampling, "
                "so 'balanced' weights come out at about 1.0. C is the only real knob. ")
    d, (lo, hi), p = test['diff'], test['diff_ci95'], test['p_best_better']
    dep_a, best_a = test['deployed_at_alert'], test['best_at_alert']
    if best_row['params'] == DEPLOYED:
        txt += ("Validation selects the deployed configuration itself, so CONDA_valid "
                f"scores one model ({test['deployed']:.4f}) and there is nothing to switch. ")
    else:
        txt += (f"Validation selects {label(best_row['params'])}. On CONDA_valid (scored "
                f"once) it reaches PR-AUC {test['best']:.4f} against {test['deployed']:.4f} "
                f"for the deployed config: a difference of {d:+.4f}, paired 95% CI "
                f"[{lo:+.4f}, {hi:+.4f}], better in {p:.0%} of resamples. At the "
                f"{ab.ALERT_T:g} alert threshold, precision/recall go from "
                f"{dep_a['precision']:.3f}/{dep_a['recall']:.3f} to "
                f"{best_a['precision']:.3f}/{best_a['recall']:.3f}. ")
        if lo <= 0 <= hi:
            txt += ("The CI includes 0, so there is no detectable gain and the hand-set "
                    "C=1.0 stands. ")
        elif lo > 0:
            txt += ("This is a real but small gain. Switching would mean re-deriving the "
                    "alert threshold, re-running the Hindi/Hinglish fairness audit and "
                    "re-checking the served bundle, so the deployed model stays as it is "
                    "and the gain is recorded as headroom. ")
        else:
            txt += ("The validation-best config is worse on gaming chat, so selection on the "
                    "pooled (mostly general-corpus) slice does not transfer to CONDA. The "
                    "deployed C=1.0 stands. ")
    txt += (f"For scale, the ablation shows that removing the CONDA domain data costs "
            f"{abl['full'] - abl['no_conda']:.3f} PR-AUC and removing char n-grams costs "
            f"{abl['full'] - abl['no_char']:.3f}. Data and representation matter more than "
            f"the regularisation strength.")
    return txt


# ── 4. robustness variant: select on in-domain (CONDA_train) text only ──

def conclude_in_domain(b):
    sl, t, dep_v = b['slice'], b['test'], b['val_deployed']
    txt = (f"Selected on a stratified 15% slice of CONDA_train alone ({sl['n_val']:,} unique "
           f"gaming-chat texts, prevalence {sl['val_prevalence']:.3f}; CONDA_valid untouched), "
           f"the 14 configs span slice PR-AUC {b['val_spread']['min']:.4f} to "
           f"{b['val_spread']['max']:.4f}; the deployed C=1, class_weight=balanced scores "
           f"{dep_v['mean']:.4f} +/- {dep_v['std']:.4f} (rank {dep_v['rank']} of 14). ")
    if b['best_params'] == DEPLOYED:
        txt += (f"In-domain selection picks the deployed configuration itself, so CONDA_valid "
                f"scores one model ({t['deployed']:.4f}) and there is nothing to switch to. ")
    else:
        lo, hi = t['diff_ci95']
        txt += (f"It picks {label(b['best_params'])}, which on CONDA_valid (scored once) reaches "
                f"PR-AUC {t['best']:.4f} against {t['deployed']:.4f} for the deployed config: "
                f"a difference of {t['diff']:+.4f}, paired 95% CI [{lo:+.4f}, {hi:+.4f}], better "
                f"in {t['p_best_better']:.1%} of resamples. ")
        if lo <= 0 <= hi:
            txt += "The CI includes 0, so there is no detectable gain and the deployed C=1.0 stands. "
        elif lo > 0:
            txt += ("This is a real but small gain, recorded as headroom and not adopted: switching "
                    "would mean re-deriving the alert threshold and re-running the fairness audit. ")
        else:
            txt += "It is worse on gaming chat, so the deployed C=1.0 stands. "
    pp = b['pooled_pick_on_conda_slice']
    if pp and pp['params'] != b['best_params']:
        txt += (f"The pooled slice's pick ({label(pp['params'])}) ranks {pp['rank']} of 14 on "
                f"the CONDA slice ({pp['mean']:.4f}), so its preference for weaker "
                f"regularisation does not carry over to gaming chat. ")
    if b['best_params'] == DEPLOYED:
        txt += "Selected in-domain, the hand-set C=1.0 is the tuned value."
    elif t['diff_ci95'][0] <= 0:
        txt += "Selected in-domain or not, the deployed C=1.0 stands."
    return txt.strip()


def in_domain_selection(src, s_dep, dep_row, y_te, x_te, full_store, pooled_pick=None):
    """Step 4. Same grid, recipe and tie rule as steps 1-3; only the slice changes (CONDA_train
    only). s_dep / dep_row are the deployed config's CONDA_valid scores from the replication
    gate, so the deployed model is not refitted; full_store shares its vectoriser fit."""
    t0 = time.time()
    src_tr, val, n_unique, n_dropped = carve_validation(src, from_sources=('conda',))
    y_val, x_val = val['toxic'].values, val['text'].tolist()
    print(f"[4] in-domain slice: {len(val)} of {n_unique} unique CONDA_train texts "
          f"(prevalence {y_val.mean():.3f}); {n_dropped} raw rows removed from training")
    store, rows = {}, []
    for C in GRID_C:
        for cw in GRID_CW:
            t1, p = time.time(), {'C': C, 'class_weight': cw}
            s, n_iter, conv = fit_and_score(src_tr, p, store, x_val)
            boots, _ = boot_values(AP, y_val, s)
            rows.append({'params': p, 'mean': float(AP(y_val, s)), 'boots': boots,
                         'std': float(np.std(boots, ddof=1)), 'lr_iterations': n_iter,
                         'converged': bool(conv)})
            print(f"    {label(p):<34} CONDA-slice PR-AUC {rows[-1]['mean']:.4f} "
                  f"+/- {rows[-1]['std']:.4f} ({n_iter} it) {time.time() - t1:.0f}s")
    dep_v = next(r for r in rows if r['params'] == DEPLOYED)
    for r in rows:
        d = r['boots'] - dep_v['boots']                     # paired: identical resamples
        r['diff_vs_deployed'], r['p_better_than_deployed'] = r['mean'] - dep_v['mean'], float(np.mean(d > 0))
    best = max(rows, key=lambda r: (round(r['mean'], 4), r['params']['C'] == DEPLOYED['C'],
                                    r['params']['class_weight'] == DEPLOYED['class_weight']))
    means = np.array([r['mean'] for r in rows])
    rank = lambda r: int(1 + np.sum(means > r['mean']))     # noqa: E731

    if best['params'] == DEPLOYED:
        best_row, diff, lo, hi, p_better = dep_row, 0.0, 0.0, 0.0, 0.0
    else:
        print(f"[4] refit {label(best['params'])} on all training corpora -> CONDA_valid")
        s_best, _, _ = fit_and_score(src, best['params'], full_store, x_te)
        best_row = ab.chat_row('best', y_te, s_best)
        diffs, (lo, hi) = boot_values(lambda yy, S: AP(yy, S[:, 1]) - AP(yy, S[:, 0]),
                                      y_te, np.column_stack([s_dep, s_best]))
        diff, p_better = float(AP(y_te, s_best) - AP(y_te, s_dep)), float(np.mean(diffs > 0))
    pp = next((r for r in rows if r['params'] == pooled_pick), None)
    b = {
        'question': ('Does selecting C / class_weight on in-domain gaming chat (CONDA_train only) '
                     'instead of the pooled, mostly general-corpus slice change the pick or the '
                     'CONDA_valid result?'),
        'protocol': ('Steps 1-3 repeated with the validation slice drawn from CONDA_train only: '
                     'de-duplicated by cleaned text (CONDA_train majority label, ties -> toxic), '
                     'stratified 15% slice (seed 42); every raw row in any corpus whose cleaned '
                     'text is in the slice removed from training; TF-IDF fitted once on the rest '
                     'and shared. Same 14 configs, metric (PR-AUC of the served score) and tie '
                     'rule. CONDA_valid takes no part in selection; it is scored once for the '
                     'pick against the deployed config (paired bootstrap, 1,000 resamples, '
                     'seed 42).'),
        'slice': {'source': 'CONDA_train only', 'n_val': int(len(val)),
                  'val_prevalence': r4(y_val.mean()), 'n_unique_conda_train_texts': int(n_unique),
                  'raw_rows_removed_from_training': int(n_dropped),
                  'vectoriser_fits': int(store['n_vectoriser_fits'])},
        'val_deployed': {'mean': r4(dep_v['mean']), 'std': r4(dep_v['std']), 'rank': rank(dep_v)},
        'val_spread': {'min': r4(means.min()), 'median': r4(np.median(means)), 'max': r4(means.max())},
        'val_all': [{'params': r['params'], 'mean': r4(r['mean']), 'std': r4(r['std']),
                     'rank': rank(r), 'diff_vs_deployed': r4(r['diff_vs_deployed']),
                     'p_better_than_deployed': r4(r['p_better_than_deployed']),
                     'lr_iterations': r['lr_iterations'], 'converged': r['converged']}
                    for r in rows],
        'best_params': best['params'],
        'pooled_pick_on_conda_slice': ({'params': pp['params'], 'mean': r4(pp['mean']),
                                        'rank': rank(pp)} if pp else None),
        'test': {'metric': 'PR-AUC (average precision) of the served score on CONDA_valid',
                 'deployed': dep_row['pr_auc'], 'best': best_row['pr_auc'], 'diff': r4(diff),
                 'diff_ci95': [r4(lo), r4(hi)], 'p_best_better': r4(p_better),
                 'deployed_ci95': dep_row['pr_auc_ci95'], 'best_ci95': best_row['pr_auc_ci95'],
                 'alert_threshold': ab.ALERT_T,
                 'deployed_at_alert': {'precision': dep_row['precision@alert'],
                                       'recall': dep_row['recall@alert']},
                 'best_at_alert': {'precision': best_row['precision@alert'],
                                   'recall': best_row['recall@alert']},
                 'n_test': int(len(y_te)),
                 'scored_on_conda_valid': ('deployed only (the pick is the deployed config)'
                                           if best['params'] == DEPLOYED
                                           else 'deployed + in-domain pick, once each')},
    }
    b['conclusion'] = conclude_in_domain(b)
    b['runtime_s'] = round(time.time() - t0, 1)
    print('    ' + b['conclusion'])
    return b


def main():
    ap = argparse.ArgumentParser(description='Chat LR hyperparameter sensitivity')
    ap.add_argument('--in-domain-only', action='store_true',
                    help='run the replication gate and step 4 only; merge into the existing JSON')
    args = ap.parse_args()
    t0 = time.time()
    src = ab.chat_sources()
    test = ab.load_norm(os.path.join(ab.DATA, 'conda', 'CONDA_valid.csv'))
    y_te, x_te = test['toxic'].values, test['text'].tolist()
    with open(os.path.join(ab.DOCS, 'ablation_results.json'), encoding='utf-8') as f:
        abl_rows = {r['config']: r for r in json.load(f)['chat']}
    ref = abl_rows['full recipe (deployed)']

    out = {'model': 'chat', 'protocol': (
        "Reuses ml/ablation_studies.py unchanged (chat_sources, load_norm, train_chat, "
        "chat_scores, chat_row, boot_ci); only LogisticRegression's C and class_weight are "
        "overridden inside train_chat. Replication gate first. Selection uses a stratified "
        "15% validation slice (seed 42) carved from the de-duplicated TRAINING corpora; every "
        "raw row whose cleaned text is in the slice is removed from training. The TF-IDF "
        "vectoriser is fitted once on the remaining rows and shared across configs "
        "(unsupervised, no label leakage). Metric: PR-AUC of the served score (isotonic-"
        "calibrated LR noisy-OR keyword score). CONDA_valid (never trained or selected on) "
        "is scored once, for the deployed config and the validation-best config, each "
        "refitted on all training corpora; paired bootstrap of the PR-AUC difference "
        "(1,000 resamples, seed 42).")}

    # ── 0. replication gate ──────────────────────────────────────────────────
    print('[0] replication gate: deployed config on all training corpora -> CONDA_valid')
    full_store = {}
    s_dep, it_dep, _ = fit_and_score(src, DEPLOYED, full_store, x_te)
    dep_row = ab.chat_row('deployed', y_te, s_dep)
    match = abs(dep_row['pr_auc'] - ref['pr_auc']) <= TOL
    out['replication'] = {
        'deployed_test': dep_row['pr_auc'], 'ablation_json': ref['pr_auc'], 'match': bool(match),
        'tolerance': TOL,
        'precision@alert': dep_row['precision@alert'],
        'ablation_precision@alert': ref['precision@alert'],
        'recall@alert': dep_row['recall@alert'], 'ablation_recall@alert': ref['recall@alert']}
    print(f"    PR-AUC {dep_row['pr_auc']:.4f} vs ablation {ref['pr_auc']:.4f} -> "
          f"{'MATCH' if match else 'NO MATCH'} ({time.time() - t0:.0f}s)")
    if not match:
        out['conclusion'] = ("Replication failed: the deployed config retrained through "
                             "ab.train_chat does not reproduce the ablation PR-AUC, so the "
                             "search was not run.")
        out['runtime_s'] = round(time.time() - t0, 1)
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=2)
        print(f'[STOP] wrote {OUT}')
        return

    if args.in_domain_only:
        with open(OUT, encoding='utf-8') as f:
            prev = json.load(f)
        assert prev['replication']['deployed_test'] == dep_row['pr_auc'], \
            'existing JSON was written from a different deployed fit; run the full study'
        prev['in_domain_selection'] = in_domain_selection(
            src, s_dep, dep_row, y_te, x_te, full_store, pooled_pick=prev.get('best_params'))
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(prev, f, indent=2)
        print(f"[OK] merged in_domain_selection into {OUT}  ({time.time() - t0:.0f}s)")
        return

    # ── 1. validation slice from the training corpora ────────────────────────
    src_tr, val, n_unique, n_dropped = carve_validation(src)
    y_val, x_val, m_conda = val['toxic'].values, val['text'].tolist(), val['in_conda'].values
    print(f"[1] validation slice: {len(val)} of {n_unique} unique texts "
          f"(prevalence {y_val.mean():.3f}; {int(m_conda.sum())} from CONDA_train); "
          f"{n_dropped} raw rows removed from training")

    # ── 2. search on the validation slice ────────────────────────────────────
    store, rows = {}, []
    for C in GRID_C:
        for cw in GRID_CW:
            t1 = time.time()
            p = {'C': C, 'class_weight': cw}
            s, n_iter, conv = fit_and_score(src_tr, p, store, x_val)
            boots, _ = boot_values(AP, y_val, s)
            rows.append({'params': p, 'mean': float(AP(y_val, s)), 'std': float(np.std(boots, ddof=1)),
                         'boots': boots, 'conda_part': float(AP(y_val[m_conda], s[m_conda])),
                         'lr_iterations': n_iter, 'converged': bool(conv)})
            print(f"    {label(p):<34} val PR-AUC {rows[-1]['mean']:.4f} "
                  f"+/- {rows[-1]['std']:.4f}  (CONDA part {rows[-1]['conda_part']:.4f}, "
                  f"{n_iter} it) {time.time() - t1:.0f}s")
    fit_key = next(k for k in store if isinstance(k, tuple) and k[0] == 'fit')
    vec_shape = store[fit_key][1].shape

    dep_cv = next(r for r in rows if r['params'] == DEPLOYED)
    for r in rows:
        d = r['boots'] - dep_cv['boots']                    # paired: identical resamples
        r['diff_vs_deployed'], r['p_better_than_deployed'] = r['mean'] - dep_cv['mean'], float(np.mean(d > 0))
        r['diff_sd'] = float(np.std(d, ddof=1))
    best_cv = max(rows, key=lambda r: (round(r['mean'], 4), r['params']['C'] == DEPLOYED['C'],
                                       r['params']['class_weight'] == DEPLOYED['class_weight']))
    ranked = sorted(rows, key=lambda r: -r['mean'])
    means = np.array([r['mean'] for r in rows])
    cw_gap = max(abs(next(r['mean'] for r in rows if r['params'] == {'C': C, 'class_weight': 'balanced'})
                     - next(r['mean'] for r in rows if r['params'] == {'C': C, 'class_weight': None}))
                 for C in GRID_C)
    conda_best = max(rows, key=lambda r: r['conda_part'])['params']

    # ── 3. test: deployed vs validation-best, CONDA_valid scored once ────────
    if best_cv['params'] == DEPLOYED:
        s_best, best_row = s_dep, dep_row
        diff, (lo, hi), p_better = 0.0, (0.0, 0.0), 0.0
    else:
        print(f"[3] refit {label(best_cv['params'])} on all training corpora -> CONDA_valid")
        s_best, _, _ = fit_and_score(src, best_cv['params'], full_store, x_te)
        best_row = ab.chat_row('best', y_te, s_best)
        diffs, (lo, hi) = boot_values(lambda yy, S: AP(yy, S[:, 1]) - AP(yy, S[:, 0]),
                                      y_te, np.column_stack([s_dep, s_best]))
        diff, p_better = float(AP(y_te, s_best) - AP(y_te, s_dep)), float(np.mean(diffs > 0))

    test_out = {
        'metric': 'PR-AUC (average precision) of the served score on CONDA_valid',
        'deployed': dep_row['pr_auc'], 'best': best_row['pr_auc'], 'diff': r4(diff),
        'diff_ci95': [r4(lo), r4(hi)], 'p_best_better': r4(p_better),
        'deployed_ci95': dep_row['pr_auc_ci95'], 'best_ci95': best_row['pr_auc_ci95'],
        'alert_threshold': ab.ALERT_T,
        'deployed_at_alert': {'precision': dep_row['precision@alert'], 'recall': dep_row['recall@alert']},
        'best_at_alert': {'precision': best_row['precision@alert'], 'recall': best_row['recall@alert']},
        'n_test': int(len(y_te)), 'test_prevalence': r4(y_te.mean())}

    abl = {'full': ref['pr_auc'], 'no_conda': abl_rows['- CONDA corpus (domain data)']['pr_auc'],
           'no_char': abl_rows['- char_wb n-grams']['pr_auc']}
    out.update({
        'search_space': {'C': GRID_C, 'class_weight': ['balanced', None],
                         'fixed': 'TF-IDF word 1-2 (20k) + char_wb 3-5 (30k), min_df=2, sublinear tf; '
                                  'max_iter=1000, lbfgs; isotonic calibration on the 15% '
                                  'calibration split; keyword noisy-OR fusion'},
        'n_configs': len(rows),
        'cv': {'scheme': 'single stratified hold-out: 15% validation slice (seed 42) carved from '
                         'the de-duplicated training corpora; vectoriser fitted once on the rest',
               'folds': 1,
               'metric': 'PR-AUC of the served score (calibrated LR noisy-OR keyword)',
               'std_definition': 'bootstrap SD over 1,000 resamples of the validation slice '
                                 '(identical resamples for every config)',
               'n_val': int(len(val)), 'val_prevalence': r4(y_val.mean()),
               'n_val_from_conda_train': int(m_conda.sum()), 'n_unique_training_texts': int(n_unique),
               'raw_rows_removed_from_training': int(n_dropped),
               'vectoriser_fits': int(store['n_vectoriser_fits']),
               'vectoriser_fit_rows': int(vec_shape[0]), 'n_features': int(vec_shape[1])},
        'cv_deployed': {'mean': r4(dep_cv['mean']), 'std': r4(dep_cv['std'])},
        'cv_top10': [{'params': r['params'], 'mean': r4(r['mean']), 'std': r4(r['std'])}
                     for r in ranked[:10]],
        'cv_spread': {'min': r4(means.min()), 'median': r4(np.median(means)), 'max': r4(means.max())},
        'marginal': {
            'C': {f'{C:g}': r4(np.mean([r['mean'] for r in rows if r['params']['C'] == C]))
                  for C in GRID_C},
            'class_weight': {str(cw): r4(np.mean([r['mean'] for r in rows
                                                 if r['params']['class_weight'] == cw]))
                             for cw in GRID_CW}},
        'best_params': best_cv['params'],
        'test': test_out,
        'cv_all': [{'params': r['params'], 'mean': r4(r['mean']), 'std': r4(r['std']),
                    'diff_vs_deployed': r4(r['diff_vs_deployed']), 'diff_sd': r4(r['diff_sd']),
                    'p_better_than_deployed': r4(r['p_better_than_deployed']),
                    'val_conda_part_pr_auc': r4(r['conda_part']),
                    'lr_iterations': r['lr_iterations'], 'converged': r['converged']}
                   for r in rows],
        'diagnostics': {
            'class_weight_max_gap': r4(cw_gap),
            'conda_part_argmax_params': conda_best,
            'conda_part_note': 'PR-AUC on the CONDA_train-origin rows of the validation slice; '
                               'a diagnostic only, not used for selection',
            'deployed_lr_iterations_full_data': it_dep},
    })
    out['conclusion'] = conclude(rows, dep_cv, best_cv, test_out, abl, cw_gap)
    out['runtime_s'] = round(time.time() - t0, 1)
    out['in_domain_selection'] = in_domain_selection(src, s_dep, dep_row, y_te, x_te, full_store,
                                                     pooled_pick=best_cv['params'])
    # keep the schema keys first, extras after
    order = ['model', 'protocol', 'search_space', 'n_configs', 'cv', 'replication', 'cv_deployed',
             'cv_top10', 'cv_spread', 'marginal', 'best_params', 'test', 'conclusion', 'runtime_s',
             'cv_all', 'diagnostics', 'in_domain_selection']
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({k: out[k] for k in order}, f, indent=2)
    print(f"\nbest {label(best_cv['params'])}; test {test_out['deployed']:.4f} -> "
          f"{test_out['best']:.4f}, diff {test_out['diff']:+.4f} CI {test_out['diff_ci95']}")
    print(out['conclusion'])
    print(f"[OK] wrote {OUT}  ({out['runtime_s']:.0f}s)")


if __name__ == '__main__':
    main()
