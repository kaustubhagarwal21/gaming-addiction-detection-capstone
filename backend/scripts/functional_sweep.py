"""
Full functional sweep of the backend in PRODUCTION mode (AUTH_ENFORCE=1), against an
isolated throwaway database. Complements the pytest suite (which runs mostly in shadow
mode): this exercises every feature flow the two apps use, with real tokens, including
the paths the suite doesn't cover — registration/family joins, the heartbeat watchdog
with child-local quiet hours, tamper events, the nudge lifecycle, chat de-dupe and
toxicity alerts, a real WAV voice upload (silence floor + late re-score), role guards,
stale-session self-healing, feedback + agreement, and the PDF report.

Run from backend/:  python scripts/functional_sweep.py
Exit code 0 = all checks passed.
"""
import io
import math
import os
import struct
import sys
import tempfile
import wave
from datetime import datetime, timedelta

# ── Isolated DB + production auth, BEFORE importing app ─────────────────────
_TMP_DB = os.path.join(tempfile.gettempdir(), 'functional_sweep.db')
for _ext in ('', '-wal', '-shm'):
    try:
        os.remove(_TMP_DB + _ext)
    except OSError:
        pass
os.environ['DATABASE_PATH'] = _TMP_DB
os.environ['AUTH_ENFORCE'] = '1'

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as appmod  # noqa: E402

client = appmod.app.test_client()
results = []


