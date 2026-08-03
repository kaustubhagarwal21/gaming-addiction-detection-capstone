"""Optional companion to ml/monitor_drift.py: the same score windows, checked with
Evidently (https://github.com/evidentlyai/evidently) — 20+ maintained drift tests
including non-parametric ones appropriate for SMALL samples, which is exactly the
regime a family pilot lives in (the hand-rolled monitor's PSI/KS need healthy row
counts; Evidently's small-sample defaults degrade more gracefully).

Reads the same DATABASE_URL/DATABASE_PATH the primary monitor uses, compares the
same reference/recent windows, and writes an HTML report + JSON verdict. The
primary monitor remains authoritative for CI (its PSI>0.2 gate); this companion
is for richer diagnosis when it fires, or a second opinion when n is small.

Usage:
  pip install evidently
  python ml/monitor_drift_evidently.py --recent-days 7 --reference-days 28 \
      --html drift_evidently.html --json drift_evidently.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ml'))

from monitor_drift import _connect as connect, load_window  # noqa: E402  (same DB + same SQL)

SCORE_COLS = ['final_risk_score', 'behavior_score', 'chat_score', 'voice_score']


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--recent-days', type=int, default=7)
    ap.add_argument('--reference-days', type=int, default=28)
    ap.add_argument('--html', default='drift_evidently.html')
    ap.add_argument('--json', dest='json_out', default=None)
    args = ap.parse_args()

    conn = connect()
    cur = conn.cursor()
    now = datetime.now()
    recent_start = now - timedelta(days=args.recent_days)
    ref_start = recent_start - timedelta(days=args.reference_days)
    ref = pd.DataFrame(load_window(cur, ref_start.isoformat(), recent_start.isoformat()))
    rec = pd.DataFrame(load_window(cur, recent_start.isoformat(), now.isoformat()))
    conn.close()
    print(f"reference {len(ref)} rows / recent {len(rec)} rows")
    if len(ref) < 10 or len(rec) < 10:
        print("Insufficient data for any drift verdict (need >= 10 rows per window).")
        if args.json_out:
            with open(args.json_out, 'w') as f:
                json.dump({'status': 'insufficient_data',
                           'reference_rows': len(ref), 'recent_rows': len(rec)}, f)
        return

    ref, rec = ref[SCORE_COLS].astype(float), rec[SCORE_COLS].astype(float)
    try:                                   # Evidently >= 0.7 API
        from evidently import Report
        from evidently.presets import DataDriftPreset
        report = Report([DataDriftPreset()])
        snapshot = report.run(current_data=rec, reference_data=ref)
        snapshot.save_html(args.html)
        result = json.loads(snapshot.json())
    except ImportError:                    # legacy 0.4-0.6 API
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset
        report = Report(metrics=[DataDriftPreset()])
        report.run(current_data=rec, reference_data=ref)
        report.save_html(args.html)
        result = json.loads(report.json())
    print(f"[OK] wrote {args.html}")
    if args.json_out:
        with open(args.json_out, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"[OK] wrote {args.json_out}")


if __name__ == '__main__':
    main()
