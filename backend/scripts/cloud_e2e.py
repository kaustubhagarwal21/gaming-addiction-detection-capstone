"""
End-to-end smoke test against the LIVE deployed API (default: Render).
Exercises every screen's endpoint with real parent/child tokens, plus the
auth/authorization guards. Usage:

    python scripts/cloud_e2e.py [BASE_URL]
"""
import sys, json, urllib.request, urllib.error

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://gaming-addiction-api.onrender.com").rstrip('/')


def call(method, path, token=None, body=None, raw=False, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
            return r.status, (content if raw else json.loads(content or b'{}'))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return None, str(e)


results = []
def check(label, ok, detail=''):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  - ' + str(detail)) if detail else ''}")


print(f"Cloud E2E against {BASE}\n(first call may take ~30-60s if the server was asleep)\n")

code, h = call('GET', '/api/health')
check('health: models_loaded', code == 200 and h and h.get('models_loaded') is True,
      f"voice={h.get('models', {}).get('voice') if h else '?'}")

# Parent login requires the family code since the family-code auth model shipped.
code, j = call('POST', '/api/user/login',
               body={'pin': '0000', 'role': 'parent', 'family_code': 'FAM789'})
ptok = (j or {}).get('token')
kids = sorted(c['user_id'] for c in (j or {}).get('children', [])) if j else []
check('parent login (FAM789/0000)', code == 200 and bool(ptok) and len(kids) >= 1, f"children={kids}")

code, j = call('POST', '/api/user/login', body={'pin': '1234', 'role': 'child'})
ctok = (j or {}).get('token')
check('child login (1234 / Arjun)', code == 200 and bool(ctok))

print("\n-- Parent screens --")
for label, path in [
    ('Dashboard',        '/api/dashboard/parent?user_id=1'),
    ('Alerts',           '/api/alerts?user_id=1'),
    ('Emotion Insights', '/api/dashboard/emotions?user_id=1'),
    ('Chat Analysis',    '/api/dashboard/chat_analysis?user_id=1'),
    ('Child status',     '/api/child/status?user_id=1'),
]:
    code, j = call('GET', path, token=ptok)
    check(label, code == 200)

code, raw = call('GET', '/api/dashboard/weekly_report/pdf?user_id=1', token=ptok, raw=True)
check('Weekly report PDF', code == 200 and raw and raw[:4] == b'%PDF', f"{len(raw) if raw else 0} bytes")

code, j = call('POST', '/api/parent/set_limit', token=ptok, body={'user_id': 1, 'daily_limit_hours': 3})
check('Set time limit', code == 200)

print("\n-- Child screens --")
for label, path in [
    ('Child dashboard (enriched)', '/api/dashboard/child_enriched?user_id=1'),
    ('User dashboard',             '/api/dashboard/user?user_id=1'),
    ('Games list',                 '/api/games'),
    ('Counselor history',          '/api/counselor/history?user_id=1'),
    ('Reflections',                '/api/child/reflections?user_id=1&days=14'),
    ('Sessions',                   '/api/sessions?user_id=1&limit=10'),
    ('Streak',                     '/api/child/streak?user_id=1'),
    ('Time limit',                 '/api/child/get_limit?user_id=1'),
    ('Anomalies',                  '/api/anomalies?user_id=1'),
    ('Consent status',             '/api/consent?user_id=1'),
]:
    code, j = call('GET', path, token=ctok)
    check(label, code == 200)

code, j = call('POST', '/api/counselor/chat', token=ctok, body={'user_id': 1, 'message': "i cant stop playing"})
check('Counselor chat (Mira)', code == 200 and j is not None)

code, j = call('POST', '/api/child/reflection', token=ctok,
               body={'user_id': 1, 'mood_rating': 3, 'sleep_quality': 3, 'energy_level': 3, 'note': 'e2e check'})
check('Daily check-in', code == 200)

print("\n-- Security guards --")
code, j = call('GET', '/api/dashboard/user?user_id=3', token=ctok)
check('cross-user blocked (child->3 = 403)', code == 403)
code, j = call('GET', '/api/dashboard/parent?user_id=1')
check('no-token blocked (401)', code == 401)
code, j = call('GET', '/api/nope')
check('unknown route -> JSON 404', code == 404)

passed = sum(results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
