"""
Hyperparameter sensitivity study: BEHAVIOUR model (RandomForest on the objective-10).

The question this answers: "the served RandomForest uses 200 trees, max_depth 6 and
min_samples_leaf 20. Were those values tuned, and would tuning have changed anything?"

Protocol (data and split are IDENTICAL to ml/ablation_studies.ablate_behavior()):
  1. DATA + SPLIT. retrain_models.generate_behavior_dataset(25000) (the survey-grounded
     simulator, seed 42; 25,000 class rows + 3,750 boundary blends = 28,750 rows), the 10
     objective features (names[:10]) and the same stratified 80/20
     train_test_split(random_state=ablation_studies.SEED) the ablation table uses:
     23,000 training rows, 5,750 test rows (the counts written to the JSON are taken from
     the data, never typed). No other data is used.
  2. REPLICATION GATE. The deployed config (n_estimators=200, max_depth=6,
     min_samples_leaf=20, max_features='sqrt' (sklearn's default, which the ablation
     relies on), class_weight='balanced', random_state=42, StandardScaler in front) is
     retrained on that split and must reproduce the ablation_results.json test accuracy
     of 'objective-10 (deployed)' within 0.002. If it does not, the study STOPS and
     writes replication.match = false. Nothing is searched.
  3. SEARCH ON THE TRAINING SPLIT ONLY. A full grid of 120 configs:
         n_estimators {100, 200, 400} x max_depth {4, 6, 8, 12, None}
         x min_samples_leaf {1, 5, 20, 50} x max_features {'sqrt', 0.5}
     is scored by 5-fold StratifiedKFold(shuffle=True, random_state=42) inside the 23,000
     training rows. Scaler and forest sit in one Pipeline, so the scaler is refit inside
     every fold. Selection metric: mean CV macro-F1 (accuracy is recorded too). Exact
     ties go to the first config in grid order, which is GridSearchCV's convention.
     class_weight and random_state stay fixed and are not searched.
  4. THE TEST SET IS USED ONCE PER MODEL. The 5,750 test rows are scored exactly twice:
     once for the deployed config (step 2) and once for the CV-best config, refit on all
     23,000 training rows. Nothing is selected on test.
  5. PAIRED BOOTSTRAP. best - deployed on the SAME 1,000 test resamples (seed 42). The CI
     comes from ablation_studies.boot_ci itself, which uses the same index stream as the
     ablation table. Reported: the 95% CI of the difference and the share of resamples
     where best > deployed. A difference whose CI includes 0 is "no detectable gain".
  6. SURVEY CHECK (real people, after steps 1-5; selects nothing). The IGDS9-SF survey
     respondents are scored exactly as ml/eval_behavior_survey.py scores them with the
     served model (same respondent filter, Q5-Q11 band midpoints, derive_psychometrics,
     scaler, forest, isotonic layer, b = 0.5 P(Some) + 1.0 P(High)) and correlated
     with their IGDS9-SF totals (Spearman rho, that script's bootstrap_rho: 2,000
     resamples, seed 7). Both forests get the served calibration recipe of
     ml/calibrate_behavior.py, refit in memory (isotonic, FrozenEstimator, fitted on the
     calibration half of the held-out split, random_state 7). Two gates first: the served
     pickles must reproduce data/survey/survey_validation.json, and the in-memory deployed
     recipe must reproduce the served pickles' rho within 0.002. Then deployed vs CV-best,
     with a paired bootstrap of the rho difference on the same resamples.

Behaviour labels are SYNTHETIC, so any gain measures fit to the simulator, not to real
children; step 6 is the real-data test of whether it transfers. This script only READS
backend/models: the deployed model stays unchanged.

Writes docs/hparam_behaviour.json. Run from the project root (a few minutes, one
process, forests threaded):   python ml/hparam_behaviour.py [--jobs 16] [--verbose 2]
"""
import argparse
import copy
import csv
import json
import os
import pickle
import sys
import time
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ablation_studies as ab                          # noqa: E402  protocol: SEED, DOCS, boot_ci
from retrain_models import generate_behavior_dataset   # noqa: E402  the loader ablate_behavior() calls

