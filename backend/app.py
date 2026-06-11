"""
AI-Driven Gaming Addiction Detection & Parental Monitoring
Clean REST API Backend — PES University Capstone PW26_SJ_05
Team: Kaustubh Agarwal, Kanak Goyal, Khushee P Kiran, Vidisha Murali
"""

from flask import Flask, request, jsonify, g, has_request_context
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
from functools import wraps, lru_cache
import json
import os
import threading
import logging
import joblib
import re
import time
import hashlib
import hmac
import secrets
from math import ceil, floor

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import numpy as np
import pandas as pd

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

# Optional SHAP for per-prediction feature attribution (falls back to importances).
# Catch broad Exception, not just ImportError: a version-mismatched shap (e.g. built
# for NumPy 1.x running under NumPy 2.x) raises AttributeError on import — we must
# degrade gracefully rather than crash the whole API at startup.
try:
    import shap
    SHAP_AVAILABLE = True
except Exception:
    SHAP_AVAILABLE = False

# Optional rate-limiting — gracefully disabled if Flask-Limiter not installed
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address as _get_ip
    _limiter_real = True
except ImportError:
    _limiter_real = False

# Firebase Admin SDK is imported LAZILY (see _ensure_firebase) — it pulls in grpc, which
# is memory-heavy, and importing it at boot can OOM the 512 MB free tier. Nothing is loaded
# until the first push actually fires; until then alerts are delivered by polling.

# ─────────────────────────── APP SETUP ───────────────────────────

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
# Largest legitimate upload is a ~10s voice segment (~320 KB WAV). 16 MB caps any
# runaway/abusive body well before it can pressure the free tier's 512 MB RAM.
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Behind Render's proxy the socket peer is the proxy, not the caller — without this
# EVERY user shares one rate-limit bucket (e.g. ALL parents worldwide share login's
# 10/min), so normal polling traffic triggered 429s under modest load. ProxyFix
# restores the real client IP from X-Forwarded-For (1 trusted hop = Render's LB).
# Set TRUST_PROXY=0 only if deploying without a reverse proxy.
if os.environ.get('TRUST_PROXY', '1') == '1':
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Postgres aggregates (AVG, ROUND, …) come back as Decimal, which Flask's default
# JSON encoder can't serialize. Teach jsonify to emit Decimal/numpy scalars as
# plain numbers so the same handlers work on both SQLite (float) and Postgres.
from decimal import Decimal as _Decimal
from flask.json.provider import DefaultJSONProvider as _DefaultJSONProvider


class _NumericJSONProvider(_DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, _Decimal):
            return float(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


app.json = _NumericJSONProvider(app)

# Rate limiter — no-op wrapper when flask_limiter isn't installed
if _limiter_real:
    # storage_uri set explicitly: single-instance deployment, in-memory is correct
    # (and silences the production warning in the boot logs).
    limiter = Limiter(app=app, key_func=_get_ip, default_limits=["120 per minute"],
                      storage_uri="memory://")
else:
    class _NoopLimiter:
        def limit(self, *a, **kw):
            return lambda f: f
        def exempt(self, f):
            return f
    limiter = _NoopLimiter()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ─────────────────────────── AUTH / AUTHORIZATION ───────────────────────────
# Signed bearer tokens (HMAC via itsdangerous — ships with Flask, no extra dep).
# A token carries the caller's role, their own user_id, and the set of user_ids
# they're allowed to read (a parent → their children; a child → just themselves).
#
# Rollout is staged via AUTH_ENFORCE:
#   shadow (default, AUTH_ENFORCE=0) — verify tokens if present and LOG ownership
#       violations, but never reject. Lets existing clients keep working while the
#       apps are updated to send tokens.
#   enforce (AUTH_ENFORCE=1, set in production) — missing/invalid token → 401,
#       accessing someone else's data → 403.
AUTH_SECRET  = os.environ.get('AUTH_SECRET')
if not AUTH_SECRET:
    # Stable dev fallback so tokens survive a reload locally; production MUST set
    # AUTH_SECRET (a random value here would invalidate every token on restart).
    AUTH_SECRET = 'dev-insecure-secret-DO-NOT-USE-IN-PRODUCTION'
    logger.warning("AUTH_SECRET not set — using insecure dev fallback. Set AUTH_SECRET in production.")
AUTH_ENFORCE = os.environ.get('AUTH_ENFORCE', '0') == '1'
TOKEN_TTL    = int(os.environ.get('AUTH_TOKEN_TTL_SECONDS', str(30 * 24 * 3600)))  # 30 days
_token_signer = URLSafeTimedSerializer(AUTH_SECRET, salt='gad-auth-v1')

# PIN hashing. PINs are never stored in plaintext. We use a keyed HMAC (server-side
# pepper) rather than a per-row salted hash because parent_pin doubles as the family
# grouping key — siblings share one parent_pin and must hash to the SAME value so we
# can still group them with a single indexed lookup. A keyed deterministic hash gives
# that while keeping the DB un-reversible without the pepper. (4-digit PINs are
# low-entropy; the pepper defends a DB-only dump, and longer passcodes are recommended
# for real deployment.)
PIN_PEPPER = os.environ.get('PIN_PEPPER') or AUTH_SECRET


def hash_pin(pin: str) -> str:
    return hmac.new(PIN_PEPPER.encode(), str(pin).strip().encode(), hashlib.sha256).hexdigest()


def verify_pin(pin: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_pin(pin), stored_hash)


def mint_token(role: str, user_id: int, allowed_ids) -> str:
    """Issue a signed token for a freshly authenticated user."""
    return _token_signer.dumps({
        'role': role,
        'uid': int(user_id),
        'allowed': sorted({int(x) for x in allowed_ids}),
    })


def _read_token():
    """Parse + verify the Authorization: Bearer token. Returns claims dict or None.
       Raises SignatureExpired / BadSignature for present-but-invalid tokens."""
    hdr = request.headers.get('Authorization', '')
    if not hdr.lower().startswith('bearer '):
        return None
    tok = hdr[7:].strip()
    if not tok:
        return None
    return _token_signer.loads(tok, max_age=TOKEN_TTL)


def guard(target_uid=None):
    """Authenticate the caller and authorize access to target_uid's data.

    Call at the top of a protected handler:
        deny = guard(uid)
        if deny: return deny
    Returns a Flask (response, status) tuple to short-circuit, or None to proceed.
    Always sets g.auth to the verified claims (or None).
    """
    g.auth = None
    try:
        g.auth = _read_token()
    except SignatureExpired:
        if AUTH_ENFORCE:
            return jsonify({'success': False, 'message': 'Session expired — please log in again'}), 401
    except BadSignature:
        if AUTH_ENFORCE:
            return jsonify({'success': False, 'message': 'Invalid authentication token'}), 401

    if g.auth is None and AUTH_ENFORCE:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    if target_uid is not None:
        try:
            tid = int(target_uid)
        except (TypeError, ValueError):
            return (jsonify({'success': False, 'message': 'invalid user id'}), 400) if AUTH_ENFORCE else None
        allowed = (g.auth or {}).get('allowed', [])
        if g.auth is not None and tid not in allowed:
            if AUTH_ENFORCE:
                logger.warning("AUTHZ DENY: uid=%s tried target=%s allowed=%s",
                               g.auth.get('uid'), tid, allowed)
                return jsonify({'success': False, 'message': 'Not authorized for this user'}), 403
            logger.warning("AUTHZ(shadow): uid=%s would be denied target=%s allowed=%s",
                           g.auth.get('uid'), tid, allowed)
    return None


def guard_session(sid):
    """Authorize access to a session by looking up its owning user."""
    conn = get_db()
    row = conn.execute('SELECT user_id FROM sessions WHERE session_id=?', (sid,)).fetchone()
    conn.close()
    if not row:
        return (jsonify({'success': False, 'message': 'Session not found'}), 404) if AUTH_ENFORCE else None
    return guard(row['user_id'])


# Firebase push — credential resolved from (in order):
#   1) FIREBASE_KEY_JSON env var holding the whole service-account JSON (best for Render —
#      no file to mount), or
#   2) backend/firebase_key.json on disk (best for local/dev; gitignored).
# Until one is provided, push stays dormant and alerts are delivered by polling.
FIREBASE_KEY    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firebase_key.json')
_firebase_app   = None
_firebase_msg   = None     # firebase_admin.messaging module, imported on first use
_firebase_tried = False    # remember a failed/credential-less init so we don't retry per push


def _ensure_firebase() -> bool:
    """Import + initialise the Firebase Admin SDK on FIRST use (not at boot — grpc is
    memory-heavy and OOMs the free tier). Returns True if push is usable."""
    global _firebase_app, _firebase_msg, _firebase_tried
    if _firebase_app is not None:
        return True
    if _firebase_tried:
        return False
    _firebase_tried = True
    try:
        import firebase_admin                                   # heavy import, deferred
        from firebase_admin import credentials as fb_creds
        from firebase_admin import messaging as fb_messaging
        cred     = None
        key_json = os.environ.get('FIREBASE_KEY_JSON', '').strip()
        if key_json:
            cred = fb_creds.Certificate(json.loads(key_json))
        elif os.path.exists(FIREBASE_KEY):
            cred = fb_creds.Certificate(FIREBASE_KEY)
        if cred is None:
            logging.getLogger(__name__).info("Firebase credential not set — push disabled "
                                             "(polling still delivers alerts)")
            return False
        _firebase_app = firebase_admin.initialize_app(cred)
        _firebase_msg = fb_messaging
        logging.getLogger(__name__).info("Firebase Admin SDK initialised (lazy)")
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Firebase init failed: {exc}")
        return False

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
# Env-overridable so the test suite can point at an isolated throwaway DB
# (DATABASE_PATH) instead of the real gaming_addiction.db. Unset in production.
DATABASE    = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'gaming_addiction.db'))
MODEL_DIR   = os.path.join(BASE_DIR, 'models')
AUDIO_DIR   = os.path.join(BASE_DIR, 'audio_uploads')
os.makedirs(AUDIO_DIR, exist_ok=True)

# ──────────────────── DB DIALECT (SQLite ⇆ Postgres) ─────────────────────
# Local/dev uses the SQLite file; production sets DATABASE_URL to a Postgres
# instance (Render wires this automatically). All SQL is written in the common
# subset (?-placeholders, SUBSTR for date parts, no GROUP_CONCAT/strftime), so
# the same statements run on both — only placeholder style, the auto-increment
# PK type, and a couple of DDL niceties differ, handled below.
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL.startswith('postgres://'):          # Render gives postgres://; psycopg2 prefers postgresql://
    DATABASE_URL = 'postgresql://' + DATABASE_URL[len('postgres://'):]
USE_POSTGRES = DATABASE_URL.startswith('postgresql')
if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool as _pg_pool_mod
    from psycopg2 import extensions as _pg_ext
    # Return SQL NUMERIC/DECIMAL as Python float (not Decimal), so arithmetic and JSON
    # behave exactly like SQLite's REAL. Without this, Postgres aggregates (SUM/AVG/…)
    # come back as Decimal and mixing them with floats raises TypeError (e.g. the
    # anomaly z-score: Decimal - float).
    _DEC2FLOAT = _pg_ext.new_type(
        _pg_ext.DECIMAL.values, 'DEC2FLOAT',
        lambda v, _cur: float(v) if v is not None else None)
    _pg_ext.register_type(_DEC2FLOAT)


def _to_pg(sql: str) -> str:
    """Translate our SQLite-style SQL to psycopg2: escape literal % then map ? → %s."""
    return sql.replace('%', '%%').replace('?', '%s')


class _PgCursor:
    """Wraps a psycopg2 RealDictCursor to behave like the sqlite3 cursor we use."""
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        self._cur.execute(_to_pg(sql), params)
        return self

    def executescript(self, sql):
        self._cur.execute(sql)        # psycopg2 runs multiple ;-separated statements
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return None                   # use insert_returning_id() on Postgres

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()


class _PgConnection:
    """Wraps a psycopg2 connection to mirror the sqlite3.Connection surface we use
       (conn.execute(...), conn.cursor(), commit/rollback/close), with dict rows.
       close() RETURNS the raw connection to the pool (idempotently — handlers close
       explicitly and the request teardown closes again as a safety net)."""
    def __init__(self, raw):
        self._raw = raw
        self._closed = False

    def cursor(self):
        return _PgCursor(self._raw.cursor())

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        _pg_release(self._raw)


# ── Postgres connection pool ────────────────────────────────────────────────
# Opening a fresh TLS connection to Neon per request (often 2-4 per request across
# helpers) was the main thing that buckled under load: each one costs several
# cross-region round trips of handshake, and Neon's serverless tier also drops idle
# connections when it scales to zero. The pool reuses warm connections; every borrow
# is validated with a 1-round-trip probe so a connection Neon silently killed is
# discarded and replaced instead of failing the request.
_PG_POOL      = None
_PG_POOL_LOCK = threading.Lock()
PG_POOL_MAX   = int(os.environ.get('PG_POOL_MAX', '10'))   # > gunicorn threads (8) + slack


def _pg_pool():
    global _PG_POOL
    if _PG_POOL is None:
        with _PG_POOL_LOCK:
            if _PG_POOL is None:
                _PG_POOL = _pg_pool_mod.ThreadedConnectionPool(
                    0, PG_POOL_MAX, DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    connect_timeout=10,
                    # TCP keepalives so long-idle pooled connections are noticed dead
                    # quickly rather than hanging a request on first reuse.
                    keepalives=1, keepalives_idle=30,
                    keepalives_interval=10, keepalives_count=3)
    return _PG_POOL


def _pg_acquire():
    """Borrow a VALIDATED connection. Retries with backoff cover both a momentarily
    exhausted pool and a Neon instance waking from scale-to-zero."""
    last_err = None
    for attempt in range(4):
        try:
            raw = _pg_pool().getconn()
        except Exception as e:                       # pool exhausted or connect refused
            last_err = e
            time.sleep(0.3 * (attempt + 1))
            continue
        try:
            if raw.closed:
                raise psycopg2.OperationalError('pooled connection was closed')
            cur = raw.cursor()
            cur.execute('SELECT 1')
            cur.fetchone()
            cur.close()
            raw.rollback()                           # clear the probe's transaction
            return raw
        except Exception as e:                       # stale/killed connection — replace it
            last_err = e
            try:
                _pg_pool().putconn(raw, close=True)
            except Exception:
                pass
            time.sleep(0.3 * (attempt + 1))          # also paces a waking Neon
    raise last_err


def _pg_release(raw):
    """Return a connection to the pool clean; a broken one is closed, not pooled."""
    try:
        raw.rollback()                               # drop any uncommitted state
        _pg_pool().putconn(raw)
    except Exception:
        try:
            _pg_pool().putconn(raw, close=True)
        except Exception:
            try:
                raw.close()
            except Exception:
                pass


def add_column(c, table, name, decl):
    """Idempotent ADD COLUMN that works on both engines (SQLite lacks IF NOT EXISTS)."""
    if USE_POSTGRES:
        c.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {decl}')
    else:
        try:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')
        except Exception:
            pass


def insert_returning_id(conn, sql, params, pk='id'):
    """INSERT and return the new row's auto-increment id, dialect-agnostically."""
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute(sql.rstrip().rstrip(';') + f' RETURNING {pk}', params)
        row = c.fetchone()
        return row[pk] if row else None
    c.execute(sql, params)
    return c.lastrowid

# ─────────────────────────── ML MODELS ───────────────────────────

behavior_model      = None   # RandomForest — used for predictions, SHAP, importances
behavior_calibrated = None   # optional isotonic calibrator over the RF — served probability only
chat_model       = None
voice_model      = None
tfidf_vectorizer = None
feature_scaler   = None

BEHAVIORAL_FEATURES = [
    'daily_play_time_hours', 'weekly_play_time_hours', 'sessions_per_day',
    'avg_session_duration_min', 'late_night_play_ratio', 'days_played_per_week',
    'longest_play_streak_days', 'binge_sessions_per_week',
    'avg_break_between_sessions_min', 'rapid_relogin_ratio',
    'urge_to_continue_score', 'loss_of_time_awareness_score',
    'control_loss_score', 'craving_score', 'tolerance_score',
    'missed_sleep_days_per_week', 'fatigue_after_play_score',
    'routine_disruption_score', 'neglect_responsibilities_score',
    'gaming_priority_score',
]

FEATURE_LABELS = {
    'daily_play_time_hours':           'Daily play time',
    'weekly_play_time_hours':          'Weekly play time',
    'sessions_per_day':                'Sessions per day',
    'avg_session_duration_min':        'Session duration',
    'late_night_play_ratio':           'Late night gaming',
    'days_played_per_week':            'Days played / week',
    'longest_play_streak_days':        'Play streak',
    'binge_sessions_per_week':         'Binge sessions',
    'avg_break_between_sessions_min':  'Short breaks',
    'rapid_relogin_ratio':             'Rapid re-login',
    'urge_to_continue_score':          'Urge to continue',
    'loss_of_time_awareness_score':    'Time awareness loss',
    'control_loss_score':              'Loss of control',
    'craving_score':                   'Gaming cravings',
    'tolerance_score':                 'Tolerance buildup',
    'missed_sleep_days_per_week':      'Sleep disruption',
    'fatigue_after_play_score':        'Post-play fatigue',
    'routine_disruption_score':        'Routine disruption',
    'neglect_responsibilities_score':  'Neglecting duties',
    'gaming_priority_score':           'Gaming over priorities',
}

# This is a wellbeing SCREENING tool, NOT a clinical diagnosis. Internal category
# keys (casual/at_risk/addicted) are kept for storage/compat; these are the
# non-clinical words shown to families, plus a disclaimer carried in responses.
RISK_DISPLAY = {
    'casual':   'Low concern',
    'at_risk':  'Some concern',
    'addicted': 'High concern',
}
SCREENING_DISCLAIMER = ("Wellbeing screening indicator based on gaming patterns — "
                        "not a medical or clinical diagnosis.")

# Risk-band cutoffs on the 0..1 fused score. These are clinically-motivated PRIORS
# (roughly even tertiles), NOT thresholds fitted to labelled outcomes — there is no
# real labelled data yet. They live here (one source of truth) so serving and every
# dashboard aggregate agree, and so the model card can report them transparently.
RISK_T1 = 0.33   # below → casual (low concern)
RISK_T2 = 0.67   # below → at_risk (some concern); at/above → addicted (high concern)

# Per-message chat-toxicity alert cutoffs. Deliberately high: on a realistic
# imbalanced stream the chat model's precision at 0.5 is poor (~0.20 — many false
# alarms), so we only raise a parent-facing alert when we're quite confident. This
# trades a little recall for far fewer false accusations of normal gaming chat.
CHAT_ALERT_T      = 0.75   # at/above → raise a toxicity alert
CHAT_ALERT_HIGH_T = 0.85   # at/above → mark that alert 'high' severity (else 'medium')

# Tamper watchdog: child app heartbeats ~every 5 min; if the server hasn't heard from it
# for this long, flag it to the parent (uninstalled / force-stopped / killed / offline).
HEARTBEAT_SILENT_MIN = 15
# Quiet hours (child-local): a phone that's silent overnight is almost always just off or
# asleep, not a tamper. Suppress the silence alert during this window to cut false alarms;
# it still fires in the morning if the app is genuinely gone. Needs the device tz offset.
HEARTBEAT_QUIET_START = 22   # 22:00 inclusive
HEARTBEAT_QUIET_END   = 7    # 07:00 exclusive


def risk_category(score: float) -> str:
    """Map a fused 0..1 risk score to its band using the shared cutoffs."""
    return 'casual' if score < RISK_T1 else ('at_risk' if score < RISK_T2 else 'addicted')


# ── Child-local time helpers ───────────────────────────────────────────────
# All timestamps are stored in the SERVER's local clock (datetime.now()). In production
# the server runs in UTC while the child's phone is e.g. IST (+5:30), so any hour-of-day
# logic (late-night play, sleep impact) computed on the raw stored hour would be shifted
# by the timezone gap: a 23:00 IST session is stored as 17:30 and wrongly read as evening.
# The child app reports its UTC offset with every heartbeat (users.tz_offset_min); these
# helpers translate stored times into the CHILD's wall clock before judging "late night".

def _parse_ts(ts):
    """Parse a stored timestamp string defensively (isoformat or 'YYYY-MM-DD HH:MM:SS')."""
    return datetime.fromisoformat(str(ts).replace(' ', 'T').split('+')[0].split('Z')[0])


def _tz_shift_min(c, user_id) -> int:
    """Minutes to ADD to a stored (server-local) timestamp to read it in the child's
    local time: child_utc_offset − server_utc_offset. 0 when the child's offset is
    unknown (old app, never heartbeated) or server and child share a timezone."""
    try:
        c.execute('SELECT tz_offset_min FROM users WHERE user_id=?', (user_id,))
        row = c.fetchone()
        tz = row['tz_offset_min'] if row else None
        if tz is None:
            return 0
        server_off = int(round((datetime.now() - datetime.utcnow()).total_seconds() / 60))
        return int(tz) - server_off
    except Exception:
        return 0


def _is_late_night(dt, shift_min: int = 0) -> bool:
    """22:00–06:00 in the CHILD's local time (stored time + tz shift)."""
    h = (dt + timedelta(minutes=shift_min)).hour
    return h >= 22 or h < 6


def load_models():
    global behavior_model, behavior_calibrated, chat_model, voice_model, tfidf_vectorizer, feature_scaler
    mapping = {
        'behavior_model':      'behavior_model.pkl',
        'behavior_calibrated': 'behavior_calibrated.pkl',  # optional; falls back to RF if absent
        'chat_model':          'chat_model.pkl',
        'voice_model':         'voice_model.pkl',
        'tfidf_vectorizer':    'tfidf_vectorizer.pkl',
        'feature_scaler':      'feature_scaler.pkl',
    }
    for var_name, filename in mapping.items():
        path = os.path.join(MODEL_DIR, filename)
        if os.path.exists(path):
            try:
                obj = joblib.load(path)
                globals()[var_name] = obj
                logger.info(f"Loaded {var_name} ({type(obj).__name__})")
            except Exception as e:
                logger.warning(f"Could not load {var_name}: {e}")
        else:
            logger.warning(f"Model file missing: {path}")


load_models()

# Load model metadata saved by retrain_models.py
MODEL_METADATA: dict = {}
_meta_path = os.path.join(MODEL_DIR, 'model_metadata.json')
if os.path.exists(_meta_path):
    try:
        with open(_meta_path) as _f:
            MODEL_METADATA = json.load(_f)
        logger.info(f"Model metadata loaded (trained {MODEL_METADATA.get('trained_at', 'unknown')})")
    except Exception:
        pass

# ─────────────────────────── DATABASE ────────────────────────────

def _open_db():
    if USE_POSTGRES:
        # Pooled + validated borrow (see _pg_acquire): reuses warm connections instead
        # of a fresh TLS handshake per request, and transparently replaces connections
        # Neon killed while scaled to zero.
        return _PgConnection(_pg_acquire())
    conn = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db():
    """Open a DB connection. Within a request, register it so it's ALWAYS closed at
    request teardown — even if a handler raises before its explicit conn.close().
    Prevents connection leaks that would exhaust Postgres's limited connection pool."""
    conn = _open_db()
    if has_request_context():
        try:
            if not hasattr(g, '_db_conns'):
                g._db_conns = []
            g._db_conns.append(conn)
        except Exception:
            pass
    return conn


@app.teardown_appcontext
def _close_request_dbs(exc):
    """Close any connections opened during the request (idempotent — handlers may
    have already closed them explicitly)."""
    for conn in getattr(g, '_db_conns', []):
        try:
            conn.close()
        except Exception:
            pass


