"""
Evaluate the voice domain-shift mitigations OFFLINE, on live pilot audio, using the
shadow-logged probability vectors in voice_events.probs — without ever having changed
what was served.

Why this exists: the pilot showed 77% of voice events labelled 'frustrated' during
casual puzzle play — domain shift (acted-adult training audio vs child/ambient phone
audio), not model skill. Raw audio is deleted by design, so candidate fixes cannot be
back-tested; instead the server logs the classifier's full distribution per event
(observe-only), and THIS script measures what each candidate WOULD have served:

  1. Abstain margin  — serve top class only if P(top) - P(neutral) > m, else neutral.
     Swept over m; shows the label distribution and % relabelled at each margin.
  2. BBSE prior correction (label-shift estimate) — solve C^T p = q for the target
     prior p (C = row-normalised held-out confusion from model_metadata.json,
     q = observed served-label distribution), then re-argmax p(y|x) * p(y)/p_train(y).
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', default=os.environ.get('DRIFT_EPOCH', '2026-07-06'))
    args = ap.parse_args()

    conn, ph = _connect()
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT emotion, probs FROM voice_events '
                    f'WHERE timestamp >= {ph} AND probs IS NOT NULL', (args.since,))
        rows = [(r['emotion'], json.loads(r['probs'])) for r in cur.fetchall()]
    except Exception as e:
        sys.exit(f"probs column not present yet ({type(e).__name__}) — it is created "
                 "by the backend's startup migration; deploy the backend first.")
    finally:
        conn.close()

    print(f"shadow-logged events since {args.since}: {len(rows)}")
    if len(rows) < MIN_EVENTS:
        print(f"Fewer than {MIN_EVENTS} events with logged distributions — let the "
              "pilot run; the column fills forward from deploy time only.")
        return

    P = np.array([[p.get(c, 0.0) for c in CLASSES] for _, p in rows])
    served = [e for e, _ in rows]
    argmax = [CLASSES[i] for i in P.argmax(axis=1)]

    print(f"\n{'served labels (with word-valence fusion)':<44}{fmt(dist(served))}")
    print(f"{'raw acoustic argmax':<44}{fmt(dist(argmax))}")

    ni = CLASSES.index('neutral')
    print("\nAbstain margin sweep  (serve top only if P(top) - P(neutral) > m):")
    for m in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
        lab = [CLASSES[int(i)] if P[k, int(i)] - P[k, ni] > m else 'neutral'
               for k, i in enumerate(P.argmax(axis=1))]
        moved = sum(1 for a, b in zip(argmax, lab) if a != b) / len(lab)
        print(f"  m={m:.1f}  {fmt(dist(lab))}   relabelled->neutral: {moved:5.1%}")

    # BBSE: C^T p = q with C row-normalised held-out confusion, q observed argmax dist.
    meta = json.load(open(os.path.join(ROOT, 'backend', 'models', 'model_metadata.json')))
    vm = meta.get('voice_metrics', {})
    C = np.array(vm.get('confusion', []), dtype=float)
    order = vm.get('confusion_labels', CLASSES)
    if C.size:
        idx = [order.index(c) for c in CLASSES]
        C = C[np.ix_(idx, idx)]
        C = C / C.sum(axis=1, keepdims=True)               # rows: true -> predicted
        q = np.array([dist(argmax)[c] for c in CLASSES])
        p_hat, *_ = np.linalg.lstsq(C.T, q, rcond=None)
        p_hat = np.clip(p_hat, 1e-4, None)
        p_hat = p_hat / p_hat.sum()
        print("\nBBSE estimated true prior (label-shift assumption — caveat above):")
        print('  ' + fmt({c: p_hat[i] for i, c in enumerate(CLASSES)}))
        w = p_hat / 0.25                                   # training prior: balanced
        corrected = [CLASSES[int(i)] for i in (P * w).argmax(axis=1)]
        print(f"{'prior-corrected argmax':<44}{fmt(dist(corrected))}")

    print("\nInterpretation guide: if the margin sweep collapses 'frustrated' toward "
          "neutral while a genuine-speech minority survives, the abstain rule is the "
          "right serving fix; pick the smallest m that stabilises the distribution.")


if __name__ == '__main__':
    main()
