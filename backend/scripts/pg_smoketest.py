"""
Postgres smoke test — exercises the real DATABASE_URL code path end to end.

Run against a local Docker Postgres OR the live Render database:

    # local throwaway Postgres
    docker run -d --name gad-pg -p 5433:5432 \
        -e POSTGRES_DB=gaming_addiction -e POSTGRES_USER=gaming_app \
        -e POSTGRES_PASSWORD=dev postgres:16-alpine
    DATABASE_URL=postgresql://gaming_app:dev@localhost:5433/gaming_addiction \
        AUTH_ENFORCE=1 python scripts/pg_smoketest.py

It imports the app (which runs init_db against Postgres → creates the schema),
registers a child + parent via the login flow, and checks that token auth and
per-user authorization behave the same as on SQLite.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if not os.environ.get('DATABASE_URL'):
    print("Set DATABASE_URL to a Postgres instance first (see this file's docstring).")
    sys.exit(2)

import app as appmod          # importing runs init_db() against Postgres
from app import app, USE_POSTGRES, get_db, hash_pin

assert USE_POSTGRES, "DATABASE_URL is set but USE_POSTGRES is False — check the scheme"

# Seed two siblings under one parent PIN directly, the same way seed_demo does.
conn = get_db()
c = conn.cursor()
for uid, name, pin, page in [(101, 'PgKid', '4321', 12), (102, 'PgKid2', '8765', 9)]:
    c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, name, pin, parent_pin, pin_hash, parent_pin_hash, age) "
                  "VALUES (?,?,'','',?,?,?)", (uid, name, hash_pin(pin), hash_pin('1111'), page))
    else:
        c.execute("UPDATE users SET pin_hash=?, parent_pin_hash=?, pin='', parent_pin='' WHERE user_id=?",
                  (hash_pin(pin), hash_pin('1111'), uid))
conn.commit()
conn.close()

cl = app.test_client()
fails = []

def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)

print("Postgres smoke test:")
r = cl.post('/api/user/login', json={'pin': '4321', 'role': 'child'})
j = r.get_json()
check("child login 200 + token", r.status_code == 200 and bool(j.get('token')))
ctok = (j or {}).get('token')

r = cl.get('/api/dashboard/user?user_id=101')
check("no-token dashboard -> 401", r.status_code == 401)

r = cl.get('/api/dashboard/user?user_id=101', headers={'Authorization': f'Bearer {ctok}'})
check("own dashboard -> 200", r.status_code == 200)

r = cl.get('/api/dashboard/user?user_id=102', headers={'Authorization': f'Bearer {ctok}'})
check("cross-user (101->102) -> 403", r.status_code == 403)

r = cl.post('/api/user/login', json={'pin': '1111', 'role': 'parent'})
j = r.get_json()
kids = sorted(ch['user_id'] for ch in (j or {}).get('children', []))
check("parent sees both children", kids == [101, 102])
ptok = (j or {}).get('token')
for u in (101, 102):
    rr = cl.get(f'/api/dashboard/parent?user_id={u}', headers={'Authorization': f'Bearer {ptok}'})
    check(f"parent -> child {u} -> 200", rr.status_code == 200)

# A query that uses the SUBSTR-based hour/date logic, to prove it runs on PG too.
r = cl.get('/api/anomalies?user_id=101', headers={'Authorization': f'Bearer {ctok}'})
check("anomalies query (SUBSTR date logic) runs", r.status_code == 200)

print(f"\n{'ALL PASSED' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