from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.ensemble import RandomForestClassifier    # noqa: E402
from sklearn.frozen import FrozenEstimator             # noqa: E402
from sklearn.metrics import accuracy_score, f1_score   # noqa: E402
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split  # noqa: E402
from sklearn.pipeline import Pipeline                  # noqa: E402
from sklearn.preprocessing import StandardScaler       # noqa: E402

OUT      = os.path.join(ab.DOCS, 'hparam_behaviour.json')
ABL_JSON = os.path.join(ab.DOCS, 'ablation_results.json')
ABL_ROW  = 'objective-10 (deployed)'
TOL      = 0.002        # replication gate on test accuracy
N_BOOT   = 1000
FOLDS    = 5
SURVEY_TOL = 0.002      # survey gate: in-memory deployed recipe vs the served pickles (rho)
SURVEY_JSON = os.path.join(ab.ROOT, 'data', 'survey', 'survey_validation.json')

SEARCH_SPACE = {
    'n_estimators':     [100, 200, 400],
    'max_depth':        [4, 6, 8, 12, None],
    'min_samples_leaf': [1, 5, 20, 50],
    'max_features':     ['sqrt', 0.5],
}
# The served behaviour model (retrain_models.train_behavior_model == ablate_behavior()).
# max_features is not passed there, so it is sklearn's default 'sqrt' (asserted in main).
DEPLOYED = {'n_estimators': 200, 'max_depth': 6, 'min_samples_leaf': 20, 'max_features': 'sqrt'}
FIXED    = {'class_weight': 'balanced', 'random_state': ab.SEED}

PROTOCOL = ('Data and split identical to ml/ablation_studies.ablate_behavior(): '
            'generate_behavior_dataset(25000, seed 42) ({n_all:,} rows incl. boundary blends), '
            'objective-10 features, stratified 80/20 train_test_split(random_state=42). '
            'Replication gate: the deployed config must reproduce the ablation-table test '
            'accuracy within 0.002. Full 120-config grid, 5-fold StratifiedKFold(shuffle, seed '
            '42) on the {n_tr:,} training rows only, with StandardScaler+RF in one Pipeline '
            '(scaler refit per fold). Selection by mean CV macro-F1 (ties go to grid order). '
            'Test set ({n_te:,} rows) scored once for the deployed and once for the CV-best '
            'config. Paired bootstrap of best - deployed: 1,000 test resamples, seed 42, via '
            'ablation_studies.boot_ci. Survey check afterwards (selects nothing): both configs '
            'scored on the IGDS9-SF respondents exactly as ml/eval_behavior_survey.py scores the '
            'served model, with the served isotonic recipe refit in memory.')


def rnd(x, k=4):
    return round(float(x), k)


def load_split():
    """The ablation's behaviour data path, call for call (see ablate_behavior())."""
    df, names = generate_behavior_dataset(25000)
    X, y = df[names[:10]].values, df['addiction_label'].values   # 'objective-10 (deployed)'
    return train_test_split(X, y, test_size=0.2, random_state=ab.SEED, stratify=y)


def make_pipe(jobs, **rf):
    """StandardScaler -> RandomForest, the served preprocessing order. A forest is
    invariant to per-feature affine scaling, but keeping the scaler makes the gate a
    like-for-like replication of the ablation code."""
    return Pipeline([('sc', StandardScaler()),
                     ('rf', RandomForestClassifier(**{**DEPLOYED, **rf}, **FIXED, n_jobs=jobs))])


def paired_boot(metric, y, pred_dep, pred_best, n=N_BOOT, seed=ab.SEED):
    """Paired bootstrap of metric(best) - metric(deployed) on the SAME resampled test rows.

    The 95% CI is ab.boot_ci itself: both prediction vectors are packed as two columns,
    so each resample scores both models on identical rows. The loop replays boot_ci's
    index stream (default_rng(seed).integers per round) to keep the whole difference
    distribution, which gives P(best > deployed). same_stream checks the replay."""
    y, a, b = np.asarray(y), np.asarray(pred_dep), np.asarray(pred_best)
    ci = ab.boot_ci(lambda yy, pq: metric(yy, pq[:, 1]) - metric(yy, pq[:, 0]),
                    y, np.column_stack([a, b]), n=n, seed=seed)
    rng, d = np.random.default_rng(seed), []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) < 2:
            continue
        d.append(metric(y[idx], b[idx]) - metric(y[idx], a[idx]))
    d = np.asarray(d)
    lo, hi = np.percentile(d, [2.5, 97.5])
    same_stream = ci == (rnd(lo), rnd(hi))
    return [ci[0], ci[1]], float(np.mean(d > 0)), float(np.mean(d == 0)), bool(same_stream)


