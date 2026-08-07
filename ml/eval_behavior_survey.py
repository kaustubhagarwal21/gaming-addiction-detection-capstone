"""
IGDS9-SF survey → behaviour-model construct validity, in one pass.

Consumes the CSV exported from the Google Form defined in docs/SURVEY_IGDS9SF.md
(File → Download → CSV from the linked Sheet) and produces every number the
validation writeup needs:

  1. IGDS9-SF totals (9–45) per respondent, after dropping under-18 / non-gamer
     rows and attention-check failures.
  2. LOCAL PREVALENCE at the ≥36 (and ≥32) cutoffs, with a Beta-posterior 95% CI —
     the anchor for ml/calibrate_thresholds_prevalence.py.
  3. Hours-vs-severity Spearman (the sanity check that replicates analyze_igds.py's
     direction on local data).
  4. CONSTRUCT VALIDITY (the headline): each respondent's gaming-pattern answers
     (Q5–Q11) are mapped to the model's 10 objective features, pushed through the
     REAL serving pipeline (shared derive_psychometrics → fitted scaler → the
     behaviour RandomForest, calibrated layer when present, identical b_score
     formula), and the resulting score is correlated against their IGDS9-SF total
     (Spearman rho with a bootstrap 95% CI).
  5. THRESHOLD SUGGESTION: IGDS bands (<21 / 21–31 / ≥32) vs a T1/T2 grid search
     maximizing quadratic-weighted kappa — the data-driven counterpart of the
     hand-set RISK_T1/RISK_T2 priors, applied the same way (env vars).

Honesty guards (see docs/VALIDATION_PLAN.md FAST PATH): correlation is the primary
endpoint; caseness metrics (AUC) print only when the sample holds >= MIN_POSITIVES
disordered-range respondents, because at a ~6% base rate a 50–100-person sample
contains too few positives for classification metrics to mean anything.

Column detection is by KEYWORD, not position, because Google Forms exports the full
question text as the header — so the form can be reworded lightly without breaking
this script, as long as the key phrases (docs/SURVEY_IGDS9SF.md wordings) survive.

Usage:  python ml/eval_behavior_survey.py [responses.csv]
        (default: data/survey/responses.csv; JSON written next to the CSV)

Self-test: python ml/eval_behavior_survey.py --selftest   (synthetic 150-row CSV)
"""
import csv
import json
import os
import re
import sys

import numpy as np
from scipy.stats import beta as beta_dist, spearmanr

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, 'backend', 'models')
DEFAULT_CSV = os.path.join(ROOT, 'data', 'survey', 'responses.csv')
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from behavior_features import derive_psychometrics  # the exact serving derivation

MIN_POSITIVES = 10   # below this, caseness metrics are noise — refuse to print them
IGDS_DISORDERED = 36 # standard cutoff (matches analyze_igds.py / the paper)
IGDS_ELEVATED   = 32

# First 10 of the serving feature list (app.BEHAVIORAL_FEATURES) — the objective
# features newer models are trained on; psychometrics are derived, order below.
OBJECTIVE = ['daily_play_time_hours', 'weekly_play_time_hours', 'sessions_per_day',
             'avg_session_duration_min', 'late_night_play_ratio', 'days_played_per_week',
             'longest_play_streak_days', 'binge_sessions_per_week',
             'avg_break_between_sessions_min', 'rapid_relogin_ratio']
PSYCH = ['urge_to_continue_score', 'loss_of_time_awareness_score', 'control_loss_score',
         'craving_score', 'tolerance_score', 'missed_sleep_days_per_week',
         'fatigue_after_play_score', 'routine_disruption_score',
         'neglect_responsibilities_score', 'gaming_priority_score']

# IGDS9-SF item detection — one distinctive phrase per item (docs/SURVEY_IGDS9SF.md).
IGDS_KEYS = ['preoccupied', 'irritable', 'increasing amounts', 'without success',
             'lost interest', 'despite', 'deceived', 'negative mood', 'jeopard']

LIKERT_WORDS = {'never': 1, 'rarely': 2, 'sometimes': 3, 'often': 4, 'very often': 5}


