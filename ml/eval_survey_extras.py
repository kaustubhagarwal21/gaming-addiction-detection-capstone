"""
IGDS9-SF survey → the analyses the paper reports *beyond* the headline correlation.

ml/eval_behavior_survey.py is the primary endpoint (construct validity, prevalence,
threshold suggestion). This script produces the rest of §6.6, from the same export
and the same eligibility filters, so every survey number in the paper is reproducible
from two commands:

  A. INCREMENTAL VALIDITY — does the model's score beat self-reported hours/week, and
     does it survive partialling hours out? (The paper's central claim is that
     *pattern* beats *volume*; this is the test of it against a real instrument.)
     Reported as a paired bootstrap on Δρ, not two correlations eyeballed side by side.
  B. FEATURE-LEVEL SIGNAL — per-feature and composite ρ, split volume vs pattern.
  C. CHAT-CHANNEL PREMISE — self-reported toxic-chat involvement vs IGDS severity,
     the local replication of the r=+0.156 the paper borrows from the LatAm dataset.
  D. GENRE — Kruskal-Wallis across most-played genres, the test of the deployed
     genre multiplier, plus the resampled power curve that says how large a sample
     the (null) result would need to overturn.
  E. STRAIGHT-LINE ROBUSTNESS — does the headline survive dropping respondents who
     gave the identical answer to all nine items?
  F. DERIVED-PROXY HONESTY — do the parent-facing psychometric proxies track the IGDS
     item each is *named* after? (Reported because mostly they do not.)

Usage:  python ml/eval_survey_extras.py [responses.csv]
        (default: data/survey/responses.csv; JSON written next to the CSV)

Row-level responses are not committed: the consent text covered research use, not
public release, so the repository carries the aggregate JSON only.
"""
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np
from scipy.stats import kruskal, rankdata, spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ml'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import eval_behavior_survey as E  # noqa: E402  (shared parsing = shared eligibility)
from behavior_features import derive_psychometrics  # noqa: E402

DEFAULT_CSV = os.path.join(ROOT, 'data', 'survey', 'responses.csv')
MIN_GENRE_N = 4      # genres rarer than this are pooled out of the Kruskal-Wallis
BOOT = 4000

# Band midpoints for the hours/week question (the screen-time baseline).
HOURS_BANDS = {'less than 2': 1.0, '2-5': 3.5, '6-10': 8.0, '11-20': 15.5,
               '21-35': 28.0, 'more than 35': 40.0}

VOLUME = {'daily_play_time_hours', 'weekly_play_time_hours', 'sessions_per_day',
          'avg_session_duration_min', 'days_played_per_week'}
PATTERN = {'late_night_play_ratio', 'longest_play_streak_days', 'binge_sessions_per_week',
           'avg_break_between_sessions_min', 'rapid_relogin_ratio'}

# proxy -> (0-indexed IGDS item, human label) per docs/SURVEY_IGDS9SF.md item order
PROXY_ITEMS = {'craving_score': (0, 'preoccupation (item 1)'),
               'tolerance_score': (2, 'tolerance (item 3)'),
               'control_loss_score': (3, 'failed cutback (item 4)'),
               'neglect_responsibilities_score': (4, 'lost interest (item 5)'),
               'gaming_priority_score': (5, 'continued despite problems (item 6)')}


def boot_ci(fn, n, seed=7, iters=BOOT):
    """Percentile bootstrap CI of fn(index_array) over n rows."""
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(iters):
        v = fn(rng.integers(0, n, n))
        if v is not None and not np.isnan(v):
            vals.append(v)
    if not vals:
        return float('nan'), float('nan'), np.array([])
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)), np.array(vals)


def partial_spearman(x, y, z):
    """Spearman partial correlation of x,y controlling z: rank-transform, then
    correlate the residuals of each on z (Kendall-free, no distributional claim)."""
    rx, ry, rz = rankdata(x), rankdata(y), rankdata(z)
    Z = np.column_stack([np.ones_like(rz), rz])

    def resid(v):
        return v - Z @ np.linalg.lstsq(Z, v, rcond=None)[0]

    return float(spearmanr(resid(rx), resid(ry)).statistic)