def macro_f1(y, p):
    return f1_score(y, p, average='macro')


def conclusion(n, n_tr, spread, marg_range, cv_dep, cv_best, best_params, same, t, f, cost,
               survey=None):
    lever = max(marg_range, key=marg_range.get)
    rest = max(v for k, v in marg_range.items() if k != lever)
    bp = ', '.join(f'{k}={v}' for k, v in best_params.items())
    lo, hi = t['diff_ci95']
    if same:
        verdict = ('the CV search picked the deployed configuration itself, so there is '
                   'nothing to switch to')
    elif lo > 0:
        verdict = (f"a real but small gain of {t['diff'] * 100:+.2f} accuracy points on the "
                   f"simulator's held-out rows. It is reported, not adopted: switching means "
                   f"re-validating the served model, re-running the fairness audit and "
                   f"re-checking the device/backend budget (pickled model "
                   f"{cost['deployed_model_kb']:.0f} KB -> {cost['best_model_kb']:.0f} KB)")
    elif hi < 0:
        verdict = ('the CV-best config is WORSE on test, so the CV-level differences are '
                   'noise and the deployed values stand')
    else:
        verdict = ('no detectable gain (the CI includes 0), so the hand-set values are within '
                   'noise of the best config in this grid')
    return (f"Across {n} RandomForest configs, 5-fold CV macro-F1 on the {n_tr:,} training rows "
            f"spans {spread['min']:.4f}-{spread['max']:.4f} (median {spread['median']:.4f}). "
            f"{lever} is the main lever: its marginal means differ by {marg_range[lever]:.4f}, "
            f"every other hyperparameter's by at most {rest:.4f}. The deployed config scores "
            f"{cv_dep['mean']:.4f} +/- {cv_dep['std']:.4f} (rank {cv_dep['rank']}/{n}, "
            f"{'within' if cv_dep['within_1se_of_best'] else 'outside'} one standard error of "
            f"the best) and the CV-best ({bp}) scores {cv_best['mean']:.4f} +/- "
            f"{cv_best['std']:.4f}. On the {t['n_test']:,} untouched test rows, accuracy is "
            f"{t['best']:.4f} for the best config vs {t['deployed']:.4f} for the deployed one: "
            f"paired difference {t['diff']:+.4f}, 95% CI [{lo:+.4f}, {hi:+.4f}], best > deployed "
            f"in {t['p_best_better']:.1%} of 1,000 resamples. That is {verdict}. The macro-F1 "
            f"difference is {f['diff']:+.4f}, CI [{f['diff_ci95'][0]:+.4f}, "
            f"{f['diff_ci95'][1]:+.4f}]. Behaviour labels come from the survey-grounded "
            f"simulator, so any gain measures fit to the simulator, not to real children. "
            + (f"{survey['conclusion']} " if survey and 'conclusion' in survey else '')
            + "The deployed model is unchanged.")


# ── 6. survey check: does the simulator gain transfer to real people? ────────────────