def likert(value) -> int | None:
    """'3', '3 - Sometimes', 'Sometimes' → 1..5 (None if unparseable)."""
    s = str(value or '').strip().lower()
    m = re.match(r'^([1-5])\b', s)
    if m:
        return int(m.group(1))
    for word, v in sorted(LIKERT_WORDS.items(), key=lambda kv: -len(kv[0])):
        if word in s:
            return v
    return None


def find_col(headers, *keywords, exclude=()):
    """First header containing ALL keywords (case-insensitive) and no excluded term."""
    for h in headers:
        low = h.lower()
        if all(k in low for k in keywords) and not any(x in low for x in exclude):
            return h
    return None


def band(value, mapping, default=None):
    """Map a banded multiple-choice answer via keyword lookup (dash-agnostic)."""
    s = str(value or '').strip().lower().replace('–', '-').replace('—', '-')
    for key, v in mapping.items():
        if key in s:
            return v
    return default


def objective_features(row, cols):
    """Q5–Q11 answers → the 10 objective features (band midpoints; documented
    approximations — this is construct validation, not precise telemetry)."""
    daily = band(row.get(cols['daily'], ''), {'less than 1': 0.5, '1-2': 1.5, '2-3': 2.5,
                                              '3-5': 4.0, 'more than 5': 6.0})
    days = None
    m = re.match(r'^([0-7])\b', str(row.get(cols['days'], '')).strip())
    if m:
        days = int(m.group(1))
    sess_min = band(row.get(cols['session'], ''), {'under 30': 20.0, '30-60': 45.0,
                                                   '1-2': 90.0, '2-4': 180.0,
                                                   'more than 4': 270.0})
    late = likert(row.get(cols['late'], ''))
    binge = band(row.get(cols['binge'], ''), {'1-2': 1.5, '3-5': 4.0, '6': 7.0, '0': 0.0})
    rapid = likert(row.get(cols['rapid'], ''))
    # '1-2 weeks' must not match the '1-2 days' band — check the week bands first.
    streak = band(row.get(cols['streak'], ''), {'more than 2 week': 21.0, '1-2 week': 10.0,
                                                '3-6': 4.5, '1-2': 1.5})
    if None in (daily, days, sess_min, late, binge, rapid, streak):
        return None
    weekly = min(daily * days, 168.0)
    return {
        'daily_play_time_hours': daily,
        'weekly_play_time_hours': weekly,
        'sessions_per_day': float(np.clip(weekly * 60.0 / sess_min / 7.0, 0.1, 10.0)),
        'avg_session_duration_min': sess_min,
        'late_night_play_ratio': [0.0, 0.1, 0.3, 0.55, 0.8][late - 1],
        'days_played_per_week': float(days),
        'longest_play_streak_days': streak,
        'binge_sessions_per_week': binge,
        'avg_break_between_sessions_min': [240.0, 180.0, 120.0, 60.0, 20.0][rapid - 1],
        'rapid_relogin_ratio': [0.0, 0.15, 0.35, 0.6, 0.85][rapid - 1],
    }


def load_model():
    """(scorer, note) — calibrated layer when present, else the raw RF; None if absent."""
    import joblib
    model_path = os.path.join(MODELS_DIR, 'behavior_model.pkl')
    scaler_path = os.path.join(MODELS_DIR, 'feature_scaler.pkl')
    if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
        return None, 'behaviour model/scaler not found under backend/models/'
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    calib_path = os.path.join(MODELS_DIR, 'behavior_calibrated.pkl')
    proba_model = joblib.load(calib_path) if os.path.exists(calib_path) else model
    n = int(getattr(scaler, 'n_features_in_', 10) or 10)
    feats = (OBJECTIVE + PSYCH)[:n]

    def score(obj_features: dict) -> float:
        import pandas as pd
        full = {**obj_features, **derive_psychometrics(**obj_features)}
        X = scaler.transform(pd.DataFrame([full])[feats])
        p = proba_model.predict_proba(X)[0]
        # Identical to serving (app.run_prediction): at_risk*0.5 + addicted*1.0.
        return float(p[1] * 0.5 + p[2] * 1.0) if len(p) > 2 else float(p[-1])

    which = 'calibrated' if proba_model is not model else 'raw RF'
    return score, f'{which}, {n} features'