def load(csv_path):
    """Apply eval_behavior_survey's exact eligibility filters; return per-respondent rows."""
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit('CSV has no data rows.')
    headers = list(rows[0].keys())
    igds_cols = [E.find_col(headers, k) for k in E.IGDS_KEYS]
    if any(c is None for c in igds_cols):
        sys.exit('Could not locate all nine IGDS9-SF item columns.')
    cols = {k: E.find_col(headers, *v) for k, v in {
        'adult': ('18',), 'gamer': ('currently play video games',),
        'hours_w': ('hours per week',), 'daily': ('typical day',), 'days': ('days per week',),
        'session': ('single', 'session'), 'late': ('after midnight',),
        'binge': ('longer than 3 hours',), 'rapid': ('within 15 minutes',),
        'streak': ('consecutive days',), 'attn': ('quality control',)}.items()}
    tox_col = E.find_col(headers, 'toxic/abusive')
    genre_col = E.find_col(headers, 'type of game')

    scorer, note = E.load_model()
    if scorer is None:
        sys.exit(note)

    kept = []
    for r in rows:
        if not str(r.get(cols['adult'], '')).strip().lower().startswith('y'):
            continue
        if not str(r.get(cols['gamer'], '')).strip().lower().startswith('y'):
            continue
        if E.likert(r.get(cols['attn'], '')) != 4:
            continue
        items = [E.likert(r.get(c, '')) for c in igds_cols]
        if any(v is None for v in items):
            continue
        feat = E.objective_features(r, cols)
        if feat is None:
            continue        # unanswered pattern question -> not scoreable
        kept.append({
            'items': items, 'total': sum(items), 'feat': feat, 'risk': scorer(feat),
            'hours': E.band(r.get(cols['hours_w'], ''), HOURS_BANDS),
            'tox': E.likert(r.get(tox_col, '')) if tox_col else None,
            'genre': str(r.get(genre_col, '')).strip(),
            'flat': len(set(items)) == 1,
        })
    return kept, len(rows), note


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    if not os.path.exists(csv_path):
        sys.exit(f'CSV not found: {csv_path}\nExport the Google Form responses '
                 f'(Sheet -> File -> Download -> CSV) to that path first.')
    d, n_raw, note = load(csv_path)
    n = len(d)
    if n < 30:
        print('WARNING: n < 30 — every number below is indicative only.\n')
    total = np.array([x['total'] for x in d], float)
    risk = np.array([x['risk'] for x in d], float)
    print(f'{n_raw} raw -> {n} scoreable respondents (behaviour model: {note})\n')
    out = {'csv': os.path.basename(csv_path), 'n_raw': n_raw, 'n': n}

    # ---- A. incremental validity over the screen-time baseline ---------------
    hm = np.array([x['hours'] is not None for x in d])
    hours = np.array([x['hours'] if x['hours'] is not None else np.nan for x in d], float)
    r_model = spearmanr(risk[hm], total[hm]).statistic
    r_hours = spearmanr(hours[hm], total[hm]).statistic
    nh = int(hm.sum())
    # Reuse the primary script's bootstrap for these two so the headline CI printed
    # here is byte-identical to the one in survey_validation.json — two scripts
    # disagreeing in the third decimal on the same quantity is a paper defect.
    mlo, mhi = E.bootstrap_rho(risk[hm], total[hm])
    hlo, hhi = E.bootstrap_rho(hours[hm], total[hm])

    def delta(i):
        a = spearmanr(risk[hm][i], total[hm][i]).statistic
        b = spearmanr(hours[hm][i], total[hm][i]).statistic
        return None if (np.isnan(a) or np.isnan(b)) else a - b

    dlo, dhi, dvals = boot_ci(delta, nh)
    pr = partial_spearman(risk[hm], total[hm], hours[hm])
    plo, phi, _ = boot_ci(
        lambda i: partial_spearman(risk[hm][i], total[hm][i], hours[hm][i]), nh)
    print('A. INCREMENTAL VALIDITY over self-reported screen time')
    print(f'   model risk    vs IGDS : rho = {r_model:+.3f}  95% CI [{mlo:+.3f}, {mhi:+.3f}]')
    print(f'   hours/week    vs IGDS : rho = {r_hours:+.3f}  95% CI [{hlo:+.3f}, {hhi:+.3f}]'
          f'   (the baseline it must beat)')
    print(f'   paired delta          : {np.mean(dvals):+.3f}  95% CI [{dlo:+.3f}, {dhi:+.3f}]'
          f'   P(model > hours) = {(dvals > 0).mean():.1%}')
    print(f'   partial | hours       : rho = {pr:+.3f}  95% CI [{plo:+.3f}, {phi:+.3f}]  n={nh}')
    # NOTE ON n: this block is restricted to respondents the model can score, so the
    # model and the baseline are compared on the *same* rows (a paired comparison is
    # meaningless otherwise). eval_behavior_survey.py reports the hours baseline over
    # all usable respondents instead, which is why its rho differs slightly. Same
    # conclusion either way: the interval includes zero.
    out['incremental'] = {'rho_model': r_model, 'rho_model_ci': [mlo, mhi],
                          'rho_hours': r_hours, 'rho_hours_ci': [hlo, hhi], 'n': nh,
                          'delta_rho': float(np.mean(dvals)), 'delta_ci': [dlo, dhi],
                          'p_model_better': float((dvals > 0).mean()),
                          'partial_rho': pr, 'partial_ci': [plo, phi],
                          'note': 'paired on the scoreable subset; eval_behavior_survey.py '
                                  'reports the hours baseline over all usable rows'}
    print()

    # ---- B. which features actually carry the signal -------------------------
    names = list(d[0]['feat'].keys())
    print('B. FEATURE-LEVEL SIGNAL vs IGDS total')
    per_feature = {}
    for nm in sorted(names, key=lambda nm: -abs(spearmanr(
            [x['feat'][nm] for x in d], total).statistic)):
        rho = float(spearmanr([x['feat'][nm] for x in d], total).statistic)
        per_feature[nm] = rho
        grp = 'VOLUME' if nm in VOLUME else 'pattern'
        print(f'   {nm:32s} {rho:+7.3f}  {grp}')

    def composite(group):
        """Sign-corrected z-score sum — the group's best single summary."""
        z = []
        for nm in names:
            if nm not in group:
                continue
            x = np.array([f['feat'][nm] for f in d], float)
            s = np.sign(spearmanr(x, total).statistic) or 1.0
            z.append(s * (x - x.mean()) / (x.std() or 1.0))
        return np.sum(z, axis=0)

    comps = {}
    for label, grp in (('volume', VOLUME), ('pattern', PATTERN)):
        c = composite(grp)
        rho = float(spearmanr(c, total).statistic)
        lo, hi, _ = boot_ci(lambda i, c=c: spearmanr(c[i], total[i]).statistic, n)
        comps[label] = {'rho': rho, 'ci': [lo, hi]}
        print(f'   {label:7s} composite            {rho:+7.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]')

    # Formal contrast for the pattern-vs-volume claim: a PAIRED bootstrap on the
    # difference of the two composite correlations (same respondents resampled for
    # both, composite weights held fixed at their full-sample values), reported with
    # a two-sided CI and a one-sided exceedance probability. Eyeballing "0.330 vs
    # 0.128" is not a test; this is.
    cv, cp = composite(VOLUME), composite(PATTERN)

    def comp_diff(i):
        a = spearmanr(cp[i], total[i]).statistic
        b = spearmanr(cv[i], total[i]).statistic
        return None if (np.isnan(a) or np.isnan(b)) else a - b

    dlo2, dhi2, dvals2 = boot_ci(comp_diff, n)
    comps['pattern_minus_volume'] = {
        'diff': float(np.mean(dvals2)), 'ci': [dlo2, dhi2],
        'p_pattern_better': float((dvals2 > 0).mean()),
        'note': 'paired bootstrap over respondents; composite weights fixed at full-sample values',
    }
    print(f'   pattern - volume diff        {np.mean(dvals2):+7.3f}  95% CI [{dlo2:+.3f}, {dhi2:+.3f}]'
          f'   P(pattern > volume) = {(dvals2 > 0).mean():.1%}')
    out['features'] = {'per_feature': per_feature, 'composites': comps}

    # ---- C. chat-channel premise --------------------------------------------
    tx = np.array([x['tox'] for x in d if x['tox'] is not None], float)
    ty = np.array([x['total'] for x in d if x['tox'] is not None], float)
    if len(tx) >= 20:
        rho = float(spearmanr(tx, ty).statistic)
        lo, hi, _ = boot_ci(lambda i: spearmanr(tx[i], ty[i]).statistic, len(tx))
        print(f'\nC. CHAT-CHANNEL PREMISE (toxic-chat involvement vs IGDS severity)')
        print(f'   rho = {rho:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]  n={len(tx)}'
              f'   (LatAm dataset: r = +0.156)')
        out['chat_premise'] = {'rho': rho, 'ci': [lo, hi], 'n': len(tx)}

    # ---- D. genre, and the power the null would need to overturn -------------
    g = defaultdict(list)
    for x in d:
        if x['genre']:
            g[x['genre']].append(x['total'])
    groups = {k: np.array(v, float) for k, v in g.items() if len(v) >= MIN_GENRE_N}
    print('\nD. GENRE vs IGDS severity (the deployed genre multiplier)')
    for k in sorted(groups, key=lambda k: -groups[k].mean()):
        print(f'   {k[:44]:46s} n={len(groups[k]):3d}  mean IGDS {groups[k].mean():5.1f}')
    if len(groups) >= 3:
        stat, p = kruskal(*groups.values())
        verdict = 'DIFFERENT' if p < 0.05 else 'no significant difference'
        print(f'   Kruskal-Wallis: H={stat:.2f}, p={p:.3f}  -> {verdict}')
        rng = np.random.default_rng(11)
        power = {}
        for mult in (1, 2, 3, 4, 6):
            hits = 0
            for _ in range(400):
                sim = [rng.choice(v, size=len(v) * mult, replace=True) for v in groups.values()]
                try:
                    hits += kruskal(*sim).pvalue < 0.05
                except ValueError:
                    pass
            power[n * mult] = hits / 400
            print(f'   power at n={n*mult:5d} ({mult}x): {hits/400:.0%}')
        out['genre'] = {'H': float(stat), 'p': float(p), 'n_groups': len(groups),
                        'means': {k: float(v.mean()) for k, v in groups.items()},
                        'power_curve': power}

    # ---- E. straight-line robustness ----------------------------------------
    keep = ~np.array([x['flat'] for x in d])
    print(f'\nE. STRAIGHT-LINE ROBUSTNESS ({int((~keep).sum())} identical-answer respondents)')
    out['robustness'] = {}
    for label, m in (('all responses', np.ones(n, bool)), ('excluding straight-line', keep)):
        rr, tt = risk[m], total[m]
        rho = float(spearmanr(rr, tt).statistic)
        lo, hi, _ = boot_ci(lambda i: spearmanr(rr[i], tt[i]).statistic, int(m.sum()))
        print(f'   {label:24s} n={int(m.sum()):3d}  rho = {rho:+.3f}  '
              f'95% CI [{lo:+.3f}, {hi:+.3f}]')
        out['robustness'][label] = {'n': int(m.sum()), 'rho': rho, 'ci': [lo, hi]}

    # ---- F. do the parent-facing proxies track their namesake items? --------
    print('\nF. DERIVED PROXIES vs the IGDS item each is NAMED after')
    proxies = {}
    for proxy, (idx, label) in PROXY_ITEMS.items():
        vals, targ = [], []
        for x in d:
            full = derive_psychometrics(**x['feat'])
            if proxy in full:
                vals.append(full[proxy])
                targ.append(x['items'][idx])
        if vals:
            rho = float(spearmanr(vals, targ).statistic)
            proxies[proxy] = rho
            print(f'   {proxy:32s} vs {label:36s} rho = {rho:+.3f}')
    out['proxies'] = proxies

    dest = os.path.join(os.path.dirname(os.path.abspath(csv_path)), 'survey_extras.json')
    with open(dest, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'\nWrote {dest}')


if __name__ == '__main__':
    main()