def survey_respondents(ebs, csv_path):
    """ml/eval_behavior_survey.py main()'s respondent filter and Q5-Q11 mapping, step for
    step (that script exposes no function for it): the objective-feature dicts and IGDS9-SF
    totals of every usable respondent with complete Q5-Q11 answers. Gate A in
    survey_check() tests this copy against that script's own output."""
    with open(csv_path, newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh))
    headers = list(rows[0].keys()) if rows else []
    igds_cols = [ebs.find_col(headers, k) for k in ebs.IGDS_KEYS]
    cols = {'adult':   ebs.find_col(headers, '18'),
            'gamer':   ebs.find_col(headers, 'currently play video games'),
            'daily':   ebs.find_col(headers, 'typical day'),
            'days':    ebs.find_col(headers, 'days per week'),
            'session': ebs.find_col(headers, 'single', 'session'),
            'late':    ebs.find_col(headers, 'after midnight'),
            'binge':   ebs.find_col(headers, 'longer than 3 hours'),
            'rapid':   ebs.find_col(headers, 'within 15 minutes'),
            'streak':  ebs.find_col(headers, 'consecutive days'),
            'attn':    ebs.find_col(headers, 'quality control')}
    if not rows or None in igds_cols or not all(
            cols[k] for k in ('daily', 'days', 'session', 'late', 'binge', 'rapid', 'streak')):
        return [], np.array([])
    feats, totals = [], []
    for r in rows:
        if cols['adult'] and not str(r.get(cols['adult'], '')).strip().lower().startswith('y'):
            continue
        if cols['gamer'] and not str(r.get(cols['gamer'], '')).strip().lower().startswith('y'):
            continue
        if cols['attn'] and ebs.likert(r.get(cols['attn'], '')) != 4:
            continue
        items = [ebs.likert(r.get(c, '')) for c in igds_cols]
        if any(v is None for v in items):
            continue
        obj = ebs.objective_features(r, cols)
        if obj is not None:
            feats.append(obj)
            totals.append(sum(items))
    return feats, np.array(totals, float)


def served_style_scorer(ebs, scaler, proba_model):
    """eval_behavior_survey.load_model()'s score(), for a given scaler + probability model."""
    import pandas as pd
    names = (ebs.OBJECTIVE + ebs.PSYCH)[:int(getattr(scaler, 'n_features_in_', 10) or 10)]

    def score(obj):
        full = {**obj, **ebs.derive_psychometrics(**obj)}
        p = proba_model.predict_proba(scaler.transform(pd.DataFrame([full])[names]))[0]
        return float(p[1] * 0.5 + p[2] * 1.0) if len(p) > 2 else float(p[-1])
    return score


def served_recipe(pipe, X_cal, y_cal, ebs):
    """The served pair for a fitted Pipeline, built as retrain_models.py + calibrate_behavior.py
    build it: the scaler with its feature names stamped, and an isotonic layer fitted on the
    frozen forest (never refit) with the calibration half of the held-out split."""
    sc = copy.deepcopy(pipe.named_steps['sc'])
    sc.feature_names_in_ = np.array((ebs.OBJECTIVE + ebs.PSYCH)[:int(sc.n_features_in_)])
    rf = pipe.named_steps['rf']
    cal = CalibratedClassifierCV(FrozenEstimator(rf), method='isotonic')
    cal.fit(sc.transform(X_cal), y_cal)
    return sc, rf, cal


def paired_rho_boot(s_dep, s_best, y, iters=2000, seed=7):
    """eval_behavior_survey.bootstrap_rho's resample stream (default_rng(seed).integers per
    round) with BOTH models scored on the same rows: 95% CI of rho(best) - rho(deployed)."""
    from scipy.stats import spearmanr
    a, b, y = (np.asarray(v, float) for v in (s_dep, s_best, y))
    rng, d = np.random.default_rng(seed), []
    for _ in range(iters):
        idx = rng.integers(0, len(y), len(y))
        if len(set(y[idx])) > 1 and len(set(a[idx])) > 1 and len(set(b[idx])) > 1:
            d.append(spearmanr(b[idx], y[idx]).statistic - spearmanr(a[idx], y[idx]).statistic)
    d = np.asarray(d)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return [rnd(lo, 3), rnd(hi, 3)], float(np.mean(d > 0)), int(len(d))


