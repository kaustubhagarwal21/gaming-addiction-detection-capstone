"""
Reflections as a free external-validity check.

The child app already collects daily self-reports (mood / sleep quality / energy,
1-5). If the risk model measures something real, a higher-risk gaming day should
tend to be followed by a WORSE self-reported next morning — especially sleep quality
after late-night play. This script tests exactly that with Spearman rank correlations
(monotonic, no linearity assumption): each child's mean risk on day D against their
self-reports on day D+1 (and same-day as a secondary view).

This is a weak-label validation — self-reports are noisy and the sample is small — but
it is REAL data the system already has, and a consistent negative correlation is
genuine evidence the screening signal tracks lived experience (a stepping stone to the
IGDS9-SF study in VALIDATION_PLAN.md).

Run from the project root:  python ml/analyze_reflections.py
DB resolution: DATABASE_URL (Postgres) > DATABASE_PATH > backend/gaming_addiction.db.
"""
import os
import sys
from datetime import datetime, timedelta

from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_PAIRS = 8   # below this, a correlation is noise — report "insufficient data"


def _connect():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url.startswith(('postgres://', 'postgresql://')):
        import psycopg2
        import psycopg2.extras
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    import sqlite3
    path = os.environ.get('DATABASE_PATH',
                          os.path.join(ROOT, 'backend', 'gaming_addiction.db'))
    if not os.path.exists(path):
        sys.exit(f"No database found at {path} (set DATABASE_PATH or DATABASE_URL)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# The seeded demo family. seed_demo.py CONSTRUCTS their reflections to track their
# seeded risk ("mood degrades as risk escalates"), so including them reports a
# perfect-looking correlation that is an artifact of the seed script, not evidence.
# On the production DB (which carries the demo accounts alongside real pilot
# children) this exclusion is what keeps the check honest.
DEMO_USER_IDS = (1, 3)


def load(conn):
    cur = conn.cursor()
    cur.execute(f'''SELECT user_id, SUBSTR(start_time,1,10) AS day,
                          AVG(final_risk_score) AS risk,
                          SUM(COALESCE(duration_seconds,0))/3600.0 AS hours
                   FROM sessions WHERE final_risk_score IS NOT NULL
                   AND user_id NOT IN {DEMO_USER_IDS}
                   GROUP BY user_id, SUBSTR(start_time,1,10)''')
    risk = {(r['user_id'], r['day']): (float(r['risk']), float(r['hours']))
            for r in cur.fetchall()}
    cur.execute(f'''SELECT user_id, SUBSTR(created_at,1,10) AS day,
                          AVG(mood_rating) AS mood, AVG(sleep_quality) AS sleep,
                          AVG(energy_level) AS energy
                   FROM reflections WHERE user_id NOT IN {DEMO_USER_IDS}
                   GROUP BY user_id, SUBSTR(created_at,1,10)''')
    refl = {(r['user_id'], r['day']):
            {k: (float(r[k]) if r[k] is not None else None)
             for k in ('mood', 'sleep', 'energy')}
            for r in cur.fetchall()}
    return risk, refl


def pair(risk, refl, lag_days):
    """(risk_on_day_D, measure_on_day_D+lag) pairs per measure."""
    pairs = {'mood': [], 'sleep': [], 'energy': []}
    for (uid, day), (rk, hours) in risk.items():
        try:
            tgt = (datetime.fromisoformat(day).date()
                   + timedelta(days=lag_days)).isoformat()
        except ValueError:
            continue
        rf = refl.get((uid, tgt))
        if not rf:
            continue
        for m in pairs:
            if rf[m] is not None:
                pairs[m].append((rk, rf[m]))
    return pairs


def report(title, pairs):
    print(f"\n{title}")
    print(f"{'measure':<8} {'n':>4} {'spearman_r':>11} {'p_value':>9}  reading")
    for m, pts in pairs.items():
        if len(pts) < MIN_PAIRS:
            print(f"{m:<8} {len(pts):>4} {'—':>11} {'—':>9}  insufficient data (<{MIN_PAIRS} pairs)")
            continue
        xs, ys = zip(*pts)
        r, p = spearmanr(xs, ys)
        if p < 0.05 and r < 0:
            reading = "higher risk -> worse self-report (supports the signal)"
        elif p < 0.05 and r > 0:
            reading = "unexpected positive association — inspect the data"
        else:
            reading = "no significant association yet"
        print(f"{m:<8} {len(pts):>4} {r:>11.3f} {p:>9.4f}  {reading}")


def main():
    conn = _connect()
    risk, refl = load(conn)
    conn.close()
    print(f"Risk-scored days: {len(risk)}   reflection days: {len(refl)}")
    if not risk or not refl:
        print("Not enough data yet — need scored sessions AND daily check-ins. "
              "Re-run once a pilot has a few weeks of both.")
        return
    report("Next-day (risk on day D vs self-report on D+1 — primary hypothesis):",
           pair(risk, refl, 1))
    report("Same-day (secondary view):", pair(risk, refl, 0))
    print(f"\nNote: Spearman rank correlation; pairs pooled across children. "
          f"Self-reports are 1-5 (higher = better), risk is 0-1 (higher = worse), "
          f"so a NEGATIVE r supports the model. Minimum {MIN_PAIRS} pairs per cell.")


if __name__ == '__main__':
    main()
