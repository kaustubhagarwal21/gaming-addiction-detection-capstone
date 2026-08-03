"""
How much do the fusion PRIORS actually matter? The 40/30/30 ensemble weights, the
genre multiplier and the 0.33/0.67 band thresholds are clinically-motivated priors,
not fitted parameters (the paper says so). The examiner's real question is not "are
they optimal?" but "would different reasonable values change what the parent sees?"

This script answers that empirically on the latest STORED prediction from each
completed pilot session: it first proves it
can replicate the served fused score exactly (same renormalised present-channel
weighting, genre multiplier, clip), then re-labels every prediction under

  1. a weight sweep  — every (w_b, w_c, w_v) on the simplex within +/-0.15 of the
     40/30/30 prior (0.05 grid), renormalised over present channels,
  2. a genre sweep   — the genre effect scaled from off (x0) to doubled (x2),
  3. a threshold sweep — RISK_T1/RISK_T2 perturbed by +/-0.05,

and reports the fraction of predictions whose BAND changes. Small numbers convert
"unvalidated prior" into "unvalidated but demonstrably insensitive in practice".
Writes docs/fusion_sensitivity.json.

Run from the project root:  python ml/analyze_fusion_sensitivity.py [--since 2026-07-06]
DB resolution: DATABASE_URL (Postgres) > DATABASE_PATH/DATA_PATH >
backend/gaming_addiction.db.
"""
import argparse
import itertools
import json
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_ROWS = 30
REPLICATION_TOL = 2e-4  # stored components/final score are rounded to four decimals

# Capture the data-side URL BEFORE neutering the env for the app import: importing
# app runs init_db(), which must hit a throwaway SQLite, never the production DB.
_DATA_URL = os.environ.pop('DATABASE_URL', '').strip()
_DATA_PATH = os.environ.get('DATABASE_PATH', '').strip()
os.environ['DATABASE_PATH'] = os.path.join(tempfile.gettempdir(), 'fusion_sens_throwaway.db')
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from app import GAME_GENRES, GENRE_RISK_WEIGHTS, RISK_T1, RISK_T2  # noqa: E402
# Importing this module in a test or notebook must not poison the caller's DB env.
if _DATA_URL:
    os.environ['DATABASE_URL'] = _DATA_URL
if _DATA_PATH:
    os.environ['DATABASE_PATH'] = _DATA_PATH
else:
    os.environ.pop('DATABASE_PATH', None)


