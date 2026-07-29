"""
Prevalence-anchored threshold calibration — the method that turns RISK_T2 from a
prior into an epidemiologically anchored parameter, once a real POPULATION exists.

Anchor: the open IGDS9-SF Latin-America dataset (ml/analyze_igds.py) puts 6.4% of
active gamers at/above the disordered-range cutoff. Method: compute each child's
duration-weighted mean risk score over the window, then set T2 at the (1 - p)
quantile of the per-child distribution so the share of children labelled
'addicted'-band matches the real-world prevalence p. (T1 has no comparable
epidemiological anchor and is deliberately not fitted here.)

POPULATION GATE: quantiles over children require children. Below --min-users the
script prints the method demonstration but refuses to recommend — one pilot child's
sessions are not a population (the same lesson the drift monitor's PSI gate encodes).
A locally collected survey (adult 18+ IGDS9-SF form) can replace the default anchor
via --prevalence once available.

Run from the project root:
  python ml/calibrate_thresholds_prevalence.py [--since 2026-07-06] [--prevalence 0.064]
"""
import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prevalence_threshold(scores, prevalence):
    """Return (quantile threshold, empirically achieved top-band share).

    Finite samples and ties mean a quantile cannot generally reproduce the requested
    prevalence exactly; reporting the achieved share prevents false precision.
    """
    if not np.isfinite(prevalence) or not 0.0 < prevalence < 1.0:
        raise ValueError('prevalence must be a finite value strictly between 0 and 1')
    values = np.asarray(scores, dtype=float)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError('scores must be a non-empty finite sequence')
    threshold = float(np.quantile(values, 1.0 - prevalence))
    achieved = float(np.mean(values >= threshold))
    return threshold, achieved


def _connect():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url.startswith(('postgres://', 'postgresql://')):
        import psycopg2
        import psycopg2.extras
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor), '%s'
    import sqlite3
    path = os.environ.get('DATABASE_PATH',
                          os.path.join(ROOT, 'backend', 'gaming_addiction.db'))
    if not os.path.exists(path):
        sys.exit(f"No database found at {path} (set DATABASE_PATH or DATABASE_URL)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, '?'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', default=os.environ.get('DRIFT_EPOCH', '2026-07-06'))
    ap.add_argument('--prevalence', type=float, default=0.064,
                    help='share of children expected in the top band '
                         '(default: IGDS9-SF LatAm disordered-range rate, 6.4%%)')
    ap.add_argument('--min-users', type=int, default=10,
                    help='refuse to recommend below this many distinct children')
    args = ap.parse_args()
    if not np.isfinite(args.prevalence) or not 0.0 < args.prevalence < 1.0:
        ap.error('--prevalence must be a finite value strictly between 0 and 1')
    if args.min_users < 2:
        ap.error('--min-users must be at least 2')

    conn, ph = _connect()
    cur = conn.cursor()
    cur.execute(f'''SELECT user_id,
                           SUM(final_risk_score * COALESCE(duration_seconds, 0)) AS ws,
                           SUM(COALESCE(duration_seconds, 0)) AS dur,
                           AVG(final_risk_score) AS mean_s
                    FROM sessions
                    WHERE start_time >= {ph} AND end_time IS NOT NULL
                      AND final_risk_score IS NOT NULL
                    GROUP BY user_id''', (args.since,))
    per_child = []
    for r in cur.fetchall():
        score = (float(r['ws']) / float(r['dur'])) if float(r['dur'] or 0) > 0 \
            else float(r['mean_s'])
        per_child.append((r['user_id'], score))
    conn.close()

    n = len(per_child)
    print(f"children with scored sessions since {args.since}: {n}")
    for uid, s in sorted(per_child, key=lambda x: -x[1]):
        print(f"  child {uid}: duration-weighted mean risk {s:.3f}")

    scores = np.array([s for _, s in per_child], dtype=float)
    if n == 0:
        sys.exit("no data")
    t2, achieved = prevalence_threshold(scores, args.prevalence)
    try:
        current_t2 = float(os.environ.get('RISK_T2', '0.67'))
    except ValueError:
        sys.exit("RISK_T2 must be a finite number strictly between 0 and 1")
    if not np.isfinite(current_t2) or not 0.0 < current_t2 < 1.0:
        sys.exit("RISK_T2 must be a finite number strictly between 0 and 1")
    print(f"\nprevalence-anchored T2 = quantile(per-child scores, {1 - args.prevalence:.3f})"
          f" = {t2:.3f}   (current RISK_T2 = {current_t2:.3f})")
    print(f"finite-sample top-band share at score >= T2: {achieved:.1%} "
          f"(target {args.prevalence:.1%})")
    if achieved > args.prevalence + (1.0 / n):
        print("note: ties at the cutoff make the achieved share materially larger than "
              "the anchor; collect a larger cohort before using this threshold.")

    if n < args.min_users:
        print(f"\nPOPULATION GATE: only {n} child(ren) < --min-users {args.min_users} — "
              "this is a METHOD DEMONSTRATION, not a recommendation. A quantile over "
              "one or two children reflects those children, not gamer prevalence. "
              "Re-run once the pilot cohort (or a local IGDS9-SF survey feeding "
              "--prevalence) provides a population.")
    else:
        print("\nRecommendation: set RISK_T2 via env to the value above and record the "
              "anchor (dataset + prevalence) next to it.")


if __name__ == '__main__':
    main()
