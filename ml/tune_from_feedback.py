"""
Feedback-driven threshold tuning — turns the parent-feedback table (the system's only
REAL labels) into concrete, conservative threshold recommendations.

What it does:
  1. Exports every feedback verdict (with its prediction snapshot + the alert type it
     responded to) to data/feedback_labels.csv — the seed dataset for future retraining.
  2. For each risk band and for chat-toxicity alerts, models the false-alarm rate with a
     Beta posterior (uniform prior), so a handful of labels moves a threshold slightly
     and many consistent labels move it decisively — never a big jump off 3 verdicts.
  3. Writes recommended values to backend/models/threshold_tuning.json.

Applying: the backend reads RISK_T1 / RISK_T2 / CHAT_ALERT_T from environment variables
(app.py), so recommendations are applied by setting those env vars on the service — no
code change, and instantly revertible.

Label semantics (see app.py FEEDBACK_LABELS):
  accurate       -> the alert/verdict was right           (true positive)
  false_alarm    -> flatly wrong                          (false positive)
  too_sensitive  -> directionally right but over-called   (soft false positive, half weight)
  too_late       -> should have fired sooner              (miss; pressure to LOWER threshold)

Run from the project root:  python ml/tune_from_feedback.py
DB resolution: DATABASE_URL (Postgres) > DATABASE_PATH > backend/gaming_addiction.db.
"""
import csv
import json
import os
import sys

from scipy.stats import beta as beta_dist

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(ROOT, 'data')
MODELS_DIR = os.path.join(ROOT, 'backend', 'models')

# Current serving defaults (must match app.py's fallbacks — a stale value here
# anchors the recommendation at the wrong operating point; kept in sync by
# tests/test_ml_units.py::test_tuner_defaults_match_serving).
DEFAULTS = {'RISK_T1': 0.33, 'RISK_T2': 0.67, 'CHAT_ALERT_T': 0.95}

# Tuning policy — deliberately conservative.
MIN_LABELS   = 5      # don't touch a threshold on fewer verdicts than this
FP_TARGET    = 0.40   # acceptable false-alarm share; above this, raise the threshold
MISS_TARGET  = 0.40   # acceptable "too_late" share; above this, lower the threshold
MAX_STEP     = 0.05   # largest single-run movement of any threshold
BOUNDS       = {'RISK_T1': (0.20, 0.50), 'RISK_T2': (0.50, 0.85), 'CHAT_ALERT_T': (0.50, 0.95)}


def _connect():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url.startswith(('postgres://', 'postgresql://')):
        import psycopg2
        import psycopg2.extras
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn, '%s'
    import sqlite3
    path = os.environ.get('DATABASE_PATH',
                          os.path.join(ROOT, 'backend', 'gaming_addiction.db'))
    if not os.path.exists(path):
        sys.exit(f"No database found at {path} (set DATABASE_PATH or DATABASE_URL)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, '?'


def load_feedback():
    conn, _ph = _connect()
    cur = conn.cursor()
    cur.execute('''SELECT f.label, f.risk_category, f.risk_score, f.note, f.created_at,
                          f.user_id, a.type AS alert_type, a.severity AS alert_severity
                   FROM feedback f LEFT JOIN alerts a ON a.id = f.alert_id''')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def export_csv(rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, 'feedback_labels.csv')
    cols = ['label', 'risk_category', 'risk_score', 'alert_type', 'alert_severity',
            'user_id', 'note', 'created_at']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})
    print(f"[OK] exported {len(rows)} labelled verdicts -> {path}")
    return path


def _posterior_exceeds(k: float, n: float, target: float) -> float:
    """P(rate > target) under Beta(1+k, 1+(n-k)) — uniform prior on the rate."""
    if n <= 0:
        return 0.0
    return float(beta_dist.sf(target, 1 + k, 1 + (n - k)))