@app.errorhandler(Exception)
def _json_errors(e):
    """Always return JSON (never an HTML error page) so the mobile clients can parse
    every response. HTTP errors keep their status; anything else is a logged 500."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({'success': False, 'message': e.description}), e.code
    logger.exception("Unhandled error on %s", request.path)
    return jsonify({'success': False, 'message': 'Internal server error'}), 500


def init_db():
    conn = get_db()
    c = conn.cursor()
    _ddl = '''
        CREATE TABLE IF NOT EXISTS users (
            user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL DEFAULT 'Player',
            pin       TEXT    NOT NULL DEFAULT '1234',
            parent_pin TEXT   NOT NULL DEFAULT '0000',
            age       INTEGER DEFAULT 15,
            created_at TEXT   DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER DEFAULT 1,
            game_name        TEXT    NOT NULL DEFAULT 'Unknown',
            start_time       TEXT    NOT NULL,
            end_time         TEXT,
            duration_seconds INTEGER DEFAULT 0,
            final_risk_score REAL,
            risk_category    TEXT,
            confidence       REAL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS behavioral_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            daily_play_time_hours REAL DEFAULT 0,
            weekly_play_time_hours REAL DEFAULT 0,
            sessions_per_day REAL DEFAULT 0,
            avg_session_duration_min REAL DEFAULT 0,
            late_night_play_ratio REAL DEFAULT 0,
            days_played_per_week REAL DEFAULT 0,
            longest_play_streak_days REAL DEFAULT 0,
            binge_sessions_per_week REAL DEFAULT 0,
            avg_break_between_sessions_min REAL DEFAULT 0,
            rapid_relogin_ratio REAL DEFAULT 0,
            urge_to_continue_score REAL DEFAULT 0,
            loss_of_time_awareness_score REAL DEFAULT 0,
            control_loss_score REAL DEFAULT 0,
            craving_score REAL DEFAULT 0,
            tolerance_score REAL DEFAULT 0,
            missed_sleep_days_per_week REAL DEFAULT 0,
            fatigue_after_play_score REAL DEFAULT 0,
            routine_disruption_score REAL DEFAULT 0,
            neglect_responsibilities_score REAL DEFAULT 0,
            gaming_priority_score REAL DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            message    TEXT    NOT NULL,
            source     TEXT    DEFAULT 'ocr',
            confidence REAL    DEFAULT 0.0,
            timestamp  TEXT    DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS voice_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            emotion     TEXT    DEFAULT 'neutral',
            intensity   REAL    DEFAULT 0.0,
            duration_s  REAL    DEFAULT 0.0,
            audio_file  TEXT,
            timestamp   TEXT    DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            behavior_score  REAL    DEFAULT 0,
            chat_score      REAL    DEFAULT 0,
            voice_score     REAL    DEFAULT 0,
            final_risk_score REAL   DEFAULT 0,
            risk_category   TEXT    DEFAULT 'casual',
            confidence      REAL    DEFAULT 0,
            timestamp       TEXT    DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            type        TEXT    DEFAULT 'risk',
            message     TEXT    NOT NULL,
            severity    TEXT    DEFAULT 'medium',
            read        INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS screen_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            event_type TEXT    NOT NULL,
            timestamp  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notification_events (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            INTEGER NOT NULL,
            package_name       TEXT,
            game_name          TEXT,
            notification_title TEXT,
            timestamp          TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS streaks (
            user_id            INTEGER PRIMARY KEY,
            current_streak     INTEGER DEFAULT 0,
            longest_streak     INTEGER DEFAULT 0,
            last_healthy_date  TEXT,
            total_healthy_days INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS time_limits (
            user_id              INTEGER PRIMARY KEY,
            daily_limit_hours    REAL    DEFAULT 0,
            set_by_parent        INTEGER DEFAULT 0,
            updated_at           TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reflections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            mood_rating     INTEGER,
            sleep_quality   INTEGER,
            energy_level    INTEGER,
            note            TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS counselor_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS anomalies (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            kind          TEXT,
            severity      TEXT,
            message       TEXT,
            z_score       REAL,
            detected_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved      INTEGER DEFAULT 0
        );

        -- Parent verdict on the model's output ("was this right?"). The only source of
        -- REAL labels in the system — every other label is synthetic — so this is what a
        -- future retrain/threshold-tune should learn from. We snapshot the model's
        -- category + score at feedback time so each label stays meaningful even as the
        -- model changes later.
        CREATE TABLE IF NOT EXISTS feedback (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,       -- the child the feedback is about
            alert_id      INTEGER DEFAULT NULL,   -- alert this responds to (optional)
            prediction_id INTEGER DEFAULT NULL,   -- prediction snapshot (optional)
            label         TEXT    NOT NULL,       -- accurate | false_alarm | too_sensitive | too_late
            risk_category TEXT    DEFAULT NULL,   -- model category at feedback time
            risk_score    REAL    DEFAULT NULL,   -- model fused score at feedback time
            note          TEXT    DEFAULT NULL,   -- optional free text
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- Parent -> child nudges: a one-off message the parent (or the system, on toxic
        -- chat) pushes to the child's phone, shown as a notification. The child app polls
        -- for undelivered ones. kind = parent | language | break.
        CREATE TABLE IF NOT EXISTS child_nudges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            message     TEXT    NOT NULL,
            kind        TEXT    DEFAULT 'parent',
            delivered   INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- One row per guardian DEVICE (mum's phone, dad's phone, ...). Keyed by family so
        -- a single alert can push to every guardian, not just the last one who logged in.
        CREATE TABLE IF NOT EXISTS guardian_devices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            family_code TEXT    NOT NULL,
            fcm_token   TEXT    NOT NULL UNIQUE,
            updated_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        );
    '''
    if USE_POSTGRES:
        # Postgres dialect: SERIAL auto-increment, and a text-typed default for the
        # ISO timestamp columns (CURRENT_TIMESTAMP is timestamptz, can't default a TEXT col).
        _ddl = _ddl.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY') \
                   .replace('CURRENT_TIMESTAMP', '(now())::text')
    c.executescript(_ddl)

    if USE_POSTGRES:
        # Our score columns are REAL (double precision), but Postgres only ships
        # ROUND(numeric, int) — not ROUND(double precision, int). Add that overload
        # once (returning float, not Decimal) so every ROUND(...) call site just works.
        c.executescript('''
            CREATE OR REPLACE FUNCTION round(double precision, integer)
            RETURNS double precision AS $fn$
                SELECT round($1::numeric, $2)::double precision
            $fn$ LANGUAGE sql IMMUTABLE;
        ''')

    # Columns added after the original schema shipped — idempotent on both engines.
    add_column(c, 'users', 'child_user_id',   'INTEGER DEFAULT NULL')   # legacy multi-child field
    add_column(c, 'users', 'fcm_token',       'TEXT DEFAULT NULL')      # FCM push token
    add_column(c, 'users', 'parent_id',       'INTEGER DEFAULT NULL')   # multi-child support
    add_column(c, 'users', 'pin_hash',        'TEXT DEFAULT NULL')      # keyed-hash credentials
    add_column(c, 'users', 'parent_pin_hash', 'TEXT DEFAULT NULL')
    add_column(c, 'users', 'consent_given_at',  'TEXT DEFAULT NULL')    # parental monitoring consent
    add_column(c, 'users', 'consent_version',   'TEXT DEFAULT NULL')
    # Unique per-family code. NULL on legacy/seed rows (parent logs in with PIN only);
    # new families get a generated code so two families sharing a parent PIN can't
    # collide — the parent logs in with code + PIN.
    add_column(c, 'users', 'family_code',       'TEXT DEFAULT NULL')
    # Tamper/uninstall detection: the child app heartbeats periodically; the server flags a
    # sustained silence (uninstalled / force-stopped / killed / offline) to the parent.
    add_column(c, 'users', 'last_seen',         'TEXT DEFAULT NULL')      # last child heartbeat (ISO)
    add_column(c, 'users', 'offline_alerted',   'INTEGER DEFAULT 0')      # one alert per outage
    add_column(c, 'users', 'tz_offset_min',     'INTEGER DEFAULT NULL')   # child device UTC offset (min)
    add_column(c, 'users', 'device_admin_active', 'INTEGER DEFAULT NULL')  # 1/0: instant-uninstall protection on?

    # Which signals actually fed each prediction. NULL on legacy rows ("unknown");
    # new predictions write explicit 1/0 so the UI can distinguish "captured and
    # clean (0%)" from "this game produced no chat/voice at all".
    add_column(c, 'predictions', 'behavior_present', 'INTEGER DEFAULT NULL')
    add_column(c, 'predictions', 'chat_present',     'INTEGER DEFAULT NULL')
    add_column(c, 'predictions', 'voice_present',    'INTEGER DEFAULT NULL')

    # Indexes on the hot query paths (filtering by user/session/time). Keeps the
    # dashboard + feature computation fast as session history grows. IF NOT EXISTS
    # works on both SQLite and Postgres.
    c.executescript('''
        CREATE INDEX IF NOT EXISTS idx_sessions_user        ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_start       ON sessions(start_time);
        CREATE INDEX IF NOT EXISTS idx_behavioral_session   ON behavioral_data(session_id);
        CREATE INDEX IF NOT EXISTS idx_chat_session         ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_voice_session        ON voice_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_predictions_session  ON predictions(session_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_user          ON alerts(user_id);
        CREATE INDEX IF NOT EXISTS idx_guardian_family      ON guardian_devices(family_code);
        CREATE INDEX IF NOT EXISTS idx_screen_user          ON screen_events(user_id);
        CREATE INDEX IF NOT EXISTS idx_notif_user           ON notification_events(user_id);
        CREATE INDEX IF NOT EXISTS idx_reflections_user     ON reflections(user_id);
        CREATE INDEX IF NOT EXISTS idx_counselor_user       ON counselor_messages(user_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_user        ON feedback(user_id);
        CREATE INDEX IF NOT EXISTS idx_nudges_user          ON child_nudges(user_id);
    ''')

    # Seed default user if none exists
    c.execute("SELECT COUNT(*) AS n FROM users")
    if c.fetchone()['n'] == 0:
        c.execute("INSERT INTO users (name, pin, parent_pin, age) VALUES ('Player','1234','0000',15)")

    # Backfill credential hashes for any row that still has plaintext but no hash,
    # then clear the plaintext (the columns are NOT NULL, so blank them) so the DB
    # never persists raw PINs going forward.
    for r in c.execute("SELECT user_id, pin, parent_pin, pin_hash, parent_pin_hash FROM users").fetchall():
        new_pin_hash    = r['pin_hash']        or (hash_pin(r['pin'])        if r['pin']        else None)
        new_parent_hash = r['parent_pin_hash'] or (hash_pin(r['parent_pin']) if r['parent_pin'] else None)
        if new_pin_hash != r['pin_hash'] or new_parent_hash != r['parent_pin_hash']:
            c.execute("UPDATE users SET pin_hash=?, parent_pin_hash=?, pin='', parent_pin='' WHERE user_id=?",
                      (new_pin_hash, new_parent_hash, r['user_id']))
    conn.commit()
    conn.close()
    logger.info("Database initialised")


init_db()

# ──────────────────────── TEXT HELPERS ───────────────────────────
# Preprocessing + lexicons live in text_utils so the backend and the model trainer
# share ONE definition (no train/serve skew). See backend/text_utils.py.
from text_utils import (SLANG_MAP, TOXIC_HIGH, TOXIC_MEDIUM, STOP_WORDS,
                        normalize_slang, clean_text, keyword_toxicity)
from behavior_features import derive_psychometrics

# ─────────────── GENRE RISK WEIGHTS ─────────────────────────────
# Battle Royale / FPS have higher addiction correlation (variable reward schedules,
# competitive pressure, no natural stopping points)
# Contextual risk multiplier applied to the final ensemble score. Direction is
# literature-motivated — competitive, real-time, social multiplayer genres (battle
# royale / FPS / MOBA) show higher problematic-use association than casual/puzzle
# games (e.g. Männikkö et al. 2017; genre–IGD correlations). The exact multipliers
# are a hand-set PRIOR, not fitted values, and should be calibrated with data. Keys
# must match the display names in Constants.PACKAGE_TO_GAME (Android) for a hit.
GENRE_RISK_WEIGHTS = {
    'Battle Royale': 1.25,
    'FPS':           1.20,
    'MOBA':          1.20,
    'MMO':           1.15,
    'RPG':           1.10,
    'Strategy':      0.90,
    'Sandbox':       0.95,
    'Casual':        0.70,
}

GAME_GENRES = {
    'PUBG Mobile':    'Battle Royale',
    'BGMI':           'Battle Royale',
    'Free Fire':      'Battle Royale',
    'Free Fire MAX':  'Battle Royale',
    'Fortnite':       'Battle Royale',
    'COD Mobile':     'FPS',
    'Warzone Mobile': 'FPS',
    'Valorant Mobile':'FPS',
    'Mobile Legends': 'MOBA',
    'Honor of Kings': 'MOBA',
    'Wild Rift':      'MOBA',
    'Genshin Impact': 'RPG',
    'Clash of Clans': 'Strategy',
    'Clash Royale':   'Strategy',
    'Roblox':         'Sandbox',
    'Minecraft':      'Sandbox',
    'Brawl Stars':    'Casual',
    'Among Us':       'Casual',
    'Stumble Guys':   'Casual',
    'Candy Crush':    'Casual',
    'Subway Surfers': 'Casual',
    'Temple Run 2':   'Casual',
    '8 Ball Pool':    'Casual',
    'Asphalt 9':      'Casual',
    'Pokemon Go':     'Casual',
}

# ─────────────── PEER COMPARISON DATA ───────────────────────────
# Weekly gaming hours → approximate percentile, used only to render a relatable
# "vs. peers" message on the parent dashboard. This is an ILLUSTRATIVE distribution
# hand-set from general screen-time ranges — NOT a validated population statistic.
# Do not present it as empirically derived; replace with real survey data if obtained.
_PEER_HOURS      = [2,  4,  6,  8,  10, 12, 14, 16, 18, 20, 25, 30, 40]
_PEER_PERCENTILE = [5, 10, 20, 30,  45, 55, 65, 73, 80, 85, 90, 95, 99]

def _explain_behavior(feat_dict: dict) -> list:
    """Return top-3 behavioral factors by contribution using RF feature importances."""
    if behavior_model is None or feature_scaler is None:
        return []
    try:
        importances = behavior_model.feature_importances_        # (n_features,)
        X_df     = pd.DataFrame([feat_dict])[BEHAVIORAL_FEATURES]
        X_scaled = feature_scaler.transform(X_df)[0]            # (n_features,)
        contribs = importances * np.abs(X_scaled)
        total    = contribs.sum() or 1.0
        top_idx  = np.argsort(contribs)[::-1][:3]
        return [
            {
                'feature':          BEHAVIORAL_FEATURES[i],
                'label':            FEATURE_LABELS.get(BEHAVIORAL_FEATURES[i], BEHAVIORAL_FEATURES[i]),
                'value':            round(float(feat_dict.get(BEHAVIORAL_FEATURES[i], 0)), 2),
                'contribution_pct': round(float(contribs[i] / total * 100), 1),
            }
            for i in top_idx
        ]
    except Exception as e:
        logger.debug(f"Explain error: {e}")
        return []


_behavior_explainer = None


def _get_behavior_explainer():
    """Lazily build (and cache) a SHAP TreeExplainer for the behaviour model."""
    global _behavior_explainer
    if _behavior_explainer is None and SHAP_AVAILABLE and behavior_model is not None:
        try:
            _behavior_explainer = shap.TreeExplainer(behavior_model)
        except Exception as e:
            logger.warning(f"SHAP explainer init failed: {e}")
            _behavior_explainer = False   # sentinel: don't retry every call
    return _behavior_explainer or None


def _shap_per_class(sv):
    """Normalise shap_values output (varies by SHAP version) to a list of
       per-class (n_features,) arrays for the single sample we passed in."""
    if isinstance(sv, list):                       # old multiclass: list[(n_samples, n_features)]
        return [np.asarray(a)[0] for a in sv]
    arr = np.asarray(sv)
    if arr.ndim == 3:                              # (n_samples, n_features, n_classes)
        return [arr[0, :, k] for k in range(arr.shape[2])]
    if arr.ndim == 2:                              # (n_samples, n_features) — binary/regression
        return [arr[0]]
    return [arr]


def _shap_explain_behavior(feat_dict: dict, top_n: int = 4) -> list:
    """Cached front-end for SHAP attribution. The parent dashboard polls every 30 s and
    re-explains the SAME latest behavioural row each time — on the free tier's ~0.1 CPU
    that repeated TreeExplainer pass was a real load multiplier. SHAP is deterministic
    for a given input, so memoising on the (rounded) feature vector is lossless."""
    key = tuple(round(float(feat_dict.get(f, 0) or 0), 4) for f in BEHAVIORAL_FEATURES)
    # Return deep copies so callers can't mutate the cached entries.
    return [dict(f) for f in _shap_explain_cached(key, top_n)]


@lru_cache(maxsize=256)
def _shap_explain_cached(key: tuple, top_n: int) -> tuple:
    return tuple(_shap_explain_impl(dict(zip(BEHAVIORAL_FEATURES, key)), top_n))


def _shap_explain_impl(feat_dict: dict, top_n: int = 4) -> list:
    """Per-prediction SHAP attribution: which behaviours pushed the risk up or down.
       Signed and local (unlike global feature importances). Falls back gracefully."""
    explainer = _get_behavior_explainer()
    if explainer is None or feature_scaler is None:
        return _explain_behavior(feat_dict)
    try:
        X_df     = pd.DataFrame([feat_dict])[BEHAVIORAL_FEATURES]
        X_scaled = feature_scaler.transform(X_df)
        arrs     = _shap_per_class(explainer.shap_values(X_scaled))
        n        = len(arrs)
        # Combine class contributions to mirror the b_score weighting
        # (at_risk × 0.5 + addicted × 1.0); for binary, the positive class.
        if n >= 3:
            contrib = arrs[1] * 0.5 + arrs[2] * 1.0
        elif n == 2:
            contrib = arrs[1]
        else:
            contrib = arrs[0]
        contrib = np.asarray(contrib, dtype=float)
        total   = float(np.abs(contrib).sum()) or 1.0
        order   = np.argsort(np.abs(contrib))[::-1][:top_n]
        return [
            {
                'feature':          BEHAVIORAL_FEATURES[i],
                'label':            FEATURE_LABELS.get(BEHAVIORAL_FEATURES[i], BEHAVIORAL_FEATURES[i]),
                'value':            round(float(feat_dict.get(BEHAVIORAL_FEATURES[i], 0)), 2),
                'impact':           round(float(contrib[i]), 4),
                'direction':        'raises' if contrib[i] > 0 else 'lowers',
                # backward-compatible magnitude (% of total absolute attribution)
                'contribution_pct': round(abs(float(contrib[i])) / total * 100, 1),
            }
            for i in order
        ]
    except Exception as e:
        logger.debug(f"SHAP explain error: {e}")
        return _explain_behavior(feat_dict)

# ──────────────────────── AUDIO HELPERS ──────────────────────────

VOICE_RISK = {'angry': 0.9, 'frustrated': 0.7, 'excited': 0.4, 'neutral': 0.1}

# At most N librosa analyses at once. Pitch (yin) + MFCC extraction allocates tens of
# MB per clip; the child app uploads a segment every ~10 s during play, and several
# arriving together (parallel uploads, offline-queue flushes) analysed concurrently
# across gunicorn threads spiked past the 512 MB instance limit and OOM-restarted the
# service (the "connection reset" Render health-check failures). Default 1 = fully
# serialise audio analysis: on the free tier's ~0.1 vCPU these are slow anyway, so
# serialising costs little latency and removes the memory-spike OOM entirely. Raise
# AUDIO_MAX_CONCURRENCY only on a larger instance.
_AUDIO_SLOTS = threading.BoundedSemaphore(int(os.environ.get('AUDIO_MAX_CONCURRENCY', '1')))


def extract_audio_features(audio_path):
    if not LIBROSA_AVAILABLE:
        return None, 0.0
    # Bounded wait: with analyses serialised, an unbounded acquire would let a burst of
    # voice uploads park most worker threads behind the semaphore and starve every other
    # request. Better to drop ONE segment (degrades to a low-confidence neutral event)
    # than to stall the whole API.
    if not _AUDIO_SLOTS.acquire(timeout=float(os.environ.get('AUDIO_QUEUE_TIMEOUT_S', '20'))):
        logger.warning("audio analysis queue full — segment skipped (degraded to neutral)")
        return None, 0.0
    try:
        return _extract_audio_features_inner(audio_path)
    finally:
        _AUDIO_SLOTS.release()


def _extract_audio_features_inner(audio_path):
    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=30)
        duration = len(y) / sr
        if len(y) < 512:
            return None, duration

        # Gain normalization: the voice model keys heavily on ABSOLUTE RMS energy,
        # so raw phone audio (variable mic gain / distance) classified inconsistently
        # — loud sessions read as all-"angry", and peak-normalization amplified quiet
        # clips into "angry" too. Instead, scale each clip to a fixed reference RMS so
        # the energy feature is gain-INVARIANT and emotion is driven by prosodic/
        # spectral shape (pitch, MFCC, energy variation). Target tuned on real device
        # clips to give a sensible neutral/frustrated/angry spread; override with
        # VOICE_RMS_TARGET. Set VOICE_DEBUG=1 to print the feature values used.
        rms_target = float(os.environ.get('VOICE_RMS_TARGET', '0.045'))
        cur_rms = float(np.sqrt(np.mean(y ** 2)))
        # Silence floor: a segment with essentially no speech must NOT be gain-boosted —
        # normalisation would amplify room/mic noise up to speech level and the model
        # would read the noise as an emotion. Treat it as "no voice" instead (the event
        # falls back to a low-confidence neutral). This is the cheap interim form of the
        # VAD step planned in Future Work.
        if cur_rms < float(os.environ.get('VOICE_SILENCE_RMS', '0.0015')):
            return None, duration
        y = y * (rms_target / cur_rms)

        mfcc      = np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13), axis=1).tolist()
        try:
            f0      = librosa.yin(y, fmin=50, fmax=500, sr=sr)
            f0v     = f0[f0 > 0]
            p_mean  = float(np.mean(f0v)) if len(f0v) > 0 else 0.0
            p_std   = float(np.std(f0v))  if len(f0v) > 0 else 0.0
        except Exception:
            p_mean, p_std = 150.0, 30.0
        rms   = librosa.feature.rms(y=y)[0]
        e_mean = float(np.mean(rms))
        e_std  = float(np.std(rms))

        if os.environ.get('VOICE_DEBUG', '').lower() in ('1', 'true', 'yes'):
            logger.info(f"[VOICE_DEBUG] rms_in={cur_rms:.4f} e_mean={e_mean:.4f} e_std={e_std:.4f} "
                        f"p_mean={p_mean:.1f} p_std={p_std:.1f} mfcc0={mfcc[0]:.1f}")

        return mfcc + [p_mean, p_std, e_mean, e_std], round(duration, 2)
    except Exception as e:
        logger.error(f"Audio feature error: {e}")
        return None, 0.0


def analyse_audio(audio_path):
    """Return (emotion_label, confidence, duration, probs_dict). probs_dict maps
       each acoustic class → probability (None when the model isn't used), so the
       caller can do distribution-aware fusion instead of relying on the argmax."""
    features, duration = extract_audio_features(audio_path)
    if features is not None and voice_model is not None:
        X      = np.array([features])
        pred   = voice_model.predict(X)[0]
        probs  = voice_model.predict_proba(X)[0]
        probs_dict = {str(c): float(p) for c, p in zip(voice_model.classes_, probs)}
        if os.environ.get('VOICE_DEBUG', '').lower() in ('1', 'true', 'yes'):
            logger.info(f"[VOICE_DEBUG] -> {pred}  probs={ {k: round(v,3) for k,v in probs_dict.items()} }")
        return str(pred), round(float(max(probs)), 3), duration, probs_dict
    if features is not None:
        e_mean = features[15]
        p_mean = features[13]
        if e_mean > 0.04 and p_mean > 250:
            return 'excited',    round(min(e_mean * 12, 0.95), 3), duration, None
        elif e_mean > 0.025:
            return 'frustrated', round(min(e_mean * 10, 0.85), 3), duration, None
        elif e_mean > 0.01:
            return 'neutral',    round(min(e_mean *  6, 0.70), 3), duration, None
    return 'neutral', 0.2, duration, None


# ── Multimodal emotion fusion (acoustic arousal × text valence) ───────────────
# The acoustic model reliably separates "animated" (angry/excited/frustrated) from
# "quiet" (neutral) — i.e. AROUSAL — but cannot judge VALENCE (positive vs negative),
# which is why loud-but-calm speech read as "angry". The spoken words supply valence.
# Fusing the two also softens the model's child-pitch bias: a child's naturally high
# voice may read as high-arousal, but neutral words then resolve to "excited", not
# "angry". Valence uses a lightweight gaming-aware lexicon (no extra dependencies).

_NEG_WORDS = {
    "stop", "annoying", "annoyed", "hate", "hates", "stupid", "idiot", "dumb", "noob",
    "trash", "garbage", "kill", "killed", "die", "death", "angry", "mad", "rage", "ugh",
    "damn", "shit", "fuck", "fucking", "crap", "loser", "cheater", "cheat", "lag", "lagging",
    "move", "come on", "comeon", "shut", "worst", "terrible", "awful", "scared", "afraid",
    "cry", "crying", "quit", "rage", "toxic", "report", "ban", "bad", "sucks", "suck",
}
_POS_WORDS = {
    "nice", "good", "great", "love", "lol", "lmao", "haha", "fun", "funny", "win", "won",
    "gg", "awesome", "cool", "thanks", "thank", "yay", "happy", "amazing", "best", "wow",
    "epic", "clutch", "victory", "lets go", "letsgo", "yes", "nice one", "well played", "wp",
}

def text_valence(text):
    """Valence in [-1, 1] from a short utterance; 0 when unknown/empty."""
    return _lexical_valence(text)[0]


def _lexical_valence(text):
    """Return (valence in [-1, 1], confidence in [0, 1]).
       Confidence rises with how many sentiment words matched (saturates ~3)."""
    if not text:
        return 0.0, 0.0
    # t is padded with spaces on both ends, so " w " matches a word at the start, middle
    # or end. (A bare " w" prefix test would wrongly match "win" inside "winter".)
    t   = " " + text.lower().strip() + " "
    pos = sum(1 for w in _POS_WORDS if (" " + w + " ") in t)
    neg = sum(1 for w in _NEG_WORDS if (" " + w + " ") in t)
    total = pos + neg
    if total == 0:
        return 0.0, 0.0
    return (pos - neg) / float(total), min(1.0, total / 3.0)


# Circumplex (valence, arousal) coordinates for the acoustic emotion classes.
# valence ∈ [-1, 1] (negative→positive), arousal ∈ [0, 1] (calm→animated).
_EMO_VA = {
    'angry':      (-0.8, 0.85),
    'frustrated': (-0.5, 0.45),
    'excited':    ( 0.6, 0.75),
    'neutral':    ( 0.0, 0.10),
}


def _acoustic_va(probs):
    """Expected (valence, arousal) from the acoustic class-probability dict."""
    if not probs:
        return None
    v = sum(p * _EMO_VA.get(c, (0.0, 0.0))[0] for c, p in probs.items())
    a = sum(p * _EMO_VA.get(c, (0.0, 0.0))[1] for c, p in probs.items())
    return v, a


def _label_from_va(v, a):
    """Nearest circumplex prototype to a (valence, arousal) point."""
    return min(_EMO_VA, key=lambda l: (v - _EMO_VA[l][0]) ** 2 + (a - _EMO_VA[l][1]) ** 2)


def _chat_toxicity(text):
    """Toxicity in [0,1] from the trained chat model (+ keyword fallback). Used as an
       extra, trained negative-valence signal in voice fusion — generalises beyond the
       hand-built lexicon for hostile speech the word list would miss."""
    if not text or not text.strip():
        return 0.0
    kw = keyword_toxicity(text)
    ml = 0.0
    if chat_model is not None and tfidf_vectorizer is not None:
        try:
            proba = chat_model.predict_proba(tfidf_vectorizer.transform([clean_text(text)]))[0]
            ml    = float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            pass
    return float(np.clip(max(kw, ml), 0, 1))


def fuse_emotion(acoustic_label, valence, probs=None, valence_conf=0.0, toxicity=0.0):
    """Fuse acoustic tone with lexical valence into an emotion label.

    Preferred path (probs given) — dimensional valence–arousal fusion:
      • Arousal comes from the acoustic distribution (what tone judges reliably).
      • Valence blends three signals: the spoken words via the lexicon (positive AND
        negative), the TRAINED chat-toxicity model (robust hostility detection beyond
        the word list → strong negative valence), and the acoustic distribution as a
        weak prior. Using the full acoustic distribution — not just the argmax class —
        keeps an *uncertain* read from over-committing to "angry".
    Fallback (no probs) — the original lexical-threshold rule, for wordless cases.
    """
    va = _acoustic_va(probs)
    if va is not None:
        v_ac, a_ac = va
        terms = [(0.4, v_ac)]                                   # acoustic valence prior
        if valence_conf > 0:
            terms.append((float(valence_conf), float(valence)))  # lexicon (pos + neg)
        if toxicity and toxicity > 0.15:
            terms.append((float(toxicity), -float(toxicity)))    # trained toxicity → negative
        wsum = sum(w for w, _ in terms)
        v = sum(w * x for w, x in terms) / wsum if wsum > 0 else v_ac
        return _label_from_va(v, a_ac)
    # ── fallback rule (no distribution available) ──
    arousal_high = bool(acoustic_label) and acoustic_label.lower() != "neutral"
    if valence <= -0.5:
        return "angry" if arousal_high else "frustrated"
    if valence <= -0.2:
        return "frustrated"
    if valence >= 0.2:
        return "excited"
    return "neutral"

# ──────────────────────── PREDICTION ENGINE ──────────────────────

def compute_behavioral_features(session_id: int) -> dict:
    """Calculate all 20 behavioural features from real session history + current session."""
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT user_id, start_time FROM sessions WHERE session_id=?', (session_id,))
    srow = c.fetchone()
    if not srow:
        conn.close()
        return {}

    user_id  = srow['user_id']
    start_dt = datetime.fromisoformat(srow['start_time'])
    elapsed  = max(1, (datetime.now() - start_dt).total_seconds())

    # Fetch past 30 days of sessions for this user, excluding the current one
    since_30d = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute('''SELECT start_time, end_time, duration_seconds
                 FROM sessions WHERE user_id=? AND start_time>=? AND session_id!=?
                 ORDER BY start_time DESC LIMIT 200''',
              (user_id, since_30d, session_id))
    past = [dict(r) for r in c.fetchall()]

    cur_hrs = elapsed / 3600.0
    today   = datetime.now().date()

    # --- Objective time features ---
    today_secs = sum((s['duration_seconds'] or 0) for s in past
                     if datetime.fromisoformat(s['start_time']).date() == today)
    daily_play_time = round(min(today_secs / 3600.0 + cur_hrs, 24), 4)

    week_cutoff = datetime.now() - timedelta(days=7)
    week_sess   = [s for s in past if datetime.fromisoformat(s['start_time']) >= week_cutoff]
    week_secs   = sum(s['duration_seconds'] or 0 for s in week_sess)
    weekly_play_time = round(min(week_secs / 3600.0 + cur_hrs, 168), 4)

    sessions_per_day = round((len(week_sess) + 1) / 7.0, 4)

    all_durs = [s['duration_seconds'] for s in past if s['duration_seconds']] + [int(elapsed)]
    avg_session_duration_min = round(float(np.mean(all_durs)) / 60.0, 2)

    # Judge "late night" on the CHILD's wall clock, not the server's — on a UTC cloud
    # host an IST child's 23:00 session is stored as 17:30 and would otherwise be missed
    # (and morning sessions wrongly flagged). This feature also drives the craving /
    # missed-sleep / fatigue psychometric proxies, so the shift matters for the model.
    tz_shift   = _tz_shift_min(c, user_id)
    all_starts = past + [{'start_time': srow['start_time']}]
    late_cnt   = sum(1 for s in all_starts
                     if _is_late_night(datetime.fromisoformat(s['start_time']), tz_shift))
    late_night_play_ratio = round(late_cnt / max(len(all_starts), 1), 4)

    played_dates = {datetime.fromisoformat(s['start_time']).date() for s in week_sess}
    played_dates.add(today)
    days_played_per_week = min(len(played_dates), 7)

    all_dates = sorted({datetime.fromisoformat(s['start_time']).date() for s in past} | {today})
    max_streak = streak = 1
    for i in range(1, len(all_dates)):
        if (all_dates[i] - all_dates[i - 1]).days == 1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1
    longest_play_streak_days = max_streak

    binge_week = sum(1 for s in week_sess if (s['duration_seconds'] or 0) >= 10800)
    if elapsed >= 10800:
        binge_week += 1
    binge_sessions_per_week = binge_week

    # Gaps between consecutive completed sessions
    ended = sorted([s for s in past if s['end_time'] and s['duration_seconds']],
                   key=lambda x: x['start_time'])
    breaks = []
    for i in range(len(ended) - 1):
        gap = (datetime.fromisoformat(ended[i + 1]['start_time'])
               - datetime.fromisoformat(ended[i]['end_time'])).total_seconds() / 60.0
        if 0 < gap < 1440:
            breaks.append(gap)
    avg_break = round(float(np.mean(breaks)) if breaks else 120.0, 2)
    rapid_relogin_ratio = round(
        min(sum(1 for b in breaks if b < 15) / max(len(breaks), 1), 1.0), 4
    ) if breaks else 0.0

    conn.close()

    # The 10 psychometric proxies are derived from the 10 objective features by the
    # SHARED derive_psychometrics() — the identical mapping the model is trained on
    # (ml/retrain_models.py), so there is NO train/serve skew. (Notification/screen-wake
    # data is still collected and used elsewhere — sleep-impact + late-night views — it
    # just no longer feeds the model's psychometric inputs in a way training never saw.)
    objective = {
        'daily_play_time_hours':          daily_play_time,
        'weekly_play_time_hours':         weekly_play_time,
        'sessions_per_day':               sessions_per_day,
        'avg_session_duration_min':       avg_session_duration_min,
        'late_night_play_ratio':          late_night_play_ratio,
        'days_played_per_week':           days_played_per_week,
        'longest_play_streak_days':       longest_play_streak_days,
        'binge_sessions_per_week':        binge_sessions_per_week,
        'avg_break_between_sessions_min': avg_break,
        'rapid_relogin_ratio':            rapid_relogin_ratio,
    }
    return {**objective, **derive_psychometrics(**objective)}


def run_prediction(session_id: int, explain: bool = True) -> dict:
    """Run 3-model ensemble prediction and persist result.

    explain=False skips the SHAP attribution (the heaviest, most memory-hungry step)
    for frequent live/intermediate predictions; the parent-facing "why this risk"
    factors are still computed on the session-end prediction. This keeps peak memory
    well under the free tier's 512 MB during an active session's burst of requests."""
    conn = get_db()
    c    = conn.cursor()

    # Count user sessions for observation-mode flag
    c.execute('SELECT user_id FROM sessions WHERE session_id=?', (session_id,))
    _sr  = c.fetchone()
    _uid = _sr['user_id'] if _sr else 1
    c.execute('SELECT COUNT(*) AS n FROM sessions WHERE user_id=?', (_uid,))
    total_sessions   = c.fetchone()['n']
    observation_mode = total_sessions < 3

    # Fetch latest behavioural row
    c.execute('SELECT * FROM behavioral_data WHERE session_id=? ORDER BY id DESC LIMIT 1', (session_id,))
    brow = c.fetchone()

    # Typed chat only for the chat-toxicity channel. Spoken words (source='voice_stt')
    # already feed the voice channel via valence fusion, so excluding them here avoids
    # double-counting the same utterance across two modalities. (Join in Python —
    # dialect-neutral vs GROUP_CONCAT/STRING_AGG.)
    c.execute("SELECT message FROM chat_messages WHERE session_id=? "
              "AND (source IS NULL OR source <> 'voice_stt')", (session_id,))
    chat_text = ' '.join(r['message'] for r in c.fetchall() if r['message'])

    # Fetch voice events
    c.execute('SELECT emotion, intensity, duration_s, audio_file FROM voice_events WHERE session_id=?', (session_id,))
    vrows = c.fetchall()
    conn.close()

    # ── Behaviour score ──────────────────────────────────────────
    b_score, b_conf, top_factors = 0.5, 0.5, []
    b_present = False
    if brow and behavior_model is not None:
        try:
            feat_dict = {f: float(brow[f] or 0) for f in BEHAVIORAL_FEATURES}
            X_df  = pd.DataFrame([feat_dict])[BEHAVIORAL_FEATURES]
            if feature_scaler is not None:
                X_arr = feature_scaler.transform(X_df)
            else:
                X_arr = X_df.values
            # Use the isotonic-calibrated probabilities for the served score when
            # available; the raw RF is the fallback (and still drives SHAP below).
            proba_model = behavior_calibrated if behavior_calibrated is not None else behavior_model
            probs     = proba_model.predict_proba(X_arr)[0]
            b_score   = float(probs[1] * 0.5 + probs[2] * 1.0) if len(probs) > 2 else float(probs[-1])
            b_conf    = float(max(probs))
            top_factors = _shap_explain_behavior(feat_dict) if explain else []
            b_present = True
        except Exception as e:
            logger.error(f"Behaviour prediction error: {e}")

    # ── Chat score ───────────────────────────────────────────────
    c_score, c_conf = 0.0, 0.5
    c_present = False
    if chat_text.strip() and chat_model is not None and tfidf_vectorizer is not None:
        try:
            vec      = tfidf_vectorizer.transform([clean_text(chat_text)])
            proba    = chat_model.predict_proba(vec)[0]
            # Class index 1 = toxic
            ml_score = float(proba[1]) if len(proba) > 1 else float(proba[0])
            kw_score = keyword_toxicity(chat_text)
            c_score  = float(np.clip(max(ml_score, kw_score), 0, 1))
            c_conf   = 0.85 if kw_score > 0.3 else round(float(max(proba)), 3)
            c_present = True
        except Exception as e:
            logger.error(f"Chat prediction error: {e}")

    # ── Voice score ──────────────────────────────────────────────
    v_score, v_conf = 0.0, 0.5
    v_present = False
    if vrows:
        try:
            all_probs = []
            if voice_model is not None and LIBROSA_AVAILABLE:
                for vr in vrows:
                    fpath = vr['audio_file']
                    if fpath:
                        fp = os.path.join(AUDIO_DIR, fpath)
                        if os.path.exists(fp):
                            feats, _ = extract_audio_features(fp)
                            if feats is not None:
                                all_probs.append(voice_model.predict_proba(np.array([feats]))[0])
            if all_probs:
                avg   = np.mean(all_probs, axis=0)
                cls   = list(voice_model.classes_)
                v_score = sum(avg[i] * VOICE_RISK.get(cls[i], 0.5) for i in range(len(cls)))
                v_score = float(np.clip(v_score, 0, 1))
                v_conf  = float(max(avg))
                v_present = True
            else:
                # Fallback: stored (fused) emotions × intensity — the normal path in
                # production, where raw audio is deleted after feature extraction.
                scores  = [VOICE_RISK.get(vr['emotion'], 0.5) * float(vr['intensity'] or 0.5) for vr in vrows]
                if scores:
                    v_score = float(np.clip(np.mean(scores), 0, 1))
                    v_present = True
        except Exception as e:
            logger.error(f"Voice prediction error: {e}")

    # ── Genre risk weighting ─────────────────────────────────────
    conn2 = get_db()
    c2 = conn2.cursor()
    c2.execute('SELECT game_name FROM sessions WHERE session_id=?', (session_id,))
    gname_row = c2.fetchone()
    conn2.close()
    genre_weight = 1.0
    game_genre   = 'Unknown'
    if gname_row:
        game_genre   = GAME_GENRES.get(gname_row['game_name'], 'Unknown')
        genre_weight = GENRE_RISK_WEIGHTS.get(game_genre, 1.0)

    # ── Availability-weighted ensemble ───────────────────────────
    # Base prior 40/30/30 (behaviour/chat/voice). Behaviour dominates because
    # DSM-5 Internet Gaming Disorder and ICD-11 Gaming Disorder are defined
    # behaviourally (impaired control, escalating priority, continuation despite
    # harm); chat and voice are secondary corroborating distress signals. This is a
    # clinically-motivated PRIOR, not an empirically-fitted weighting — it should be
    # calibrated against labelled outcomes via the active-learning loop.
    #
    # Weights are re-normalized over only the modalities that produced a score, so an
    # absent modality contributes nothing (previously a missing chat/voice injected a
    # placeholder value, adding a fake risk floor and capping behaviour-only sessions
    # below the "addicted" threshold).
    components = []
    if b_present: components.append((0.40, b_score, b_conf))
    if c_present: components.append((0.30, c_score, c_conf))
    if v_present: components.append((0.30, v_score, v_conf))
    if components:
        tw        = sum(w for w, _, _ in components)
        raw_final = sum(w * s for w, s, _ in components) / tw
        conf      = round(sum(w * cf for w, _, cf in components) / tw, 4)
    else:
        raw_final = 0.5   # no modality produced data
        conf      = 0.3
    final = float(np.clip(raw_final * genre_weight, 0, 1))
    cat   = risk_category(final)
    # Don't assert the highest-concern band on sparse data — a few sessions are
    # needed before a confident screening signal. Caps at "Some concern" early on.
    if observation_mode and cat == 'addicted':
        cat = 'at_risk'

    result = {
        'behavior_score':    round(b_score, 4),
        'chat_score':        round(c_score, 4),
        'voice_score':       round(v_score, 4),
        'final_risk_score':  round(final,   4),
        'risk_category':     cat,
        'risk_label':        RISK_DISPLAY.get(cat, cat),
        'disclaimer':        SCREENING_DISCLAIMER,
        'confidence':        conf,
        'observation_mode':  observation_mode,
        'sessions_analyzed': total_sessions,
        'top_factors':       top_factors,
        'game_genre':        game_genre,
        'genre_weight':      round(genre_weight, 2),
        # Which signals were actually captured for this session. A score of 0 with
        # present=False means "no data for this game" (e.g. a game with no text chat,
        # or a silent single-player session), NOT "captured and harmless".
        'modalities':        {'behavior': b_present, 'chat': c_present, 'voice': v_present},
    }

    conn = get_db()
    c    = conn.cursor()
    c.execute('''INSERT INTO predictions
                 (session_id, behavior_score, chat_score, voice_score,
                  final_risk_score, risk_category, confidence, timestamp,
                  behavior_present, chat_present, voice_present)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
              (session_id, result['behavior_score'], result['chat_score'],
               result['voice_score'], result['final_risk_score'],
               result['risk_category'], result['confidence'],
               datetime.now().isoformat(),
               1 if b_present else 0, 1 if c_present else 0, 1 if v_present else 0))
    c.execute('UPDATE sessions SET final_risk_score=?, risk_category=?, confidence=? WHERE session_id=?',
              (result['final_risk_score'], result['risk_category'], result['confidence'], session_id))
    conn.commit()
    conn.close()
    logger.info(f"[Session {session_id}] Prediction: {cat} ({final:.3f})")
    return result

# ──────────────────────── ALERT HELPERS ──────────────────────────

def _insert_alert(cursor, user_id, atype, message, severity):
    """Insert an alert with an EXPLICIT local timestamp. The created_at column DEFAULT
    differs by engine (SQLite's CURRENT_TIMESTAMP is UTC, Postgres' now() is
    server-local), which skewed alert ages/ordering against every other timestamp the
    app writes via datetime.now()."""
    cursor.execute('INSERT INTO alerts (user_id, type, message, severity, created_at) '
                   'VALUES (?,?,?,?,?)',
                   (user_id, atype, message, severity, datetime.now().isoformat()))


def _maybe_create_alert(cursor, user_id: int, prediction: dict):
    """Insert an alert row when risk is elevated or changes."""
    risk = prediction.get('risk_category', 'casual')
    score = prediction.get('final_risk_score', 0.0)
    if risk == 'addicted':
        _insert_alert(cursor, user_id, 'risk',
                      f'High addiction risk detected — score {score:.0%}. Immediate attention recommended.',
                      'high')
    elif risk == 'at_risk':
        _insert_alert(cursor, user_id, 'risk',
                      f'At-risk gaming patterns detected — score {score:.0%}. Monitor gaming time.',
                      'medium')


def _build_recommendations(risk_level: str) -> list:
    if risk_level == 'addicted':
        return [
            'Set strict daily limits (max 1 hour per day).',
            'Remove gaming devices from the bedroom.',
            'Schedule structured offline activities every day.',
            'Consider consulting a school counselor or therapist.',
            'Enable parental controls to enforce time limits.',
        ]
    elif risk_level == 'at_risk':
        return [
            'Discuss healthy gaming habits openly with your child.',
            'Agree on gaming time limits (1–2 hours per day).',
            'Ensure gaming does not interfere with sleep or study.',
            'Encourage physical activities and social hobbies.',
            'Monitor late-night sessions closely.',
        ]
    else:
        return [
            'Current gaming patterns look healthy — keep it up!',
            'Continue encouraging diverse offline activities.',
            'Maintain open conversations about gaming.',
            'Periodic check-ins to ensure continued balance.',
        ]

def _suggest_time_limit(weekly_hours: float, risk_level: str, age: int = 15) -> dict:
    """Suggest a personalised daily time limit based on child's baseline and risk level."""
    avg_daily = weekly_hours / 7.0
    if risk_level == 'addicted':
        suggested  = 1.0
        reason     = "High addiction risk — strict 1-hour daily limit recommended"
        urgency    = 'high'
    elif risk_level == 'at_risk':
        suggested  = min(avg_daily * 0.70, 2.0)
        reason     = f"At-risk pattern — reduce from {avg_daily:.1f}h to {suggested:.1f}h daily"
        urgency    = 'medium'
    else:
        cap        = 2.5 if age < 13 else 3.0
        suggested  = min(avg_daily, cap)
        reason     = "Healthy pattern — current balance looks good"
        urgency    = 'low'
    suggested = max(0.5, round(suggested * 2) / 2)   # round to nearest 0.5h
    return {
        'suggested_daily_hours':  suggested,
        'current_avg_daily_hours': round(avg_daily, 1),
        'reason':  reason,
        'urgency': urgency,
    }


def _peer_comparison(weekly_hours: float, age: int = 15) -> dict:
    """Return child's percentile rank vs peer group for weekly gaming hours."""
    pct = _PEER_PERCENTILE[-1]
    for i, h in enumerate(_PEER_HOURS):
        if weekly_hours <= h:
            if i == 0:
                pct = _PEER_PERCENTILE[0]
            else:
                frac = (weekly_hours - _PEER_HOURS[i-1]) / max(h - _PEER_HOURS[i-1], 0.01)
                pct  = int(_PEER_PERCENTILE[i-1] + frac * (_PEER_PERCENTILE[i] - _PEER_PERCENTILE[i-1]))
            break
    pct = min(pct, 99)
    if pct >= 90:
        level = 'very_high'
        msg   = f"Gaming {weekly_hours:.1f}h/week — more than {pct}% of peers. High-risk range."
    elif pct >= 70:
        level = 'high'
        msg   = f"Gaming {weekly_hours:.1f}h/week — more than {pct}% of peers. Worth monitoring."
    elif pct >= 40:
        level = 'average'
        msg   = f"Gaming {weekly_hours:.1f}h/week — typical for their age group."
    else:
        level = 'low'
        msg   = f"Gaming {weekly_hours:.1f}h/week — less than most peers. Healthy balance."
    return {'weekly_hours': round(weekly_hours, 1), 'percentile': pct, 'level': level, 'message': msg}


def _sleep_impact_analysis(user_id: int, conn) -> dict:
    """
    Correlate late-night device activity with sleep disruption.
    Uses screen_events (ground truth) when available; falls back to session timestamps.
    """
    c = conn.cursor()
    since = (datetime.now() - timedelta(days=30)).isoformat()
    # All hour-of-day judgements below use the CHILD's wall clock (stored server time
    # + tz shift) — otherwise a UTC host mislabels an IST child's whole night.
    tz_shift = _tz_shift_min(c, user_id)

    # Prefer screen_events — these fire even when no session is running
    c.execute('''SELECT COUNT(*) AS n FROM screen_events WHERE user_id=? AND timestamp>=?''',
              (user_id, since))
    has_screen_events = c.fetchone()['n'] > 0

    if has_screen_events:
        c.execute('''SELECT timestamp FROM screen_events
                     WHERE user_id=? AND event_type='screen_on' AND timestamp>=?''',
                  (user_id, since))
        wakes_by_day = {}
        for r in c.fetchall():
            try:
                dt = _parse_ts(r['timestamp']) + timedelta(minutes=tz_shift)
            except Exception:
                continue
            if dt.hour >= 22 or dt.hour < 6:
                d = dt.date().isoformat()
                wakes_by_day[d] = wakes_by_day.get(d, 0) + 1
        late_rows = [{'day': d, 'wakes': n} for d, n in sorted(wakes_by_day.items())]

        c.execute('''SELECT COUNT(DISTINCT SUBSTR(timestamp,1,10)) AS total
                     FROM screen_events WHERE user_id=? AND timestamp>=?''', (user_id, since))
        total_days = c.fetchone()['total'] or 1

        late_nights   = len(late_rows)
        total_wakes   = sum(r['wakes'] for r in late_rows)
        late_pct      = round(late_nights / total_days * 100, 1)
        disruption    = sum(1 for r in late_rows if r['wakes'] >= 3)
        source        = 'screen_events'
    else:
        # Fallback: session timestamps, bucketed per child-local day
        c.execute('''SELECT start_time FROM sessions WHERE user_id=? AND start_time>=?''',
                  (user_id, since))
        hours_by_day = {}
        for r in c.fetchall():
            try:
                dt = _parse_ts(r['start_time']) + timedelta(minutes=tz_shift)
            except Exception:
                continue
            d = dt.date().isoformat()
            lo, hi = hours_by_day.get(d, (dt.hour, dt.hour))
            hours_by_day[d] = (min(lo, dt.hour), max(hi, dt.hour))
        rows = [{'day': d, 'first_hour': lo, 'last_hour': hi}
                for d, (lo, hi) in sorted(hours_by_day.items())]
        if len(rows) < 3:
            return {'available': False, 'message': 'Not enough data yet for sleep analysis'}
        late_night_rows = [r for r in rows if r['last_hour'] >= 22 or r['last_hour'] < 4]
        late_nights     = len(late_night_rows)
        total_days      = len(rows)
        late_pct        = round(late_nights / total_days * 100, 1)
        disruption      = sum(1 for i in range(len(rows)-1)
                              if rows[i]['last_hour'] >= 22 and rows[i+1]['first_hour'] < 10)
        total_wakes     = late_nights
        source          = 'sessions'

    return {
        'available':             True,
        'late_night_sessions':   late_nights,
        'total_days_analyzed':   total_days,
        'late_night_percent':    late_pct,
        'sleep_disruption_days': disruption,
        'data_source':           source,
        'message': (
            f"{late_nights} of {total_days} days had late-night activity (after 10 PM). "
            + (f"Sleep disruption pattern detected on {disruption} days." if disruption > 0
               else "No clear sleep disruption detected.")
        )
    }


def _update_streak(user_id: int, weekly_hours: float, risk_level: str) -> dict:
    """Increment or reset child's healthy-day streak after each session end."""
    avg_daily  = weekly_hours / 7.0
    is_healthy = avg_daily <= 2.0 and risk_level == 'casual'
    today      = datetime.now().date().isoformat()
    yesterday  = (datetime.now().date() - timedelta(days=1)).isoformat()
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT * FROM streaks WHERE user_id=?', (user_id,))
    row  = c.fetchone()
    if not row:
        c.execute('INSERT INTO streaks (user_id) VALUES (?)', (user_id,))
        current = longest = total = 0
        last_date = None
    else:
        row = dict(row)
        current   = row['current_streak']
        longest   = row['longest_streak']
        total     = row['total_healthy_days']
        last_date = row['last_healthy_date']

    if is_healthy:
        if last_date == yesterday:
            current += 1
        elif last_date != today:
            current = 1
        total  += 1 if last_date != today else 0
        longest = max(longest, current)
        c.execute('''UPDATE streaks SET current_streak=?, longest_streak=?,
                     last_healthy_date=?, total_healthy_days=? WHERE user_id=?''',
                  (current, longest, today, total, user_id))
    elif last_date != today:
        current = 0
        c.execute('UPDATE streaks SET current_streak=0 WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()
    return {'current_streak': current, 'longest_streak': longest,
            'total_healthy_days': total, 'is_healthy_today': is_healthy}


def _send_fcm_push(token: str, title: str, body: str) -> str:
    """Send a Firebase Cloud Messaging push to a single device token.
    Returns: 'ok' | 'invalid' (token dead → caller should prune) | 'skip' | 'error'."""
    if not token or not _ensure_firebase():     # lazily imports/inits Firebase on first push
        return 'skip'
    try:
        msg = _firebase_msg.Message(
            notification=_firebase_msg.Notification(title=title, body=body),
            data={'type': 'risk_alert'},
            token=token,
        )
        _firebase_msg.send(msg)
        logger.info("FCM push sent")
        return 'ok'
    except Exception as exc:
        # A token that's been uninstalled / rotated returns Unregistered or
        # SenderIdMismatch — those should be pruned so the table doesn't grow stale.
        name = type(exc).__name__
        logger.warning(f"FCM push failed ({name}): {exc}")
        return 'invalid' if name in ('UnregisteredError', 'SenderIdMismatchError') else 'error'


def _push_to_family(family_code: str, title: str, body: str):
    """Push to EVERY guardian device registered for a family (both parents' phones, etc.),
    pruning any dead tokens as we go. Falls back to legacy per-user tokens too."""
    if not family_code:
        return
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT fcm_token FROM guardian_devices WHERE family_code=?', (family_code,))
    tokens = {r['fcm_token'] for r in c.fetchall() if r['fcm_token']}
    # Legacy fallback: tokens written directly on family member rows before this table existed.
    c.execute("SELECT fcm_token FROM users WHERE family_code=? "
              "AND fcm_token IS NOT NULL AND fcm_token != ''", (family_code,))
    tokens.update(r['fcm_token'] for r in c.fetchall() if r['fcm_token'])
    stale = [t for t in tokens if _send_fcm_push(t, title, body) == 'invalid']
    for t in stale:
        c.execute('DELETE FROM guardian_devices WHERE fcm_token=?', (t,))
    if stale:
        conn.commit()
    conn.close()


def _push_to_user_family(c, user_id: int, title: str, body: str):
    """Resolve a child's family and FCM-push to every guardian device. Best-effort and
    used for the most time-critical alerts (tamper / monitoring-went-silent), so they
    reach a parent whose app isn't actively polling rather than waiting for the next poll.
    No-op when push isn't configured — polling still delivers."""
    try:
        c.execute('SELECT family_code FROM users WHERE user_id=?', (user_id,))
        row = c.fetchone()
        fam = row['family_code'] if row else None
        if fam:
            _push_to_family(fam, title, body)
    except Exception as exc:
        logger.warning(f"push_to_user_family skipped: {exc}")

# ═══════════════════════════ API ROUTES ══════════════════════════

@app.route('/api/health', methods=['GET'])
@limiter.exempt   # platform health checks poll this frequently — never rate-limit it
def health():
    all_loaded = all([behavior_model, chat_model, voice_model, tfidf_vectorizer, feature_scaler])
    # Is an FCM credential available? Checked WITHOUT importing firebase/grpc (stays lazy):
    # env var = Render, file = local. 'configured' just means a credential is present; the
    # SDK is only actually loaded + validated on the first real push.
    fcm_configured = bool(os.environ.get('FIREBASE_KEY_JSON', '').strip()) or os.path.exists(FIREBASE_KEY)
    return jsonify({
        'status':        'ok',
        'models_loaded': all_loaded,
        'fcm_configured': fcm_configured,
        'fcm_initialized': _firebase_app is not None,   # True only after the first push
        'models': {
            'behavior':            behavior_model      is not None,
            'behavior_calibrated': behavior_calibrated is not None,
            'chat':                chat_model          is not None,
            'voice':               voice_model         is not None,
            'tfidf':               tfidf_vectorizer    is not None,
            'scaler':              feature_scaler      is not None,
        },
        'model_trained_at':    MODEL_METADATA.get('trained_at'),
        'behavior_cv_accuracy': MODEL_METADATA.get('cv_mean_accuracy'),
        'behavior_cv_std':      MODEL_METADATA.get('cv_std_accuracy'),
        'behavior_test_accuracy': MODEL_METADATA.get('test_accuracy'),
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/api/model_card', methods=['GET'])
def model_card():
    """Transparent 'model card' for the behaviour model: honest held-out metrics, the
    confusion matrix, the risk-band cutoffs, and an explicit statement that this is a
    screening signal trained on synthetic/illustrative data — not a clinical tool.
    Public (exposes no user data)."""
    m = MODEL_METADATA
    return jsonify({
        'success':             True,
        'model':               'Behaviour risk — RandomForest, 3 classes',
        'trained_at':          m.get('trained_at'),
        'test_accuracy':       m.get('test_accuracy'),
        'macro_f1':            m.get('macro_f1'),
        'per_class_precision': m.get('per_class_precision'),
        'per_class_recall':    m.get('per_class_recall'),
        'per_class_f1':        m.get('per_class_f1'),
        'cv_mean_accuracy':    m.get('cv_mean_accuracy'),
        'cv_std_accuracy':     m.get('cv_std_accuracy'),
        'calibration':         m.get('calibration'),
        'confusion_matrix':    m.get('confusion_matrix'),
        'confusion_labels':    m.get('confusion_labels'),
        'train_samples':       m.get('train_samples'),
        'test_samples':        m.get('test_samples'),
        'feature_count':       m.get('feature_count'),
        'chat_metrics':        m.get('chat_metrics'),
        'voice_metrics':       m.get('voice_metrics'),
        'risk_bands': {
            'casual':   f'score < {RISK_T1}',
            'at_risk':  f'{RISK_T1} <= score < {RISK_T2}',
            'addicted': f'score >= {RISK_T2}',
        },
        'chat_alert_threshold': CHAT_ALERT_T,
        'chat_alert_note':     ('A chat message triggers a toxicity alert only at '
                                f'score >= {CHAT_ALERT_T} (high severity >= {CHAT_ALERT_HIGH_T}). '
                                'Set high on purpose: the chat model over-flags at lower '
                                'thresholds, so this favours precision over recall to avoid '
                                'false alarms on normal gaming chat.'),
        'ensemble_weights':    {'behaviour': 0.40, 'chat': 0.30, 'voice': 0.30},
        'thresholds_note':     ('Risk-band cutoffs are clinically-motivated priors (even '
                                'tertiles), not values fitted to labelled outcomes.'),
        'data_note':           m.get('data_note'),
        'evaluation_note':     m.get('evaluation_note'),
        'disclaimer':          SCREENING_DISCLAIMER,
    })

# ─────────────── USER AUTH ───────────────────────────────────────

_FAMILY_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # no easily-confused 0/O/1/I/L


def _generate_family_code(c) -> str:
    """A short, unique, unambiguous family code, collision-checked against existing ones."""
    import secrets
    for _ in range(20):
        code = ''.join(secrets.choice(_FAMILY_ALPHABET) for _ in range(6))
        c.execute('SELECT 1 FROM users WHERE family_code=?', (code,))
        if not c.fetchone():
            return code
    return ''.join(secrets.choice(_FAMILY_ALPHABET) for _ in range(8))  # rare-miss widen


@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per minute")
def register_user():
    """Create a child account so a real family can onboard (previously accounts were
    seed-only). Identity is PIN-based: the child gets their own login PIN, and a shared
    FAMILY PIN groups siblings under one parent — the parent logs into the Parent app
    with that family PIN to see every child who shares it. Returns a token so the child
    is signed in immediately."""
    data       = request.get_json() or {}
    name        = str(data.get('name', '')).strip()
    pin         = str(data.get('pin', '')).strip()          # child's own login PIN
    parent_pin  = str(data.get('parent_pin', '')).strip()   # shared family PIN
    family_code = str(data.get('family_code', '')).strip().upper()  # blank => new family
    try:
        age = int(data.get('age', 0))
    except (TypeError, ValueError):
        age = 0

    if not name:
        return jsonify({'success': False, 'message': 'Name is required'}), 400
    if not (1 <= age <= 100):
        return jsonify({'success': False, 'message': 'Enter a valid age'}), 400
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        return jsonify({'success': False, 'message': 'Child PIN must be 4–6 digits'}), 400
    if not (parent_pin.isdigit() and 4 <= len(parent_pin) <= 6):
        return jsonify({'success': False, 'message': 'Family PIN must be 4–6 digits'}), 400
    if pin == parent_pin:
        return jsonify({'success': False, 'message': 'Child PIN and Family PIN must be different'}), 400

    conn = get_db()
    c    = conn.cursor()
    pin_h, ppin_h = hash_pin(pin), hash_pin(parent_pin)

    # Child login matches on pin_hash and takes the first row, so a child PIN must be
    # globally unique or two children's logins would collide.
    c.execute('SELECT user_id FROM users WHERE pin_hash=?', (pin_h,))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'That child PIN is already taken — pick another'}), 409

    # Resolve the family: a blank code starts a NEW family (unique generated code); a
    # provided code JOINS that existing family, but only when the family PIN matches it
    # (so you can't attach a child to someone else's family).
    if family_code:
        c.execute('SELECT parent_pin_hash FROM users WHERE family_code=? LIMIT 1', (family_code,))
        frow = c.fetchone()
        if not frow:
            conn.close()
            return jsonify({'success': False, 'message': 'Unknown family code'}), 404
        if frow['parent_pin_hash'] != ppin_h:
            conn.close()
            return jsonify({'success': False, 'message': 'Family PIN does not match this family code'}), 403
        code = family_code
    else:
        code = _generate_family_code(c)

    now = datetime.now().isoformat()
    # Store only the hashes; the plaintext pin/parent_pin columns are kept empty.
    uid = insert_returning_id(
        conn,
        "INSERT INTO users (name, age, pin, parent_pin, pin_hash, parent_pin_hash, family_code, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (name, age, '', '', pin_h, ppin_h, code, now),
        pk='user_id')
    conn.commit()
    conn.close()

    logger.info(f"Registered child user {uid} ({name}) in family {code}")
    return jsonify({
        'success':     True,
        'user_id':     uid,
        'name':        name,
        'age':         age,
        'role':        'child',
        'family_code': code,
        'token':       mint_token('child', uid, [uid]),
    })


@app.route('/api/user/login', methods=['POST'])
@limiter.limit("10 per minute")
def user_login():
    data = request.get_json() or {}
    pin  = str(data.get('pin', '')).strip()
    role = str(data.get('role', 'child')).strip()
    if not pin:
        return jsonify({'success': False, 'message': 'PIN is required'}), 400
    if role not in ('child', 'parent'):
        return jsonify({'success': False, 'message': 'role must be child or parent'}), 400
    conn = get_db()
    c    = conn.cursor()
    pin_h = hash_pin(pin)
    family_code = str(data.get('family_code', '')).strip().upper()
    if role == 'parent':
        # A parent always signs in with their family code + PIN. The code (unique per
        # family) makes this collision-free even if two families chose the same PIN.
        if not family_code:
            conn.close()
            return jsonify({'success': False, 'message': 'Family code is required'}), 400
        c.execute('SELECT user_id, name, age FROM users WHERE family_code=? AND parent_pin_hash=?',
                  (family_code, pin_h))
    else:
        # family_code included so the Child app can keep showing it in Settings —
        # otherwise the code is seen exactly once (registration dialog) and easily
        # forgotten. It's an identifier, not a credential: parent login and sibling
        # joins both still require the family PIN alongside it.
        c.execute('SELECT user_id, name, age, family_code FROM users WHERE pin_hash=?', (pin_h,))
    rows = c.fetchall()
    if not rows:
        conn.close()
        msg = 'Invalid family code or PIN' if role == 'parent' else 'Invalid PIN'
        return jsonify({'success': False, 'message': msg}), 401
    row  = rows[0]
    resp = {'success': True, 'user_id': row['user_id'],
            'name': row['name'], 'age': row['age'], 'role': role}
    if role == 'parent':
        if family_code:
            resp['family_code'] = family_code
        # All users in this family are children of this parent
        children = [{'user_id': r['user_id'], 'name': r['name'], 'age': r['age']} for r in rows]
        resp['children'] = children
        resp['child_user_id'] = children[0]['user_id']
        allowed = [r['user_id'] for r in rows]
    else:
        if row['family_code']:
            resp['family_code'] = row['family_code']
        allowed = [row['user_id']]
        # Parent-awareness symmetry: logging OUT raises an alert, so signing back IN
        # does too — confirming monitoring resumed. Also stamp last_seen immediately,
        # so the dashboard's monitoring strip turns green now rather than when the
        # first heartbeat lands minutes later.
        try:
            _insert_alert(c, row['user_id'], 'login',
                          f"{row['name'] or 'Your child'} signed in to the monitoring app — "
                          "monitoring is active again.", 'info')
            c.execute("UPDATE users SET last_seen=?, offline_alerted=0 WHERE user_id=?",
                      (datetime.now().isoformat(), row['user_id']))
            conn.commit()
        except Exception as e:
            logger.warning(f"login alert skipped: {e}")
    # Signed bearer token the client sends on every subsequent request
    resp['token'] = mint_token(role, row['user_id'], allowed)
    conn.close()
    return jsonify(resp)


@app.route('/api/user/fcm_token', methods=['POST'])
def update_fcm_token():
    """Store or update a device's FCM registration token."""
    data  = request.get_json() or {}
    uid   = data.get('user_id')
    token = str(data.get('fcm_token', '')).strip()
    if not uid or not token:
        return jsonify({'error': 'user_id and fcm_token required'}), 400
    deny = guard(uid)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute('UPDATE users SET fcm_token=? WHERE user_id=?', (token, int(uid)))   # legacy/compat
    # Register this DEVICE under its family so every guardian's phone gets pushes — not just
    # whoever logged in last. Keyed by the unique token (re-register just refreshes the row).
    c.execute('SELECT family_code FROM users WHERE user_id=?', (int(uid),))
    frow = c.fetchone()
    fam  = frow['family_code'] if frow else None
    if fam:
        c.execute('''INSERT INTO guardian_devices (family_code, fcm_token, updated_at)
                     VALUES (?,?,?)
                     ON CONFLICT(fcm_token) DO UPDATE SET family_code=excluded.family_code,
                     updated_at=excluded.updated_at''',
                  (fam, token, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/user/profile', methods=['GET'])
def get_profile():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT user_id, name, age, created_at FROM users WHERE user_id=?', (user_id,))
    row  = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(dict(row))


@app.route('/api/user/update', methods=['POST'])
def update_profile():
    data = request.get_json() or {}
    user_id = data.get('user_id', 1)
    deny = guard(user_id)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    if 'name' in data:
        c.execute('UPDATE users SET name=? WHERE user_id=?', (data['name'], user_id))
    if 'age' in data:
        c.execute('UPDATE users SET age=? WHERE user_id=?', (data['age'], user_id))
    if 'pin' in data:
        c.execute("UPDATE users SET pin_hash=?, pin='' WHERE user_id=?", (hash_pin(str(data['pin'])), user_id))
    if 'parent_pin' in data:
        # Only a PARENT may change the family PIN. A child's own token passes the
        # ownership guard above (it's their row), but letting them rewrite parent_pin
        # would defeat the parent-PIN gate on logout/settings — the exact tamper
        # protection it exists for. (Role is unknown only for legacy shadow-mode
        # callers without a token, which production's AUTH_ENFORCE already rejects.)
        role = (g.auth or {}).get('role')
        if role is not None and role != 'parent':
            conn.close()
            return jsonify({'success': False,
                            'message': 'Only a parent can change the family PIN'}), 403
        c.execute("UPDATE users SET parent_pin_hash=?, parent_pin='' WHERE user_id=?",
                  (hash_pin(str(data['parent_pin'])), user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─────────────── PRIVACY: CONSENT + DATA DELETION + RETENTION ──────────────

CONSENT_VERSION = os.environ.get('CONSENT_VERSION', '2026-06-01')
# Raw event data older than this many days is purged on startup (0 = keep forever).
DATA_RETENTION_DAYS = int(os.environ.get('DATA_RETENTION_DAYS', '0'))

# Every table holding a child's collected data, so "delete my data" is complete.
_USER_TABLES    = ['alerts', 'screen_events', 'notification_events', 'streaks',
                   'time_limits', 'reflections', 'counselor_messages', 'anomalies']
_SESSION_TABLES = ['behavioral_data', 'chat_messages', 'voice_events', 'predictions']


def _delete_user_data(conn, user_id):
    """Delete all collected monitoring data for a user (keeps the account row)."""
    c = conn.cursor()
    for t in _SESSION_TABLES:
        c.execute(f"DELETE FROM {t} WHERE session_id IN "
                  f"(SELECT session_id FROM sessions WHERE user_id=?)", (user_id,))
    c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    for t in _USER_TABLES:
        c.execute(f"DELETE FROM {t} WHERE user_id=?", (user_id,))
    conn.commit()


def purge_old_data():
    """Enforce the data-retention window by deleting stale raw events on startup."""
    if DATA_RETENTION_DAYS <= 0:
        return
    cutoff = (datetime.now() - timedelta(days=DATA_RETENTION_DAYS)).isoformat()
    conn = get_db()
    c = conn.cursor()
    for t in ('chat_messages', 'voice_events', 'screen_events', 'notification_events'):
        c.execute(f"DELETE FROM {t} WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()
    logger.info(f"Retention purge: removed raw events older than {DATA_RETENTION_DAYS} days")


@app.route('/api/consent', methods=['POST'])
def record_consent():
    """Record parental consent to monitoring for a child account."""
    data    = request.get_json() or {}
    user_id = data.get('user_id')
    deny = guard(user_id)
    if deny: return deny
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    version = str(data.get('version', CONSENT_VERSION))
    conn = get_db()
    conn.cursor().execute("UPDATE users SET consent_given_at=?, consent_version=? WHERE user_id=?",
                          (datetime.now().isoformat(), version, int(user_id)))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'consent_version': version})


@app.route('/api/consent', methods=['GET'])
def get_consent():
    user_id = request.args.get('user_id', type=int)
    deny = guard(user_id)
    if deny: return deny
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    conn = get_db()
    row = conn.execute("SELECT consent_given_at, consent_version FROM users WHERE user_id=?",
                       (user_id,)).fetchone()
    conn.close()
    given = bool(row and row['consent_given_at'])
    stale = bool(row and row['consent_version'] and row['consent_version'] != CONSENT_VERSION)
    return jsonify({
        'success': True,
        'consent_given':    given,
        'consent_given_at': row['consent_given_at'] if row else None,
        'consent_version':  row['consent_version'] if row else None,
        'current_version':  CONSENT_VERSION,
        'needs_consent':    (not given) or stale,
    })


@app.route('/api/user/delete_data', methods=['POST'])
def delete_user_data():
    """Erase a child's collected data ('data'), or the whole account ('account').
       PARENT-controlled (per the privacy design): a child's own token must not be able
       to wipe the monitoring history — that would be a quiet-tamper loophole. Role is
       unknown only for token-less shadow-mode callers, which production rejects."""
    data    = request.get_json() or {}
    user_id = data.get('user_id')
    deny = guard(user_id)
    if deny: return deny
    role = (g.auth or {}).get('role')
    if role is not None and role != 'parent':
        return jsonify({'success': False,
                        'message': 'Data deletion is managed from the Parent app'}), 403
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    scope = str(data.get('scope', 'data')).lower()
    conn = get_db()
    _delete_user_data(conn, int(user_id))
    if scope == 'account':
        conn.cursor().execute("DELETE FROM users WHERE user_id=?", (int(user_id),))
        conn.commit()
    conn.close()
    logger.info(f"Data deletion (scope={scope}) for user {user_id}")
    return jsonify({'success': True, 'scope': scope})


# ─────────────── SESSION MANAGEMENT ─────────────────────────────

# A session whose end-event never reaches the server (e.g. the device was offline when
# the child stopped playing) would otherwise stay open forever — showing "currently
# playing" and never counting toward stats. Auto-close any session left open longer than
# this, ending it at its last recorded activity so the duration stays realistic. This is
# the server-side safety net for best-effort uploads (there is no offline retry queue).
STALE_SESSION_HOURS = 6
# A live, playing app heartbeats every ~5 min. If heartbeats STOP while a session is
# open, the monitoring app was killed/swiped/uninstalled — so the session's end-event is
# never coming and the child is no longer being tracked as "playing". Close it promptly
# (this many minutes of heartbeat silence) instead of waiting out the 6-hour fallback,
# which is what left a child shown as "playing" with the green dot after a swipe-away.
SESSION_SILENT_MIN = 12


def _close_stale_sessions(c, user_id):
    """Self-heal sessions orphaned by a lost end-event. Closes a session when EITHER it
    has been open past the 6-hour fallback, OR the monitoring app's heartbeat has gone
    silent (the app can't still be tracking play if it isn't checking in). Caller
    commits. Best-effort: never raises into the request."""
    try:
        cutoff = (datetime.now() - timedelta(hours=STALE_SESSION_HOURS)).isoformat()
        # Heartbeat-silent branch: if last_seen is older than the silence window, every
        # open session for this user is orphaned (the app isn't running). last_seen NULL
        # means "never heartbeated" (old app) — don't use it to close; the 6h rule covers
        # that case.
        c.execute('SELECT last_seen FROM users WHERE user_id=?', (user_id,))
        _hb = c.fetchone()
        hb_silent = False
        if _hb and _hb['last_seen']:
            try:
                silent_min = (datetime.now() - _parse_ts(_hb['last_seen'])).total_seconds() / 60.0
                hb_silent = silent_min >= SESSION_SILENT_MIN
            except Exception:
                hb_silent = False
        if hb_silent:
            c.execute("SELECT session_id, start_time FROM sessions "
                      "WHERE user_id=? AND end_time IS NULL", (user_id,))
        else:
            c.execute("SELECT session_id, start_time FROM sessions "
                      "WHERE user_id=? AND end_time IS NULL AND start_time < ?",
                      (user_id, cutoff))
        rows = c.fetchall()
        for r in rows:
            sid = r['session_id']
            # End at the last activity we actually recorded for this session.
            c.execute("SELECT MAX(t) AS t FROM ("
                      "  SELECT MAX(timestamp) AS t FROM chat_messages   WHERE session_id=? "
                      "  UNION ALL SELECT MAX(timestamp) FROM voice_events    WHERE session_id=? "
                      "  UNION ALL SELECT MAX(timestamp) FROM behavioral_data WHERE session_id=? "
                      "  UNION ALL SELECT MAX(timestamp) FROM predictions     WHERE session_id=? "
                      ") q", (sid, sid, sid, sid))
            last   = c.fetchone()
            end_ts = last['t'] if (last and last['t']) else r['start_time']
            try:
                sdt = datetime.fromisoformat(str(r['start_time']).replace(' ', 'T'))
                edt = datetime.fromisoformat(str(end_ts).replace(' ', 'T').split('+')[0].split('Z')[0])
                dur = max(0, int((edt - sdt).total_seconds()))
            except Exception:
                end_ts, dur = r['start_time'], 0
            dur = min(dur, STALE_SESSION_HOURS * 3600)   # cap against bad timestamps
            c.execute("UPDATE sessions SET end_time=?, duration_seconds=? WHERE session_id=?",
                      (end_ts, dur, sid))
            logger.info("Auto-closed stale session %s (offline end-event presumed lost)", sid)
    except Exception as e:
        logger.warning("Stale-session sweep failed for user %s: %s", user_id, e)


@app.route('/api/session/start', methods=['POST'])
@limiter.limit("5 per minute")
def start_session():
    data      = request.get_json() or {}
    game_name = str(data.get('game_name', '')).strip()
    user_id   = data.get('user_id')
    if not game_name:
        return jsonify({'error': 'game_name is required'}), 400
    try:
        user_id = int(user_id)
        if user_id <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id must be a positive integer'}), 400
    deny = guard(user_id)
    if deny: return deny
    now       = datetime.now().isoformat()
    conn = get_db()
    # Self-heal any session orphaned by a lost end-event before opening a new one.
    _close_stale_sessions(conn.cursor(), user_id)
    # Invariant: at most ONE open session per user. Starting a new one means any session
    # still open is definitively over (you can't play two games at once) — close it at its
    # last activity. This clears a duplicate left when the app was killed mid-play and a
    # later detection opened a fresh session on top of the orphan (which then showed
    # "running" forever). Best-effort.
    try:
        cc = conn.cursor()
        cc.execute("SELECT session_id, start_time FROM sessions "
                   "WHERE user_id=? AND end_time IS NULL", (user_id,))
        for orow in cc.fetchall():
            osid = orow['session_id']
            cc.execute("SELECT MAX(t) AS t FROM ("
                       "  SELECT MAX(timestamp) AS t FROM chat_messages   WHERE session_id=? "
                       "  UNION ALL SELECT MAX(timestamp) FROM voice_events    WHERE session_id=? "
                       "  UNION ALL SELECT MAX(timestamp) FROM behavioral_data WHERE session_id=? "
                       ") q", (osid, osid, osid))
            lt = cc.fetchone()
            oend = lt['t'] if (lt and lt['t']) else orow['start_time']
            try:
                sdt = _parse_ts(orow['start_time']); edt = _parse_ts(oend)
                odur = min(max(0, int((edt - sdt).total_seconds())), STALE_SESSION_HOURS * 3600)
            except Exception:
                oend, odur = orow['start_time'], 0
            cc.execute("UPDATE sessions SET end_time=?, duration_seconds=? WHERE session_id=?",
                       (oend, odur, osid))
    except Exception as e:
        logger.warning("close-prior-open-session skipped for user %s: %s", user_id, e)
    sid  = insert_returning_id(
        conn,
        'INSERT INTO sessions (user_id, game_name, start_time) VALUES (?,?,?)',
        (user_id, game_name, now),
        pk='session_id')
    # Real-time awareness for the parent: raise a low-priority alert the moment gaming
    # starts. The parent app's AlertPollingService picks it up (~60 s) and notifies.
    # De-dupe: if the previous session began within the last 10 min (rapid app-switching
    # / quick reopen of the same play bout) we skip it so the parent isn't spammed.
    try:
        c = conn.cursor()
        c.execute('SELECT start_time FROM sessions WHERE user_id=? AND session_id<>? '
                  'ORDER BY session_id DESC LIMIT 1', (user_id, sid))
        prev   = c.fetchone()
        recent = False
        if prev and prev['start_time']:
            try:
                pdt    = datetime.fromisoformat(str(prev['start_time']).replace(' ', 'T')
                                                .split('+')[0].split('Z')[0])
                recent = (datetime.now() - pdt).total_seconds() < 600
            except Exception:
                recent = False
        if not recent:
            c.execute('SELECT name FROM users WHERE user_id=?', (user_id,))
            urow  = c.fetchone()
            cname = urow['name'] if (urow and urow['name']) else 'Your child'
            _insert_alert(c, user_id, 'session_start',
                          f'{cname} just started playing {game_name}.', 'info')
    except Exception as e:
        logger.warning(f"session_start alert skipped: {e}")
    conn.commit()
    conn.close()
    logger.info(f"Session {sid} started: {game_name}")
    return jsonify({'success': True, 'session_id': sid, 'start_time': now, 'game_name': game_name})


@app.route('/api/session/<int:sid>/end', methods=['POST'])
def end_session(sid):
    deny = guard_session(sid)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT start_time FROM sessions WHERE session_id=?', (sid,))
    row  = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    # How many seconds before "now" the player actually stopped — the grace / ancillary
    # tail the auto-monitor waited out before ending. Sent as a delta (not an absolute
    # timestamp) so device/server clock skew is irrelevant. Clamped so a session can
    # never end before it started or in the future. 0 for an explicit "end now".
    try:
        ago = max(0, int(request.args.get('ended_seconds_ago')
                          or (request.get_json(silent=True) or {}).get('ended_seconds_ago', 0)))
    except (TypeError, ValueError):
        ago = 0
    start    = datetime.fromisoformat(row['start_time'])
    end_time = datetime.now() - timedelta(seconds=ago)
    if end_time < start:
        end_time = start
    duration = max(0, int((end_time - start).total_seconds()))
    c.execute('UPDATE sessions SET end_time=?, duration_seconds=? WHERE session_id=?',
              (end_time.isoformat(), duration, sid))
    conn.commit()
    conn.close()

    # Save final behavioural snapshot before predicting
    _save_behavioral_snapshot(sid)

    prediction = run_prediction(sid)
    logger.info(f"Session {sid} ended ({duration}s)")

    # Create alert if risk is elevated
    conn2 = get_db()
    c2    = conn2.cursor()
    c2.execute('SELECT user_id FROM sessions WHERE session_id=?', (sid,))
    srow  = c2.fetchone()
    if srow:
        _maybe_create_alert(c2, srow['user_id'], prediction)
        conn2.commit()
        # Update healthy-day streak
        conn2.close()
        conn2 = get_db()
        c2    = conn2.cursor()
        c2.execute('''SELECT COALESCE(ROUND(SUM(duration_seconds)/3600.0,2),0) AS wh
                      FROM sessions WHERE user_id=? AND start_time>=?''',
                   (srow['user_id'], (datetime.now()-timedelta(days=7)).isoformat()))
        wh_row = c2.fetchone()
        weekly_h = float(wh_row['wh'] or 0) if wh_row else 0.0
        _update_streak(srow['user_id'], weekly_h, prediction.get('risk_category','casual'))

        # FCM push to EVERY guardian device when a child session is high-risk (both
        # parents' phones, etc.) — not just whoever registered last.
        if prediction.get('risk_category') == 'addicted':
            conn2b = get_db()
            c2b    = conn2b.cursor()
            c2b.execute('SELECT family_code FROM users WHERE user_id=?', (srow['user_id'],))
            _fc  = c2b.fetchone()
            conn2b.close()
            fam  = _fc['family_code'] if _fc else None
            if fam:
                score_pct = int(prediction['final_risk_score'] * 100)
                _push_to_family(
                    fam,
                    "High Gaming Risk Alert",
                    f"Your child's gaming risk reached {score_pct}% — check the app now."
                )
    conn2.close()

    short_session = duration < 60
    pred_response = {
        'risk_label':        prediction['risk_category'],
        'risk_score':        prediction['final_risk_score'],
        'behavior_score':    prediction['behavior_score'],
        'chat_score':        prediction['chat_score'],
        'voice_score':       prediction['voice_score'],
        'modalities':        prediction.get('modalities'),
        'recommendations':   _build_recommendations(prediction['risk_category']),
        'top_factors':       prediction.get('top_factors', []),
        'observation_mode':  prediction.get('observation_mode', False),
        'sessions_analyzed': prediction.get('sessions_analyzed', 0),
    }
    if short_session:
        pred_response['short_session_note'] = 'Session under 1 minute — collect more data for reliable results.'
    return jsonify({'success': True, 'session_id': sid,
                    'duration_seconds': duration,
                    'short_session': short_session,
                    'prediction': pred_response})


@app.route('/api/session/<int:sid>', methods=['GET'])
def get_session(sid):
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT * FROM sessions WHERE session_id=?', (sid,))
    row  = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    deny = guard(row['user_id'])
    if deny:
        conn.close()
        return deny

    c.execute('SELECT * FROM predictions WHERE session_id=? ORDER BY id DESC LIMIT 1', (sid,))
    pred = c.fetchone()
    c.execute('SELECT COUNT(*) AS n FROM chat_messages WHERE session_id=?', (sid,))
    n_chat = c.fetchone()['n']
    c.execute('SELECT COUNT(*) AS n FROM voice_events WHERE session_id=?', (sid,))
    n_voice = c.fetchone()['n']
    conn.close()
    return jsonify({
        **dict(row),
        'prediction':   dict(pred) if pred else None,
        'chat_count':   n_chat,
        'voice_count':  n_voice,
    })


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    limit   = request.args.get('limit', 50, type=int)
    conn = get_db()
    c    = conn.cursor()
    c.execute('''SELECT s.*,
                 (SELECT COUNT(*) FROM chat_messages  WHERE session_id=s.session_id) AS chat_count,
                 (SELECT COUNT(*) FROM voice_events   WHERE session_id=s.session_id) AS voice_count
                 FROM sessions s WHERE s.user_id=? ORDER BY s.start_time DESC LIMIT ?''',
              (user_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ─────────────── DATA INGESTION ──────────────────────────────────

def _save_behavioral_snapshot(session_id: int):
    data = compute_behavioral_features(session_id)
    if not data:
        return
    conn = get_db()
    c    = conn.cursor()
    cols = ', '.join(BEHAVIORAL_FEATURES)
    ph   = ', '.join(['?'] * len(BEHAVIORAL_FEATURES))
    vals = [data[f] for f in BEHAVIORAL_FEATURES]
    c.execute(f'INSERT INTO behavioral_data (session_id, {cols}, timestamp) VALUES (?,{ph},?)',
              [session_id] + vals + [datetime.now().isoformat()])
    conn.commit()
    conn.close()


@app.route('/api/session/<int:sid>/behavioral', methods=['POST'])
def save_behavioral(sid):
    """Accept manual behavioural data from Android app (or auto-compute if empty)."""
    deny = guard_session(sid)
    if deny: return deny
    data = request.get_json() or {}
    if not data:
        _save_behavioral_snapshot(sid)
        return jsonify({'success': True, 'computed': True})

    conn = get_db()
    c    = conn.cursor()
    vals = [float(data.get(f, 0)) for f in BEHAVIORAL_FEATURES]
    cols = ', '.join(BEHAVIORAL_FEATURES)
    ph   = ', '.join(['?'] * len(BEHAVIORAL_FEATURES))
    c.execute(f'INSERT INTO behavioral_data (session_id, {cols}, timestamp) VALUES (?,{ph},?)',
              [sid] + vals + [datetime.now().isoformat()])
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/session/<int:sid>/chat', methods=['POST'])
def save_chat(sid):
    deny = guard_session(sid)
    if deny: return deny
    data    = request.get_json() or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Empty message'}), 400

    # Real-time toxicity scoring for alert generation
    kw_score = keyword_toxicity(message)
    ml_score = 0.0
    if chat_model is not None and tfidf_vectorizer is not None:
        try:
            vec      = tfidf_vectorizer.transform([clean_text(message)])
            proba    = chat_model.predict_proba(vec)[0]
            ml_score = float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            pass
    tox_score = float(np.clip(max(ml_score, kw_score), 0, 1))

    conn = get_db()
    c    = conn.cursor()
    # De-dupe: the custom keyboard (IME) and the accessibility path can both observe the
    # same typed line. Skip an identical message for this session seen in the last few
    # seconds so it isn't scored/alerted twice.
    c.execute("SELECT 1 FROM chat_messages WHERE session_id=? AND message=? AND timestamp>=? LIMIT 1",
              (sid, message, (datetime.now() - timedelta(seconds=8)).isoformat()))
    if c.fetchone():
        conn.close()
        return jsonify({'success': True, 'duplicate': True, 'toxicity_score': round(tox_score, 3)})
    c.execute('INSERT INTO chat_messages (session_id, message, source, confidence, timestamp) VALUES (?,?,?,?,?)',
              (sid, message, data.get('source', 'ocr'), round(tox_score, 3),
               datetime.now().isoformat()))

    # Raise social toxicity alert only when a single message is confidently toxic
    # (CHAT_ALERT_T is intentionally high to suppress the chat model's false positives).
    if tox_score >= CHAT_ALERT_T:
        c.execute('SELECT user_id FROM sessions WHERE session_id=?', (sid,))
        srow = c.fetchone()
        if srow:
            snippet = message[:60] + ('…' if len(message) > 60 else '')
            _insert_alert(c, srow['user_id'], 'toxicity',
                          f'Toxic language detected during gaming: "{snippet}"',
                          'high' if tox_score >= CHAT_ALERT_HIGH_T else 'medium')
            # Gentle self-correction nudge to the CHILD too — but at most one pending at a
            # time so a toxic streak doesn't spam them.
            c.execute("SELECT 1 FROM child_nudges WHERE user_id=? AND kind='language' AND delivered=0 LIMIT 1",
                      (srow['user_id'],))
            if not c.fetchone():
                c.execute("INSERT INTO child_nudges (user_id, message, kind) VALUES (?,?,?)",
                          (srow['user_id'], "Let's keep it friendly — mind the language 🙂", 'language'))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'toxicity_score': round(tox_score, 3)})


# Last voice-driven re-score per session (monotonic seconds) — see save_voice.
_voice_rescore_last: dict = {}


@app.route('/api/session/<int:sid>/voice', methods=['POST'])
def save_voice(sid):
    """Accept audio file or pre-computed emotion from Android."""
    deny = guard_session(sid)
    if deny: return deny
    audio_file = request.files.get('audio')
    if audio_file:
        fname  = f"voice_{sid}_{int(time.time())}.wav"
        fpath  = os.path.join(AUDIO_DIR, fname)
        audio_file.save(fpath)
        try:
            acoustic, intensity, duration, probs = analyse_audio(fpath)
        except Exception as e:
            # A malformed clip or model hiccup must not 500 the upload (the app would
            # lose the segment) or leak the temp WAV on the small ephemeral disk.
            logger.warning(f"analyse_audio failed for session {sid}: {e}")
            acoustic, intensity, duration, probs = 'neutral', 0.2, 0.0, None
        # Multimodal fusion: pull the words spoken in this segment (Vosk STT, uploaded
        # as voice_stt chat in the last ~20s) and fuse their valence with the acoustic
        # distribution (valence–arousal). Falls back to the acoustic label when no
        # transcript is available.
        emotion = acoustic
        try:
            conn0 = get_db()
            rows = conn0.execute(
                "SELECT message FROM chat_messages WHERE session_id=? AND source='voice_stt' "
                "AND timestamp >= ? ORDER BY id DESC LIMIT 5",
                (sid, (datetime.now() - timedelta(seconds=20)).isoformat())
            ).fetchall()
            conn0.close()
            recent_text = " ".join(r["message"] for r in rows if r["message"])
            v_text, v_conf = _lexical_valence(recent_text)
            tox = _chat_toxicity(recent_text)   # trained model: robust hostility signal
            # Even without words, the acoustic distribution still gives a steady label.
            emotion = fuse_emotion(acoustic, v_text, probs=probs,
                                   valence_conf=v_conf, toxicity=tox)
        except Exception:
            pass
        # Privacy default: delete raw audio after feature extraction.
        # For local testing, set KEEP_AUDIO=1 in the environment to retain WAVs
        # under backend/audio_uploads/ so you can listen back via verify_captures.py.
        if os.environ.get('KEEP_AUDIO', '').lower() in ('1', 'true', 'yes'):
            pass  # keep file, leave fname pointing at it
        else:
            try:
                os.remove(fpath)
                fname = None
            except Exception:
                pass
    else:
        body      = request.get_json() or {}
        emotion   = body.get('emotion', 'neutral')
        intensity = float(body.get('intensity', 0.5))
        duration  = float(body.get('duration_seconds', 0.0))
        fname     = None

    conn = get_db()
    c    = conn.cursor()
    c.execute('INSERT INTO voice_events (session_id, emotion, intensity, duration_s, audio_file, timestamp) VALUES (?,?,?,?,?,?)',
              (sid, emotion, intensity, duration, fname, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    # Re-score so a freshly-arrived voice emotion actually counts. The voice pipeline
    # (record → buffer → analyse → fuse → upload) is slower than behaviour/chat, so on a
    # short session the session-end prediction can be computed BEFORE the last voice
    # segment lands — leaving voice marked "not captured". Re-running here (cheap, no
    # SHAP) folds the new emotion into the latest stored prediction's voice flag + score.
    # Throttled per session: segments arrive every ~10 s (and in bursts after an offline
    # flush); re-scoring once per burst gives the same final state for a fraction of the
    # CPU/DB work on the free tier.
    now_mono = time.monotonic()
    if now_mono - _voice_rescore_last.get(sid, 0) >= 8:
        _voice_rescore_last[sid] = now_mono
        try:
            run_prediction(sid, explain=False)
        except Exception as e:
            logger.warning(f"voice re-prediction skipped: {e}")
    return jsonify({'success': True, 'emotion': emotion, 'intensity': intensity, 'duration': duration})


@app.route('/api/session/<int:sid>/predict', methods=['POST'])
def predict_now(sid):
    """Trigger intermediate prediction (live during session)."""
    deny = guard_session(sid)
    if deny: return deny
    _save_behavioral_snapshot(sid)
    result = run_prediction(sid, explain=False)   # skip SHAP on frequent live predicts (memory)
    # Spread result FIRST so the explicit keys win: risk_label must be the internal
    # category (casual/at_risk/addicted) to match the /end response that clients
    # pattern-match on — result's own risk_label is the human display string.
    return jsonify({
        **result,
        'success':    True,
        'risk_label': result['risk_category'],
        'risk_score': result['final_risk_score'],
    })

# ─────────────── CHAT ANALYSIS ───────────────────────────────────

@app.route('/api/analyse/chat', methods=['POST'])
def analyse_chat():
    """Analyse a single chat message and return toxicity score (no DB write)."""
    data = request.get_json() or {}
    msg  = data.get('message', '')
    if not msg:
        return jsonify({'error': 'No message'}), 400

    ml_score = 0.0
    if chat_model is not None and tfidf_vectorizer is not None:
        try:
            vec      = tfidf_vectorizer.transform([clean_text(msg)])
            # The chat model is a classifier: use P(toxic), not predict() (a 0/1 class
            # label) — the same continuous score the alert path and ensemble use. The
            # old `predict()*1.5` collapsed this to a crude binary 0/1.
            proba    = chat_model.predict_proba(vec)[0]
            ml_score = float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            pass
    kw_score = keyword_toxicity(msg)
    final    = float(np.clip(max(ml_score, kw_score), 0, 1))
    # Label bands aligned with the alert threshold: don't call a message 'toxic' in the UI
    # unless it would actually raise an alert — avoids scaring parents over normal gaming
    # chat the model tends to over-score.
    label    = 'toxic' if final >= CHAT_ALERT_T else ('borderline' if final >= 0.4 else 'safe')
    return jsonify({'message': msg, 'toxicity_score': round(final, 4),
                    'ml_score': round(ml_score, 4), 'keyword_score': round(kw_score, 4),
                    'label': label})

# ─────────────── DASHBOARD APIs ──────────────────────────────────

@app.route('/api/dashboard/user', methods=['GET'])
def user_dashboard():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    days    = request.args.get('days', 30, type=int)
    since   = (datetime.now() - timedelta(days=days)).isoformat()
    conn    = get_db()
    c       = conn.cursor()

    # Sessions in period
    c.execute('''SELECT session_id, game_name, start_time, end_time,
                 duration_seconds, final_risk_score, risk_category
                 FROM sessions WHERE user_id=? AND start_time>=? ORDER BY start_time DESC''',
              (user_id, since))
    sessions = [dict(r) for r in c.fetchall()]

    # Aggregate stats
    c.execute('''SELECT COUNT(*) AS n_sessions,
                 ROUND(AVG(duration_seconds)/60.0,1) AS avg_duration_min,
                 ROUND(AVG(final_risk_score),4)       AS avg_risk,
                 MAX(final_risk_score)                AS max_risk
                 FROM sessions WHERE user_id=? AND start_time>=? AND end_time IS NOT NULL''',
              (user_id, since))
    stats = dict(c.fetchone())

    # Risk distribution
    c.execute('''SELECT risk_category, COUNT(*) AS n
                 FROM sessions WHERE user_id=? AND start_time>=? AND risk_category IS NOT NULL
                 GROUP BY risk_category''', (user_id, since))
    dist = {r['risk_category']: r['n'] for r in c.fetchall()}

    # Latest prediction
    c.execute('''SELECT p.* FROM predictions p
                 JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    _row = c.fetchone()
    latest = dict(_row) if _row else None

    # Game breakdown
    c.execute('''SELECT game_name, COUNT(*) AS sessions,
                 ROUND(SUM(duration_seconds)/60.0,1) AS total_min
                 FROM sessions WHERE user_id=? AND start_time>=? GROUP BY game_name
                 ORDER BY total_min DESC''', (user_id, since))
    games = [dict(r) for r in c.fetchall()]

    # Trend data (last 14 days)
    c.execute(f'''SELECT SUBSTR(start_time,1,10) AS date,
                 ROUND(AVG(final_risk_score),4) AS score,
                 (CASE WHEN AVG(final_risk_score) < {RISK_T1} THEN 'casual'
                       WHEN AVG(final_risk_score) < {RISK_T2} THEN 'at_risk'
                       ELSE 'addicted' END) AS label
                 FROM sessions WHERE user_id=? AND start_time>=? AND final_risk_score IS NOT NULL
                 GROUP BY date ORDER BY date ASC LIMIT 14''',
              (user_id, (datetime.now() - timedelta(days=14)).isoformat()))
    trend = [dict(r) for r in c.fetchall()]

    conn.close()

    current_risk = latest.get('risk_category', 'casual') if latest else 'casual'
    latest_score = latest.get('final_risk_score', 0.0) if latest else 0.0
    total_hours  = round(sum(s['duration_seconds'] or 0 for s in sessions) / 3600.0, 2)
    avg_daily    = round(total_hours / max(days, 1), 2)

    recent_formatted = []
    for s in sessions[:10]:
        dur_s = s['duration_seconds'] or 0
        dur_str = '%dh %dm' % (dur_s // 3600, (dur_s % 3600) // 60)
        recent_formatted.append({
            'id':         s['session_id'],
            'game_name':  s['game_name'],
            'risk_label': s['risk_category'] or 'unknown',
            'risk_score': s['final_risk_score'] or 0.0,
            'duration':   dur_str,
            'created_at': s['start_time'],
        })

    return jsonify({
        'success':    True,
        'user_id':    user_id,
        'stats': {
            'total_sessions':  stats.get('n_sessions', 0),
            'total_hours':     total_hours,
            'current_risk':    current_risk,
            'risk_score':      round(latest_score, 4),
            'avg_daily_hours': avg_daily,
        },
        'risk_distribution': dist,
        'recent_sessions':   recent_formatted,
        'trend_data':        trend,
        'game_breakdown':    games,
    })


@app.route('/api/dashboard/parent', methods=['GET'])
def parent_dashboard():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()

    # Child profile
    c.execute('SELECT name, age FROM users WHERE user_id=?', (user_id,))
    profile = dict(c.fetchone() or {})

    # Self-heal lost end-events before reading live state, so this dashboard never
    # shows a child "perpetually playing" a session whose end never arrived.
    _close_stale_sessions(c, user_id)
    conn.commit()

    # ── Live status strip ────────────────────────────────────────────
    # Is the child playing RIGHT NOW, and is the monitoring app checking in?
    # last_seen is written by the ~5-minute heartbeat, so <=10 min means healthy;
    # beyond that the app is likely killed/offline (the watchdog alert follows later).
    monitoring = None
    c.execute('SELECT last_seen, device_admin_active FROM users WHERE user_id=?', (user_id,))
    lsrow = c.fetchone()
    if lsrow and lsrow['last_seen']:
        try:
            mins = max(0, int((datetime.now() - _parse_ts(lsrow['last_seen'])).total_seconds() // 60))
            # protected: instant uninstall-attempt alerting is on (Device Admin enabled).
            # None = unknown (older child app that doesn't report it yet).
            prot = lsrow['device_admin_active']
            monitoring = {'online': mins <= 10, 'minutes_since_checkin': mins,
                          'protected': (bool(prot) if prot is not None else None)}
        except Exception:
            monitoring = None
    c.execute('''SELECT game_name, start_time FROM sessions
                 WHERE user_id=? AND end_time IS NULL ORDER BY session_id DESC LIMIT 1''',
              (user_id,))
    lrow_live = c.fetchone()
    live_status = {'is_playing': False, 'current_game': None, 'session_duration_mins': None}
    # Don't claim "playing now" when we KNOW the app has gone silent — an open session
    # with a stale heartbeat is unconfirmed (the stale-session sweep above closes it once
    # silence crosses SESSION_SILENT_MIN; this guards the in-between window so the green
    # "playing" dot can't linger after the app is swiped away). When there's no heartbeat
    # data at all (monitoring is None — legacy/seed child that never pinged) we can't
    # judge, so we don't suppress.
    monitoring_silent = monitoring is not None and monitoring.get('online') is not True
    if lrow_live and not monitoring_silent:
        try:
            live_min = max(0, int((datetime.now() - _parse_ts(lrow_live['start_time'])).total_seconds() // 60))
        except Exception:
            live_min = None
        live_status = {'is_playing': True, 'current_game': lrow_live['game_name'],
                       'session_duration_mins': live_min}

    # Latest risk prediction
    c.execute('''SELECT p.risk_category, p.final_risk_score, p.timestamp
                 FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    lrow   = c.fetchone()
    latest = dict(lrow) if lrow else {}

    # Headline risk as a per-DAY roll-up (most recent active day), DURATION-WEIGHTED so a
    # brief session can't dominate — far more stable/representative for a parent than the
    # single last session. (The child app stays per-session/live.) Falls back to a simple
    # average if a day's sessions somehow total zero duration.
    risk_period   = None
    daily_signals = None
    c.execute('''SELECT SUBSTR(start_time,1,10) AS d FROM sessions
                 WHERE user_id=? AND final_risk_score IS NOT NULL
                 ORDER BY start_time DESC LIMIT 1''', (user_id,))
    drow = c.fetchone()
    if drow and drow['d']:
        day = drow['d']
        c.execute('''SELECT final_risk_score AS s, COALESCE(duration_seconds,0) AS dur
                     FROM sessions WHERE user_id=? AND SUBSTR(start_time,1,10)=?
                     AND final_risk_score IS NOT NULL''', (user_id, day))
        drows = c.fetchall()
        if drows:
            wsum  = sum(float(r['dur']) for r in drows)
            score = (sum(float(r['s']) * float(r['dur']) for r in drows) / wsum
                     if wsum > 0 else sum(float(r['s']) for r in drows) / len(drows))
            latest['final_risk_score'] = round(score, 4)
            latest['risk_category']    = ('casual' if score < RISK_T1 else
                                          'at_risk' if score < RISK_T2 else 'addicted')
            # Signals analysed across the WHOLE day (union): if ANY session that day had
            # voice/chat, show it — not just whatever the last session happened to catch.
            c.execute('''SELECT MAX(p.behavior_present) b, MAX(p.chat_present) ch, MAX(p.voice_present) v
                         FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                         WHERE s.user_id=? AND SUBSTR(s.start_time,1,10)=?''', (user_id, day))
            sg = c.fetchone()
            if sg and sg['b'] is not None:
                daily_signals = {'behavior': bool(sg['b']), 'chat': bool(sg['ch']),
                                 'voice': bool(sg['v'])}
            today = datetime.now().date()
            try:
                dd = datetime.fromisoformat(day).date()
            except Exception:
                dd = today
            label = ('Today' if dd == today else
                     'Yesterday' if dd == today - timedelta(days=1) else dd.strftime('%b %d'))
            risk_period = {'label': label, 'date': day, 'sessions': len(drows)}

    # 14-day trend. The window filter matters: without it, ORDER BY date ASC LIMIT 14
    # returns the OLDEST 14 days in history, so the chart would freeze at the child's
    # first two weeks forever once more history accumulates.
    c.execute(f'''SELECT SUBSTR(start_time,1,10) AS date,
                 ROUND(AVG(final_risk_score),4) AS score,
                 (CASE WHEN AVG(final_risk_score) < {RISK_T1} THEN 'casual'
                       WHEN AVG(final_risk_score) < {RISK_T2} THEN 'at_risk'
                       ELSE 'addicted' END) AS label
                 FROM sessions WHERE user_id=? AND start_time>=? AND final_risk_score IS NOT NULL
                 GROUP BY date ORDER BY date ASC LIMIT 14''',
              (user_id, (datetime.now() - timedelta(days=14)).isoformat()))
    trend = [dict(r) for r in c.fetchall()]

    # Top games
    c.execute('''SELECT game_name AS game, COUNT(*) AS sessions,
                 ROUND(SUM(duration_seconds)/3600.0,2) AS hours
                 FROM sessions WHERE user_id=? GROUP BY game_name ORDER BY hours DESC LIMIT 5''',
              (user_id,))
    top_games = [dict(r) for r in c.fetchall()]

    # Recently played: distinct games ordered by most recent session. "Top games" is
    # ranked by cumulative hours and capped at 5, so a brand-new short session (e.g. a
    # 1-min Roblox try) can rank below it and stay hidden — this list surfaces it.
    c.execute('''SELECT game_name AS game, MAX(start_time) AS last_played, COUNT(*) AS sessions,
                 ROUND(SUM(duration_seconds)/60.0,1) AS minutes
                 FROM sessions WHERE user_id=? GROUP BY game_name
                 ORDER BY last_played DESC LIMIT 6''', (user_id,))
    recent_games = [dict(r) for r in c.fetchall()]

    # Weekly total hours
    since7 = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute('''SELECT ROUND(SUM(duration_seconds)/3600.0,2) AS h
                 FROM sessions WHERE user_id=? AND start_time>=?''', (user_id, since7))
    weekly_row  = c.fetchone()
    total_hours_week = float(weekly_row['h'] or 0) if weekly_row else 0.0

    # Weekly variants for the Weekly Report screen. top_games above is the all-time
    # leaderboard ("most played"); the weekly screen needs THIS week's games and the
    # real session count (it previously summed the all-time top-5's sessions).
    c.execute('''SELECT game_name AS game, COUNT(*) AS sessions,
                 ROUND(SUM(duration_seconds)/3600.0,2) AS hours
                 FROM sessions WHERE user_id=? AND start_time>=? GROUP BY game_name
                 ORDER BY hours DESC LIMIT 5''', (user_id, since7))
    top_games_week = [dict(r) for r in c.fetchall()]
    c.execute('SELECT COUNT(*) AS n FROM sessions WHERE user_id=? AND start_time>=?',
              (user_id, since7))
    week_session_count = c.fetchone()['n']

    # Late-night count — last 7 days (it sits beside "Weekly hours" in the app header,
    # so it must cover the same window), evaluated in the child's local time (see
    # _tz_shift_min) so a UTC-hosted server still counts a 23:00-IST session.
    tz_shift = _tz_shift_min(c, user_id)
    c.execute('SELECT start_time FROM sessions WHERE user_id=? AND start_time>=?',
              (user_id, since7))
    late_night = 0
    for r in c.fetchall():
        try:
            if r['start_time'] and _is_late_night(_parse_ts(r['start_time']), tz_shift):
                late_night += 1
        except Exception:
            pass

    # Observation mode: has the child played enough sessions?
    c.execute('SELECT COUNT(*) AS n FROM sessions WHERE user_id=?', (user_id,))
    total_sessions   = c.fetchone()['n']
    observation_mode = total_sessions < 3

    # Hours per day for last 7 days (bar chart)
    today      = datetime.now().date()
    daily_hours_week = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        c.execute('''SELECT COALESCE(ROUND(SUM(duration_seconds)/3600.0, 2), 0.0) AS hours
                     FROM sessions WHERE user_id=? AND SUBSTR(start_time,1,10)=?''',
                  (user_id, day.isoformat()))
        row = c.fetchone()
        daily_hours_week.append({
            'date':  day.isoformat(),
            'day':   day.strftime('%a'),
            'hours': float(row['hours'] or 0),
        })

    # Unread alerts
    c.execute('SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC LIMIT 20', (user_id,))
    alert_rows = [dict(r) for r in c.fetchall()]
    formatted_alerts = [{'id': a['id'], 'type': a['type'], 'message': a['message'],
                          'severity': a['severity'], 'created_at': a['created_at'],
                          'read': bool(a['read'])} for a in alert_rows]

    # Streak data
    c.execute('SELECT * FROM streaks WHERE user_id=?', (user_id,))
    srow = c.fetchone()
    streak_data = dict(srow) if srow else {'current_streak': 0, 'longest_streak': 0, 'total_healthy_days': 0}

    # Explainable risk: top factors from latest prediction's behavioral row
    risk_explanation = []
    c.execute('''SELECT p.session_id FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    latest_pred_sess = c.fetchone()
    if latest_pred_sess:
        c.execute('SELECT * FROM behavioral_data WHERE session_id=? ORDER BY id DESC LIMIT 1',
                  (latest_pred_sess['session_id'],))
        brow = c.fetchone()
        if brow:
            risk_explanation = _shap_explain_behavior({f: float(brow[f] or 0) for f in BEHAVIORAL_FEATURES})

    # Latest prediction's game genre
    c.execute('''SELECT p.final_risk_score FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    lp = c.fetchone()

    # Which signals fed the latest prediction, so the UI can say "Chat: not captured
    # for this game" rather than showing a misleading 0%. NULL flags (legacy rows)
    # are reported as None → the app simply omits the breakdown for those.
    c.execute('''SELECT p.behavior_present, p.chat_present, p.voice_present
                 FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    sig_row = c.fetchone()
    if sig_row and sig_row['behavior_present'] is not None:
        latest_signals = {
            'behavior': bool(sig_row['behavior_present']),
            'chat':     bool(sig_row['chat_present']),
            'voice':    bool(sig_row['voice_present']),
        }
    else:
        latest_signals = None
    # The headline is per-day, so report which signals were analysed across the WHOLE day
    # (union), not just the last session — otherwise a short final session could hide that
    # chat/voice were captured earlier the same day.
    if daily_signals is not None:
        latest_signals = daily_signals

    # Child age for personalised suggestions
    child_age = profile.get('age', 15) or 15
    risk_level = latest.get('risk_category', 'casual')

    sleep_impact = _sleep_impact_analysis(user_id, conn)

    # Time limit suggestion + peer comparison
    time_limit   = _suggest_time_limit(total_hours_week, risk_level, child_age)
    peer_comp    = _peer_comparison(total_hours_week, child_age)

    # Saved parent-set limit
    c.execute('SELECT daily_limit_hours FROM time_limits WHERE user_id=?', (user_id,))
    tlrow = c.fetchone()
    parent_set_limit = float(tlrow['daily_limit_hours']) if tlrow else None

    conn.close()

    recs = _build_recommendations(risk_level)

    # Anomaly detection (refreshed on every dashboard fetch)
    try:
        _detect_anomalies(user_id)
        ac = get_db()
        arow = ac.execute('''
            SELECT message, severity, z_score FROM anomalies
            WHERE user_id = ? AND resolved = 0
            ORDER BY detected_at DESC LIMIT 1
        ''', (user_id,)).fetchone()
        top_anomaly = dict(arow) if arow else None
    except Exception:
        top_anomaly = None

    return jsonify({
        'success':             True,
        'child_name':          profile.get('name', 'Your Child'),
        'current_risk':        risk_level,
        'risk_label':          RISK_DISPLAY.get(risk_level, risk_level),
        'disclaimer':          SCREENING_DISCLAIMER,
        'risk_score':          latest.get('final_risk_score', 0.0),
        'alerts':              formatted_alerts,
        'trend_data':          trend,
        'top_games':           top_games,
        'top_games_week':      top_games_week,
        'week_session_count':  week_session_count,
        'recent_games':        recent_games,
        'total_hours_week':    total_hours_week,
        'late_night_count':    late_night,
        'recommendations':     recs,
        'observation_mode':    observation_mode,
        'sessions_analyzed':   total_sessions,
        'daily_hours_week':    daily_hours_week,
        # New enriched fields
        'time_limit_suggestion': time_limit,
        'peer_comparison':       peer_comp,
        'sleep_impact':          sleep_impact,
        'risk_explanation':      risk_explanation,
        'risk_period':           risk_period,
        'streak':                streak_data,
        'parent_set_limit':      parent_set_limit,
        'top_anomaly':           top_anomaly,
        'latest_signals':        latest_signals,
        'monitoring':            monitoring,
        'live_status':           live_status,
    })


@app.route('/api/dashboard/emotions', methods=['GET'])
def emotion_dashboard():
    """Emotion analytics for parental insight screen."""
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    since   = (datetime.now() - timedelta(days=30)).isoformat()
    conn    = get_db()
    c       = conn.cursor()

    # Emotion distribution
    c.execute('''SELECT ve.emotion, COUNT(*) AS n, ROUND(AVG(ve.intensity),3) AS avg_intensity
                 FROM voice_events ve JOIN sessions s ON s.session_id=ve.session_id
                 WHERE s.user_id=? AND s.start_time>=?
                 GROUP BY ve.emotion ORDER BY n DESC''', (user_id, since))
    dist = [dict(r) for r in c.fetchall()]

    # Dominant emotion per session
    c.execute('''SELECT s.game_name, s.start_time,
                 (SELECT ve2.emotion FROM voice_events ve2
                  WHERE ve2.session_id=s.session_id
                  GROUP BY ve2.emotion ORDER BY COUNT(*) DESC LIMIT 1) AS dominant_emotion
                 FROM sessions s WHERE s.user_id=? AND s.start_time>=?
                 ORDER BY s.start_time DESC LIMIT 10''', (user_id, since))
    recent = [dict(r) for r in c.fetchall()]

    # Correlation: angry/frustrated emotions vs risk score
    c.execute('''SELECT s.final_risk_score,
                 SUM(CASE WHEN ve.emotion IN ('angry','frustrated') THEN 1 ELSE 0 END) AS stress_events,
                 COUNT(ve.id) AS total_events
                 FROM sessions s JOIN voice_events ve ON ve.session_id=s.session_id
                 WHERE s.user_id=? AND s.final_risk_score IS NOT NULL
                 GROUP BY s.session_id ORDER BY s.start_time DESC LIMIT 20''', (user_id,))
    correlation = [dict(r) for r in c.fetchall()]

    conn.close()
    return jsonify({
        'success':           True,
        'emotion_distribution': dist,
        'recent_sessions':      recent,
        'risk_correlation':     correlation,
    })


@app.route('/api/dashboard/chat_analysis', methods=['GET'])
def chat_analysis_dashboard():
    """Chat analytics for parental insight screen."""
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    since   = (datetime.now() - timedelta(days=30)).isoformat()
    conn    = get_db()
    c       = conn.cursor()

    # Total messages and average toxicity
    c.execute('''SELECT COUNT(*) AS total_messages,
                 ROUND(AVG(cm.confidence),3) AS avg_toxicity
                 FROM chat_messages cm JOIN sessions s ON s.session_id=cm.session_id
                 WHERE s.user_id=? AND cm.timestamp>=?''', (user_id, since))
    stats = dict(c.fetchone() or {})

    # Recent chat samples. cm.source tells the parent whether a line was typed in-game
    # ('keyboard'/'ocr') or transcribed from speech ('voice_stt').
    c.execute('''SELECT cm.message, cm.confidence, cm.source, cm.timestamp, s.game_name
                 FROM chat_messages cm JOIN sessions s ON s.session_id=cm.session_id
                 WHERE s.user_id=? ORDER BY cm.timestamp DESC LIMIT 20''', (user_id,))
    messages = [dict(r) for r in c.fetchall()]

    conn.close()

    # Toxicity label distribution — same bands the rest of the system uses ('toxic'
    # at the alert threshold, 'borderline' at 0.4; see analyse_chat), so this screen
    # can't call a message concerning that would never have raised an alert.
    high_tox  = sum(1 for m in messages if float(m.get('confidence') or 0) >= CHAT_ALERT_T)
    mid_tox   = sum(1 for m in messages if 0.4 <= float(m.get('confidence') or 0) < CHAT_ALERT_T)
    safe_msg  = len(messages) - high_tox - mid_tox

    return jsonify({
        'success':     True,
        'stats':       stats,
        'toxicity_distribution': {'high': high_tox, 'medium': mid_tox, 'safe': safe_msg},
        'recent_messages': messages,
    })


def _check_heartbeat(c, user_id):
    """If the child app has gone silent past the threshold, raise ONE 'offline' alert to the
    parent (covers uninstall / force-stop / killed-from-recents / offline). Caller commits.
    Best-effort: never raises into the request."""
    try:
        c.execute("SELECT last_seen, offline_alerted, name, tz_offset_min FROM users WHERE user_id=?",
                  (user_id,))
        row = c.fetchone()
        if not row or not row['last_seen']:
            return                  # never heartbeated (old app / not set up yet) — nothing to judge
        last = datetime.fromisoformat(str(row['last_seen']).replace(' ', 'T').split('+')[0].split('Z')[0])
        silent_min = (datetime.now() - last).total_seconds() / 60.0
        if silent_min < HEARTBEAT_SILENT_MIN or row['offline_alerted']:
            return
        # Quiet hours: if we know the child's timezone, don't alarm overnight (the phone is
        # almost certainly just off/asleep). Skip WITHOUT setting the flag, so the alert
        # still fires in the morning if the app is genuinely gone. Unknown tz → alert normally.
        tz = row['tz_offset_min']
        if tz is not None:
            child_hour = (datetime.utcnow() + timedelta(minutes=int(tz))).hour
            if child_hour >= HEARTBEAT_QUIET_START or child_hour < HEARTBEAT_QUIET_END:
                return
        nm  = row['name'] or 'Your child'
        dur = f"{int(silent_min // 60)} hours" if silent_min >= 120 else f"{int(silent_min)} min"
        msg = (f"{nm}'s monitoring app hasn't checked in for {dur} — it may be offline, "
               f"powered off, or have been closed/uninstalled.")
        _insert_alert(c, user_id, 'offline', msg, 'high')
        c.execute("UPDATE users SET offline_alerted=1 WHERE user_id=?", (user_id,))
        # Push instantly — "monitoring went silent" (incl. a plain uninstall, where there
        # is no client callback) is exactly the alert a parent must not have to be polling
        # to receive.
        _push_to_user_family(c, user_id, "Monitoring went silent", msg)
    except Exception as e:
        logger.warning(f"heartbeat check skipped: {e}")


@app.route('/api/child/heartbeat', methods=['POST'])
def child_heartbeat():
    """Child app liveness ping (~every 5 min). Re-arms the watchdog for the next outage and
    records the device's UTC offset so the watchdog can apply child-local quiet hours."""
    data = request.get_json() or {}
    try:
        uid = int(data.get('user_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    deny = guard(uid)
    if deny: return deny
    try:
        tz = int(data.get('tz_offset_min'))
    except (TypeError, ValueError):
        tz = None
    # Whether the child has enabled Device Admin (instant uninstall-attempt alert). Lets
    # the parent see their actual protection level rather than assuming it's on.
    da = data.get('device_admin')
    da = (1 if int(da) else 0) if da is not None else None
    conn = get_db()
    c    = conn.cursor()
    # COALESCE keeps a previously-stored value if this ping omitted the field.
    c.execute("UPDATE users SET last_seen=?, offline_alerted=0, "
              "tz_offset_min=COALESCE(?, tz_offset_min), "
              "device_admin_active=COALESCE(?, device_admin_active) "
              "WHERE user_id=?",
              (datetime.now().isoformat(), tz, da, int(uid)))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/child/tamper', methods=['POST'])
def child_tamper():
    """A child-initiated event the parent should know about (currently: logout)."""
    data  = request.get_json() or {}
    uid   = data.get('user_id')
    event = str(data.get('event', '')).strip()
    deny  = guard(uid)
    if deny: return deny
    messages = {
        'logout':        "logged out of the monitoring app",
        'admin_disable': "is trying to remove monitoring (turning off device administrator)",
    }
    if event not in messages:
        return jsonify({'success': False, 'message': 'unknown event'}), 400
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT name FROM users WHERE user_id=?", (int(uid),))
    r  = c.fetchone()
    nm = r['name'] if (r and r['name']) else 'Your child'
    _insert_alert(c, int(uid), 'tamper', f"{nm} {messages[event]}.", 'high')
    # Tamper is time-critical (the child may be uninstalling now) — push instantly so the
    # parent doesn't have to wait for the next poll.
    _push_to_user_family(c, int(uid), "Monitoring alert", f"{nm} {messages[event]}.")
    if event == 'logout':
        # The silence that follows is EXPLAINED, so: clear last_seen so the parent
        # dashboard stops claiming "monitoring active" off a heartbeat that would
        # otherwise look fresh for ~10 more minutes, and so the watchdog doesn't
        # later pile a redundant "gone silent" alert on top of this logout alert.
        c.execute("UPDATE users SET last_seen=NULL WHERE user_id=?", (int(uid),))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/verify_parent_pin', methods=['POST'])
@limiter.limit("6 per minute")
def verify_parent_pin():
    """Verify the family parent PIN so the child app can gate logout/settings behind it —
    without the child ever knowing the PIN (checked server-side against the stored hash)."""
    data = request.get_json() or {}
    uid  = data.get('user_id')
    pin  = str(data.get('pin', '')).strip()
    deny = guard(uid)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT parent_pin_hash FROM users WHERE user_id=?", (int(uid),))
    row = c.fetchone()
    conn.close()
    valid = bool(row and verify_pin(pin, row['parent_pin_hash']))   # constant-time compare
    return jsonify({'success': True, 'valid': valid})


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()
    _check_heartbeat(c, user_id)   # raise an 'offline' alert if the child app went silent
    conn.commit()
    c.execute('''SELECT a.*, f.label AS feedback_label
                 FROM alerts a
                 LEFT JOIN feedback f ON f.alert_id = a.id
                 WHERE a.user_id=? ORDER BY a.created_at DESC LIMIT 50''', (user_id,))
    rows    = [dict(r) for r in c.fetchall()]
    conn.close()
    unread  = sum(1 for r in rows if not r['read'])

    def _age_min(ts):
        """Alert age in minutes, computed server-side so the phone can render an
        accurate '2h ago' without knowing the server's timezone (created_at is
        server-local; diffing it against device time would be off by the tz gap)."""
        try:
            return max(0, int((datetime.now() - _parse_ts(ts)).total_seconds() // 60))
        except Exception:
            return None

    alerts  = [{'id': r['id'], 'type': r['type'], 'message': r['message'],
                'severity': r['severity'], 'created_at': r['created_at'],
                'age_minutes': _age_min(r['created_at']),
                'read': bool(r['read']), 'feedback': r.get('feedback_label')} for r in rows]
    return jsonify({'success': True, 'alerts': alerts, 'unread_count': unread})


@app.route('/api/alerts/mark_read', methods=['POST'])
def mark_alerts_read():
    data      = request.get_json() or {}
    alert_ids = data.get('alert_ids', [])
    deny = guard()   # require a valid token in enforce mode; populates g.auth
    if deny: return deny
    if not alert_ids:
        return jsonify({'success': True, 'message': 'Nothing to mark'})
    conn = get_db()
    c    = conn.cursor()
    ph   = ','.join(['?'] * len(alert_ids))
    allowed = (g.auth or {}).get('allowed')
    if allowed:
        # Only mark alerts owned by a user this caller is allowed to access.
        aph = ','.join(['?'] * len(allowed))
        c.execute(f'UPDATE alerts SET read=1 WHERE id IN ({ph}) AND user_id IN ({aph})',
                  list(alert_ids) + list(allowed))
    else:
        c.execute(f'UPDATE alerts SET read=1 WHERE id IN ({ph})', alert_ids)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Marked {len(alert_ids)} alerts read'})


# Parent verdicts the model can learn from. accurate/false_alarm are the calibration
# signal; too_sensitive/too_late capture timing complaints.
FEEDBACK_LABELS = {'accurate', 'false_alarm', 'too_sensitive', 'too_late'}


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """A parent's verdict on the model's output ('was this right?'). The only source of
    REAL labels in the system — everything else is synthetic — so this is what a future
    retrain or threshold-tune should learn from. We snapshot the child's latest model
    category + score so each label stays interpretable even after the model changes."""
    data     = request.get_json() or {}
    label    = (data.get('label') or '').strip().lower()
    alert_id = data.get('alert_id')
    note     = ((data.get('note') or '').strip()[:500]) or None
    if label not in FEEDBACK_LABELS:
        return jsonify({'success': False,
                        'message': f'label must be one of {sorted(FEEDBACK_LABELS)}'}), 400

    conn = get_db()
    c    = conn.cursor()

    # Which child is this about? Prefer an explicit user_id; otherwise derive from the alert.
    user_id = data.get('user_id')
    if user_id is None and alert_id is not None:
        c.execute('SELECT user_id FROM alerts WHERE id=?', (alert_id,))
        arow = c.fetchone()
        if arow:
            user_id = arow['user_id']
    if user_id is None:
        conn.close()
        return jsonify({'success': False, 'message': 'user_id or a valid alert_id is required'}), 400
    user_id = int(user_id)

    deny = guard(user_id)
    if deny:
        conn.close()
        return deny

    # Snapshot the model's most recent verdict for this child (retraining context).
    c.execute('''SELECT p.id, p.risk_category, p.final_risk_score
                 FROM predictions p JOIN sessions s ON p.session_id = s.session_id
                 WHERE s.user_id=? ORDER BY p.id DESC LIMIT 1''', (user_id,))
    prow     = c.fetchone()
    pred_id  = prow['id'] if prow else None
    pred_cat = prow['risk_category'] if prow else None
    pred_sc  = float(prow['final_risk_score']) if prow and prow['final_risk_score'] is not None else None

    # One verdict per alert: a re-submission replaces the earlier one.
    if alert_id is not None:
        c.execute('DELETE FROM feedback WHERE alert_id=?', (alert_id,))

    c.execute('''INSERT INTO feedback (user_id, alert_id, prediction_id, label,
                                       risk_category, risk_score, note)
                 VALUES (?,?,?,?,?,?,?)''',
              (user_id, alert_id, pred_id, label, pred_cat, pred_sc, note))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Feedback recorded', 'label': label})


@app.route('/api/feedback/summary', methods=['GET'])
def feedback_summary():
    """Aggregate of parent verdicts for a child — the model-credibility / drift view.
    agreement_rate = accurate / (accurate + false_alarm): a real-world precision proxy
    built from genuine labels, unlike the synthetic test-set metrics in the model card."""
    user_id = request.args.get('user_id', type=int)
    if user_id is None:
        return jsonify({'success': False, 'message': 'user_id is required'}), 400
    deny = guard(user_id)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute('SELECT label, COUNT(*) AS n FROM feedback WHERE user_id=? GROUP BY label', (user_id,))
    counts = {r['label']: int(r['n']) for r in c.fetchall()}
    c.execute('''SELECT label, risk_category, risk_score, note, created_at
                 FROM feedback WHERE user_id=? ORDER BY id DESC LIMIT 10''', (user_id,))
    recent = [dict(r) for r in c.fetchall()]
    conn.close()
    total = sum(counts.values())
    acc   = counts.get('accurate', 0)
    fa    = counts.get('false_alarm', 0)
    agreement = round(acc / (acc + fa), 3) if (acc + fa) else None
    return jsonify({'success': True, 'user_id': user_id, 'total': total,
                    'counts': counts, 'agreement_rate': agreement, 'recent': recent})


@app.route('/api/child/status', methods=['GET'])
def child_status():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()

    # Self-heal any session orphaned by a lost end-event, so the parent view doesn't
    # show the child "playing" indefinitely.
    _close_stale_sessions(c, user_id)
    conn.commit()

    # Check if currently in an active (not-ended) session
    c.execute('''SELECT session_id, game_name, start_time
                 FROM sessions WHERE user_id=? AND end_time IS NULL
                 ORDER BY session_id DESC LIMIT 1''', (user_id,))
    active = c.fetchone()

    # Latest prediction
    c.execute('''SELECT p.risk_category, p.final_risk_score
                 FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    pred_row = c.fetchone()
    conn.close()

    if active:
        start   = datetime.fromisoformat(active['start_time'])
        dur_min = int((datetime.now() - start).total_seconds() / 60)
        return jsonify({
            'success':              True,
            'is_playing':           True,
            'current_game':         active['game_name'],
            'session_duration_mins': dur_min,
            'current_risk':         pred_row['risk_category'] if pred_row else 'unknown',
            'risk_score':           pred_row['final_risk_score'] if pred_row else 0.0,
        })
    return jsonify({
        'success':    True,
        'is_playing': False,
        'current_game': None,
        'session_duration_mins': None,
        'current_risk': pred_row['risk_category'] if pred_row else 'unknown',
        'risk_score':   pred_row['final_risk_score'] if pred_row else 0.0,
    })

# ─────────────── GAMES LIST ──────────────────────────────────────

GAMES = [
    {'name': 'PUBG Mobile',   'icon': 'pubg',    'genre': 'Battle Royale', 'has_voice': True,  'has_chat': True},
    {'name': 'BGMI',          'icon': 'bgmi',    'genre': 'Battle Royale', 'has_voice': True,  'has_chat': True},
    {'name': 'COD Mobile',    'icon': 'cod',     'genre': 'FPS',           'has_voice': True,  'has_chat': True},
    {'name': 'Fortnite',      'icon': 'fortnite','genre': 'Battle Royale', 'has_voice': True,  'has_chat': True},
    {'name': 'Valorant',      'icon': 'valorant','genre': 'FPS',           'has_voice': True,  'has_chat': True},
    {'name': 'CS2',           'icon': 'cs2',     'genre': 'FPS',           'has_voice': True,  'has_chat': True},
    {'name': 'Clash of Clans','icon': 'coc',     'genre': 'Strategy',      'has_voice': False, 'has_chat': True},
    {'name': 'Roblox',        'icon': 'roblox',  'genre': 'Sandbox',       'has_voice': True,  'has_chat': True},
    {'name': 'Minecraft',     'icon': 'minecraft','genre': 'Sandbox',      'has_voice': True,  'has_chat': True},
    {'name': 'Candy Crush',   'icon': 'candy',   'genre': 'Casual',        'has_voice': False, 'has_chat': False},
    {'name': 'Sudoku',        'icon': 'sudoku',  'genre': 'Casual',        'has_voice': False, 'has_chat': False},
    {'name': 'Free Fire',     'icon': 'freefire','genre': 'Battle Royale', 'has_voice': True,  'has_chat': True},
    {'name': 'Clash Royale',  'icon': 'cr',      'genre': 'Strategy',      'has_voice': False, 'has_chat': True},
]


@app.route('/api/games', methods=['GET'])
def get_games():
    games_with_ids = [{'id': i+1, 'name': g['name'], 'package_name': None,
                       'icon_url': None, **g} for i, g in enumerate(GAMES)]
    return jsonify({'success': True, 'games': games_with_ids})

# ─────────────── PAIRING ─────────────────────────────────────────

# Device pairing (pair-by-user-id) was removed: parents now link to their children
# via the family code at login, which is authenticated and collision-free. The old
# /api/pair (unauthenticated) and /api/pair/info endpoints are gone.


# ─────────────── WEEKLY REPORT ───────────────────────────────────

@app.route('/api/dashboard/weekly_report', methods=['GET'])
def weekly_report():
    """7-day breakdown for parental weekly report screen."""
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    since7  = (datetime.now() - timedelta(days=7)).isoformat()
    since14 = (datetime.now() - timedelta(days=14)).isoformat()
    conn    = get_db()
    c       = conn.cursor()

    # Sessions this week
    c.execute('''SELECT session_id, game_name, start_time, duration_seconds,
                 final_risk_score, risk_category
                 FROM sessions WHERE user_id=? AND start_time>=? ORDER BY start_time DESC''',
              (user_id, since7))
    week_sessions = [dict(r) for r in c.fetchall()]

    week_hours = sum((s['duration_seconds'] or 0) for s in week_sessions) / 3600.0
    avg_daily  = week_hours / 7.0
    tz_shift   = _tz_shift_min(c, user_id)
    late_count = sum(1 for s in week_sessions
                     if _is_late_night(datetime.fromisoformat(s['start_time']), tz_shift))

    # Top games this week
    game_agg = {}
    for s in week_sessions:
        g = s['game_name']
        if g not in game_agg:
            game_agg[g] = {'sessions': 0, 'hours': 0.0}
        game_agg[g]['sessions'] += 1
        game_agg[g]['hours']    += (s['duration_seconds'] or 0) / 3600.0
    top_games = sorted(
        [{'game': k, 'sessions': v['sessions'], 'hours': round(v['hours'], 2)}
         for k, v in game_agg.items()],
        key=lambda x: x['hours'], reverse=True
    )[:5]

    # 14-day trend
    c.execute(f'''SELECT SUBSTR(start_time,1,10) AS date,
                 ROUND(AVG(final_risk_score),4) AS score,
                 (CASE WHEN AVG(final_risk_score) < {RISK_T1} THEN 'casual'
                       WHEN AVG(final_risk_score) < {RISK_T2} THEN 'at_risk'
                       ELSE 'addicted' END) AS label
                 FROM sessions WHERE user_id=? AND start_time>=? AND final_risk_score IS NOT NULL
                 GROUP BY date ORDER BY date ASC''',
              (user_id, since14))
    trend = [dict(r) for r in c.fetchall()]

    # Latest risk
    c.execute('''SELECT p.risk_category, p.final_risk_score FROM predictions p
                 JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    lrow = c.fetchone()
    conn.close()

    current_risk  = lrow['risk_category']  if lrow else 'casual'
    current_score = lrow['final_risk_score'] if lrow else 0.0

    return jsonify({
        'success':           True,
        'week_hours':        round(week_hours, 2),
        'avg_daily_hours':   round(avg_daily, 2),
        'session_count':     len(week_sessions),
        'late_night_count':  late_count,
        'current_risk':      current_risk,
        'risk_score':        current_score,
        'top_games':         top_games,
        'trend_data':        trend,
        'recommendations':   _build_recommendations(current_risk),
    })

# ─────────────── SCREEN EVENTS ───────────────────────────────────

@app.route('/api/child/screen_event', methods=['POST'])
def save_screen_event():
    """Receive screen on/off/unlock events from the child's device."""
    data = request.get_json() or {}
    user_id    = data.get('user_id')
    event_type = str(data.get('event_type', '')).strip()
    if not user_id or event_type not in ('screen_on', 'screen_off', 'unlocked'):
        return jsonify({'error': 'user_id and valid event_type required'}), 400
    deny = guard(user_id)
    if deny: return deny
    ts = data.get('timestamp')
    if ts:
        try:
            ts = datetime.fromtimestamp(int(ts) / 1000).isoformat()
        except Exception:
            ts = datetime.now().isoformat()
    else:
        ts = datetime.now().isoformat()
    conn = get_db()
    c    = conn.cursor()
    c.execute('INSERT INTO screen_events (user_id, event_type, timestamp) VALUES (?,?,?)',
              (int(user_id), event_type, ts))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─────────────── NOTIFICATION EVENTS ─────────────────────────────

@app.route('/api/child/notification_event', methods=['POST'])
def save_notification_event():
    """Receive game notification events — direct craving signal."""
    data     = request.get_json() or {}
    user_id  = data.get('user_id')
    pkg      = str(data.get('package_name', '')).strip()
    if not user_id or not pkg:
        return jsonify({'error': 'user_id and package_name required'}), 400
    deny = guard(user_id)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute('''INSERT INTO notification_events
                 (user_id, package_name, game_name, notification_title, timestamp)
                 VALUES (?,?,?,?,?)''',
              (int(user_id), pkg,
               str(data.get('game_name', '')),
               str(data.get('notification_title', ''))[:120],
               datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─────────────── CHILD STREAK ────────────────────────────────────

@app.route('/api/child/streak', methods=['GET'])
def get_streak():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()
    c.execute('SELECT * FROM streaks WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'success': True, 'current_streak': 0, 'longest_streak': 0,
                        'total_healthy_days': 0, 'is_healthy_today': False,
                        'badge': 'none', 'message': 'Start gaming healthily to build your streak!'})

    row  = dict(row)
    cur  = row['current_streak']
    best = row['longest_streak']
    total = row['total_healthy_days']

    # Badge tier
    if cur >= 30:   badge = 'gold';   badge_label = 'Gold — 30-day streak!'
    elif cur >= 14: badge = 'silver'; badge_label = 'Silver — 2-week streak!'
    elif cur >= 7:  badge = 'bronze'; badge_label = 'Bronze — 1-week streak!'
    elif cur >= 3:  badge = 'starter';badge_label = f'{cur}-day streak going!'
    else:           badge = 'none';   badge_label = 'Keep gaming healthily to start a streak'

    msg = (f"You've maintained healthy gaming for {cur} day{'s' if cur != 1 else ''}! "
           f"Best streak: {best} days. Total healthy days: {total}.")

    return jsonify({'success': True, 'current_streak': cur, 'longest_streak': best,
                    'total_healthy_days': total, 'badge': badge, 'badge_label': badge_label,
                    'message': msg})


# ─────────────── PARENT TIME LIMIT SETTER ────────────────────────

@app.route('/api/parent/children', methods=['GET'])
def parent_children():
    """List the children in the authenticated parent's family so the parent app can switch
    between them WITHOUT re-entering the family code. The bearer token already carries the
    allowed child ids (set at login), so no family code/PIN is needed here."""
    deny = guard()                       # authenticate; populates g.auth {role, uid, allowed}
    if deny: return deny
    allowed = (g.auth or {}).get('allowed') or []
    if not allowed:
        return jsonify({'success': True, 'children': []})
    conn = get_db()
    c    = conn.cursor()
    ph   = ','.join(['?'] * len(allowed))
    c.execute(f'SELECT user_id, name, age FROM users WHERE user_id IN ({ph}) ORDER BY user_id',
              tuple(allowed))
    children = [{'user_id': r['user_id'], 'name': r['name'], 'age': r['age']} for r in c.fetchall()]
    conn.close()
    return jsonify({'success': True, 'children': children})


@app.route('/api/parent/set_limit', methods=['POST'])
def set_time_limit():
    """Parent approves or sets a daily gaming time limit for a child."""
    data    = request.get_json() or {}
    user_id = data.get('user_id')
    deny = guard(user_id)
    if deny: return deny
    hours   = data.get('daily_limit_hours')
    if not user_id or hours is None:
        return jsonify({'success': False, 'message': 'user_id and daily_limit_hours required'}), 400
    try:
        hours = float(hours)
        if hours < 0 or hours > 24:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'daily_limit_hours must be 0–24'}), 400
    conn = get_db()
    c    = conn.cursor()
    c.execute('''INSERT INTO time_limits (user_id, daily_limit_hours, set_by_parent, updated_at)
                 VALUES (?,?,1,?)
                 ON CONFLICT(user_id) DO UPDATE SET daily_limit_hours=excluded.daily_limit_hours,
                 set_by_parent=1, updated_at=excluded.updated_at''',
              (int(user_id), hours, datetime.now().isoformat()))
    # Notify the CHILD — the message is addressed to the child, and the child app reads
    # child_nudges (the alerts table is the PARENT's feed, so writing it there meant the
    # parent saw a message meant for the child). Keep only the latest pending limit nudge
    # so repeated edits don't stack.
    c.execute("DELETE FROM child_nudges WHERE user_id=? AND kind='limit' AND delivered=0",
              (int(user_id),))
    c.execute("INSERT INTO child_nudges (user_id, message, kind) VALUES (?,?,?)",
              (int(user_id),
               f'Your parent set a {hours:.1f}h daily gaming limit. Keep an eye on your playtime!',
               'limit'))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'daily_limit_hours': hours})


@app.route('/api/parent/nudge', methods=['POST'])
def send_nudge():
    """Parent sends a one-off nudge that pops up as a notification on the child's phone
    (e.g. 'time for a break', 'please watch your language', or a custom message)."""
    data    = request.get_json() or {}
    user_id = data.get('user_id')
    deny = guard(user_id)
    if deny: return deny
    message = (str(data.get('message') or '').strip())[:200]
    if not user_id or not message:
        return jsonify({'success': False, 'message': 'user_id and message required'}), 400
    conn = get_db()
    c    = conn.cursor()
    c.execute("INSERT INTO child_nudges (user_id, message, kind) VALUES (?,?,?)",
              (int(user_id), message, 'parent'))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Nudge sent'})


@app.route('/api/child/nudges', methods=['GET'])
def get_nudges():
    """Child app polls for undelivered nudges; returns them and marks them delivered so
    each pops up exactly once."""
    user_id = request.args.get('user_id', type=int)
    if user_id is None:
        return jsonify({'success': False, 'message': 'user_id is required'}), 400
    deny = guard(user_id)
    if deny: return deny
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT id, message, kind, created_at FROM child_nudges "
              "WHERE user_id=? AND delivered=0 ORDER BY id ASC LIMIT 10", (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    if rows:
        ids = [r['id'] for r in rows]
        ph  = ','.join(['?'] * len(ids))
        c.execute(f"UPDATE child_nudges SET delivered=1 WHERE id IN ({ph})", ids)
        conn.commit()
    conn.close()
    return jsonify({'success': True, 'nudges': rows})


@app.route('/api/child/get_limit', methods=['GET'])
def get_time_limit():
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()
    c.execute('SELECT daily_limit_hours, updated_at FROM time_limits WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'success': True, 'daily_limit_hours': None, 'has_limit': False})
    return jsonify({'success': True, 'daily_limit_hours': float(row['daily_limit_hours']),
                    'has_limit': True, 'updated_at': row['updated_at']})


# ─────────────── ENRICHED CHILD DASHBOARD ────────────────────────

@app.route('/api/dashboard/child_enriched', methods=['GET'])
def child_dashboard_enriched():
    """User dashboard + streak + time limit + self-awareness message."""
    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()

    # Streak
    c.execute('SELECT * FROM streaks WHERE user_id=?', (user_id,))
    srow   = c.fetchone()
    streak = dict(srow) if srow else {'current_streak': 0, 'longest_streak': 0, 'total_healthy_days': 0}

    # Time limit
    c.execute('SELECT daily_limit_hours FROM time_limits WHERE user_id=?', (user_id,))
    tlrow = c.fetchone()
    daily_limit = float(tlrow['daily_limit_hours']) if tlrow else None

    # Today's hours
    today_iso = datetime.now().date().isoformat()
    c.execute('''SELECT COALESCE(ROUND(SUM(duration_seconds)/3600.0,2),0) AS h
                 FROM sessions WHERE user_id=? AND SUBSTR(start_time,1,10)=? AND end_time IS NOT NULL''',
              (user_id, today_iso))
    today_h = float(c.fetchone()['h'] or 0)
    conn.close()

    cur = streak['current_streak']
    if cur >= 14:
        self_msg = f"Amazing! {cur}-day healthy gaming streak. You're in control!"
    elif cur >= 7:
        self_msg = f"Great job! {cur} days of balanced gaming. Keep it up!"
    elif cur >= 3:
        self_msg = f"{cur}-day streak — you're building great habits!"
    else:
        self_msg = "Game smart. Stay under your daily limit to start a healthy streak."

    limit_status = None
    if daily_limit:
        remaining = max(0.0, daily_limit - today_h)
        limit_status = {
            'daily_limit_hours':   daily_limit,
            'used_today_hours':    round(today_h, 2),
            'remaining_hours':     round(remaining, 2),
            'exceeded':            today_h > daily_limit,
        }

    # Always expose today's play time + a goal (the parent's limit, else a gentle
    # default) so the child's home can show self-awareness even with no limit set.
    DEFAULT_GOAL_HOURS = 2.0
    goal = daily_limit if daily_limit else DEFAULT_GOAL_HOURS
    return jsonify({
        'success':          True,
        'streak':           streak,
        'limit_status':     limit_status,
        'played_today_hours': round(today_h, 2),
        'daily_goal_hours':   round(goal, 2),
        'goal_is_parent_set': bool(daily_limit),
        'self_awareness_message': self_msg,
    })


# ─────────────── PDF WEEKLY REPORT ───────────────────────────────

def _latin1(text):
    """Make text safe for FPDF core (latin-1) fonts: map common Unicode punctuation
    to ASCII and drop anything else (e.g. emoji) so PDF generation never crashes."""
    s = str(text)
    for k, v in {'—': '-', '–': '-', '’': "'", '‘': "'",
                 '“': '"', '”': '"', '…': '...', '•': '*'}.items():
        s = s.replace(k, v)
    return s.encode('latin-1', 'ignore').decode('latin-1')


@app.route('/api/dashboard/weekly_report/pdf', methods=['GET'])
def weekly_report_pdf():
    """Generate and serve a PDF weekly report for the child."""
    import io
    from flask import send_file, make_response

    user_id = request.args.get('user_id', 1, type=int)
    deny = guard(user_id)
    if deny: return deny
    conn    = get_db()
    c       = conn.cursor()
    c.execute('SELECT name, age FROM users WHERE user_id=?', (user_id,))
    profile = dict(c.fetchone() or {})
    pdf_tz_shift = _tz_shift_min(c, user_id)   # child-local hours for the late-night stat

    since7 = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute('''SELECT session_id, game_name, start_time, duration_seconds,
                 final_risk_score, risk_category
                 FROM sessions WHERE user_id=? AND start_time>=? ORDER BY start_time DESC''',
              (user_id, since7))
    sessions = [dict(r) for r in c.fetchall()]

    c.execute('''SELECT p.risk_category, p.final_risk_score, p.behavior_score, p.chat_score, p.voice_score
                 FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? ORDER BY p.timestamp DESC LIMIT 1''', (user_id,))
    lp = c.fetchone()

    c.execute('SELECT * FROM streaks WHERE user_id=?', (user_id,))
    streak = c.fetchone()

    # Weekly model averages — average each channel only over sessions where it was present,
    # so absent-modality zeros don't drag the picture down. NULL = never captured this week.
    c.execute('''SELECT AVG(CASE WHEN behavior_present=1 THEN behavior_score END) AS b,
                        AVG(CASE WHEN chat_present=1     THEN chat_score     END) AS ch,
                        AVG(CASE WHEN voice_present=1    THEN voice_score    END) AS v
                 FROM predictions p JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=? AND s.start_time>=?''', (user_id, since7))
    mrow = dict(c.fetchone() or {})

    # Chat insights this week (chat_messages.timestamp is local isoformat, same as since7).
    c.execute('''SELECT COUNT(*) AS total,
                 SUM(CASE WHEN cm.confidence>=? THEN 1 ELSE 0 END) AS toxic
                 FROM chat_messages cm JOIN sessions s ON s.session_id=cm.session_id
                 WHERE s.user_id=? AND cm.timestamp>=?''', (CHAT_ALERT_T, user_id, since7))
    crow = dict(c.fetchone() or {})

    # Voice emotion distribution this week.
    c.execute('''SELECT ve.emotion AS emotion, COUNT(*) AS n
                 FROM voice_events ve JOIN sessions s ON s.session_id=ve.session_id
                 WHERE s.user_id=? AND ve.timestamp>=? GROUP BY ve.emotion ORDER BY n DESC''',
              (user_id, since7))
    voice_rows = [dict(r) for r in c.fetchall()]

    # Behavioural drivers (what's pushing the risk up/down) from the latest snapshot.
    c.execute('''SELECT bd.* FROM behavioral_data bd JOIN sessions s ON s.session_id=bd.session_id
                 WHERE s.user_id=? ORDER BY bd.id DESC LIMIT 1''', (user_id,))
    brow = c.fetchone()
    conn.close()

    drivers = []
    if brow:
        try:
            drivers = _shap_explain_behavior({f: float(brow[f] or 0) for f in BEHAVIORAL_FEATURES})[:3]
        except Exception:
            drivers = []

    week_hours  = sum((s['duration_seconds'] or 0) for s in sessions) / 3600.0
    late_count  = sum(1 for s in sessions
                      if _is_late_night(datetime.fromisoformat(s['start_time']), pdf_tz_shift))
    avg_daily   = week_hours / 7.0
    risk_level  = lp['risk_category'] if lp else 'casual'
    risk_score  = lp['final_risk_score'] if lp else 0.0
    peer_comp   = _peer_comparison(week_hours, profile.get('age', 15) or 15)
    time_lim    = _suggest_time_limit(week_hours, risk_level, profile.get('age', 15) or 15)
    recs        = _build_recommendations(risk_level)

    if not FPDF_AVAILABLE:
        return jsonify({'error': 'PDF generation not available on this server'}), 503

    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Header
    pdf.set_fill_color(33, 150, 243)
    pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_y(8)
    pdf.cell(0, 10, 'Gaming Health Weekly Report', align='C', ln=True)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d %b %Y')}  |  Child: {profile.get('name','Unknown')}  |  Age: {profile.get('age','?')}", align='C', ln=True)
    pdf.ln(10)

    # Risk summary box
    risk_color = {'casual': (76,175,80), 'at_risk': (255,152,0), 'addicted': (244,67,54)}.get(risk_level, (158,158,158))
    pdf.set_fill_color(*risk_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 24)
    pdf.cell(0, 16, risk_level.upper().replace('_',' '), align='C', fill=True, ln=True)
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, f"Risk Score: {risk_score*100:.0f}%   |   Peer Percentile: Top {peer_comp['percentile']}%", align='C', fill=True, ln=True)
    pdf.ln(6)

    # Stats table
    pdf.set_text_color(33, 33, 33)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'This Week At a Glance', ln=True)
    pdf.set_font('Helvetica', '', 11)
    stats = [
        ('Total Gaming Time',   f"{week_hours:.1f} hours"),
        ('Daily Average',       f"{avg_daily:.1f} hours/day"),
        ('Sessions Played',     str(len(sessions))),
        ('Late-Night Sessions', str(late_count)),
        ('Healthy Day Streak',  f"{streak['current_streak'] if streak else 0} days"),
        ('Suggested Daily Limit', f"{time_lim['suggested_daily_hours']:.1f} hours"),
    ]
    for label, value in stats:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(90, 7, label + ':', ln=False)
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(0, 7, value, ln=True)
    pdf.ln(4)

    # Top games this week
    games_week = {}
    for s in sessions:
        g = s['game_name'] or 'Unknown'
        e = games_week.setdefault(g, [0.0, 0])
        e[0] += (s['duration_seconds'] or 0) / 3600.0
        e[1] += 1
    top_games_week = sorted(games_week.items(), key=lambda kv: kv[1][0], reverse=True)[:5]
    if top_games_week:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.cell(0, 8, 'Top Games This Week', ln=True)
        pdf.set_font('Helvetica', '', 11)
        for g, (hrs, cnt) in top_games_week:
            pdf.set_x(pdf.l_margin)
            pdf.cell(95, 6, _latin1(f"  {g}"), ln=False)
            pdf.cell(0, 6, _latin1(f"{hrs:.1f} h  ({cnt} session{'s' if cnt != 1 else ''})"), ln=True)
        pdf.ln(4)

    # Daily activity pattern (last 7 days) — bars scaled to the busiest day.
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'Daily Activity Pattern', ln=True)
    pdf.set_font('Helvetica', '', 11)
    today_d = datetime.now().date()
    daily, max_day = [], 0.001
    for i in range(6, -1, -1):
        d   = today_d - timedelta(days=i)
        hrs = sum((s['duration_seconds'] or 0) / 3600.0
                  for s in sessions if str(s['start_time'])[:10] == d.isoformat())
        daily.append((d.strftime('%a %d'), hrs))
        max_day = max(max_day, hrs)
    for lbl, hrs in daily:
        y = pdf.get_y()
        pdf.set_x(pdf.l_margin)
        pdf.cell(35, 6, lbl + ':', ln=False)
        tx, tw = pdf.l_margin + 35, 105.0
        pdf.set_fill_color(225, 225, 225)
        pdf.rect(tx, y + 1.0, tw, 4.5, 'F')
        if hrs > 0:
            pdf.set_fill_color(33, 150, 243)
            pdf.rect(tx, y + 1.0, tw * min(1.0, hrs / max_day), 4.5, 'F')
        pdf.set_xy(tx + tw + 3, y)
        pdf.cell(0, 6, f"{hrs:.1f} h", ln=True)
    pdf.ln(4)

    # AI Model Breakdown — weekly averages per channel (present-only). Bars are drawn with
    # rect() at explicit coords because FPDF treats a 0-width cell() as "extend to the right
    # margin", which previously made 0% (and 100%) scores render as a full-width bar.
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'AI Model Breakdown (weekly average)', ln=True)
    pdf.set_font('Helvetica', '', 11)
    for label, score in [('Behaviour', mrow.get('b')),
                         ('Chat Toxicity', mrow.get('ch')),
                         ('Voice Emotion', mrow.get('v'))]:
        y = pdf.get_y()
        pdf.set_x(pdf.l_margin)
        pdf.cell(55, 6, label + ':', ln=False)
        tx, tw = pdf.l_margin + 55, 95.0
        pdf.set_fill_color(225, 225, 225)
        pdf.rect(tx, y + 1.0, tw, 4.5, 'F')
        if score is None:
            pdf.set_xy(tx + tw + 3, y)
            pdf.set_text_color(140, 140, 140)
            pdf.cell(0, 6, 'not captured', ln=True)
            pdf.set_text_color(33, 33, 33)
        else:
            s = max(0.0, min(1.0, float(score)))
            if s > 0:
                pdf.set_fill_color(*risk_color)
                pdf.rect(tx, y + 1.0, tw * s, 4.5, 'F')
            pdf.set_xy(tx + tw + 3, y)
            pdf.cell(0, 6, f"{s * 100:.0f}%", ln=True)
    pdf.ln(4)

    # Chat & voice insights this week
    chat_total = crow.get('total') or 0
    chat_toxic = crow.get('toxic') or 0
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'Chat & Voice Insights', ln=True)
    pdf.set_font('Helvetica', '', 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, _latin1(
        f"  Chat lines captured: {chat_total}    Flagged toxic (>={int(CHAT_ALERT_T * 100)}%): {chat_toxic}"))
    pdf.set_x(pdf.l_margin)
    if voice_rows:
        emos = ", ".join(f"{r['emotion']} ({r['n']})" for r in voice_rows[:4])
        pdf.multi_cell(pdf.epw, 6, _latin1(f"  Voice emotions detected: {emos}"))
    else:
        pdf.multi_cell(pdf.epw, 6, _latin1("  Voice emotions detected: none this week"))
    pdf.ln(4)

    # What's driving the risk (top behavioural factors)
    if drivers:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.cell(0, 8, "What's Driving the Risk", ln=True)
        pdf.set_font('Helvetica', '', 11)
        for d in drivers:
            arrow = 'raises' if d.get('direction') == 'raises' else 'lowers'
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(pdf.epw, 6, _latin1(
                f"  - {d['label']}: {d['value']}  ({arrow} risk, {d['contribution_pct']:.0f}% of impact)"))
        pdf.ln(4)

    # Recommendations
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'Recommendations', ln=True)
    pdf.set_font('Helvetica', '', 11)
    for rec in recs:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 6, _latin1(f"  * {rec}"))
    pdf.ln(4)

    # Peer context
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'Peer Comparison', ln=True)
    pdf.set_font('Helvetica', '', 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, _latin1(peer_comp['message']))
    pdf.ln(2)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5, _latin1('Report generated by AI Gaming Addiction Detection System — PES University Capstone PW26_SJ_05'))

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="gaming_report_{user_id}.pdf"'
    return response


# ═════════════════════════════════════════════════════════════════
# ANOMALY DETECTION (statistical baseline on per-day session hours)
# ═════════════════════════════════════════════════════════════════

# The dashboard refreshes every 30 s per parent; re-scanning 28 days of sessions (plus
# de-dup reads and possible writes) each tick is wasted load — daily-hours anomalies
# can't meaningfully change minute-to-minute. Throttled per child; /api/anomalies
# bypasses the throttle (force=True) so an explicit refresh stays fully live.
_ANOMALY_TTL_S    = 300
_anomaly_last_run: dict = {}


def _detect_anomalies(user_id: int, force: bool = False):
    """Detect statistically unusual patterns in a child's session history.

    Uses simple z-score on daily hours over the trailing 28 days. Returns a
    list of anomaly dicts. Severity: 'high' if z >= 2.5, 'medium' if >= 1.8.
    """
    now_mono = time.monotonic()
    if not force and now_mono - _anomaly_last_run.get(user_id, 0) < _ANOMALY_TTL_S:
        return []
    _anomaly_last_run[user_id] = now_mono
    conn = get_db()
    cutoff_28d = (datetime.now() - timedelta(days=28)).isoformat()
    rows = conn.execute('''
        SELECT SUBSTR(start_time,1,10) AS d, SUM(duration_seconds)/3600.0 AS hours
        FROM sessions
        WHERE user_id = ? AND start_time >= ?
        GROUP BY SUBSTR(start_time,1,10)
        ORDER BY d
    ''', (user_id, cutoff_28d)).fetchall()
    if len(rows) < 7:
        conn.close()
        return []

    hours = [r['hours'] for r in rows]
    mean = float(np.mean(hours))
    std = float(np.std(hours)) or 0.001

    # rows[-1] is the latest day WITH sessions, which is not necessarily today — a big
    # day from last week must not keep raising "Today's playtime is +X%" all week. Key
    # the checks on the actual calendar dates instead.
    by_day        = {r['d']: float(r['hours']) for r in rows}
    today_str     = datetime.now().strftime('%Y-%m-%d')
    yesterday_str = (datetime.now().date() - timedelta(days=1)).isoformat()
    today_hours     = by_day.get(today_str, 0.0)
    yesterday_hours = by_day.get(yesterday_str, 0.0)
    z_today = (today_hours - mean) / std

    out = []
    if today_hours > 0 and z_today >= 1.8:
        sev = 'high' if z_today >= 2.5 else 'medium'
        delta_pct = ((today_hours - mean) / max(mean, 0.1)) * 100
        msg = (f"Today's playtime ({today_hours:.1f}h) is {delta_pct:+.0f}% "
               f"vs. 4-week average ({mean:.1f}h)")
        out.append({
            'kind': 'spike_daily_hours',
            'severity': sev,
            'message': msg,
            'z_score': round(z_today, 2),
        })

    # Sudden 2-day jump (today + yesterday vs the baseline of the days before them)
    baseline = [h for d, h in by_day.items() if d not in (today_str, yesterday_str)]
    if baseline and (today_hours > 0 or yesterday_hours > 0):
        last2_avg = (today_hours + yesterday_hours) / 2
        prev_avg  = float(np.mean(baseline))
        if prev_avg > 0 and last2_avg > prev_avg * 1.75:
            out.append({
                'kind': 'sustained_increase',
                'severity': 'medium',
                'message': f"Gaming has averaged {last2_avg:.1f}h over the last 2 days vs. "
                           f"{prev_avg:.1f}h baseline — a sustained jump.",
                'z_score': round((last2_avg - prev_avg) / std, 2),
            })

    # Persist new anomalies (de-dup by message + same day)
    today = datetime.now().strftime('%Y-%m-%d')
    for a in out:
        existing = conn.execute(
            'SELECT id FROM anomalies WHERE user_id = ? AND message = ? AND SUBSTR(detected_at,1,10) = ?',
            (user_id, a['message'], today)
        ).fetchone()
        if existing:
            continue
        conn.execute(
            'INSERT INTO anomalies (user_id, kind, severity, message, z_score) VALUES (?, ?, ?, ?, ?)',
            (user_id, a['kind'], a['severity'], a['message'], a['z_score'])
        )
    conn.commit()
    conn.close()
    return out


@app.route('/api/anomalies', methods=['GET'])
def get_anomalies():
    user_id = request.args.get('user_id', type=int)
    deny = guard(user_id)
    if deny: return deny
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id required'}), 400
    fresh = _detect_anomalies(user_id, force=True)   # explicit fetch: bypass the throttle
    conn = get_db()
    rows = conn.execute('''
        SELECT id, kind, severity, message, z_score, detected_at, resolved
        FROM anomalies
        WHERE user_id = ? AND resolved = 0
        ORDER BY detected_at DESC LIMIT 10
    ''', (user_id,)).fetchall()
    return jsonify({
        'success': True,
        'fresh': fresh,
        'anomalies': [dict(r) for r in rows]
    })


@app.route('/api/anomalies/<int:aid>/resolve', methods=['POST'])
def resolve_anomaly(aid: int):
    conn = get_db()
    row = conn.execute('SELECT user_id FROM anomalies WHERE id=?', (aid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Not found'}), 404
    deny = guard(row['user_id'])
    if deny:
        conn.close()
        return deny
    conn.execute('UPDATE anomalies SET resolved = 1 WHERE id = ?', (aid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ═════════════════════════════════════════════════════════════════
# AI COUNSELOR CHATBOT (rule-based + contextual responses)
# ═════════════════════════════════════════════════════════════════

# Uses session history + risk context to produce CBT-style supportive replies.
# Could be swapped out for a real LLM (Claude/OpenAI) — function is the only
# integration point.

_COUNSELOR_REPLIES = {
    'greeting': [
        "Hi! I'm Mira — your gaming wellness companion. How are you feeling today?",
        "Hey, glad you're checking in. What's on your mind?",
    ],
    'tired': [
        "Sounds like you've been pushing hard. Sleep is when your brain locks in everything you've learned — including your gaming reflexes. Want to talk about your sleep this week?",
    ],
    'angry': [
        "Frustration after a tough match is real. Some of the best players take a 10-minute walk between losses — it actually resets your reaction speed. What set it off?",
    ],
    'sad': [
        "Thanks for telling me. Gaming can feel like the only thing that makes the noise go quiet, but it works better with other things alongside it. What else has been good for you lately?",
    ],
    'happy': [
        "Love hearing that. What's been going well?",
    ],
    'craving': [
        "That pull to play again is real — it's literally a dopamine signal. Try this: set a 5-minute timer, do something with your hands (cook, draw, stretch). Most cravings fade in under 10. Want me to set a check-in?",
    ],
    'sleep': [
        "Late-night gaming is one of the strongest signals of how your week is going. Even shifting your stop time 30 min earlier makes a huge difference. What time do you usually stop?",
    ],
    'limit': [
        "Time limits work best when they're your choice, not a rule someone else makes. What would feel right to you — 1 hour? 2? Let's pick something that matches your week.",
    ],
    'default': [
        "Tell me more about that.",
        "What does that look like for you day-to-day?",
        "How long has this been going on?",
    ],
}


def _classify_intent(text: str) -> str:
    # Single keywords are matched as WHOLE words (substring matching misrouted e.g.
    # "this" → greeting via 'hi', "made" → angry via 'mad'); multi-word phrases are
    # still matched as substrings of the lowered text.
    t = text.lower()
    words = set(re.findall(r"[a-z']+", t))
    if words & {'hi', 'hello', 'hey', 'mira'}:
        return 'greeting'
    if words & {'tired', 'exhausted', 'sleepy', 'fatigued'}:
        return 'tired'
    if words & {'angry', 'mad', 'rage', 'pissed', 'frustrated'}:
        return 'angry'
    if words & {'sad', 'lonely', 'down', 'depressed', 'upset'}:
        return 'sad'
    if words & {'happy', 'great', 'excited', 'awesome'} or 'good day' in t:
        return 'happy'
    if words & {'urge', 'craving'} or any(p in t for p in ('want to play', 'cant stop', "can't stop")):
        return 'craving'
    if words & {'sleep', 'night', 'late', 'bed'}:
        return 'sleep'
    if words & {'limit', 'reduce'} or any(p in t for p in ('cut down', 'stop playing')):
        return 'limit'
    return 'default'


def _build_counselor_context(user_id: int) -> dict:
    """Pulls recent risk and streak to personalize responses."""
    conn = get_db()
    try:
        cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
        row = conn.execute('''
            SELECT AVG(p.final_risk_score) AS avg_risk
            FROM predictions p
            JOIN sessions s ON s.session_id = p.session_id
            WHERE s.user_id = ? AND s.start_time >= ?
        ''', (user_id, cutoff_7d)).fetchone()
        avg_risk = row['avg_risk'] if row and row['avg_risk'] is not None else 0.5

        streak_row = conn.execute(
            'SELECT current_streak FROM streaks WHERE user_id = ?', (user_id,)
        ).fetchone()
        streak = streak_row['current_streak'] if streak_row else 0
    finally:
        conn.close()

    return {'avg_risk': float(avg_risk), 'streak': int(streak)}


@app.route('/api/counselor/chat', methods=['POST'])
def counselor_chat():
    data = request.get_json() or {}
    user_id = data.get('user_id')
    deny = guard(user_id)
    if deny: return deny
    message = (data.get('message') or '').strip()
    if not user_id or not message:
        return jsonify({'success': False, 'error': 'user_id and message required'}), 400

    intent = _classify_intent(message)
    ctx = _build_counselor_context(user_id)
    base = _COUNSELOR_REPLIES.get(intent, _COUNSELOR_REPLIES['default'])[0]

    # Personalize tail based on context
    tail = ''
    if ctx['streak'] >= 3 and intent in ('default', 'happy'):
        tail = f" By the way — you're on a {ctx['streak']}-day healthy streak. That's not nothing."
    elif ctx['avg_risk'] > 0.7 and intent in ('default', 'tired'):
        tail = " I've noticed your gaming has been pretty intense this week — I'm here whenever you want to talk through it."

    reply = base + tail

    conn = get_db()
    conn.execute('INSERT INTO counselor_messages (user_id, role, content) VALUES (?, ?, ?)',
                 (user_id, 'user', message))
    conn.execute('INSERT INTO counselor_messages (user_id, role, content) VALUES (?, ?, ?)',
                 (user_id, 'assistant', reply))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'reply': reply, 'intent': intent})


@app.route('/api/counselor/history', methods=['GET'])
def counselor_history():
    user_id = request.args.get('user_id', type=int)
    deny = guard(user_id)
    if deny: return deny
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id required'}), 400
    conn = get_db()
    rows = conn.execute('''
        SELECT role, content, created_at FROM counselor_messages
        WHERE user_id = ? ORDER BY id ASC LIMIT 200
    ''', (user_id,)).fetchall()
    conn.close()
    return jsonify({
        'success': True,
        'messages': [dict(r) for r in rows]
    })


# ═════════════════════════════════════════════════════════════════
# DAILY REFLECTION / MOOD CHECK-IN
# ═════════════════════════════════════════════════════════════════

@app.route('/api/child/reflection', methods=['POST'])
def post_reflection():
    data = request.get_json() or {}
    user_id = data.get('user_id')
    deny = guard(user_id)
    if deny: return deny
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id required'}), 400
    mood = data.get('mood_rating')
    sleep = data.get('sleep_quality')
    energy = data.get('energy_level')
    note = (data.get('note') or '')[:500]
    conn = get_db()
    conn.execute('''
        INSERT INTO reflections (user_id, mood_rating, sleep_quality, energy_level, note)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, mood, sleep, energy, note))
    conn.commit()
    return jsonify({'success': True})


@app.route('/api/child/reflections', methods=['GET'])
def get_reflections():
    user_id = request.args.get('user_id', type=int)
    deny = guard(user_id)
    if deny: return deny
    days = request.args.get('days', default=14, type=int)
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id required'}), 400
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=int(days))).isoformat()
    rows = conn.execute('''
        SELECT mood_rating, sleep_quality, energy_level, note, created_at
        FROM reflections
        WHERE user_id = ? AND created_at >= ?
        ORDER BY created_at DESC
    ''', (user_id, cutoff)).fetchall()
    return jsonify({
        'success': True,
        'reflections': [dict(r) for r in rows]
    })


# ─────────────────────────────────────────────────────────────────

# Enforce the retention window once at import (covers gunicorn workers too).
purge_old_data()   # no-op unless DATA_RETENTION_DAYS is set

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Gaming Addiction Detection API on port {port} "
                f"({'Postgres' if USE_POSTGRES else 'SQLite'}, "
                f"auth={'enforce' if AUTH_ENFORCE else 'shadow'})")
    app.run(host='0.0.0.0', port=port, debug=False)
