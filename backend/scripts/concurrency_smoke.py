"""
Concurrency smoke: 288 mixed requests across 24 threads against a REAL threaded
server (werkzeug, threaded=True) on an isolated throwaway DB — the permanent,
re-runnable form of the load check the paper cites. Re-run after any change that
alters per-request cost (e.g. a heavier vectorizer) to re-verify the zero-error claim
and watch the latency profile.

The mix mirrors live traffic: cheap polls (health, dashboards, alerts, sessions),
the model card, chat ingestion (TF-IDF + calibrated LogReg per message), and live
predictions (behaviour model + fusion). Fails (exit 1) on ANY 5xx.

Run from backend/:  python scripts/concurrency_smoke.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

# ── Isolated DB BEFORE importing app ────────────────────────────────────────
_TMP_DB = os.path.join(tempfile.gettempdir(), 'concurrency_smoke.db')
for _ext in ('', '-wal', '-shm'):
    try:
        os.remove(_TMP_DB + _ext)
    except OSError:
        pass
os.environ['DATABASE_PATH'] = _TMP_DB
os.environ.setdefault('AUTH_ENFORCE', '0')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app  # noqa: E402

from werkzeug.serving import make_server  # noqa: E402

THREADS, PER_THREAD = 24, 12              # 288 total, matching the cited check


def call(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header('Content-Type', 'application/json')
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            r.read()
            return r.status, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0


def main():
    srv = make_server('127.0.0.1', 0, app, threaded=True)
    base = f'http://127.0.0.1:{srv.server_port}'
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # Seed one session so the write/predict paths have a target.
    status, _ = call(base, 'POST', '/api/session/start',
                     {'user_id': 1, 'game_name': 'BGMI'})
    assert status == 200, f'seed session failed: {status}'
    sid = 1

    mix = [
        ('GET', '/api/health', None),
        ('GET', '/api/model_card', None),
        ('GET', '/api/dashboard/user?user_id=1', None),
        ('GET', '/api/sessions?user_id=1', None),
        ('GET', '/api/alerts?user_id=1', None),
        ('GET', '/api/child/status?user_id=1', None),
        ('GET', '/api/dashboard/child_enriched?user_id=1', None),
        ('GET', '/api/user/profile?user_id=1', None),
        ('POST', f'/api/session/{sid}/chat',
         {'message': 'nice shot bro lets push mid'}),
        ('POST', f'/api/session/{sid}/predict', None),
        ('GET', '/api/games', None),
        ('GET', '/api/child/streak?user_id=1', None),
    ]

    results, lock = [], threading.Lock()

    def worker(wid):
        for i in range(PER_THREAD):
            m, p, b = mix[(wid + i) % len(mix)]
            s, dt = call(base, m, p, b)
            with lock:
                results.append((s, dt, p))

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(w,)) for w in range(THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wall = time.perf_counter() - t0
    srv.shutdown()

    lats = sorted(dt for _, dt, _ in results)
    errors = [(s, p) for s, _, p in results if s >= 500]
    limited = sum(1 for s, _, _ in results if s == 429)   # rate limiter is WORKING, not an error
    p = lambda q: lats[int(q * (len(lats) - 1))] * 1000
    print(f"{len(results)} requests / {THREADS} threads in {wall:.1f}s "
          f"({len(results) / wall:.0f} req/s)")
    print(f"latency ms: p50 {p(0.5):.0f}  p95 {p(0.95):.0f}  max {p(1.0):.0f}")
    print(f"5xx errors: {len(errors)}   429 rate-limited: {limited}")
    if errors:
        for s, path in errors[:5]:
            print(f"  {s} {path}")
        sys.exit(1)
    print("CONCURRENCY SMOKE PASSED (zero server errors)")


if __name__ == '__main__':
    main()
