"""Pytest fixtures — PES Capstone PW26_SJ_05.

Runs the suite against an ISOLATED throwaway SQLite DB (never the real
gaming_addiction.db) seeded with deterministic data, so tests don't depend on
`seed_demo.py` having been run and never mutate real data. Auth runs in shadow
mode (AUTH_ENFORCE=0) for the smoke tests; the dedicated auth test flips it on.

The DB path + auth mode are set BEFORE importing app, because app.init_db()
runs at import time.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

# ── Isolate the database + auth mode BEFORE importing the app ──────────────
_TMP_DB = os.path.join(tempfile.gettempdir(), 'capstone_test.db')
for _ext in ('', '-wal', '-shm'):
    try:
        os.remove(_TMP_DB + _ext)
    except OSError:
        pass
os.environ['DATABASE_PATH'] = _TMP_DB
os.environ.setdefault('AUTH_ENFORCE', '0')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app as flask_app, get_db, insert_returning_id  # noqa: E402

FAMILY_CODE = 'TEST01'   # child PIN 1234 / parent PIN 0000 are seeded by init_db's default user


def _seed():
    """Give the default user (user_id=1, from init_db) a family code + a completed
    session with a prediction and an alert, so dashboards/feedback have real rows."""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET family_code=? WHERE user_id=1", (FAMILY_CODE,))

    now = datetime.now()
    start = (now - timedelta(hours=2)).isoformat()
    end   = (now - timedelta(hours=1)).isoformat()
    sid = insert_returning_id(
        conn,
        "INSERT INTO sessions (user_id, game_name, start_time, end_time, duration_seconds, "
        "final_risk_score, risk_category, confidence) VALUES (1,'BGMI',?,?,3600,0.55,'at_risk',0.8)",
        (start, end), pk='session_id')
    c.execute(
        "INSERT INTO predictions (session_id, behavior_score, chat_score, voice_score, "
        "final_risk_score, risk_category, confidence, timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (sid, 0.6, 0.3, 0.4, 0.55, 'at_risk', 0.8, end))
    c.execute(
        "INSERT INTO alerts (user_id, type, message, severity, read, created_at) "
        "VALUES (1,'risk','At-risk patterns detected for testing — score 55%.','medium',0,?)",
        (end,))
    conn.commit()
    conn.close()


@pytest.fixture(scope='session', autouse=True)
def _seed_db():
    _seed()
    yield


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c
