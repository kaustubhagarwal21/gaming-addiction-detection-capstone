"""
Evaluate the voice domain-shift mitigations OFFLINE, on live pilot audio, using the
shadow-logged probability vectors in voice_events.probs — without ever having changed
what was served. These are distribution diagnostics, not accuracy estimates: pilot
events have no emotion ground truth, so this script cannot by itself select a serving
rule or prove that a lower "frustrated" share is more correct.

Why this exists: the pilot showed 77% of voice events labelled 'frustrated' during
casual puzzle play — domain shift (acted-adult training audio vs child/ambient phone
audio), not model skill. Raw audio is deleted by design, so candidate fixes cannot be
back-tested; instead the server logs the classifier's full distribution per event
(observe-only), and THIS script describes how each acoustic candidate would change
raw model decisions:

  1. Abstain margin  — serve top class only if P(top) - P(neutral) > m, else neutral.
     Swept over m; shows the raw acoustic-decision distribution and % relabelled.
  2. BBSE prior correction (label-shift estimate) — solve C^T p = q for the target
     prior p (C = row-normalised held-out confusion from model_metadata.json,
     q = observed acoustic-argmax distribution), then re-argmax
     p(y|x) * p(y)/p_train(y).
     Honest caveat printed: the real problem is domain shift; BBSE assumes label
     shift, so treat its output as a mitigation estimate, not truth.

Run from the project root (DB resolution like monitor_drift):
  python ml/analyze_voice_shadow.py [--since 2026-07-06]
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES = ['angry', 'excited', 'frustrated', 'neutral']
MIN_EVENTS = 30


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


def dist(labels):
    n = max(len(labels), 1)
    return {c: sum(1 for l in labels if l == c) / n for c in CLASSES}


def fmt(d):
    return '  '.join(f"{c[:5]}={d.get(c, 0.0):5.1%}" for c in CLASSES)


def probability_vector(value):
    """Parse, validate and normalise one shadow vector; return None if malformed."""
    try:
        obj = json.loads(value) if isinstance(value, str) else value
        if not isinstance(obj, dict):
            return None
        p = np.array([float(obj.get(c, 0.0)) for c in CLASSES], dtype=float)
        if not np.all(np.isfinite(p)) or np.any(p < 0) or p.sum() <= 0:
            return None
        return p / p.sum()  # stored values are rounded, so restore the simplex
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def abstain_labels(P, margin):
    """Raw acoustic decisions under a top-vs-neutral abstention margin."""
    P = np.asarray(P, dtype=float)
    ni = CLASSES.index('neutral')
    top = P.argmax(axis=1)
    return [CLASSES[int(i)] if P[k, int(i)] - P[k, ni] > margin else 'neutral'
            for k, i in enumerate(top)]


def bbse_prior(confusion, observed_predicted):
    """Constrained-after-solve BBSE estimate on the class simplex."""
    C = np.asarray(confusion, dtype=float)
    q = np.asarray(observed_predicted, dtype=float)
    if C.shape != (len(CLASSES), len(CLASSES)) or q.shape != (len(CLASSES),):
        raise ValueError('BBSE inputs have incompatible shapes')
    row_sums = C.sum(axis=1, keepdims=True)
    if np.any(row_sums <= 0) or not np.all(np.isfinite(C)) or not np.all(np.isfinite(q)):
        raise ValueError('BBSE inputs must be finite with non-empty confusion rows')
    C = C / row_sums
    p_hat, *_ = np.linalg.lstsq(C.T, q, rcond=None)
    p_hat = np.clip(p_hat, 1e-4, None)
    return p_hat / p_hat.sum()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', default=os.environ.get('DRIFT_EPOCH', '2026-07-06'))
    args = ap.parse_args()

    conn, ph = _connect()
    cur = conn.cursor()
    try:
        cur.execute(f'''SELECT ve.emotion, ve.probs, ve.session_id, s.user_id
                        FROM voice_events ve
                        JOIN sessions s ON s.session_id=ve.session_id
                        WHERE ve.timestamp >= {ph} AND ve.probs IS NOT NULL
                          AND COALESCE(ve.capture_valid, 1)=1''', (args.since,))
        raw_rows = cur.fetchall()
        cur.execute(f'''SELECT COUNT(*) AS total,
                               SUM(CASE WHEN COALESCE(capture_valid, 1)=0
                                        THEN 1 ELSE 0 END) AS rejected
                        FROM voice_events WHERE timestamp >= {ph}''', (args.since,))
        capture_counts = cur.fetchone()
    except Exception as e:
        sys.exit(f"voice shadow columns not present yet ({type(e).__name__}) — they are "
                 "created by the backend's startup migration; deploy the backend first.")
    finally:
        conn.close()

    rows = []
    malformed = 0
    for r in raw_rows:
        p = probability_vector(r['probs'])
        if p is None:
            malformed += 1
            continue
        rows.append((r['emotion'], p, r['session_id'], r['user_id']))

    total = int((capture_counts['total'] if capture_counts else 0) or 0)
    rejected = int((capture_counts['rejected'] if capture_counts else 0) or 0)
    print(f"shadow-logged events since {args.since}: {len(rows)}")
    print(f"capture attempts: {total}; rejected before classification: {rejected} "
          f"({rejected / max(total, 1):.1%})")
    print(f"coverage: {len({r[3] for r in rows})} children, "
          f"{len({r[2] for r in rows})} sessions")
    if malformed:
        print(f"warning: skipped {malformed} malformed/non-finite probability vector(s)")
    if len(rows) < MIN_EVENTS:
        print(f"Fewer than {MIN_EVENTS} events with logged distributions — let the "
              "pilot run; the column fills forward from deploy time only.")
        return

    P = np.vstack([p for _, p, _, _ in rows])
    served = [e for e, _, _, _ in rows]
    argmax = [CLASSES[i] for i in P.argmax(axis=1)]

    print(f"\n{'served labels (with word-valence fusion)':<44}{fmt(dist(served))}")
    print(f"{'raw acoustic argmax':<44}{fmt(dist(argmax))}")

    print("\nAcoustic abstain diagnostic  (top only if P(top) - P(neutral) > m):")
    for m in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
        lab = abstain_labels(P, m)
        moved = sum(1 for a, b in zip(argmax, lab) if a != b) / len(lab)
        print(f"  m={m:.1f}  {fmt(dist(lab))}   relabelled->neutral: {moved:5.1%}")

    # BBSE: C^T p = q with C row-normalised held-out confusion, q observed argmax dist.
    with open(os.path.join(ROOT, 'backend', 'models', 'model_metadata.json')) as f:
        meta = json.load(f)
    vm = meta.get('voice_metrics', {})
    C = np.array(vm.get('confusion', []), dtype=float)
    order = vm.get('confusion_labels', CLASSES)
    if C.size:
        idx = [order.index(c) for c in CLASSES]
        C = C[np.ix_(idx, idx)]
        q = np.array([dist(argmax)[c] for c in CLASSES])
        p_hat = bbse_prior(C, q)
        print("\nBBSE estimated true prior (label-shift assumption — caveat above):")
        print('  ' + fmt({c: p_hat[i] for i, c in enumerate(CLASSES)}))
        w = p_hat / 0.25                                   # training prior: balanced
        corrected = [CLASSES[int(i)] for i in (P * w).argmax(axis=1)]
        print(f"{'prior-corrected argmax':<44}{fmt(dist(corrected))}")

    print("\nInterpretation: these shifts show candidate behaviour only. They do not "
          "measure accuracy, and repeated events from the same children are correlated. "
          "Choose a serving margin only against a separately labelled child-speech "
          "validation set; do not select it merely because one label share looks nicer.")


if __name__ == '__main__':
    main()