def _connect():
    if _DATA_URL.startswith(('postgres://', 'postgresql://')):
        import psycopg2
        import psycopg2.extras
        url = _DATA_URL
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor), '%s'
    import sqlite3
    path = (os.environ.get('DATA_PATH', '').strip() or _DATA_PATH
            or os.path.join(ROOT, 'backend', 'gaming_addiction.db'))
    if not os.path.exists(path):
        sys.exit(f"No database found at {path} (set DATABASE_URL or DATA_PATH)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, '?'


def band(score, t1, t2):
    return 'casual' if score < t1 else ('at_risk' if score < t2 else 'addicted')


def served_band(row, score, t1, t2):
    """Apply the observation-mode ceiling recorded on the original prediction."""
    value = band(score, t1, t2)
    return 'at_risk' if row.get('observation_cap') and value == 'addicted' else value


def weight_combos():
    """The exact +/-0.15, 0.05-grid simplex around (0.40, 0.30, 0.30).

    Work in integer twentieths: float boundary checks silently dropped all 0.15
    endpoints (23 combinations instead of the mathematically intended 37).
    """
    out = []
    for ib in range(5, 12):       # 0.25 .. 0.55
        for ic in range(3, 10):   # 0.15 .. 0.45
            iv = 20 - ib - ic
            if 3 <= iv <= 9:      # 0.15 .. 0.45 and weights sum exactly to one
                out.append((ib / 20.0, ic / 20.0, iv / 20.0))
    return out


def fuse(row, wb, wc, wv, genre_scale=1.0):
    comps = []
    if row['bp']: comps.append((wb, row['b']))
    if row['cp']: comps.append((wc, row['c']))
    if row['vp']: comps.append((wv, row['v']))
    if not comps:
        raw = 0.5
    else:
        tw = sum(w for w, _ in comps)
        raw = sum(w * s for w, s in comps) / tw
    g = 1.0 + (row['g'] - 1.0) * genre_scale
    return float(np.clip(raw * g, 0.0, 1.0))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', default=os.environ.get('DRIFT_EPOCH', '2026-07-06'))
    ap.add_argument('--unit', choices=('session', 'prediction'), default='session',
                    help='session (default): latest prediction from each completed '
                         'session; prediction: every live/intermediate snapshot')
    ap.add_argument('--output', default=os.path.join(ROOT, 'docs', 'fusion_sensitivity.json'),
                    help='JSON output path (default: docs/fusion_sensitivity.json)')
    args = ap.parse_args()

    conn, ph = _connect()
    cur = conn.cursor()
    unit_filter = ''
    if args.unit == 'session':
        # Live polling and voice re-scores can create many correlated snapshots for one
        # session. Parents ultimately see the final/latest state, so each completed
        # session must contribute once rather than long sessions dominating the sweep.
        unit_filter = '''AND s.end_time IS NOT NULL
                         AND p.id=(SELECT MAX(p2.id) FROM predictions p2
                                  WHERE p2.session_id=p.session_id
                                    AND p2.behavior_present IS NOT NULL)'''
    cur.execute(f'''SELECT p.behavior_score AS b, p.chat_score AS c, p.voice_score AS v,
                           p.behavior_present AS bp, p.chat_present AS cp,
                           p.voice_present AS vp, p.final_risk_score AS fin,
                           p.risk_category AS category, s.game_name AS game
                    FROM predictions p JOIN sessions s ON s.session_id = p.session_id
                    WHERE p.timestamp >= {ph} AND p.behavior_present IS NOT NULL
                    {unit_filter}''',
                (args.since,))
    rows = []
    for r in cur.fetchall():
        genre = GAME_GENRES.get(r['game'], 'Unknown')
        final = float(r['fin'] or 0)
        category = str(r['category'] or '')
        raw_category = band(final, RISK_T1, RISK_T2)
        rows.append({'b': float(r['b'] or 0), 'c': float(r['c'] or 0),
                     'v': float(r['v'] or 0), 'bp': bool(r['bp']), 'cp': bool(r['cp']),
                     'vp': bool(r['vp']), 'fin': final, 'category': category,
                     # run_prediction caps an early addicted score to at_risk. Preserve
                     # that served policy in every counterfactual instead of reporting
                     # band flips the parent could never actually see.
                     'observation_cap': category == 'at_risk' and raw_category == 'addicted',
                     'g': float(GENRE_RISK_WEIGHTS.get(genre, 1.0))})
    conn.close()

    print(f"{args.unit} rows since {args.since} (with modality flags): {len(rows)}")
    if len(rows) < MIN_ROWS:
        sys.exit(f"Fewer than {MIN_ROWS} usable {args.unit} rows — run once the pilot has history.")

    # 0) Replication proof: the re-implementation must match the SERVED score.
    diffs = [abs(fuse(r, 0.40, 0.30, 0.30) - r['fin']) for r in rows]
    max_diff = max(diffs)
    print(f"replication vs stored final_risk_score: max |diff| = {max_diff:.6f} "
          f"(rounding tolerance)")
    if not np.isfinite(max_diff) or max_diff > REPLICATION_TOL:
        sys.exit(f"Replication check FAILED ({max_diff:.6f} > {REPLICATION_TOL:.6f}); "
                 "serving logic/config has diverged, so sensitivity results would be invalid.")
    invalid_categories = [r['category'] for r in rows
                          if r['category'] not in ('casual', 'at_risk', 'addicted')]
    category_mismatches = [r for r in rows
                           if served_band(r, fuse(r, 0.40, 0.30, 0.30), RISK_T1, RISK_T2)
                           != r['category']]
    if invalid_categories or category_mismatches:
        sys.exit("Replication check FAILED for stored risk categories; serving policy "
                 "has diverged, so sensitivity results would be invalid.")
    baseline = [r['category'] for r in rows]

    report = {'n': len(rows), 'analysis_unit': args.unit,
              'replication_max_abs_diff': round(max_diff, 6),
              'observation_capped_rows': sum(1 for r in rows if r['observation_cap']),
              'baseline_shares': {k: round(sum(1 for x in baseline if x == k) / len(rows), 4)
                                  for k in ('casual', 'at_risk', 'addicted')}}

    # 1) Weight sweep on the simplex, +/-0.15 around the 40/30/30 prior, 0.05 grid.
    combos = weight_combos()
    flips = []
    for wb, wc, wv in combos:
        lab = [served_band(r, fuse(r, wb, wc, wv), RISK_T1, RISK_T2) for r in rows]
        flips.append(sum(1 for a, x in zip(baseline, lab) if a != x) / len(rows))
    report['weight_sweep'] = {
        'combos': len(combos),
        'median_band_flip': round(float(np.median(flips)), 4),
        'max_band_flip': round(float(max(flips)), 4),
        'worst_combo': list(combos[int(np.argmax(flips))]),
    }
    print(f"\nweight sweep (+/-0.15 around 40/30/30, {len(combos)} combos): "
          f"median band-flip {np.median(flips):.1%}, worst {max(flips):.1%} "
          f"at {combos[int(np.argmax(flips))]}")

    # 2) Genre-effect sweep: off (x0) .. doubled (x2).
    report['genre_sweep'] = {}
    for scale in (0.0, 0.5, 1.5, 2.0):
        lab = [served_band(r, fuse(r, 0.40, 0.30, 0.30, genre_scale=scale),
                           RISK_T1, RISK_T2)
               for r in rows]
        f = sum(1 for a, x in zip(baseline, lab) if a != x) / len(rows)
        report['genre_sweep'][f'x{scale}'] = round(f, 4)
        print(f"genre effect x{scale}: band-flip {f:.1%}")

    # 2b) CHANNEL CONTRIBUTION: what does each modality add to the final decision?
    # Re-fuse every row using only a SUBSET of its present channels (weights
    # renormalised over the subset, same genre effect and observation cap — i.e.
    # exactly what serving would have produced had the other channels never been
    # captured) and compare bands against the served all-channels result. This is
    # the fused-decision counterpart of the per-model ablation table: it justifies
    # the multimodal design on real pilot traffic rather than held-out corpora.
    subsets = {
        'behaviour_only':   ('bp',),
        'behaviour_chat':   ('bp', 'cp'),
        'behaviour_voice':  ('bp', 'vp'),
        'chat_voice_only':  ('cp', 'vp'),
    }
    report['channel_contribution'] = {}
    for name, keep in subsets.items():
        agree = flips_n = usable = 0
        deltas = []
        for r, base_cat in zip(rows, baseline):
            masked = dict(r)
            for flag in ('bp', 'cp', 'vp'):
                if flag not in keep:
                    masked[flag] = False
            if not any(masked[f] for f in ('bp', 'cp', 'vp')):
                continue                      # subset has no evidence for this row
            usable += 1
            s = fuse(masked, 0.40, 0.30, 0.30)
            deltas.append(abs(s - r['fin']))
            if served_band(r, s, RISK_T1, RISK_T2) == base_cat:
                agree += 1
            else:
                flips_n += 1
        entry = {'usable_rows': usable,
                 'band_agreement': round(agree / usable, 4) if usable else None,
                 'band_flip': round(flips_n / usable, 4) if usable else None,
                 'mean_abs_score_delta': round(float(np.mean(deltas)), 4) if deltas else None}
        report['channel_contribution'][name] = entry
        if usable:
            print(f"channel subset {name:<16} n={usable:>4}  band-agree "
                  f"{entry['band_agreement']:.1%}  mean |dScore| {entry['mean_abs_score_delta']:.3f}")
        else:
            print(f"channel subset {name:<16} no rows with evidence")

    # 3) Threshold sweep: +/-0.05 on each cut independently.
    report['threshold_sweep'] = {}
    scores = [fuse(r, 0.40, 0.30, 0.30) for r in rows]
    for dt1, dt2 in itertools.product((-0.05, 0.0, 0.05), repeat=2):
        if dt1 == dt2 == 0.0:
            continue
        lab = [served_band(r, s, RISK_T1 + dt1, RISK_T2 + dt2)
               for r, s in zip(rows, scores)]
        f = sum(1 for a, x in zip(baseline, lab) if a != x) / len(rows)
        report['threshold_sweep'][f'T1{dt1:+.2f}_T2{dt2:+.2f}'] = round(f, 4)
    worst_t = max(report['threshold_sweep'].values())
    print(f"threshold sweep (+/-0.05): worst band-flip {worst_t:.1%}")

    out = args.output
    with open(out, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n[OK] wrote {out}")


if __name__ == '__main__':
    main()
