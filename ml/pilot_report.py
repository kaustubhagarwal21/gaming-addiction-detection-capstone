"""
Aggregate pilot snapshot — everything the paper's pilot table needs, nothing private.

Summarises one (or every) pilot child's collected data since --since into counts,
distributions and a per-day series. PRIVACY RULE (this report may travel as a CI
artifact on a public repo): STRICTLY AGGREGATE — no chat/transcript text, no
notification titles, no reflection notes, no names; users are keyed by numeric id
only. Game titles and emotion labels are app-level facts, not utterances, and the
published paper already reports them.

Demo accounts (user_id 1/3 — Arjun/Priya seed data) are excluded unless --user
asks for them explicitly.

Run from the project root:  python ml/pilot_report.py [--since 2026-07-06]
                            [--user N ...] [--json pilot_report.json]
DB resolution: DATABASE_URL (Postgres) > DATABASE_PATH > backend/gaming_addiction.db.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_USER_IDS = (1, 3)

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


def _parse_ts(ts):
    s = str(ts).replace(' ', 'T')
    for suffix in ('+00:00', 'Z'):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return datetime.fromisoformat(s.split('+')[0])


def _pct(values, q):
    values = sorted(values)
    if not values:
        return None
    idx = min(len(values) - 1, int(round(q * (len(values) - 1))))
    return values[idx]


def report_user(cur, uid: int, since: str) -> dict:
    out = {'user_id': uid}
    # SELECT * so the report works against any schema vintage (older local DBs lack
    # newer columns); only the non-sensitive keys below are ever read or emitted.
    cur.execute(f'SELECT * FROM users WHERE user_id={_PH}', (uid,))
    u = cur.fetchone()
    if not u:
        out['error'] = 'user not found'
        return out
    u = {k: v for k, v in dict(u).items()}
    tz_min = int(u.get('tz_offset_min') or 0)   # server stores its own local time (UTC in prod)
    out['account'] = {
        'created': str(u.get('created_at') or '')[:10],
        'consent_version': u.get('consent_version'),
        'consented': str(u.get('consent_given_at') or '')[:10] or None,
        'last_seen': str(u.get('last_seen') or '')[:16] or None,
        'tz_offset_min': u.get('tz_offset_min'),
        'device_admin': u.get('device_admin_active'),
        'perms': {'usage': u.get('perm_usage'), 'accessibility': u.get('perm_accessibility'),
                  'keyboard': u.get('perm_keyboard'), 'voice': u.get('voice_capture_active')},
    }

    # ── Sessions + per-child-local-day series ────────────────────────────────
    cur.execute(f'''SELECT start_time, end_time, COALESCE(duration_seconds,0) AS dur,
                           final_risk_score, risk_category, game_name
                    FROM sessions WHERE user_id={_PH} AND start_time>={_PH}
                    ORDER BY start_time''', (uid, since))
    sessions = [dict(r) for r in cur.fetchall()]
    durations = [int(s['dur'] or 0) for s in sessions if s['end_time']]
    by_day = defaultdict(lambda: {'sessions': 0, 'seconds': 0, 'weighted': 0.0, 'wsum': 0.0})
    games = defaultdict(float)
    late_night = 0
    for s in sessions:
        try:
            local = _parse_ts(s['start_time']) + timedelta(minutes=tz_min)
        except Exception:
            continue
        day = by_day[local.date().isoformat()]
        day['sessions'] += 1
        day['seconds'] += int(s['dur'] or 0)
        if s['final_risk_score'] is not None and s['end_time']:
            day['weighted'] += float(s['final_risk_score']) * max(1, int(s['dur'] or 0))
            day['wsum'] += max(1, int(s['dur'] or 0))
        games[s['game_name'] or 'Unknown'] += (s['dur'] or 0) / 3600.0
        if local.hour >= 22 or local.hour < 6:
            late_night += 1
    out['sessions'] = {
        'total': len(sessions),
        'completed': len(durations),
        'total_hours': round(sum(durations) / 3600.0, 1),
        'active_days': len(by_day),
        'first_day': min(by_day) if by_day else None,
        'last_day': max(by_day) if by_day else None,
        'late_night_sessions': late_night,
        'duration_min_median': round((_pct(durations, 0.5) or 0) / 60.0, 1),
        'duration_min_p90': round((_pct(durations, 0.9) or 0) / 60.0, 1),
        'top_games_hours': dict(sorted(((g, round(h, 1)) for g, h in games.items()),
                                       key=lambda kv: -kv[1])[:5]),
        'daily': {d: {'sessions': v['sessions'],
                      'hours': round(v['seconds'] / 3600.0, 2),
                      'risk': round(v['weighted'] / v['wsum'], 3) if v['wsum'] else None}
                  for d, v in sorted(by_day.items())},
    }

    # ── Predictions: score distribution + modality coverage ──────────────────
    cur.execute(f'''SELECT p.final_risk_score AS s, p.risk_category AS c,
                           p.behavior_present AS bp, p.chat_present AS cp,
                           p.voice_present AS vp
                    FROM predictions p JOIN sessions x ON x.session_id=p.session_id
                    WHERE x.user_id={_PH} AND p.timestamp>={_PH}''', (uid, since))
    rows = [dict(r) for r in cur.fetchall()]
    scores = [float(r['s']) for r in rows if r['s'] is not None]
    cats = defaultdict(int)
    for r in rows:
        cats[r['c'] or 'unknown'] += 1
    known = [r for r in rows if r['bp'] is not None]
    out['predictions'] = {
        'total': len(rows),
        'score_mean': round(sum(scores) / len(scores), 3) if scores else None,
        'score_median': round(_pct(scores, 0.5), 3) if scores else None,
        'score_p90': round(_pct(scores, 0.9), 3) if scores else None,
        'categories': dict(cats),
        'modality_coverage_pct': ({
            'behavior': round(100 * sum(1 for r in known if r['bp']) / len(known)),
            'chat': round(100 * sum(1 for r in known if r['cp']) / len(known)),
            'voice': round(100 * sum(1 for r in known if r['vp']) / len(known)),
        } if known else None),
    }

    # ── Chat volume + toxicity buckets (counts only — never text) ────────────
    cur.execute(f'''SELECT cm.source AS src, cm.confidence AS conf
                    FROM chat_messages cm JOIN sessions x ON x.session_id=cm.session_id
                    WHERE x.user_id={_PH} AND cm.timestamp>={_PH}''', (uid, since))
    chat = [dict(r) for r in cur.fetchall()]
    typed = [c for c in chat if (c['src'] or 'ocr') != 'voice_stt']
    spoken = [c for c in chat if (c['src'] or '') == 'voice_stt']

    def tox_buckets(rows_):
        b = {'safe_lt_0.4': 0, 'borderline_0.4_0.9': 0, 'toxic_ge_0.9': 0}
        for r in rows_:
            v = float(r['conf'] or 0)
            key = ('toxic_ge_0.9' if v >= 0.9 else
                   'borderline_0.4_0.9' if v >= 0.4 else 'safe_lt_0.4')
            b[key] += 1
        return b
    out['chat'] = {'typed': len(typed), 'spoken_transcribed': len(spoken),
                   'typed_toxicity': tox_buckets(typed),
                   'spoken_toxicity': tox_buckets(spoken)}

    # ── Voice events: emotion distribution ───────────────────────────────────
    try:
        cur.execute(f'''SELECT ve.emotion AS e, COALESCE(ve.capture_valid,1) AS ok,
                           CASE WHEN ve.probs IS NULL THEN 0 ELSE 1 END AS has_probs
                    FROM voice_events ve JOIN sessions x ON x.session_id=ve.session_id
                    WHERE x.user_id={_PH} AND ve.timestamp>={_PH}''', (uid, since))
    except Exception:   # pre-migration local DB without capture_valid/probs
        cur.execute(f'''SELECT ve.emotion AS e, 1 AS ok, 0 AS has_probs
                    FROM voice_events ve JOIN sessions x ON x.session_id=ve.session_id
                    WHERE x.user_id={_PH} AND ve.timestamp>={_PH}''', (uid, since))
    voice = [dict(r) for r in cur.fetchall()]
    emo = defaultdict(int)
    for v in voice:
        if v['ok']:
            emo[v['e'] or '?'] += 1
    out['voice'] = {'events': len(voice),
                    'valid': sum(1 for v in voice if v['ok']),
                    'with_shadow_probs': sum(int(v['has_probs']) for v in voice),
                    'emotions': dict(sorted(emo.items(), key=lambda kv: -kv[1]))}

    # ── Alerts / feedback / reflections / streak ─────────────────────────────
    cur.execute(f'''SELECT type, severity, read FROM alerts
                    WHERE user_id={_PH} AND created_at>={_PH}''', (uid, since))
    alerts = [dict(r) for r in cur.fetchall()]
    by_type, by_sev = defaultdict(int), defaultdict(int)
    for a in alerts:
        by_type[a['type'] or '?'] += 1
        by_sev[a['severity'] or '?'] += 1
    out['alerts'] = {'total': len(alerts), 'unread': sum(1 for a in alerts if not a['read']),
                     'by_type': dict(by_type), 'by_severity': dict(by_sev)}

    cur.execute(f'SELECT label, COUNT(*) AS n FROM feedback WHERE user_id={_PH} GROUP BY label',
                (uid,))
    out['feedback_verdicts'] = {r['label']: int(r['n']) for r in (dict(x) for x in cur.fetchall())}

    cur.execute(f'''SELECT mood_rating AS m, sleep_quality AS s, energy_level AS e
                    FROM reflections WHERE user_id={_PH} AND created_at>={_PH}''', (uid, since))
    refl = [dict(r) for r in cur.fetchall()]

    def _mean(key):
        vals = [r[key] for r in refl if r[key] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    out['reflections'] = {'count': len(refl), 'mood_mean': _mean('m'),
                          'sleep_mean': _mean('s'), 'energy_mean': _mean('e')}

    cur.execute(f'SELECT current_streak, longest_streak, total_healthy_days FROM streaks '
                f'WHERE user_id={_PH}', (uid,))
    srow = cur.fetchone()
    out['streak'] = dict(srow) if srow else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', default='2026-07-06', help='pilot epoch (ISO date)')
    ap.add_argument('--user', type=int, action='append',
                    help='user id(s); default = every non-demo user with sessions since --since')
    ap.add_argument('--json', default='pilot_report.json')
    args = ap.parse_args()

    conn = _connect()
    cur = conn.cursor()
    if args.user:
        uids = args.user
    else:
        cur.execute(f'''SELECT DISTINCT user_id FROM sessions WHERE start_time>={_PH}
                        ORDER BY user_id''', (args.since,))
        uids = [int(dict(r)['user_id']) for r in cur.fetchall()
                if int(dict(r)['user_id']) not in DEMO_USER_IDS]
    if not uids:
        sys.exit(f'No non-demo users with sessions since {args.since}.')

    report = {'generated': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
              'since': args.since, 'users': [report_user(cur, u, args.since) for u in uids]}
    conn.close()

    for u in report['users']:
        s, p = u.get('sessions', {}), u.get('predictions', {})
        print(f"\nuser {u['user_id']}: {s.get('total')} sessions "
              f"({s.get('total_hours')}h over {s.get('active_days')} days, "
              f"{s.get('late_night_sessions')} late-night) | "
              f"{p.get('total')} predictions, median score {p.get('score_median')} | "
              f"chat typed/spoken {u['chat']['typed']}/{u['chat']['spoken_transcribed']} | "
              f"voice {u['voice']['valid']} valid | alerts {u['alerts']['total']} | "
              f"reflections {u['reflections']['count']}")

    with open(args.json, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f'\nWrote {args.json}')


if __name__ == '__main__':
    main()