def beta_ci(k, n):
    lo, hi = beta_dist.ppf([0.025, 0.975], k + 1, n - k + 1)
    return float(lo), float(hi)


def bootstrap_rho(x, y, iters=2000, seed=7):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    stats = []
    for _ in range(iters):
        idx = rng.integers(0, len(x), len(x))
        if len(set(y[idx])) > 1 and len(set(x[idx])) > 1:
            stats.append(spearmanr(x[idx], y[idx]).statistic)
    if not stats:                       # constant input — no CI is computable
        return float('nan'), float('nan')
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def quadratic_kappa(a, b, n_classes=3):
    a, b = np.asarray(a, int), np.asarray(b, int)
    obs = np.zeros((n_classes, n_classes))
    for i, j in zip(a, b):
        obs[i, j] += 1
    w = np.array([[((i - j) ** 2) / (n_classes - 1) ** 2
                   for j in range(n_classes)] for i in range(n_classes)])
    exp = np.outer(obs.sum(1), obs.sum(0)) / max(obs.sum(), 1)
    denom = float((w * exp).sum())
    return 1.0 - float((w * obs).sum()) / denom if denom > 0 else 0.0


def fit_thresholds(scores, igds_bands):
    """Grid-search T1<T2 maximizing quadratic-weighted kappa vs the IGDS bands."""
    best = (0.33, 0.67, -1.0)
    for t1 in np.arange(0.05, 0.86, 0.01):
        for t2 in np.arange(t1 + 0.05, 0.96, 0.01):
            pred = np.digitize(scores, [t1, t2])
            k = quadratic_kappa(pred, igds_bands)
            if k > best[2]:
                best = (round(float(t1), 2), round(float(t2), 2), round(k, 3))
    return best


def make_selftest_csv(path):
    """Synthetic 150-row export shaped like the real form, severity ↔ hours linked."""
    rng = np.random.default_rng(42)
    headers = ['Timestamp', 'Are you 18 years or older?', 'Do you play video games?',
               'Your age group', 'On average, how many hours per week do you play video games (phone/PC/console)?',
               'Which type of game do you play most?',
               'On a typical day you play, about how many hours do you game?',
               'How many days per week do you usually game?',
               'How long is a typical single gaming session?',
               'How often do you game after midnight?',
               'For quality control, please select \'Often\' for this question.',
               'In a typical week, how many gaming sessions run longer than 3 hours?',
               'After ending a session, how often do you start another within 15 minutes?',
               'What is the longest run of consecutive days you\'ve gamed recently?'] + \
              [f'Gaming over the past 12 months [{k}]' for k in
               ['I feel preoccupied with my gaming', 'I feel more irritable, anxious or sad',
                'I need increasing amounts of time gaming', 'I have tried to reduce or stop gaming without success',
                'I have lost interest in previous hobbies', 'I continued gaming despite knowing it was causing problems',
                'I have deceived family members or others', 'I game to escape or relieve a negative mood',
                'I have jeopardised or lost an important relationship']]
    daily_bands = ['Less than 1', '1–2', '2–3', '3–5', 'More than 5']
    lik = ['Never', 'Rarely', 'Sometimes', 'Often', 'Very often']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for i in range(150):
            sev = rng.beta(1.6, 5.0)                      # skewed-low severity latent
            d = min(4, int(sev * 5 + rng.normal(0, 0.7)))
            d = max(0, d)
            items = [str(int(np.clip(round(1 + sev * 4 + rng.normal(0, 0.7)), 1, 5)))
                     for _ in range(9)]
            w.writerow(['t', 'Yes', 'Yes', '18–20',
                        ['Less than 2', '2–5', '6–10', '11–20', '21–35'][d], 'FPS (Valorant/COD)',
                        daily_bands[d], str(min(7, d * 2 + 1)),
                        ['Under 30 minutes', '30–60 minutes', '1–2 hours', '2–4 hours',
                         'More than 4 hours'][d],
                        lik[min(4, d + (1 if sev > .5 else 0))],
                        'Often' if i % 25 else 'Never',   # a few attention failures
                        ['0', '1–2', '1–2', '3–5', '6 or more'][d],
                        lik[d], ['1–2 days', '3–6 days', '3–6 days', '1–2 weeks',
                                 'More than 2 weeks'][d]] + items)
    return path


