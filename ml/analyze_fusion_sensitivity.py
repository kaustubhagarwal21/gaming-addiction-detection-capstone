"""
How much do the fusion PRIORS actually matter? The 40/30/30 ensemble weights, the
genre multiplier and the 0.33/0.67 band thresholds are clinically-motivated priors,
not fitted parameters (the paper says so). The examiner's real question is not "are
they optimal?" but "would different reasonable values change what the parent sees?"

This script answers that empirically on STORED pilot predictions: it first proves it
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
DB resolution: DATABASE_URL (Postgres) > DATABASE_PATH > backend/gaming_addiction.db.
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

# Capture the data-side URL BEFORE neutering the env for the app import: importing
# app runs init_db(), which must hit a throwaway SQLite, never the production DB.
_DATA_URL = os.environ.pop('DATABASE_URL', '').strip()
os.environ['DATABASE_PATH'] = os.path.join(tempfile.gettempdir(), 'fusion_sens_throwaway.db')
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from app import GAME_GENRES, GENRE_RISK_WEIGHTS, RISK_T1, RISK_T2  # noqa: E402


def _connect():
    if _DATA_URL.startswith(('postgres://', 'postgresql://')):
        import psycopg2
        import psycopg2.extras
        url = _DATA_URL
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor), '%s'
    import sqlite3
    path = os.environ.get('DATA_PATH', os.path.join(ROOT, 'backend', 'gaming_addiction.db'))
    if not os.path.exists(path):
        sys.exit(f"No database found at {path} (set DATABASE_URL or DATA_PATH)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, '?'


def band(score, t1, t2):
    return 'casual' if score < t1 else ('at_risk' if score < t2 else 'addicted')


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
    args = ap.parse_args()

    conn, ph = _connect()
    cur = conn.cursor()
    cur.execute(f'''SELECT p.behavior_score AS b, p.chat_score AS c, p.voice_score AS v,
                           p.behavior_present AS bp, p.chat_present AS cp,
                           p.voice_present AS vp, p.final_risk_score AS fin,
                           s.game_name AS game
                    FROM predictions p JOIN sessions s ON s.session_id = p.session_id
                    WHERE p.timestamp >= {ph} AND p.behavior_present IS NOT NULL''',
                (args.since,))
    rows = []
    for r in cur.fetchall():
        genre = GAME_GENRES.get(r['game'], 'Unknown')
        rows.append({'b': float(r['b'] or 0), 'c': float(r['c'] or 0),
                     'v': float(r['v'] or 0), 'bp': bool(r['bp']), 'cp': bool(r['cp']),
                     'vp': bool(r['vp']), 'fin': float(r['fin'] or 0),
                     'g': float(GENRE_RISK_WEIGHTS.get(genre, 1.0))})
    conn.close()

    print(f"predictions since {args.since} (with modality flags): {len(rows)}")
    if len(rows) < MIN_ROWS:
        sys.exit(f"Fewer than {MIN_ROWS} usable predictions — run once the pilot has history.")

    # 0) Replication proof: the re-implementation must match the SERVED score.
    diffs = [abs(fuse(r, 0.40, 0.30, 0.30) - r['fin']) for r in rows]
    print(f"replication vs stored final_risk_score: max |diff| = {max(diffs):.4f} "
          f"(rounding tolerance)")
    baseline = [band(fuse(r, 0.40, 0.30, 0.30), RISK_T1, RISK_T2) for r in rows]

    report = {'n': len(rows), 'replication_max_abs_diff': round(max(diffs), 4),
              'baseline_shares': {k: round(sum(1 for x in baseline if x == k) / len(rows), 4)
                                  for k in ('casual', 'at_risk', 'addicted')}}

    # 1) Weight sweep on the simplex, +/-0.15 around the 40/30/30 prior, 0.05 grid.
    grid = [round(0.05 * k, 2) for k in range(2, 12)]
    combos = [(wb, wc, round(1 - wb - wc, 2)) for wb, wc in itertools.product(grid, grid)
              if abs(wb - 0.40) <= 0.15 and abs(wc - 0.30) <= 0.15
              and abs(round(1 - wb - wc, 2) - 0.30) <= 0.15
              and round(1 - wb - wc, 2) >= 0.05]
    flips = []
    for wb, wc, wv in combos:
        lab = [band(fuse(r, wb, wc, wv), RISK_T1, RISK_T2) for r in rows]
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
        lab = [band(fuse(r, 0.40, 0.30, 0.30, genre_scale=scale), RISK_T1, RISK_T2)
               for r in rows]
        f = sum(1 for a, x in zip(baseline, lab) if a != x) / len(rows)
        report['genre_sweep'][f'x{scale}'] = round(f, 4)
        print(f"genre effect x{scale}: band-flip {f:.1%}")

    # 3) Threshold sweep: +/-0.05 on each cut independently.
    report['threshold_sweep'] = {}
    scores = [fuse(r, 0.40, 0.30, 0.30) for r in rows]
    for dt1, dt2 in itertools.product((-0.05, 0.0, 0.05), repeat=2):
        if dt1 == dt2 == 0.0:
            continue
        lab = [band(s, RISK_T1 + dt1, RISK_T2 + dt2) for s in scores]
        f = sum(1 for a, x in zip(baseline, lab) if a != x) / len(rows)
        report['threshold_sweep'][f'T1{dt1:+.2f}_T2{dt2:+.2f}'] = round(f, 4)
    worst_t = max(report['threshold_sweep'].values())
    print(f"threshold sweep (+/-0.05): worst band-flip {worst_t:.1%}")

    out = os.path.join(ROOT, 'docs', 'fusion_sensitivity.json')
    with open(out, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n[OK] wrote {out}")


if __name__ == '__main__':
    main()
