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
    keeps empty bins finite.

    Near-constant reference: the quantile bins collapse, and the previous fallback
    (a single interior edge at the reference median) put every non-negative score in
    ONE bin on both sides — so any amount of mass arriving away from the constant
    reported PSI 0.000. Observed in production (2026-08-24 run: chat mean 0.005 ->
    0.145, KS p = 0, verdict 'stable'). The fallback is now a tolerance band around
    the constant: mass leaving that band IS what drift means there."""
    ref, cur = np.asarray(ref, dtype=float), np.asarray(cur, dtype=float)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:                       # degenerate reference (near-constant)
        v = float(np.median(ref))
        eps = max(1e-6, 1e-3 * max(abs(v), 1.0))
        edges = np.array([-np.inf, v - eps, v + eps, np.inf])
    else:
        edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def reference_degenerate(ref, bins: int = 10) -> bool:
    """True when the reference's quantile bins collapse (near-constant reference).
    Surfaced in the report because PSI then measures departure-from-a-constant
    rather than a reshaped distribution."""
    ref = np.asarray(ref, dtype=float)
    return len(np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))) < 3


def parse_excluded(spec: str):
    """'1,3' / '1 3' / '' -> sorted unique ints. Raises ValueError on junk."""
    return sorted({int(t) for t in (spec or '').replace(',', ' ').split()})


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


def _exclusion_sql(excluded):
    """(sql_fragment, params) filtering out excluded user ids. LEFT JOIN semantics:
    predictions whose session row is gone (orphans) are kept, exactly as the
    pre-exclusion loader kept them — the filter must only ever REMOVE the named ids."""
    if not excluded:
        return '', []
    ph = ','.join([_PH] * len(excluded))
    return f' AND (s.user_id IS NULL OR s.user_id NOT IN ({ph}))', list(excluded)


def load_window(cur, start_iso, end_iso, excluded=()):
    frag, extra = _exclusion_sql(excluded)
    cur.execute(f'''SELECT p.final_risk_score, p.behavior_score, p.chat_score,
                          p.voice_score, p.risk_category, p.behavior_present,
                          p.chat_present, p.voice_present,
                          SUBSTR(p.timestamp,1,10) AS day
                   FROM predictions p
                   LEFT JOIN sessions s ON s.session_id = p.session_id
                   WHERE p.timestamp >= {_PH} AND p.timestamp < {_PH}{frag}''',
                [start_iso, end_iso] + extra)
    return [dict(r) for r in cur.fetchall()]


def window_users(cur, start_iso, end_iso, excluded=()) -> int:
    """Distinct children behind a window's predictions. PSI's industry 0.1/0.2 bars
    assume a POPULATION; with one pilot user, week-over-week PSI blows past 0.2 from
    ordinary behavioural variability (observed: PSI 1.4 because one child simply
    played 4.7x more in week two). Used to gate --fail-on-drift, not the report."""
    frag, extra = _exclusion_sql(excluded)
    cur.execute(f'''SELECT COUNT(DISTINCT s.user_id) AS n
                    FROM predictions p JOIN sessions s ON s.session_id = p.session_id
                    WHERE p.timestamp >= {_PH} AND p.timestamp < {_PH}{frag}''',
                [start_iso, end_iso] + extra)
    row = cur.fetchone()
    return int(row['n'] or 0)


def label(v):
    return 'DRIFT' if v > 0.2 else ('moderate' if v > 0.1 else 'stable')


def drift_gate_eligible(users_ref: int, users_rec: int, min_users: int) -> bool:
    """Whether both windows contain the configured minimum population."""
    return min(users_ref, users_rec) >= min_users


def finite_mean(values):
    """Mean of finite observed values, or None when a legacy column has no data."""
    clean = np.asarray([v for v in values if v is not None], dtype=float)
    clean = clean[np.isfinite(clean)]
    return float(clean.mean()) if clean.size else None


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
    ap.add_argument('--min-users', type=int,
                    default=int(os.environ.get('DRIFT_MIN_USERS', '3')),
                    help='fail-on-drift only fires when BOTH windows contain at least '
                         'this many distinct children. Population-stability metrics '
                         'need a population: with a single pilot user, week-over-week '
                         'PSI exceeds 0.2 from ordinary behavioural variability. The '
                         'report is still printed and written either way.')
    ap.add_argument('--exclude-users',
                    default=os.environ.get('DRIFT_EXCLUDE_USERS', '1,3'),
                    help='comma-separated user ids removed from BOTH windows before any '
                         'statistic (env DRIFT_EXCLUDE_USERS; default the published demo '
                         'children, ids 1 and 3). seed_demo.py OVERWRITES those accounts '
                         'and re-anchors their history to "now" on every reseed, so their '
                         'distributions change by construction, not by drift — the '
                         '2026-08-24 red run was exactly this (a demo reseed plus a '
                         'device-metrics drill dominating the recent window). Pass an '
                         'empty string to monitor everything.')
    args = ap.parse_args()
    try:
        excluded = parse_excluded(args.exclude_users)
    except ValueError:
        ap.error(f'--exclude-users must be comma-separated integers, got {args.exclude_users!r}')
    if args.recent_days <= 0 or args.reference_days <= 0:
        ap.error('--recent-days and --reference-days must be positive')
    if args.min_users <= 0:
        ap.error('--min-users must be positive')

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
    ref = load_window(cur, ref_start.isoformat(), recent_start.isoformat(), excluded)
    rec = load_window(cur, recent_start.isoformat(), now.isoformat(), excluded)
    users_ref = window_users(cur, ref_start.isoformat(), recent_start.isoformat(), excluded)
    users_rec = window_users(cur, recent_start.isoformat(), now.isoformat(), excluded)
    conn.close()

    if excluded:
        print(f"excluded user ids (demo/test accounts): {excluded}")
    print(f"reference: {ref_start.date()} .. {recent_start.date()}  "
          f"({len(ref)} predictions, {users_ref} children)")
    print(f"recent   : {recent_start.date()} .. {now.date()}  "
          f"({len(rec)} predictions, {users_rec} children)")
    report = {'windows': {'reference': [str(ref_start.date()), str(recent_start.date()),
                                        len(ref)],
                          'recent': [str(recent_start.date()), str(now.date()), len(rec)]},
              'population': {'reference_users': users_ref, 'recent_users': users_rec,
                             'min_users': args.min_users, 'excluded_users': excluded},
              'scores': {}, 'bands': {}, 'presence': {}, 'volume': {}}
    if len(ref) < MIN_ROWS or len(rec) < MIN_ROWS:
        print(f"\nInsufficient data (need >= {MIN_ROWS} predictions per window) — "
              "widen the windows or re-run once the pilot has accumulated history.")
        report['status'] = 'insufficient_data'
        if args.json:
            with open(args.json, 'w') as f:
                json.dump(report, f, indent=2, allow_nan=False)
            print(f"[OK] wrote {args.json}")
        return

    report['status'] = 'ok'

    print(f"\n{'score':<18} {'PSI':>7} {'verdict':<10} {'KS p':>9} {'mean ref->rec'}")
    for col in ('final_risk_score', 'behavior_score', 'chat_score', 'voice_score'):
        a = np.array([r[col] for r in ref if r[col] is not None], dtype=float)
        b = np.array([r[col] for r in rec if r[col] is not None], dtype=float)
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if len(a) < MIN_ROWS or len(b) < MIN_ROWS:
            print(f"{col:<18} {'—':>7} insufficient rows")
            continue
        v = psi(a, b)
        ks_p = float(ks_2samp(a, b).pvalue)
        entry = {'psi': round(v, 4), 'ks_p': round(ks_p, 5),
                 'mean_ref': round(float(a.mean()), 4),
                 'mean_recent': round(float(b.mean()), 4),
                 'verdict': label(v)}
        if reference_degenerate(a):
            entry['psi_note'] = ('reference near-constant: PSI measures departure '
                                 'from that constant (tolerance-band bins)')
        report['scores'][col] = entry
        print(f"{col:<18} {v:7.3f} {label(v):<10} {ks_p:9.4f} "
              f"{a.mean():.3f} -> {b.mean():.3f}"
              + ('   [degenerate ref]' if 'psi_note' in entry else ''))

    print("\nrisk-band shares (reference -> recent):")
    for band in ('casual', 'at_risk', 'addicted'):
        pr = sum(1 for r in ref if r['risk_category'] == band) / len(ref)
        pc = sum(1 for r in rec if r['risk_category'] == band) / len(rec)
        report['bands'][band] = [round(pr, 3), round(pc, 3)]
        print(f"  {band:<10} {pr:5.1%} -> {pc:5.1%}")

    print("\nmodality-presence rates (a falling rate = capture regression, not drift):")
    for col in ('behavior_present', 'chat_present', 'voice_present'):
        pr = finite_mean([r[col] for r in ref])
        pc = finite_mean([r[col] for r in rec])
        report['presence'][col] = [round(pr, 3) if pr is not None else None,
                                   round(pc, 3) if pc is not None else None]
        pr_text = f"{pr:5.1%}" if pr is not None else "  n/a"
        pc_text = f"{pc:5.1%}" if pc is not None else "  n/a"
        print(f"  {col:<18} {pr_text} -> {pc_text}")

    vol_ref = len(ref) / max(args.reference_days, 1)
    vol_rec = len(rec) / max(args.recent_days, 1)
    report['volume'] = {'per_day_ref': round(vol_ref, 2), 'per_day_recent': round(vol_rec, 2)}
    print(f"\nprediction volume: {vol_ref:.1f}/day -> {vol_rec:.1f}/day")

    worst = max((s['psi'] for s in report['scores'].values()), default=0.0)
    eligible = drift_gate_eligible(users_ref, users_rec, args.min_users)
    report['gate'] = {'eligible': eligible,
                      'fail_on_drift': bool(args.fail_on_drift),
                      'would_fail': bool(worst > 0.2 and eligible)}
    print(f"\nOVERALL: {label(worst)} (worst score PSI {worst:.3f})")
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(report, f, indent=2, allow_nan=False)
        print(f"[OK] wrote {args.json}")
    if args.fail_on_drift and worst > 0.2:
        pop = min(users_ref, users_rec)
        if not eligible:
            print(f"\nnote: red-run gate NOT enforced — only {pop} distinct child(ren) in a "
                  f"window (< --min-users {args.min_users}). Population-stability metrics "
                  "need a population: single-user week-over-week PSI reflects one child's "
                  "ordinary variability, not model drift. Reported above, not failed.")
        else:
            sys.exit(2)


if __name__ == '__main__':
    main()