def main():
    args = [a for a in sys.argv[1:] if a != '--selftest']
    if '--selftest' in sys.argv:
        os.makedirs(os.path.join(ROOT, 'data', 'survey'), exist_ok=True)
        csv_path = make_selftest_csv(os.path.join(ROOT, 'data', 'survey', '_selftest.csv'))
        print(f'(self-test: synthetic data at {csv_path})\n')
    else:
        csv_path = args[0] if args else DEFAULT_CSV
    if not os.path.exists(csv_path):
        sys.exit(f'CSV not found: {csv_path}\nExport the Google Form responses '
                 f'(Sheet -> File -> Download -> CSV) to that path first.')

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit('CSV has no data rows.')
    headers = list(rows[0].keys())

    igds_cols = [find_col(headers, k) for k in IGDS_KEYS]
    missing = [k for k, c in zip(IGDS_KEYS, igds_cols) if c is None]
    if missing:
        sys.exit(f'Could not locate IGDS9-SF item columns for: {missing}\n'
                 f'(headers must contain the docs/SURVEY_IGDS9SF.md key phrases)')
    cols = {
        'adult':   find_col(headers, '18'),
        # MUST be specific: 'do you play video games' also appears inside the
        # hours-per-week question, and matching that would bind the yes/no
        # eligibility gate to a banded answer ("2-5") and silently drop EVERY
        # row. Verified by the dry-run harness (ml/tests/test_survey_parsing.py).
        'gamer':   find_col(headers, 'currently play video games'),
        'hours_w': find_col(headers, 'hours per week'),
        'daily':   find_col(headers, 'typical day'),
        'days':    find_col(headers, 'days per week'),
        'session': find_col(headers, 'single', 'session'),
        'late':    find_col(headers, 'after midnight'),
        'binge':   find_col(headers, 'longer than 3 hours'),
        'rapid':   find_col(headers, 'within 15 minutes'),
        'streak':  find_col(headers, 'consecutive days'),
        'attn':    find_col(headers, 'quality control'),
    }

    kept, dropped = [], {'eligibility': 0, 'attention': 0, 'incomplete_igds': 0}
    for r in rows:
        if cols['adult'] and not str(r.get(cols['adult'], '')).strip().lower().startswith('y'):
            dropped['eligibility'] += 1
            continue
        if cols['gamer'] and not str(r.get(cols['gamer'], '')).strip().lower().startswith('y'):
            dropped['eligibility'] += 1
            continue
        if cols['attn'] and likert(r.get(cols['attn'], '')) != 4:
            dropped['attention'] += 1
            continue
        items = [likert(r.get(c, '')) for c in igds_cols]
        if any(v is None for v in items):
            dropped['incomplete_igds'] += 1
            continue
        r['_igds'] = sum(items)
        kept.append(r)

    n = len(kept)
    print(f'Responses: {len(rows)} raw -> {n} usable '
          f'(dropped: {dropped})')
    if n < 30:
        print('WARNING: n < 30 — every number below is indicative only.')
    if n == 0:
        sys.exit('No usable responses.')

    out = {'csv': os.path.basename(csv_path), 'n_raw': len(rows), 'n_usable': n,
           'dropped': dropped}
    totals = np.array([r['_igds'] for r in kept], float)

    # ── Prevalence (the calibrate_thresholds_prevalence.py anchor) ─────────────
    print('\n-- IGDS9-SF severity --')
    print(f'  total score: mean {totals.mean():.1f}, median {np.median(totals):.0f}, '
          f'range {totals.min():.0f}-{totals.max():.0f}')
    for label, cut in (('disordered (>=36)', IGDS_DISORDERED),
                       ('elevated (>=32)', IGDS_ELEVATED)):
        k = int((totals >= cut).sum())
        lo, hi = beta_ci(k, n)
        print(f'  {label}: {k}/{n} = {k / n:.1%}  (95% CI {lo:.1%}-{hi:.1%})')
        out[f'prevalence_{cut}'] = {'k': k, 'n': n, 'rate': round(k / n, 4),
                                    'ci95': [round(lo, 4), round(hi, 4)]}

    # ── Hours vs severity (direction check) ────────────────────────────────────
    if cols['hours_w']:
        hb = {'less than 2': 1.0, '2-5': 3.5, '6-10': 8.0, '11-20': 15.5,
              '21-35': 28.0, 'more than 35': 40.0}
        hours = np.array([band(r.get(cols['hours_w'], ''), hb, np.nan) for r in kept], float)
        ok = ~np.isnan(hours)
        if ok.sum() >= 10 and len(set(hours[ok])) > 1 and len(set(totals[ok])) > 1:
            rho = spearmanr(hours[ok], totals[ok]).statistic
            lo, hi = bootstrap_rho(hours[ok], totals[ok])
            print(f'\n-- hours/week vs IGDS total --\n  Spearman rho = {rho:.3f} '
                  f'(95% CI {lo:.3f} to {hi:.3f}, n={int(ok.sum())})')
            out['hours_vs_igds'] = {'rho': round(float(rho), 3),
                                    'ci95': [round(lo, 3), round(hi, 3)],
                                    'n': int(ok.sum())}

    # ── Construct validity: behaviour model score vs IGDS total ───────────────
    behaviour_cols_ok = all(cols[k] for k in
                            ('daily', 'days', 'session', 'late', 'binge', 'rapid', 'streak'))
    scorer, note = load_model() if behaviour_cols_ok else (None, 'gaming-pattern (Q5-Q11) columns missing from the CSV')
    if scorer is None:
        print(f'\n-- construct validity SKIPPED: {note} --')
        out['construct_validity'] = {'skipped': note}
    else:
        scores, labels = [], []
        for r in kept:
            obj = objective_features(r, cols)
            if obj is not None:
                scores.append(scorer(obj))
                labels.append(r['_igds'])
        scores, labels = np.array(scores), np.array(labels, float)
        m = len(scores)
        print(f'\n-- construct validity (behaviour model: {note}) --')
        if m < 20:
            print(f'  only {m} respondents had complete Q5-Q11 answers — too few, skipping.')
            out['construct_validity'] = {'skipped': f'only {m} complete feature rows'}
        else:
            rho = spearmanr(scores, labels).statistic
            lo, hi = bootstrap_rho(scores, labels)
            print(f'  model risk score vs IGDS total: Spearman rho = {rho:.3f} '
                  f'(95% CI {lo:.3f} to {hi:.3f}, n={m})   <- the headline number')
            out['construct_validity'] = {'rho': round(float(rho), 3),
                                         'ci95': [round(lo, 3), round(hi, 3)], 'n': m}

            # Threshold fit on IGDS bands (<21 / 21-31 / >=32), weighted kappa.
            bands = np.digitize(labels, [21, IGDS_ELEVATED])
            t1, t2, kappa = fit_thresholds(scores, bands)
            print(f'  suggested bands: RISK_T1={t1} RISK_T2={t2} '
                  f'(quadratic-weighted kappa {kappa:.3f} vs IGDS bands; '
                  f'current serving prior 0.33/0.67)')
            print('  apply by setting the env vars on the service - instantly revertible.')
            out['threshold_fit'] = {'RISK_T1': t1, 'RISK_T2': t2, 'kappa': kappa,
                                    'igds_band_counts': [int((bands == i).sum()) for i in range(3)]}

            positives = int((labels >= IGDS_DISORDERED).sum())
            if positives >= MIN_POSITIVES:
                from sklearn.metrics import roc_auc_score
                auc = roc_auc_score((labels >= IGDS_DISORDERED).astype(int), scores)
                print(f'  caseness AUC (>= {IGDS_DISORDERED}): {auc:.3f} ({positives} positives)')
                out['caseness_auc'] = {'auc': round(float(auc), 3), 'positives': positives}
            else:
                print(f'  caseness metrics withheld: only {positives} disordered-range '
                      f'respondents (< {MIN_POSITIVES}) - correlation is the endpoint at this n.')
                out['caseness_auc'] = {'withheld': True, 'positives': positives}

    out_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)),
                            'survey_validation.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