def check(label, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  - ' + str(detail)) if detail and not ok else ''}")


def auth(tok):
    return {'Authorization': f'Bearer {tok}'}


def db():
    import sqlite3
    conn = sqlite3.connect(_TMP_DB)
    conn.row_factory = sqlite3.Row
    return conn


print("== Registration / family / auth ==")
r = client.post('/api/register', json={'name': 'Asha', 'age': 13, 'pin': '4321', 'parent_pin': '9876'})
j = r.get_json()
check('register new family', r.status_code == 200 and j['success'] and j['family_code'], j)
FAM, child_a, tok_a = j['family_code'], j['user_id'], j['token']

r = client.post('/api/register', json={'name': 'Ravi', 'age': 15, 'pin': '8765',
                                       'parent_pin': '1111', 'family_code': FAM})
check('sibling join with WRONG family PIN -> 403', r.status_code == 403)

r = client.post('/api/register', json={'name': 'Ravi', 'age': 15, 'pin': '8765',
                                       'parent_pin': '9876', 'family_code': FAM})
j = r.get_json()
check('sibling joins family', r.status_code == 200 and j['family_code'] == FAM)
child_b, tok_b = j['user_id'], j['token']

r = client.post('/api/register', json={'name': 'Dup', 'age': 14, 'pin': '4321', 'parent_pin': '2222'})
check('duplicate child PIN -> 409', r.status_code == 409)

r = client.post('/api/user/login', json={'pin': '0000', 'role': 'parent'})
check('parent login without family code -> 400', r.status_code == 400)

r = client.post('/api/user/login', json={'pin': '9876', 'role': 'parent', 'family_code': FAM})
j = r.get_json()
check('parent login sees both children', r.status_code == 200 and
      sorted(c['user_id'] for c in j['children']) == sorted([child_a, child_b]))
tok_p = j['token']

r = client.get('/api/parent/children', headers=auth(tok_p))
check('parent/children via token', r.status_code == 200 and len(r.get_json()['children']) == 2)

print("== Security guards (enforce mode) ==")
check('no token -> 401', client.get(f'/api/dashboard/user?user_id={child_a}').status_code == 401)
check('cross-user read -> 403',
      client.get(f'/api/dashboard/user?user_id={child_b}', headers=auth(tok_a)).status_code == 403)
check('garbage token -> 401',
      client.get(f'/api/dashboard/user?user_id={child_a}',
                 headers={'Authorization': 'Bearer not-a-token'}).status_code == 401)
r = client.post('/api/user/update', json={'user_id': child_a, 'parent_pin': '0000'}, headers=auth(tok_a))
check('CHILD token cannot change family PIN -> 403', r.status_code == 403)
r = client.post('/api/user/delete_data', json={'user_id': child_a, 'scope': 'data'}, headers=auth(tok_a))
check('CHILD token cannot delete data -> 403', r.status_code == 403)
r = client.post('/api/verify_parent_pin', json={'user_id': child_a, 'pin': '9876'}, headers=auth(tok_a))
check('verify parent PIN (right)', r.status_code == 200 and r.get_json()['valid'] is True)
r = client.post('/api/verify_parent_pin', json={'user_id': child_a, 'pin': '0000'}, headers=auth(tok_a))
check('verify parent PIN (wrong)', r.status_code == 200 and r.get_json()['valid'] is False)

print("== Consent ==")
r = client.post('/api/consent', json={'user_id': child_a}, headers=auth(tok_a))
check('record consent', r.status_code == 200)
r = client.get(f'/api/consent?user_id={child_a}', headers=auth(tok_a))
j = r.get_json()
check('consent status', r.status_code == 200 and j['consent_given'] and not j['needs_consent'])

print("== Session lifecycle / prediction ==")
r = client.post('/api/session/start', json={'user_id': child_a, 'game_name': 'Roblox'}, headers=auth(tok_a))
sid = r.get_json()['session_id']
check('session start', r.status_code == 200 and sid)

r = client.post(f'/api/session/{sid}/predict', headers=auth(tok_a))
j = r.get_json()
check('live predict: internal category + genre', r.status_code == 200 and
      j['risk_label'] in ('casual', 'at_risk', 'addicted') and j['game_genre'] == 'Sandbox'
      and abs(j['genre_weight'] - 0.95) < 1e-6, j)
check('observation mode on sparse data', j['observation_mode'] is True)

print("== Chat: de-dupe, toxicity alert, auto language nudge ==")
r = client.post(f'/api/session/{sid}/chat', json={'message': 'nice one gg', 'source': 'keyboard'},
                headers=auth(tok_a))
check('clean chat scored low', r.status_code == 200 and r.get_json()['toxicity_score'] < 0.4)
r = client.post(f'/api/session/{sid}/chat', json={'message': 'nice one gg', 'source': 'keyboard'},
                headers=auth(tok_a))
check('duplicate within 8s flagged', r.status_code == 200 and r.get_json().get('duplicate') is True)
TOXIC = 'fuck shit bitch kill yourself stupid idiot'
r = client.post(f'/api/session/{sid}/chat', json={'message': TOXIC, 'source': 'keyboard'},
                headers=auth(tok_a))
check('toxic chat scored high', r.status_code == 200 and r.get_json()['toxicity_score'] >= appmod.CHAT_ALERT_T)
r = client.get(f'/api/alerts?user_id={child_a}', headers=auth(tok_p))
alerts = r.get_json()['alerts']
check('toxicity alert raised (with age_minutes)',
      any(a['type'] == 'toxicity' for a in alerts) and all('age_minutes' in a for a in alerts))
tox_alert = next(a for a in alerts if a['type'] == 'toxicity')

print("== Nudges: auto + limit + parent custom, delivered exactly once ==")
r = client.post('/api/parent/set_limit', json={'user_id': child_a, 'daily_limit_hours': 2.5},
                headers=auth(tok_p))
check('parent sets daily limit', r.status_code == 200)
r = client.post('/api/parent/nudge', json={'user_id': child_a, 'message': 'Dinner time!'},
                headers=auth(tok_p))
check('parent sends custom nudge', r.status_code == 200)
r = client.get(f'/api/child/nudges?user_id={child_a}', headers=auth(tok_a))
kinds = sorted(n['kind'] for n in r.get_json()['nudges'])
check('child receives language+limit+parent nudges', kinds == ['language', 'limit', 'parent'], kinds)
r = client.get(f'/api/child/nudges?user_id={child_a}', headers=auth(tok_a))
check('nudges delivered exactly once', r.get_json()['nudges'] == [])

print("== Voice: real WAV upload, silence floor, late re-score ==")
def wav_bytes(samples, sr=16000):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h', s) for s in samples))
    buf.seek(0)
    return buf

# End the session first so the voice upload exercises the LATE re-score path.
r = client.post(f'/api/session/{sid}/end', headers=auth(tok_a))
j = r.get_json()
check('session end returns prediction', r.status_code == 200 and
      j['prediction']['risk_label'] in ('casual', 'at_risk', 'addicted'))

silent = wav_bytes([0] * 16000)                      # 1 s of silence
r = client.post(f'/api/session/{sid}/voice', headers=auth(tok_a),
                data={'audio': (silent, 'silent.wav')}, content_type='multipart/form-data')
check('silent clip -> neutral (silence floor)', r.status_code == 200 and
      r.get_json()['emotion'] == 'neutral', r.get_json())

loud = wav_bytes([int(12000 * math.sin(2 * math.pi * 220 * t / 16000)) for t in range(32000)])
r = client.post(f'/api/session/{sid}/voice', headers=auth(tok_a),
                data={'audio': (loud, 'loud.wav')}, content_type='multipart/form-data')
check('voiced clip classified', r.status_code == 200 and
      r.get_json()['emotion'] in ('angry', 'frustrated', 'excited', 'neutral'))
check('raw audio deleted (KEEP_AUDIO off)', not [f for f in os.listdir(appmod.AUDIO_DIR)
                                                 if f.startswith(f'voice_{sid}_')])
r = client.get(f'/api/session/{sid}', headers=auth(tok_a))
check('late voice re-scored into prediction', r.get_json()['prediction']['voice_present'] == 1)

print("== Stale-session self-healing ==")
conn = db()
old = (datetime.now() - timedelta(hours=9)).isoformat()
conn.execute("INSERT INTO sessions (user_id, game_name, start_time) VALUES (?, 'BGMI', ?)",
             (child_a, old))
conn.commit(); conn.close()
r = client.get(f'/api/child/status?user_id={child_a}', headers=auth(tok_p))
check('orphaned session auto-closed', r.status_code == 200 and r.get_json()['is_playing'] is False)

print("== Heartbeat watchdog (child-local quiet hours) ==")
r = client.post('/api/child/heartbeat', json={'user_id': child_a, 'tz_offset_min': 330},
                headers=auth(tok_a))
check('heartbeat accepted', r.status_code == 200)
nowu = datetime.utcnow()
nowmin = nowu.hour * 60 + nowu.minute
tz_night = (2 * 60 - nowmin) % 1440          # child-local 02:00 (inside quiet hours)
tz_day   = (12 * 60 - nowmin) % 1440         # child-local 12:00 (outside quiet hours)
conn = db()
conn.execute("UPDATE users SET last_seen=?, offline_alerted=0, tz_offset_min=? WHERE user_id=?",
             ((datetime.now() - timedelta(minutes=40)).isoformat(), tz_night, child_a))
conn.commit(); conn.close()
client.get(f'/api/alerts?user_id={child_a}', headers=auth(tok_p))
conn = db()
n_off = conn.execute("SELECT COUNT(*) c FROM alerts WHERE user_id=? AND type='offline'",
                     (child_a,)).fetchone()['c']
conn.execute("UPDATE users SET tz_offset_min=? WHERE user_id=?", (tz_day, child_a))
conn.commit(); conn.close()
check('silence at child-local NIGHT suppressed', n_off == 0)
client.get(f'/api/alerts?user_id={child_a}', headers=auth(tok_p))
conn = db()
n_off2 = conn.execute("SELECT COUNT(*) c FROM alerts WHERE user_id=? AND type='offline'",
                      (child_a,)).fetchone()['c']
conn.close()
check('silence at child-local DAY raises ONE offline alert', n_off2 == 1)

print("== Tamper + logout alert ==")
r = client.post('/api/child/tamper', json={'user_id': child_a, 'event': 'logout'}, headers=auth(tok_a))
check('logout tamper alert', r.status_code == 200)
r = client.post('/api/child/tamper', json={'user_id': child_a, 'event': 'weird'}, headers=auth(tok_a))
check('unknown tamper event -> 400', r.status_code == 400)

print("== Feedback loop ==")
r = client.post('/api/feedback', json={'alert_id': tox_alert['id'], 'label': 'accurate'},
                headers=auth(tok_p))
check('feedback accurate', r.status_code == 200)
r = client.get(f'/api/feedback/summary?user_id={child_a}', headers=auth(tok_p))
check('agreement 100% after accurate', r.get_json()['agreement_rate'] == 1.0)
r = client.post('/api/feedback', json={'alert_id': tox_alert['id'], 'label': 'false_alarm'},
                headers=auth(tok_p))
r = client.get(f'/api/feedback/summary?user_id={child_a}', headers=auth(tok_p))
check('re-rating replaces verdict (agreement 0%)', r.get_json()['agreement_rate'] == 0.0)

print("== Dashboards / report / misc ==")
r = client.get(f'/api/dashboard/parent?user_id={child_a}', headers=auth(tok_p))
j = r.get_json()
check('parent dashboard complete', r.status_code == 200 and all(
    k in j for k in ('live_status', 'monitoring', 'top_games_week', 'week_session_count',
                     'trend_data', 'risk_explanation', 'sleep_impact', 'peer_comparison')))
check('monitoring shows online (fresh heartbeat path)', j['monitoring'] is not None)
r = client.get(f'/api/dashboard/child_enriched?user_id={child_a}', headers=auth(tok_a))
j = r.get_json()
check('child enriched: parent-set goal', j['goal_is_parent_set'] is True and j['daily_goal_hours'] == 2.5)
r = client.get(f'/api/dashboard/weekly_report/pdf?user_id={child_a}', headers=auth(tok_p))
check('weekly PDF generates', r.status_code == 200 and r.data[:4] == b'%PDF', r.status_code)
r = client.post('/api/child/screen_event', json={'user_id': child_a, 'event_type': 'screen_on'},
                headers=auth(tok_a))
check('screen event', r.status_code == 200)
r = client.post('/api/child/notification_event',
                json={'user_id': child_a, 'package_name': 'com.roblox.client', 'game_name': 'Roblox'},
                headers=auth(tok_a))
check('notification event', r.status_code == 200)
r = client.post('/api/counselor/chat', json={'user_id': child_a, 'message': 'i cant stop playing'},
                headers=auth(tok_a))
check('Mira: craving intent', r.status_code == 200 and r.get_json()['intent'] == 'craving')
r = client.post('/api/child/reflection', json={'user_id': child_a, 'mood_rating': 4,
                'sleep_quality': 3, 'energy_level': 4}, headers=auth(tok_a))
check('reflection saved', r.status_code == 200)
r = client.get('/api/model_card')
check('model card public + honest note', r.status_code == 200 and 'chat_alert_note' in r.get_json())
r = client.post('/api/analyse/chat', json={'message': 'you are trash'})
check('analyse chat labels', r.status_code == 200 and r.get_json()['label'] in ('safe', 'borderline', 'toxic'))

print("== Parent-controlled deletion ==")
r = client.post('/api/user/delete_data', json={'user_id': child_b, 'scope': 'account'},
                headers=auth(tok_p))
check('parent deletes sibling account', r.status_code == 200)
r = client.post('/api/user/login', json={'pin': '8765', 'role': 'child'})
check('deleted child can no longer log in', r.status_code == 401)

passed = sum(results)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
