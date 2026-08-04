# -*- coding: utf-8 -*-
"""Reality-check of the behaviour generator's late-night prior against real phone
telemetry — StudentLife (Wang et al., UbiComp 2014; RData mirror, Zenodo 3529253,
CC-BY-4.0; 48 Dartmouth students, 10 weeks).

SCOPE, measured before claiming (2026-08-04): this open mirror carries only
COARSE lock/dark events — both tables record intervals of AT LEAST ONE HOUR
(verified: min locked duration exactly 1.00 h), and the original's fine-grained
app-usage tables are not in it (the original 53 GB distribution is offline). So
the generator's session-level priors (sessions/day, durations, breaks, rapid
re-logins) CANNOT be checked here. What can: the LATE-NIGHT ACTIVITY share.
Active periods = the complement of >=1 h locked intervals per student; the
late-night ratio is the fraction of active time falling 22:00-06:00 local
(America/New_York), the backend's exact _is_late_night() window.

Reading: an upper-bound-flavoured, all-usage analogue of the generator's
late_night_play_ratio priors (casual 0.08 / at-risk 0.30 / heavy 0.60). Students
are not children and phone activity is not gaming, so this bounds plausibility,
nothing more.

Usage: python ml/analyze_studentlife.py  (expects data/studentlife/dataset_rds.zip;
downloads from Zenodo if absent; pip install pyreadr)
"""
import json
import os
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'studentlife')
ZIP = os.path.join(CACHE, 'dataset_rds.zip')
URL = 'https://zenodo.org/records/3529253/files/dataset_rds.zip?download=1'
TZ = ZoneInfo('America/New_York')
LATE_START, LATE_END = 22, 6            # backend _is_late_night()
STEP_S = 600                            # 10-min sampling of active periods


def ensure_table():
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.exists(ZIP):
        print('downloading StudentLife RData mirror (~230 MB, CC-BY-4.0)...')
        urllib.request.urlretrieve(URL, ZIP)
    member = 'dataset_rds/sensing/phonelock.Rds'
    path = os.path.join(CACHE, member.replace('/', os.sep))
    if not os.path.exists(path):
        zipfile.ZipFile(ZIP).extract(member, CACHE)
    import pyreadr
    return next(iter(pyreadr.read_r(path).values()))


def late_share_for(locked):
    """Fraction of ACTIVE (not locked>=1h) time in 22:00-06:00 local, sampled at
    10-minute resolution across the student's observation span."""
    lo = float(locked['start_timestamp'].min())
    hi = float(locked['end_timestamp'].max())
    if hi - lo < 7 * 86400:
        return None
    ts = np.arange(lo, hi, STEP_S)
    in_lock = np.zeros(len(ts), dtype=bool)
    for s, e in locked[['start_timestamp', 'end_timestamp']].itertuples(index=False):
        in_lock |= (ts >= s) & (ts < e)
    active = ts[~in_lock]
    if len(active) < 100:
        return None
    hours = pd.to_datetime(active, unit='s', utc=True).tz_convert(TZ).hour
    late = ((hours >= LATE_START) | (hours < LATE_END)).mean()
    return float(late)


def main():
    df = ensure_table()
    df['uid'] = df['uid'].astype(str)
    rows = []
    for uid, g in df.groupby('uid', observed=True):
        v = late_share_for(g.sort_values('start_timestamp'))
        if v is not None:
            rows.append({'uid': uid, 'late_night_active_share': v})
    r = pd.DataFrame(rows)
    q1, med, q3 = r['late_night_active_share'].quantile([0.25, 0.5, 0.75])
    p90 = r['late_night_active_share'].quantile(0.90)
    print(f'{len(r)} students | late-night active share: '
          f'median {med:.3f}  IQR [{q1:.3f}, {q3:.3f}]  p90 {p90:.3f}')
    print('generator late_night_play_ratio priors: casual 0.08 / at-risk 0.30 / heavy 0.60')

    out = {
        'source': 'StudentLife (Wang et al. 2014), Zenodo 3529253 RData mirror, CC-BY-4.0',
        'scope_note': 'Mirror carries only >=1h lock events (verified min 1.00h); '
                      'session-level priors are NOT checkable from it. This is the '
                      'late-night ACTIVITY share of all phone use by college students '
                      '(22:00-06:00 America/New_York, the backend window).',
        'n_students': int(len(r)),
        'late_night_active_share': {'median': round(float(med), 3),
                                    'iqr': [round(float(q1), 3), round(float(q3), 3)],
                                    'p90': round(float(p90), 3)},
        'generator_late_night_priors': {'casual': 0.08, 'at_risk': 0.30, 'heavy': 0.60},
    }
    dest = os.path.join(ROOT, 'docs', 'studentlife_check.json')
    with open(dest, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'[OK] wrote {dest}')


if __name__ == '__main__':
    main()