def survey_sentence(sc):
    d, (lo, hi) = sc['diff'], sc['diff_ci95']
    b, p = sc['best'], sc['deployed']
    s = (f"The decisive real-data test is the IGDS9-SF survey: scored exactly as "
         f"ml/eval_behavior_survey.py scores the served model, the CV-best forest's score "
         f"correlates with the IGDS9-SF total of the {sc['n']} scored respondents at Spearman "
         f"rho {b['rho']:.3f} [{b['ci95'][0]:.3f}, {b['ci95'][1]:.3f}], against "
         f"{p['rho']:.3f} [{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}] for the deployed forest: "
         f"paired difference {d:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]. ")
    if lo > 0:
        return s + "The simulator gain carries over to real respondents."
    if hi < 0:
        return s + ("The tuned forest ranks real respondents worse, so the simulator gain does "
                    "not transfer and the regularised deployed forest is the better real-world "
                    "choice.")
    return s + ("The CI includes 0, so the simulator gain is not shown to transfer to real "
                f"people; at n = {sc['n']} the survey cannot tell the two forests apart"
                + (", and the point estimate favours the deployed forest." if d < 0 else "."))


def survey_check(dep, best, X_te, y_te, same):
    """Step 6. Reads backend/models (the served pickles) and the gitignored survey CSV;
    writes nothing but the returned dict. Selects nothing: both configs were fixed by
    steps 2-3 before this runs."""
    import eval_behavior_survey as ebs
    from scipy.stats import spearmanr
    rel = os.path.relpath(ebs.DEFAULT_CSV, ab.ROOT).replace('\\', '/')
    if not (os.path.exists(ebs.DEFAULT_CSV) and os.path.exists(SURVEY_JSON)):
        return {'skipped': f'{rel} or survey_validation.json not found (survey data is gitignored)'}
    feats, totals = survey_respondents(ebs, ebs.DEFAULT_CSV)
    if len(totals) < 20:
        return {'skipped': f'only {len(totals)} complete survey rows'}
    with open(SURVEY_JSON, encoding='utf-8') as fh:
        ref = json.load(fh)['construct_validity']

    def evaluate(score_fn):
        s = np.array([score_fn(o) for o in feats])
        lo, hi = ebs.bootstrap_rho(s, totals)
        return s, float(spearmanr(s, totals).statistic), [rnd(lo, 3), rnd(hi, 3)]

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)   # feature-name notices, as in serving
        # Gate A: the served pickles through this copy of the filter = the published output.
        served_fn, served_note = ebs.load_model()
        s_srv, rho_srv, ci_srv = evaluate(served_fn)
        # Gate B: the in-memory deployed recipe = the served pickles.
        X_cal, _, y_cal, _ = train_test_split(X_te, y_te, test_size=0.5, random_state=7,
                                              stratify=y_te)     # calibrate_behavior.py's half
        sc_d, rf_d, cal_d = served_recipe(dep, X_cal, y_cal, ebs)
        s_dep, rho_dep, ci_dep = evaluate(served_style_scorer(ebs, sc_d, cal_d))
        gate = {'served_pickles': {'rho': rnd(rho_srv, 3), 'ci95': ci_srv, 'n': int(len(s_srv)),
                                   'scorer': served_note},
                'survey_validation_json': ref,
                'a_filter_reproduces_published': bool(rnd(rho_srv, 3) == ref['rho']
                                                      and ci_srv == ref['ci95']
                                                      and len(s_srv) == ref['n']),
                'inmemory_deployed_rho': rnd(rho_dep, 4), 'served_rho': rnd(rho_srv, 4),
                'max_abs_score_diff_inmemory_vs_served': float(np.max(np.abs(s_dep - s_srv))),
                'tolerance': SURVEY_TOL}
        gate['b_inmemory_reproduces_served'] = bool(abs(rho_dep - rho_srv) <= SURVEY_TOL)
        gate['match'] = gate['a_filter_reproduces_published'] and gate['b_inmemory_reproduces_served']
        if not gate['match']:
            return {'gate': gate, 'skipped': 'survey gate failed, so no like-for-like comparison'}
        if same:
            s_best, rho_best, ci_best, rf_b, sc_b = s_dep, rho_dep, ci_dep, rf_d, sc_d
        else:
            sc_b, rf_b, cal_b = served_recipe(best, X_cal, y_cal, ebs)
            s_best, rho_best, ci_best = evaluate(served_style_scorer(ebs, sc_b, cal_b))
        raw = {k: rnd(spearmanr([served_style_scorer(ebs, sc, rf)(o) for o in feats],
                                totals).statistic, 3)
               for k, sc, rf in (('deployed_rho', sc_d, rf_d), ('best_rho', sc_b, rf_b))}
    d_ci, p_better, n_ok = paired_rho_boot(s_dep, s_best, totals)
    out = {
        'question': ('Does the CV-best forest\'s gain on simulated labels transfer to real '
                     'people? Construct validity on the IGDS9-SF survey (it validates meaning, '
                     'not clinical accuracy).'),
        'data': (f'{rel} (gitignored): respondents kept by ml/eval_behavior_survey.py\'s filter '
                 f'(adult, current gamer, attention check, complete IGDS9-SF) with complete '
                 f'Q5-Q11 answers'),
        'n': int(len(totals)),
        'scoring': ('eval_behavior_survey.objective_features (Q5-Q11 band midpoints) -> '
                    'derive_psychometrics -> StandardScaler -> RandomForest -> isotonic layer '
                    '(ml/calibrate_behavior.py recipe refit in memory: CalibratedClassifierCV('
                    'FrozenEstimator(rf), method=isotonic) on the calibration half of the '
                    'held-out simulator split, random_state 7) -> b = 0.5 P(Some concern) + '
                    '1.0 P(High concern); Spearman rho with the IGDS9-SF total'),
        'gate': gate,
        'deployed': {'params': DEPLOYED, 'rho': rnd(rho_dep, 3), 'ci95': ci_dep,
                     'distinct_scores': int(len(np.unique(s_dep)))},
        'best': {'params': None, 'rho': rnd(rho_best, 3), 'ci95': ci_best,
                 'distinct_scores': int(len(np.unique(s_best)))},
        'diff': rnd(rho_best - rho_dep, 3), 'diff_ci95': d_ci, 'p_best_better': rnd(p_better, 3),
        'bootstrap': {'resamples': 2000, 'valid_resamples': n_ok, 'seed': 7, 'paired': True,
                      'ci_from': 'eval_behavior_survey.bootstrap_rho per model; its index '
                                 'stream replayed for the paired difference'},
        'diagnostic_uncalibrated_rf': {**raw, 'note': 'raw forest probabilities, no isotonic '
                                                      'layer; diagnostic only'},
    }
    out['conclusion'] = survey_sentence(out)
    return out


