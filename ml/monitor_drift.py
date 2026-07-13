"""
Score-distribution drift monitor — the pilot-phase instrument that notices when the
live system starts behaving differently from its reference period.

Why: the models are frozen between retrains, but the POPULATION isn't — new games,
new families, seasonal play patterns. A shift in the served score distributions is
the earliest observable symptom of the models mismatching reality (or of a silent
capture regression, e.g. a channel going dark). This script compares a RECENT window
of stored predictions against a REFERENCE window on:

  - PSI (population stability index) per channel score + fused score
      < 0.10 stable | 0.10-0.20 moderate shift | > 0.20 DRIFT (industry convention)
  - Kolmogorov-Smirnov two-sample test (distribution shape)
  - risk-band shares (casual / at-risk / addicted mix)
  - prediction volume per day and per-modality presence rates
      (a falling voice-presence rate = capture problem, not model problem)

Run from the project root (defaults: reference = days 35..7 ago, recent = last 7):
  python ml/monitor_drift.py
  python ml/monitor_drift.py --recent-days 30 --reference-days 90 --json out.json
DB resolution: DATABASE_URL (Postgres) > DATABASE_PATH > backend/gaming_addiction.db.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np
from scipy.stats import ks_2samp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_ROWS = 30   # below this per window, distribution comparisons are noise


def psi(ref, cur, bins: int = 10) -> float:
    """Population Stability Index over quantile bins of the REFERENCE distribution.
    0 = identical; >0.2 = material drift (standard monitoring convention). Bins are
    taken from reference quantiles so the measure is scale-free; a small epsilon
    keeps empty bins finite."""
    ref, cur = np.asarray(ref, dtype=float), np.asarray(cur, dtype=float)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:                       # degenerate reference (near-constant)
        edges = np.array([min(ref.min(), cur.min()) - 1e-9,
                          np.median(ref), max(ref.max(), cur.max()) + 1e-9])
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


_PH = '?'   # SQL placeholder — swapped to %s when connecting to Postgres (psycopg2)


def _connect():
    global _PH
    url = os.environ.get('DATABASE_URL', '').strip()
    if url.startswith(('postgres://', 'postgresql://')):
        import psycopg2
        import psycopg2.extras
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        _PH = '%s'
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    import sqlite3
    path = os.environ.get('DATABASE_PATH',
                          os.path.join(ROOT, 'backend', 'gaming_addiction.db'))
    if not os.path.exists(path):
        sys.exit(f"No database found at {path} (set DATABASE_PATH or DATABASE_URL)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_window(cur, start_iso, end_iso):
    cur.execute(f'''SELECT final_risk_score, behavior_score, chat_score, voice_score,
                          risk_category, behavior_present, chat_present, voice_present,
                          SUBSTR(timestamp,1,10) AS day
                   FROM predictions WHERE timestamp >= {_PH} AND timestamp < {_PH}''',
                (start_iso, end_iso))
    return [dict(r) for r in cur.fetchall()]


def label(v):
    return 'DRIFT' if v > 0.2 else ('moderate' if v > 0.1 else 'stable')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--recent-days', type=int, default=7)
    ap.add_argument('--reference-days', type=int, default=28,
                    help='length of the reference window that PRECEDES the recent one')
    ap.add_argument('--json', default=None, help='also write the report to this path')
    ap.add_argument('--fail-on-drift', action='store_true',
                    help='exit 2 when any score PSI exceeds 0.2 — lets a scheduled CI '
                         'run turn red instead of printing into the void')
    ap.add_argument('--since', default=os.environ.get('DRIFT_EPOCH'),
                    help='ignore predictions before this ISO date (env DRIFT_EPOCH). '
                         'Set to the pilot start so windows never straddle a data-regime '
                         'boundary: demo/seed rows vs real pilot rows differ hugely by '
                         'construction, and comparing across that boundary reports '
                         'population change as model drift (first pilot Monday: PSI 5.97).')
    args = ap.parse_args()

    now = datetime.now()
    recent_start = now - timedelta(days=args.recent_days)
    ref_start = recent_start - timedelta(days=args.reference_days)
    if args.since:
        epoch = datetime.fromisoformat(args.since)
        if ref_start < epoch:
            print(f"epoch: windows clamped to >= {epoch.date()} (DRIFT_EPOCH)")
            ref_start = max(ref_start, epoch)
            recent_start = max(recent_start, ref_start)

    conn = _connect()
    cur = conn.cursor()
    ref = load_window(cur, ref_start.isoformat(), recent_start.isoformat())
    rec = load_window(cur, recent_start.isoformat(), now.isoformat())
    conn.close()

    print(f"reference: {ref_start.date()} .. {recent_start.date()}  ({len(ref)} predictions)")
    print(f"recent   : {recent_start.date()} .. {now.date()}  ({len(rec)} predictions)")
    if len(ref) < MIN_ROWS or len(rec) < MIN_ROWS:
        print(f"\nInsufficient data (need >= {MIN_ROWS} predictions per window) — "
              "widen the windows or re-run once the pilot has accumulated history.")
        return

    report = {'windows': {'reference': [str(ref_start.date()), str(recent_start.date()),
                                        len(ref)],
                          'recent': [str(recent_start.date()), str(now.date()), len(rec)]},
              'scores': {}, 'bands': {}, 'presence': {}, 'volume': {}}

    print(f"\n{'score':<18} {'PSI':>7} {'verdict':<10} {'KS p':>9} {'mean ref->rec'}")
    for col in ('final_risk_score', 'behavior_score', 'chat_score', 'voice_score'):
        a = np.array([r[col] for r in ref if r[col] is not None], dtype=float)
        b = np.array([r[col] for r in rec if r[col] is not None], dtype=float)
        if len(a) < MIN_ROWS or len(b) < MIN_ROWS:
            print(f"{col:<18} {'—':>7} insufficient rows")
            continue
        v = psi(a, b)
        ks_p = float(ks_2samp(a, b).pvalue)
        report['scores'][col] = {'psi': round(v, 4), 'ks_p': round(ks_p, 5),
                                 'mean_ref': round(float(a.mean()), 4),
                                 'mean_recent': round(float(b.mean()), 4),
                                 'verdict': label(v)}
        print(f"{col:<18} {v:7.3f} {label(v):<10} {ks_p:9.4f} "
              f"{a.mean():.3f} -> {b.mean():.3f}")

    print("\nrisk-band shares (reference -> recent):")
    for band in ('casual', 'at_risk', 'addicted'):
        pr = sum(1 for r in ref if r['risk_category'] == band) / len(ref)
        pc = sum(1 for r in rec if r['risk_category'] == band) / len(rec)
        report['bands'][band] = [round(pr, 3), round(pc, 3)]
        print(f"  {band:<10} {pr:5.1%} -> {pc:5.1%}")

    print("\nmodality-presence rates (a falling rate = capture regression, not drift):")
    for col in ('behavior_present', 'chat_present', 'voice_present'):
        pr = np.mean([r[col] for r in ref if r[col] is not None] or [np.nan])
        pc = np.mean([r[col] for r in rec if r[col] is not None] or [np.nan])
        report['presence'][col] = [round(float(pr), 3), round(float(pc), 3)]
        print(f"  {col:<18} {pr:5.1%} -> {pc:5.1%}")

    vol_ref = len(ref) / max(args.reference_days, 1)
    vol_rec = len(rec) / max(args.recent_days, 1)
    report['volume'] = {'per_day_ref': round(vol_ref, 2), 'per_day_recent': round(vol_rec, 2)}
    print(f"\nprediction volume: {vol_ref:.1f}/day -> {vol_rec:.1f}/day")

    worst = max((s['psi'] for s in report['scores'].values()), default=0.0)
    print(f"\nOVERALL: {label(worst)} (worst score PSI {worst:.3f})")
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"[OK] wrote {args.json}")
    if args.fail_on_drift and worst > 0.2:
        sys.exit(2)


if __name__ == '__main__':
    main()