def _analyse_group(rows):
    """Evidence summary for one alert group. too_sensitive counts as HALF a false alarm
    (directionally right, over-called); too_late pressures the threshold DOWN."""
    n_acc  = sum(1 for r in rows if r['label'] == 'accurate')
    n_fa   = sum(1 for r in rows if r['label'] == 'false_alarm')
    n_ts   = sum(1 for r in rows if r['label'] == 'too_sensitive')
    n_late = sum(1 for r in rows if r['label'] == 'too_late')
    fp_evid   = n_fa + 0.5 * n_ts
    fp_n      = n_acc + n_fa + 0.5 * n_ts
    late_n    = n_acc + n_late
    return {
        'n': len(rows), 'accurate': n_acc, 'false_alarm': n_fa,
        'too_sensitive': n_ts, 'too_late': n_late,
        'p_fp_high':   round(_posterior_exceeds(fp_evid, fp_n, FP_TARGET), 3),
        'p_miss_high': round(_posterior_exceeds(n_late, late_n, MISS_TARGET), 3),
    }


def _recommend(current: float, evidence: dict, key: str):
    lo, hi = BOUNDS[key]
    if evidence['n'] < MIN_LABELS:
        return current, f"only {evidence['n']} verdicts (<{MIN_LABELS}) — unchanged"
    # Net pressure: up when false alarms dominate, down when "too late" dominates.
    delta = MAX_STEP * (evidence['p_fp_high'] - evidence['p_miss_high'])
    new = round(min(hi, max(lo, current + delta)), 3)
    why = (f"P(false-alarm rate>{FP_TARGET})={evidence['p_fp_high']}, "
           f"P(miss rate>{MISS_TARGET})={evidence['p_miss_high']} -> delta {delta:+.3f}")
    return new, why


def main():
    rows = load_feedback()
    if not rows:
        print("No feedback recorded yet — nothing to tune. "
              "(Verdicts arrive via POST /api/feedback from the Parent app.)")
        return
    export_csv(rows)

    current = {k: float(os.environ.get(k, str(v))) for k, v in DEFAULTS.items()}

    # Risk-band verdicts: judged against the model's snapshotted category.
    risk_rows = [r for r in rows if (r.get('alert_type') in (None, 'risk'))]
    ev_addicted = _analyse_group([r for r in risk_rows if r.get('risk_category') == 'addicted'])
    ev_at_risk  = _analyse_group([r for r in risk_rows if r.get('risk_category') == 'at_risk'])
    # Chat-toxicity verdicts: judged against the per-message alert.
    ev_chat = _analyse_group([r for r in rows if r.get('alert_type') == 'toxicity'])

    rec, notes = {}, {}
    rec['RISK_T2'],      notes['RISK_T2']      = _recommend(current['RISK_T2'], ev_addicted, 'RISK_T2')
    rec['RISK_T1'],      notes['RISK_T1']      = _recommend(current['RISK_T1'], ev_at_risk, 'RISK_T1')
    rec['CHAT_ALERT_T'], notes['CHAT_ALERT_T'] = _recommend(current['CHAT_ALERT_T'], ev_chat, 'CHAT_ALERT_T')
    if rec['RISK_T1'] >= rec['RISK_T2']:            # keep the bands ordered
        rec['RISK_T1'] = round(rec['RISK_T2'] - 0.05, 3)
        notes['RISK_T1'] += ' (clamped below RISK_T2)'

    out = {
        'labels_analysed': len(rows),
        'evidence': {'addicted_band': ev_addicted, 'at_risk_band': ev_at_risk,
                     'chat_toxicity': ev_chat},
        'current': current,
        'recommended': rec,
        'notes': notes,
        'apply': ('Set these as environment variables on the backend service '
                  '(RISK_T1 / RISK_T2 / CHAT_ALERT_T) — app.py reads them at boot. '
                  'Conservative by design: max +/-0.05 per run, no change under '
                  f'{MIN_LABELS} verdicts.'),
    }
    path = os.path.join(MODELS_DIR, 'threshold_tuning.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    print(f"\n[OK] wrote recommendations -> {path}")


if __name__ == '__main__':
    main()