def write(out):
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=2)
    print(f'[OK] wrote {OUT}')


def main():
    ap = argparse.ArgumentParser(description='Behaviour RandomForest hyperparameter sensitivity')
    ap.add_argument('--jobs', type=int, default=16,
                    help='threads per forest (one process, so memory stays light)')
    ap.add_argument('--verbose', type=int, default=1,
                    help='GridSearchCV verbosity (2 = one line per fit)')
    args = ap.parse_args()
    t0 = time.time()
    assert RandomForestClassifier().max_features == DEPLOYED['max_features'], \
        "sklearn's default max_features changed; the ablation config relies on it"

    X_tr, X_te, y_tr, y_te = load_split()
    n_tr, n_te = int(len(y_tr)), int(len(y_te))
    print(f'train {n_tr} rows | test {n_te} rows | {X_tr.shape[1]} features')
    base = {'model': 'behaviour: RandomForestClassifier on the 10 objective features '
                     '(synthetic, survey-grounded labels)',
            'protocol': PROTOCOL.format(n_all=n_tr + n_te, n_tr=n_tr, n_te=n_te),
            'search_space': SEARCH_SPACE,
            'fixed_params': {**FIXED, 'preprocessing': 'StandardScaler (refit inside each fold)'},
            'n_configs': int(np.prod([len(v) for v in SEARCH_SPACE.values()])),
            'data': {'rows': n_tr + n_te, 'train_rows': n_tr, 'test_rows': n_te,
                     'features': int(X_tr.shape[1])},
            'cv': {'scheme': f'StratifiedKFold(n_splits=5, shuffle=True, random_state=42) on the '
                             f'{n_tr:,}-row training split only',
                   'folds': FOLDS, 'metric': 'macro_f1 (selection); accuracy recorded'}}

    # 1. Replication gate. This is test touch 1 of 2 (the deployed config).
    with open(ABL_JSON) as fh:
        ref = next(r for r in json.load(fh)['behaviour'] if r['config'] == ABL_ROW)
    t_fit = time.time()
    dep = make_pipe(args.jobs).fit(X_tr, y_tr)
    dep_fit_s = time.time() - t_fit
    pred_dep = dep.predict(X_te)
    acc_dep = float(accuracy_score(y_te, pred_dep))
    f1_dep = float(macro_f1(y_te, pred_dep))
    ci_dep = ab.boot_ci(accuracy_score, y_te, pred_dep)
    rep = {'deployed_test': rnd(acc_dep), 'ablation_json': ref['accuracy'],
           'match': bool(abs(acc_dep - ref['accuracy']) <= TOL), 'tolerance': TOL,
           'abs_diff': rnd(abs(acc_dep - ref['accuracy'])),
           'macro_f1': {'deployed_test': rnd(f1_dep), 'ablation_json': ref['macro_f1']},
           'acc_ci95': {'deployed_test': list(ci_dep), 'ablation_json': ref['acc_ci95']}}
    print(f"replication gate: test acc {acc_dep:.4f} vs ablation {ref['accuracy']:.4f} "
          f"(macro-F1 {f1_dep:.4f} vs {ref['macro_f1']:.4f}; CI {list(ci_dep)} vs "
          f"{ref['acc_ci95']}) -> match={rep['match']}")
    if not rep['match']:
        write({**base, 'replication': rep, 'cv_deployed': None, 'cv_top10': None,
               'cv_spread': None, 'marginal': None, 'best_params': None, 'test': None,
               'conclusion': (f"STOPPED at the replication gate: the deployed config gives "
                              f"test accuracy {acc_dep:.4f} on the ablation split but "
                              f"ablation_results.json says {ref['accuracy']:.4f} (|diff| "
                              f"{abs(acc_dep - ref['accuracy']):.4f} > {TOL}). The generator, "
                              f"split or library version has drifted since the table was "
                              f"written, so no search was run."),
               'runtime_s': rnd(time.time() - t0, 1)})
        sys.exit(1)

    # 2. Grid search on the training split only. The test rows are never seen here.
    cv = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=ab.SEED)
    gs = GridSearchCV(make_pipe(args.jobs), {f'rf__{k}': v for k, v in SEARCH_SPACE.items()},
                      scoring={'macro_f1': 'f1_macro', 'accuracy': 'accuracy'},
                      refit='macro_f1', cv=cv, n_jobs=1, return_train_score=True,
                      verbose=args.verbose)
    t_cv = time.time()
    gs.fit(X_tr, y_tr)
    print(f'grid search: {len(gs.cv_results_["params"])} configs x {FOLDS} folds '
          f'in {time.time() - t_cv:.0f}s')

    r = gs.cv_results_
    P = [{k: p[f'rf__{k}'] for k in SEARCH_SPACE} for p in r['params']]
    m, s = r['mean_test_macro_f1'], r['std_test_macro_f1']
    i_dep, i_best = P.index(DEPLOYED), int(gs.best_index_)
    se_best = s[i_best] / np.sqrt(FOLDS)          # standard error of the best CV mean
    in_1se = m >= m[i_best] - se_best

    def cv_entry(i):
        return {'params': P[i], 'mean': rnd(m[i]), 'std': rnd(s[i]),
                'acc_mean': rnd(r['mean_test_accuracy'][i]),
                'acc_std': rnd(r['std_test_accuracy'][i]),
                'train_mean': rnd(r['mean_train_macro_f1'][i])}

    cv_dep = {**cv_entry(i_dep), 'rank': int(r['rank_test_macro_f1'][i_dep]),
              'within_1se_of_best': bool(in_1se[i_dep])}
    cv_best = {**cv_entry(i_best), 'rank': int(r['rank_test_macro_f1'][i_best])}
    top10 = [cv_entry(i) for i in np.argsort(-m, kind='stable')[:10]]
    spread = {'min': rnd(m.min()), 'median': rnd(np.median(m)), 'max': rnd(m.max()),
              'acc_min': rnd(r['mean_test_accuracy'].min()),
              'acc_median': rnd(np.median(r['mean_test_accuracy'])),
              'acc_max': rnd(r['mean_test_accuracy'].max()),
              'n_within_1se_of_best': int(in_1se.sum())}
    # Marginal mean of CV macro-F1 for each value of each hyperparameter, averaged over
    # every config that has that value: which knob actually moves the score.
    marginal = {k: {str(v): rnd(np.mean([m[i] for i, p in enumerate(P) if p[k] == v]))
                    for v in vals} for k, vals in SEARCH_SPACE.items()}
    marg_range = {k: rnd(max(d.values()) - min(d.values())) for k, d in marginal.items()}

    # 3. Test touch 2 of 2: the CV-best config, refit by GridSearchCV on all training rows.
    same = i_best == i_dep
    best_model = dep if same else gs.best_estimator_
    pred_best = pred_dep if same else best_model.predict(X_te)
    acc_best = float(accuracy_score(y_te, pred_best))
    f1_best = float(macro_f1(y_te, pred_best))
    a_ci, a_p, a_tie, a_ok = paired_boot(accuracy_score, y_te, pred_dep, pred_best)
    f_ci, f_p, f_tie, f_ok = paired_boot(macro_f1, y_te, pred_dep, pred_best)
    ok_b, ok_d = pred_best == y_te, pred_dep == y_te
    test = {'metric': 'accuracy', 'n_test': int(len(y_te)),
            'deployed': rnd(acc_dep), 'best': rnd(acc_best), 'diff': rnd(acc_best - acc_dep),
            'diff_ci95': a_ci, 'p_best_better': rnd(a_p), 'p_tie': rnd(a_tie),
            'deployed_ci95': list(ci_dep),
            'best_ci95': list(ab.boot_ci(accuracy_score, y_te, pred_best)),
            # The paired difference lives entirely in the rows where the two models disagree.
            'discordant': {'rows_predictions_differ': int(np.sum(pred_best != pred_dep)),
                           'best_only_correct': int(np.sum(ok_b & ~ok_d)),
                           'deployed_only_correct': int(np.sum(ok_d & ~ok_b))},
            'macro_f1': {'deployed': rnd(f1_dep), 'best': rnd(f1_best),
                         'diff': rnd(f1_best - f1_dep), 'diff_ci95': f_ci,
                         'p_best_better': rnd(f_p), 'p_tie': rnd(f_tie)},
            'bootstrap': {'resamples': N_BOOT, 'seed': ab.SEED, 'paired': True,
                          'ci_from': 'ablation_studies.boot_ci',
                          'replay_matches_boot_ci': bool(a_ok and f_ok)}}
    cost = {'deployed_model_kb': rnd(len(pickle.dumps(dep)) / 1024, 1),
            'best_model_kb': rnd(len(pickle.dumps(best_model)) / 1024, 1),
            'deployed_fit_s': rnd(dep_fit_s, 2),
            'best_fit_s': rnd(dep_fit_s if same else gs.refit_time_, 2),
            'note': f'fit times on {n_tr:,} rows with {args.jobs} threads'}

    # 4. Survey check (real people). Both configs are fixed by now; nothing is selected.
    survey = survey_check(dep, best_model, X_te, y_te, same)
    if 'best' in survey:
        survey['best']['params'] = P[i_best]
    print(f"survey check: {survey.get('conclusion') or survey.get('skipped')}")

    out = {**base, 'replication': rep, 'cv_deployed': cv_dep, 'cv_top10': top10,
           'cv_spread': spread, 'marginal': marginal, 'marginal_range': marg_range,
           'best_params': P[i_best], 'cv_best': cv_best, 'test': test, 'cost': cost,
           'survey_check': survey}
    out['conclusion'] = conclusion(len(P), n_tr, spread, marg_range, cv_dep, cv_best, P[i_best],
                                   same, test, test['macro_f1'], cost, survey)
    out['runtime_s'] = rnd(time.time() - t0, 1)
    write(out)
    print('\n' + out['conclusion'])
    print(f"\nruntime {out['runtime_s']}s")


if __name__ == '__main__':
    main()
