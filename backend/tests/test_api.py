"""Backend smoke + integration tests — PES Capstone PW26_SJ_05.

Run from the backend dir:
    cd backend && pytest tests/ -v

Uses Flask's test client (no live server). conftest.py points the app at an
isolated throwaway SQLite DB seeded with deterministic data, so no real DB or
`seed_demo.py` run is required. The seeded family is: child PIN 1234,
parent PIN 0000, family code TEST01 (user_id=1).
"""
import time

import pytest

FAMILY_CODE = 'TEST01'   # must match the family code seeded in conftest.py


# ─── Health and basic endpoints ────────────────────────────────────

def test_health(client):
    r = client.get('/api/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data['status'] in ('ok', 'healthy')


def test_games_list(client):
    r = client.get('/api/games')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert isinstance(data['games'], list)
    assert len(data['games']) > 0


# ─── Login flow ────────────────────────────────────────────────────

def test_child_login(client):
    r = client.post('/api/user/login',
                    json={'pin': '1234', 'role': 'child'})
    assert r.status_code in (200, 401)


def test_parent_login_requires_family_code(client):
    """Parent login without a family code must be rejected (family-code model)."""
    r = client.post('/api/user/login', json={'pin': '0000', 'role': 'parent'})
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_parent_login_with_family_code(client):
    """Parent login with the seeded family code + PIN succeeds and returns children."""
    r = client.post('/api/user/login',
                    json={'pin': '0000', 'role': 'parent', 'family_code': FAMILY_CODE})
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['token']
    assert isinstance(data.get('children'), list) and len(data['children']) >= 1


def test_bad_login(client):
    r = client.post('/api/user/login',
                    json={'pin': 'wrong', 'role': 'child'})
    assert r.status_code in (401, 200)
    data = r.get_json()
    assert data['success'] is False


def test_login_returns_token(client):
    """A successful login must hand back a signed bearer token."""
    r = client.post('/api/user/login', json={'pin': '1234', 'role': 'child'})
    if r.status_code == 200:
        data = r.get_json()
        assert data.get('token'), 'login should return a signed auth token'


# ─── Postgres dialect translation ──────────────────────────────────
def test_pg_placeholder_translation():
    """? placeholders become %s and literal % is escaped for psycopg2."""
    from app import _to_pg
    assert _to_pg("SELECT * FROM t WHERE a=? AND b=?") == \
        "SELECT * FROM t WHERE a=%s AND b=%s"
    assert _to_pg("UPDATE t SET note='100%' WHERE id=?") == \
        "UPDATE t SET note='100%%' WHERE id=%s"


# ─── Privacy: consent + data deletion ──────────────────────────────
def test_consent_flow(client):
    import app as appmod
    r = client.post('/api/consent',
                    json={'user_id': 1, 'version': appmod.CONSENT_VERSION,
                          'parent_pin': '0000'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    r = client.get('/api/consent?user_id=1')
    j = r.get_json()
    assert r.status_code == 200
    assert j['consent_given'] is True
    assert j['needs_consent'] is False


def test_delete_data_endpoint(client):
    # Use a throwaway user id so the seeded demo data is never touched.
    r = client.post('/api/user/delete_data', json={'user_id': 999999, 'scope': 'data'})
    assert r.status_code == 200 and r.get_json()['success'] is True


# ─── SHAP explanation: version-shape normalization ─────────────────
def test_shap_per_class_shapes():
    import numpy as np
    from app import _shap_per_class
    # shap < 0.46 multiclass: list of (n_samples, n_features)
    lst = [np.array([[1., 2., 3.]]), np.array([[4., 5., 6.]]), np.array([[7., 8., 9.]])]
    out = _shap_per_class(lst)
    assert len(out) == 3 and list(out[2]) == [7., 8., 9.]
    # shap >= 0.46: (n_samples, n_features, n_classes)
    arr = np.zeros((1, 3, 3)); arr[0, :, 2] = [7., 8., 9.]
    out2 = _shap_per_class(arr)
    assert len(out2) == 3 and list(out2[2]) == [7., 8., 9.]
    # binary/regression: (n_samples, n_features)
    out3 = _shap_per_class(np.array([[1., 2., 3.]]))
    assert len(out3) == 1 and list(out3[0]) == [1., 2., 3.]


# ─── Voice emotion: valence-arousal fusion ─────────────────────────
def test_fuse_emotion_va():
    from app import fuse_emotion
    angry = {'angry': 0.7, 'frustrated': 0.2, 'excited': 0.05, 'neutral': 0.05}
    calm  = {'neutral': 0.6, 'frustrated': 0.25, 'angry': 0.1, 'excited': 0.05}
    happy = {'neutral': 0.5, 'excited': 0.3, 'angry': 0.1, 'frustrated': 0.1}
    # confident animated tone + negative words -> angry
    assert fuse_emotion('angry', -1.0, probs=angry, valence_conf=1.0) == 'angry'
    # negative words but CALM tone -> frustrated, not angry (the key win)
    assert fuse_emotion('neutral', -1.0, probs=calm, valence_conf=1.0) == 'frustrated'
    # positive words -> excited
    assert fuse_emotion('neutral', 1.0, probs=happy, valence_conf=1.0) == 'excited'
    # trained toxicity pulls valence negative even with no lexicon words + calm tone
    assert fuse_emotion('neutral', 0.0, probs=calm, valence_conf=0.0, toxicity=0.9) == 'frustrated'
    # fallback path (no distribution) still behaves
    assert fuse_emotion('angry', -0.6) == 'angry'
    assert fuse_emotion('neutral', 0.5) == 'excited'


# ─── Dashboards (require seeded data) ──────────────────────────────

def test_user_dashboard(client):
    r = client.get('/api/dashboard/user?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True


def test_parent_dashboard(client):
    r = client.get('/api/dashboard/parent?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert 'current_risk' in data
    assert 'risk_score' in data


def test_legacy_risk_alerts_use_family_facing_labels(client):
    alerts = client.get('/api/alerts?user_id=1').get_json()['alerts']
    risk_messages = [a['message'] for a in alerts if a['type'] == 'risk']
    assert risk_messages
    assert all('At-risk' not in message for message in risk_messages)
    assert all('addiction risk' not in message.lower() for message in risk_messages)
    assert any('Some concern' in message for message in risk_messages)


# ─── New endpoints (Phase 3) ───────────────────────────────────────

def test_screen_event(client):
    r = client.post('/api/child/screen_event',
                    json={'user_id': '1', 'event_type': 'screen_on',
                          'timestamp': str(int(time.time() * 1000))})
    assert r.status_code == 200


def test_notification_event(client):
    r = client.post('/api/child/notification_event',
                    json={'user_id': '1', 'package_name': 'com.tencent.ig',
                          'game_name': 'BGMI', 'notification_title': 'test'})
    assert r.status_code == 200


def test_streak(client):
    r = client.get('/api/child/streak?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert 'current_streak' in data


def test_get_time_limit(client):
    r = client.get('/api/child/get_limit?user_id=1')
    assert r.status_code == 200


def test_child_enriched(client):
    expected_name = client.get('/api/user/profile?user_id=1').get_json()['name']
    r = client.get('/api/dashboard/child_enriched?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['child_name'] == expected_name


# ─── Counselor chatbot ─────────────────────────────────────────────

def test_counselor_chat_greeting(client):
    r = client.post('/api/counselor/chat',
                    json={'user_id': 1, 'message': 'hi mira'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert len(data['reply']) > 0
    assert data['intent'] == 'greeting'


def test_counselor_chat_craving(client):
    r = client.post('/api/counselor/chat',
                    json={'user_id': 1, 'message': "I can't stop playing"})
    assert r.status_code == 200
    data = r.get_json()
    assert data['intent'] == 'craving'


def test_counselor_history(client):
    # After the above two messages, history should have at least 4 entries
    r = client.get('/api/counselor/history?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert len(data['messages']) >= 2


def test_counselor_chat_validation(client):
    r = client.post('/api/counselor/chat', json={'user_id': 1})
    assert r.status_code == 400


# ─── Reflection ────────────────────────────────────────────────────

def test_post_reflection(client):
    r = client.post('/api/child/reflection',
                    json={'user_id': 1, 'mood_rating': 3,
                          'sleep_quality': 4, 'energy_level': 3,
                          'note': 'okay day'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True


def test_get_reflections(client):
    r = client.get('/api/child/reflections?user_id=1&days=14')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert isinstance(data['reflections'], list)


# ─── Anomaly detection ─────────────────────────────────────────────

def test_anomalies(client):
    r = client.get('/api/anomalies?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert 'anomalies' in data
    assert isinstance(data['anomalies'], list)


def test_anomalies_validation(client):
    r = client.get('/api/anomalies')
    assert r.status_code == 400


# ─── Sessions and history ──────────────────────────────────────────

def test_get_sessions(client):
    r = client.get('/api/sessions?user_id=1&limit=10')
    assert r.status_code == 200


def test_session_lifecycle(client):
    # Start
    r = client.post('/api/session/start',
                    json={'user_id': 1, 'game_name': 'BGMI'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    sid = data['session_id']

    # End
    r = client.post(f'/api/session/{sid}/end')
    assert r.status_code == 200

    # JSON booleans/fractions are not valid integer account identifiers.
    assert client.post('/api/session/start',
                       json={'user_id': True, 'game_name': 'BGMI'}).status_code == 400
    assert client.post('/api/session/start',
                       json={'user_id': 1.5, 'game_name': 'BGMI'}).status_code == 400


# ─── Validation guards ─────────────────────────────────────────────

def test_missing_user_id(client):
    r = client.get('/api/dashboard/user')
    # Should default or 400 — either is acceptable
    assert r.status_code in (200, 400)


# ─── Model card (per-model metrics) ────────────────────────────────

def test_model_card(client):
    r = client.get('/api/model_card')
    assert r.status_code == 200
    data = r.get_json()
    assert 'test_accuracy' in data
    # chat + voice metrics are now reported alongside behaviour
    assert 'chat_metrics' in data
    assert 'voice_metrics' in data


# ─── Parent feedback loop (real labels) ────────────────────────────

def test_feedback_loop(client):
    alerts = client.get('/api/alerts?user_id=1').get_json()['alerts']
    assert alerts, 'seed should provide at least one alert'
    aid = next(a['id'] for a in alerts if a['type'] in ('risk', 'toxicity'))

    r = client.post('/api/feedback', json={'alert_id': aid, 'label': 'accurate'})
    assert r.status_code == 200 and r.get_json()['success'] is True

    # The verdict should now be attached to the alert and counted in the summary.
    again = client.get('/api/alerts?user_id=1').get_json()['alerts']
    marked = next(a for a in again if a['id'] == aid)
    assert marked['feedback'] == 'accurate'

    summary = client.get('/api/feedback/summary?user_id=1').get_json()
    assert summary['success'] is True
    assert summary['counts'].get('accurate', 0) >= 1


def test_feedback_on_revision_and_streak_alerts(client):
    """The Parent app offers verdict buttons on risk_revision and toxicity_streak
    alerts (AlertTriage.isFeedbackEligible) — the backend must accept those types,
    not just the original one-event 'risk'/'toxicity' forms."""
    from app import _insert_alert, get_db
    conn = get_db()
    c = conn.cursor()
    # Attach the revision to a real scored session so its prediction snapshot resolves.
    c.execute('''SELECT p.session_id FROM predictions p
                 JOIN sessions s ON s.session_id=p.session_id
                 WHERE s.user_id=1 ORDER BY p.id DESC LIMIT 1''')
    sid = c.fetchone()['session_id']
    rev_id = _insert_alert(c, 1, 'risk_revision',
                           'Late evidence revised this session to Low concern.',
                           'info', session_id=sid)
    streak_id = _insert_alert(c, 1, 'toxicity_streak',
                              'Repeated concerning language this gaming session.',
                              'high', session_id=sid)
    conn.commit()
    conn.close()

    for aid in (rev_id, streak_id):
        r = client.post('/api/feedback', json={'alert_id': aid, 'label': 'false_alarm'})
        assert r.status_code == 200, (aid, r.get_json())
        assert r.get_json()['success'] is True

    # And session_start stays operational-only (nothing to rate).
    conn = get_db()
    c = conn.cursor()
    op_id = _insert_alert(c, 1, 'session_start', 'started playing BGMI', 'info')
    conn.commit()
    conn.close()
    r = client.post('/api/feedback', json={'alert_id': op_id, 'label': 'accurate'})
    assert r.status_code == 400

    # Clean up: later tests count user 1's toxicity_streak alerts in the shared DB.
    conn = get_db()
    c = conn.cursor()
    ids = tuple(i for i in (rev_id, streak_id, op_id) if i is not None)
    ph = ','.join(['?'] * len(ids))
    c.execute(f'DELETE FROM feedback WHERE alert_id IN ({ph})', ids)
    c.execute(f'DELETE FROM alerts WHERE id IN ({ph})', ids)
    conn.commit()
    conn.close()


def test_feedback_bad_label(client):
    r = client.post('/api/feedback', json={'user_id': 1, 'label': 'definitely_not_valid'})
    assert r.status_code == 400


def test_feedback_unknown_alert_rejected(client):
    """A verdict must not attach to a non-existent alert id."""
    r = client.post('/api/feedback', json={'alert_id': 999999, 'label': 'accurate'})
    assert r.status_code == 404


def test_feedback_alert_user_mismatch_rejected(client):
    """alert_id must belong to the stated child — a crafted foreign alert_id previously
    deleted/planted feedback on another family's alert feed."""
    alerts = client.get('/api/alerts?user_id=1').get_json()['alerts']
    aid = alerts[0]['id']
    r = client.post('/api/feedback', json={'alert_id': aid, 'user_id': 4242, 'label': 'accurate'})
    assert r.status_code == 400


def test_feedback_summary_validation(client):
    r = client.get('/api/feedback/summary')
    assert r.status_code == 400


# ─── Input robustness (malformed bodies must not 500) ──────────────

def test_chat_non_string_message_rejected_cleanly(client):
    """A non-string 'message' used to crash .strip() into a 500."""
    r = client.post('/api/session/start', json={'user_id': 1, 'game_name': 'BGMI'})
    sid = r.get_json()['session_id']
    r = client.post(f'/api/session/{sid}/chat', json={'message': 12345})
    assert r.status_code == 400
    r = client.post(f'/api/session/{sid}/chat', json={'message': None})
    assert r.status_code == 400          # empty after coercion
    client.post(f'/api/session/{sid}/end')


def test_voice_garbage_intensity_rejected_cleanly(client):
    """Garbage intensity/duration in the JSON voice path used to 500."""
    r = client.post('/api/session/start', json={'user_id': 1, 'game_name': 'BGMI'})
    sid = r.get_json()['session_id']
    r = client.post(f'/api/session/{sid}/voice',
                    json={'emotion': 'angry', 'intensity': 'not-a-number', 'duration_seconds': None})
    assert r.status_code == 400
    client.post(f'/api/session/{sid}/end')


def test_backfill_offline_session(client):
    """An offline session posts start/end + a client key; the server creates a scored,
    already-closed session, and a re-send with the SAME key dedupes (no duplicate)."""
    from datetime import datetime, timedelta
    start = (datetime.now() - timedelta(hours=2)).isoformat()
    end   = (datetime.now() - timedelta(hours=1)).isoformat()
    body  = {'user_id': 1, 'game_name': 'BGMI', 'start_time': start,
             'end_time': end, 'client_key': 'offline-abc-123'}
    r = client.post('/api/session/backfill', json=body)
    assert r.status_code == 200
    d = r.get_json()
    assert d['success'] is True and d['backfilled'] is True
    assert d['duration_seconds'] == 3600
    sid = d['session_id']
    assert d['prediction']['risk_label'] in ('casual', 'at_risk', 'addicted')

    # Idempotent: same client_key returns the same session, no new row.
    r2 = client.post('/api/session/backfill', json=body)
    d2 = r2.get_json()
    assert d2['session_id'] == sid and d2.get('deduped') is True


def test_backfill_validates_and_clamps(client):
    """Missing key / bad times are 400; an absurd interval is clamped, not stored raw."""
    from datetime import datetime, timedelta
    assert client.post('/api/session/backfill',
                       json={'user_id': 1, 'game_name': 'BGMI',
                             'start_time': 'x', 'end_time': 'y',
                             'client_key': 'k1'}).status_code == 400
    assert client.post('/api/session/backfill',
                       json={'user_id': 1, 'game_name': 'BGMI',
                             'start_time': datetime.now().isoformat(),
                             'end_time': datetime.now().isoformat()}).status_code == 400
    # Explicit client timestamps allow a genuine long bout, capped independently of
    # the six-hour orphan timeout.
    start = (datetime.now() - timedelta(hours=40)).isoformat()
    r = client.post('/api/session/backfill',
                    json={'user_id': 1, 'game_name': 'BGMI', 'start_time': start,
                          'end_time': datetime.now().isoformat(), 'client_key': 'k-long'})
    assert r.get_json()['duration_seconds'] == 24 * 3600


def test_backfill_rejects_malformed_reverse_stale_future_and_tiny_intervals(client):
    """The backfill endpoint is a data-integrity boundary, not a timestamp repair tool."""
    from datetime import datetime, timedelta

    now = datetime.now()
    base = {'user_id': 1, 'game_name': 'BGMI', 'client_key': 'invalid-shape-key'}
    assert client.post('/api/session/backfill', json=[]).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'game_name': None,
                       'start_time': (now - timedelta(minutes=2)).isoformat(),
                       'end_time': now.isoformat()}).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'user_id': True,
                       'start_time': (now - timedelta(minutes=2)).isoformat(),
                       'end_time': now.isoformat()}).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'user_id': 1.5,
                       'start_time': (now - timedelta(minutes=2)).isoformat(),
                       'end_time': now.isoformat()}).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'client_key': 'reverse-key',
                       'start_time': now.isoformat(),
                       'end_time': (now - timedelta(seconds=1)).isoformat()}).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'client_key': 'tiny-key',
                       'start_time_ms': int(now.timestamp() * 1000),
                       'end_time_ms': int(now.timestamp() * 1000) + 500}).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'client_key': 'stale-key',
                       'start_time': (now - timedelta(days=8)).isoformat(),
                       'end_time': (now - timedelta(days=8) + timedelta(minutes=1)).isoformat()
                       }).status_code == 400
    assert client.post('/api/session/backfill', json={**base, 'client_key': 'future-key',
                       'start_time': (now + timedelta(minutes=10)).isoformat(),
                       'end_time': (now + timedelta(minutes=11)).isoformat()}).status_code == 400


def test_backfill_epoch_contract_and_idempotency_key_conflict(client):
    """Epoch millis preserve the instant; a key cannot silently alias another bout."""
    from datetime import datetime, timedelta

    end = datetime.now() - timedelta(minutes=10)
    start = end - timedelta(minutes=2)
    body = {'user_id': 1, 'game_name': 'BGMI',
            'start_time_ms': int(start.timestamp() * 1000),
            'end_time_ms': int(end.timestamp() * 1000),
            'client_key': 'epoch-contract-key'}
    created = client.post('/api/session/backfill', json=body)
    assert created.status_code == 200
    assert created.get_json()['duration_seconds'] == 120
    assert client.post('/api/session/backfill', json=body).get_json()['deduped'] is True

    reused = dict(body)
    reused['game_name'] = 'Candy Crush'
    conflict = client.post('/api/session/backfill', json=reused)
    assert conflict.status_code == 409


def test_backfill_retry_repairs_partial_scoring_once(client, monkeypatch):
    """A crash after the session INSERT must be recoverable without duplicate evidence."""
    from datetime import datetime, timedelta
    import app as appmod

    end = datetime.now() - timedelta(minutes=20)
    body = {'user_id': 1, 'game_name': 'BGMI',
            'start_time': (end - timedelta(minutes=3)).isoformat(),
            'end_time': end.isoformat(), 'client_key': 'partial-retry-key'}
    real_prediction = appmod.run_prediction
    monkeypatch.setattr(appmod, 'run_prediction',
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('boom')))
    assert client.post('/api/session/backfill', json=body).status_code == 500
    monkeypatch.setattr(appmod, 'run_prediction', real_prediction)

    repaired = client.post('/api/session/backfill', json=body)
    assert repaired.status_code == 200 and repaired.get_json()['deduped'] is True
    sid = repaired.get_json()['session_id']
    conn = appmod.get_db()
    assert conn.execute('SELECT COUNT(*) AS n FROM behavioral_data WHERE session_id=?',
                        (sid,)).fetchone()['n'] == 1
    assert conn.execute('SELECT COUNT(*) AS n FROM predictions WHERE session_id=?',
                        (sid,)).fetchone()['n'] == 1
    assert conn.execute('SELECT backfill_finalized FROM sessions WHERE session_id=?',
                        (sid,)).fetchone()['backfill_finalized'] == 1
    conn.close()


def test_voice_probs_shadow_logged_without_changing_serving(client, monkeypatch):
    """The shadow evidence column: the full acoustic distribution is stored per voice
    event while the SERVED emotion/intensity stay exactly what the fusion produced —
    the observe-only prerequisite for the domain-shift mitigations (abstain margin,
    prior correction), mirroring the AUTH_ENFORCE shadow-mode pattern."""
    import io
    import json as _json
    import app as appmod

    fixed = {'angry': 0.05, 'excited': 0.1, 'frustrated': 0.7, 'neutral': 0.15}
    monkeypatch.setattr(appmod, 'analyse_audio',
                        lambda path: ('frustrated', 0.7, 9.5, dict(fixed)))

    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    r = client.post(f'/api/session/{sid}/voice',
                    data={'audio': (io.BytesIO(b'RIFFfakewav'), 'seg.wav')},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['success'] is True

    conn = appmod.get_db()
    row = conn.execute('SELECT emotion, intensity, probs, capture_valid FROM voice_events '
                       'WHERE session_id=? ORDER BY id DESC LIMIT 1', (sid,)).fetchone()
    conn.close()
    assert row is not None
    stored = _json.loads(row['probs'])
    assert stored == {k: round(v, 4) for k, v in fixed.items()}
    assert abs(sum(stored.values()) - 1.0) < 1e-6
    # Serving unchanged: intensity is still the model max-prob the fusion consumed.
    assert row['intensity'] == 0.7
    assert row['capture_valid'] == 1
    assert r.get_json()['captured'] is True
    client.post(f'/api/session/{sid}/end')


def test_voice_rejected_by_extractor_is_missing_not_neutral_evidence(client, monkeypatch):
    """A VAD/silence rejection must not add a low neutral score to the ensemble.

    The upload is retained for shadow observability, but capture_valid=0 excludes it
    from voice counts, emotion analytics and prediction modality presence.
    """
    import io
    import app as appmod

    monkeypatch.setattr(appmod, 'analyse_audio',
                        lambda path: (None, 0.0, 9.5, None))
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    r = client.post(f'/api/session/{sid}/voice',
                    data={'audio': (io.BytesIO(b'RIFFnon-speech'), 'noise.wav')},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    assert r.get_json()['captured'] is False

    conn = appmod.get_db()
    event = conn.execute(
        'SELECT emotion, intensity, probs, capture_valid FROM voice_events '
        'WHERE session_id=? ORDER BY id DESC LIMIT 1', (sid,)).fetchone()
    # Rejected uploads remain auditable, but are explicitly invalid evidence.
    assert dict(event) == {'emotion': 'neutral', 'intensity': 0.0,
                           'probs': None, 'capture_valid': 0}
    assert conn.execute('SELECT COUNT(*) AS n FROM predictions WHERE session_id=?',
                        (sid,)).fetchone()['n'] == 0
    conn.close()

    pred = client.post(f'/api/session/{sid}/predict').get_json()
    assert pred['modalities']['voice'] is False
    detail = client.get(f'/api/session/{sid}').get_json()
    assert detail['voice_count'] == 0
    client.post(f'/api/session/{sid}/end')


def test_export_user_data(client):
    """Access/portability: the bundle carries the deletion-scope tables and NEVER the
    credential/push fields."""
    r = client.get('/api/user/export?user_id=1')
    assert r.status_code == 200
    d = r.get_json()
    assert d['success'] is True
    for secret in ('pin', 'parent_pin', 'pin_hash', 'parent_pin_hash', 'fcm_token'):
        assert secret not in d['profile']
    assert set(d['data']) >= {'sessions', 'chat_messages', 'voice_events',
                              'predictions', 'alerts', 'reflections', 'feedback'}
    assert isinstance(d['data']['sessions'], list) and d['data']['sessions']
    r = client.get('/api/user/export')                # missing user_id
    assert r.status_code == 400


def test_tamper_missing_user_id_is_400(client):
    r = client.post('/api/child/tamper', json={'event': 'logout'})
    assert r.status_code == 400


def test_verify_parent_pin_missing_user_id_is_400(client):
    """Regression: a malformed request (no user_id) used to reach int(None) and 500."""
    r = client.post('/api/verify_parent_pin', json={'pin': '0000'})
    assert r.status_code == 400
    r = client.post('/api/verify_parent_pin', json={'user_id': 'abc', 'pin': '0000'})
    assert r.status_code == 400
    r = client.post('/api/verify_parent_pin', json={'user_id': 1, 'pin': '0000'})
    assert r.status_code == 200 and r.get_json()['valid'] is True


def test_session_chat_score_is_max_of_messages(client, monkeypatch):
    """The session chat score must be the MAX of per-message scores (chosen by a
    707-conversation experiment) — one toxic line among clean ones must NOT be
    diluted the way the old concatenated-blob scoring diluted it."""
    import app as appmod
    monkeypatch.setattr(appmod, '_ml_toxicity',
                        lambda text: 0.9 if 'zzz' in str(text) else 0.05)
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    client.post(f'/api/session/{sid}/chat', json={'message': 'plain words one'})
    client.post(f'/api/session/{sid}/chat', json={'message': 'zzz bad words here'})
    client.post(f'/api/session/{sid}/chat', json={'message': 'plain words two'})
    pred = client.post(f'/api/session/{sid}/end').get_json()['prediction']
    assert pred['chat_score'] == pytest.approx(0.9, abs=0.01)


def test_voice_stt_not_counted_as_typed_chat(client):
    """Spoken transcripts (source=voice_stt) are the voice channel's words — chat_count
    and the chat-analysis totals must report TYPED chat only, while the labeled
    recent-messages sample keeps both and toxic speech still alerts at upload."""
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    client.post(f'/api/session/{sid}/chat',
                json={'message': 'typed hello line', 'source': 'keyboard'})
    client.post(f'/api/session/{sid}/chat',
                json={'message': 'spoken transcript line', 'source': 'voice_stt'})

    rows = client.get('/api/sessions?user_id=1&limit=10').get_json()
    row = next(r for r in rows if r['session_id'] == sid)
    assert row['chat_count'] == 1                      # typed only

    dash = client.get('/api/dashboard/chat_analysis?user_id=1').get_json()
    assert dash['stats']['spoken_messages'] >= 1       # speech reported separately
    dist = dash['toxicity_distribution']
    # Totals and distribution share the same window + typed-only filter, so the
    # buckets must sum to the headline count (they diverged when speech was mixed in).
    assert dash['stats']['total_messages'] == dist['high'] + dist['medium'] + dist['safe']


def test_toxicity_streak_session_alert(client, monkeypatch):
    """Three moderately-toxic messages (below the per-message alert bar) in one session
    must raise exactly ONE aggregate 'toxicity_streak' alert — and never a second."""
    import app as appmod
    monkeypatch.setattr(appmod, '_ml_toxicity', lambda text: 0.7)   # bar<=0.7<alert_t
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']

    def streaks():
        alerts = client.get('/api/alerts?user_id=1').get_json()['alerts']
        return [a for a in alerts if a['type'] == 'toxicity_streak']

    client.post(f'/api/session/{sid}/chat', json={'message': 'plain words one'})
    client.post(f'/api/session/{sid}/chat', json={'message': 'plain words two'})
    assert not streaks()                          # 2 flagged — below the streak count
    client.post(f'/api/session/{sid}/chat', json={'message': 'plain words three'})
    assert len(streaks()) == 1                    # 3rd flagged message fires the alert
    client.post(f'/api/session/{sid}/chat', json={'message': 'plain words four'})
    assert len(streaks()) == 1                    # 4th must not re-fire it
    client.post(f'/api/session/{sid}/end')


# ─── Auth gate (enforce mode) ──────────────────────────────────────

def test_auth_enforced_blocks_untokened_request(client, monkeypatch):
    """With AUTH_ENFORCE on, a protected endpoint must 401 without a bearer token."""
    import app as appmod
    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    r = client.get('/api/alerts?user_id=1')
    assert r.status_code == 401


def test_parent_can_edit_child_profile(client):
    """A parent edits name + age; the change persists and is readable back."""
    r = client.post('/api/user/update',
                    json={'user_id': 1, 'name': 'Arjun R', 'age': 15})
    assert r.status_code == 200 and r.get_json()['success'] is True
    prof = client.get('/api/user/profile?user_id=1').get_json()
    assert prof['name'] == 'Arjun R'
    assert prof['age'] == 15
    # The already-signed-in Child app refreshes this endpoint, so a parent rename must
    # be visible there without forcing a logout/login.
    enriched = client.get('/api/dashboard/child_enriched?user_id=1').get_json()
    assert enriched['child_name'] == 'Arjun R'

    # Invalid data is rejected explicitly rather than ignored behind a false success.
    bad_age = client.post('/api/user/update', json={'user_id': 1, 'age': 999})
    assert bad_age.status_code == 400 and bad_age.get_json()['success'] is False
    assert client.get('/api/user/profile?user_id=1').get_json()['age'] == 15


@pytest.mark.parametrize('payload', [
    {'name': '   '},
    {'name': 'x' * 41},
    {'age': 'fifteen'},
    {'age': 15.5},
    {'age': True},
])
def test_profile_update_rejects_invalid_fields(client, payload):
    payload = {'user_id': 1, **payload}
    r = client.post('/api/user/update', json=payload)
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_profile_update_requires_explicit_user_and_json_object(client):
    assert client.post('/api/user/update', json={'name': 'Wrong child'}).status_code == 400
    assert client.post('/api/user/update', json=[]).status_code == 400
    assert client.post('/api/user/update', json={'user_id': 1}).status_code == 400
    assert client.post('/api/user/update', json={'user_id': True, 'name': 'Wrong'}).status_code == 400
    assert client.post('/api/user/update', json={'user_id': 1.5, 'name': 'Wrong'}).status_code == 400
    assert client.post('/api/user/update', json={'user_id': 1, 'name': 123}).status_code == 400


def test_registration_uses_the_same_profile_name_and_age_boundary(client):
    common = {'pin': '654321', 'parent_pin': '654320'}
    assert client.post('/api/register',
                       json={**common, 'name': 'x' * 41, 'age': 15}).status_code == 400
    assert client.post('/api/register',
                       json={**common, 'name': 'Child', 'age': True}).status_code == 400
    assert client.post('/api/register',
                       json={**common, 'name': 'Child', 'age': 15.5}).status_code == 400
    assert client.post('/api/register',
                       json={**common, 'name': None, 'age': 15}).status_code == 400


def test_profile_pin_reset_preserves_child_parent_separation(client):
    # Registration refuses equal Child/Family PINs; reset must preserve that invariant
    # in both directions for the selected child and every sibling in the family.
    child_same = client.post('/api/user/update', json={'user_id': 1, 'pin': '0000'})
    assert child_same.status_code == 400
    family_same = client.post('/api/user/update', json={'user_id': 1, 'parent_pin': '1234'})
    assert family_same.status_code == 400
    # Neither rejected request changed the existing credentials.
    assert client.post('/api/user/login',
                       json={'pin': '1234', 'role': 'child'}).status_code == 200
    assert client.post('/api/user/login',
                       json={'pin': '0000', 'role': 'parent',
                             'family_code': 'TEST01'}).status_code == 200

    # Validate the final state, not each new value against the old counterpart: an
    # atomic two-PIN rotation may legitimately move the child onto the old family PIN.
    rotated = client.post('/api/user/update',
                          json={'user_id': 1, 'pin': '0000', 'parent_pin': '9999'})
    assert rotated.status_code == 200
    assert client.post('/api/user/login',
                       json={'pin': '0000', 'role': 'child'}).status_code == 200
    assert client.post('/api/user/login',
                       json={'pin': '9999', 'role': 'parent',
                             'family_code': 'TEST01'}).status_code == 200
    restored = client.post('/api/user/update',
                           json={'user_id': 1, 'pin': '1234', 'parent_pin': '0000'})
    assert restored.status_code == 200


def test_child_token_cannot_edit_profile(client, monkeypatch):
    """A child's own token owns the row but must NOT rewrite the profile (age is a
    monitoring-tamper vector). Enforce mode + a real child token → 403."""
    import app as appmod
    tok = client.post('/api/user/login',
                      json={'pin': '1234', 'role': 'child'}).get_json().get('token')
    assert tok
    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    r = client.post('/api/user/update',
                    json={'user_id': 1, 'age': 25},
                    headers={'Authorization': f'Bearer {tok}'})
    assert r.status_code == 403


# ─── Regression tests for the external-audit round of fixes ───────────

def test_set_limit_rejects_nan(client):
    """A NaN daily limit must be rejected (every comparison with NaN is False, so it
    slipped past the range check, stored as NULL, and 500'd the child dashboard)."""
    r = client.post('/api/parent/set_limit', json={'user_id': 1, 'daily_limit_hours': float('nan')})
    assert r.status_code == 400
    # And a valid value still works.
    assert client.post('/api/parent/set_limit',
                       json={'user_id': 1, 'daily_limit_hours': 2.0}).status_code == 200
    # The child dashboard must load cleanly afterwards (no NULL-limit 500).
    assert client.get('/api/dashboard/child_enriched?user_id=1').status_code == 200


def test_reflection_rejects_all_empty(client):
    """An all-invalid, note-less reflection is rejected rather than stored as an
    all-NULL row that pollutes the history/averages."""
    r = client.post('/api/child/reflection', json={'user_id': 1, 'mood_rating': 'x'})
    assert r.status_code == 400
    assert client.post('/api/child/reflection',
                       json={'user_id': 1, 'mood_rating': 5}).status_code == 200


def test_end_session_idempotent_single_prediction(client):
    """Ending a session twice must not create a second prediction (atomic end-claim)."""
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    first  = client.post(f'/api/session/{sid}/end')
    second = client.post(f'/api/session/{sid}/end')
    assert first.status_code == 200 and second.status_code == 200
    assert second.get_json().get('already_ended') is True
    import app as appmod
    c = appmod.get_db()
    n = c.execute('SELECT COUNT(*) AS n FROM predictions WHERE session_id=?', (sid,)).fetchone()['n']
    c.close()
    assert n == 1


def test_sleep_impact_ignores_notification_blips_and_alarm_wakes(client):
    """Sleep-impact day counting must not be triggered by (a) a single passive screen_on
    (notification lighting the lock screen) or (b) early-morning alarm wakes (5–6 am);
    genuine repeated night wakes still count, unlocks count as real use, and the
    message names phone use — not gaming (the pilot-reported 100%-vs-0 contradiction)."""
    import app as appmod
    from datetime import datetime, timedelta
    conn = appmod.get_db()
    c = conn.cursor()
    c.execute('DELETE FROM screen_events WHERE user_id=1')
    now = datetime.now()

    def ev(days_ago, hour, minute=0, etype='screen_on'):
        d = (now - timedelta(days=days_ago)).replace(hour=hour, minute=minute,
                                                     second=0, microsecond=0)
        c.execute('INSERT INTO screen_events (user_id, event_type, timestamp) VALUES (1,?,?)',
                  (etype, d.isoformat()))

    # Day 1: one lone 23:00 screen_on (notification blip)  → must NOT count.
    ev(1, 23)
    # Day 2: 05:30 screen_on daily-alarm wake              → must NOT count (outside 22–05).
    ev(2, 5, 30)
    # Day 3: three separate 23:xx screen_ons (real usage)  → counts, and is a disruption.
    ev(3, 23, 0); ev(3, 23, 20); ev(3, 23, 40)
    # Day 4: daytime only                                  → must NOT count.
    ev(4, 15)
    conn.commit()

    res = appmod._sleep_impact_analysis(1, conn)
    conn.close()
    assert res['available'] is True
    assert res['data_source'] == 'screen_events'
    assert res['late_night_sessions'] == 1          # only day 3
    assert res['total_days_analyzed'] == 4
    assert res['sleep_disruption_days'] == 1
    assert 'not just gaming' in res['message']       # can't be read as gaming-at-night

    # With unlock events present, a single genuine unlock at night counts as real use.
    conn = appmod.get_db()
    c = conn.cursor()
    c.execute('DELETE FROM screen_events WHERE user_id=1')
    conn.commit()
    d = (now - timedelta(days=1)).replace(hour=23, minute=15, second=0, microsecond=0)
    c.execute("INSERT INTO screen_events (user_id, event_type, timestamp) VALUES (1,'unlocked',?)",
              (d.isoformat(),))
    conn.commit()
    res2 = appmod._sleep_impact_analysis(1, conn)
    conn.close()
    assert res2['late_night_sessions'] == 1

    # Clean up so other tests see the original (empty) screen_events state.
    conn = appmod.get_db()
    conn.cursor().execute('DELETE FROM screen_events WHERE user_id=1')
    conn.commit()
    conn.close()


def test_streak_spoiled_by_same_day_unhealthy(client):
    """A healthy session then a high-risk session the SAME day must break the streak
    (the day is spoiled regardless of within-day order)."""
    import app as appmod
    # Start from a clean streak row — other tests (end_session) mutate user 1's streak.
    _c = appmod.get_db()
    _c.execute('DELETE FROM streaks WHERE user_id=1')
    _c.commit()
    _c.close()
    appmod._update_streak(1, weekly_hours=7.0, risk_level='casual')      # healthy → credits today
    after_healthy = appmod._update_streak(1, weekly_hours=7.0, risk_level='casual')
    assert after_healthy['current_streak'] >= 1
    spoiled = appmod._update_streak(1, weekly_hours=70.0, risk_level='addicted')  # unhealthy same day
    assert spoiled['current_streak'] == 0
    # A later healthy session the same (spoiled) day must NOT re-credit it.
    again = appmod._update_streak(1, weekly_hours=7.0, risk_level='casual')
    assert again['current_streak'] == 0


def test_all_aggregate_headlines_share_latest_daily_risk(client, monkeypatch):
    """Reproduce the reported 34% day versus 25% last-session discrepancy.

    Aggregate dashboards/reports must agree on the duration-weighted latest day, while
    the recent-session row must remain the actual 25% per-session result.
    """
    from datetime import datetime, timedelta
    import app as appmod

    conn = appmod.get_db()
    uid = appmod.insert_returning_id(
        conn,
        "INSERT INTO users (name, pin, parent_pin, age) VALUES (?,?,?,?)",
        ('Risk Contract Child', '8642', '2468', 16),
        pk='user_id',
    )
    c = conn.cursor()
    day = (datetime.now() - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0)

    def add_session(start, score, category):
        end = start + timedelta(hours=1)
        sid = appmod.insert_returning_id(
            conn,
            "INSERT INTO sessions (user_id, game_name, start_time, end_time, "
            "duration_seconds, final_risk_score, risk_category, confidence) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (uid, 'Candy Crush', start.isoformat(), end.isoformat(), 3600,
             score, category, 0.8),
            pk='session_id',
        )
        c.execute(
            "INSERT INTO predictions (session_id, behavior_score, chat_score, voice_score, "
            "final_risk_score, risk_category, confidence, timestamp, behavior_present, "
            "chat_present, voice_present) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, score, 0.0, 0.0, score, category, 0.8, end.isoformat(), 1, 0, 0),
        )

    # The newer session is Casual/25%, but the two equal-duration sessions average 34%.
    add_session(day, 0.43, 'at_risk')
    add_session(day + timedelta(hours=2), 0.25, 'casual')
    conn.commit()
    conn.close()

    parent = client.get(f'/api/dashboard/parent?user_id={uid}').get_json()
    child = client.get(f'/api/dashboard/user?user_id={uid}').get_json()
    weekly = client.get(f'/api/dashboard/weekly_report?user_id={uid}').get_json()

    expected_period = parent['risk_period']
    assert expected_period['sessions'] == 2
    assert expected_period['aggregation'] == 'latest_active_day_duration_weighted'
    for payload in (parent, child, weekly):
        assert payload['current_risk'] == 'at_risk'
        assert payload['risk_label'] == 'Some concern'
        assert payload['risk_score'] == pytest.approx(0.34)
        assert payload['risk_period'] == expected_period
        assert payload['trend_data'][-1]['score'] == pytest.approx(0.34)

    assert child['stats']['current_risk'] == 'at_risk'
    assert child['stats']['risk_label'] == 'Some concern'
    assert child['stats']['risk_score'] == pytest.approx(0.34)
    assert child['stats']['risk_period'] == expected_period
    # Per-session history is intentionally not flattened into the daily aggregate.
    assert child['recent_sessions'][0]['risk_label'] == 'casual'
    assert child['recent_sessions'][0]['risk_score'] == pytest.approx(0.25)

    if not appmod.FPDF_AVAILABLE:
        pytest.skip('fpdf2 is not installed')

    captured = []
    real_fpdf = appmod.FPDF

    class RecordingFPDF(real_fpdf):
        def cell(self, *args, **kwargs):
            value = kwargs.get('text')
            if value is None and len(args) >= 3:
                value = args[2]
            if value is not None:
                captured.append(str(value))
            return super().cell(*args, **kwargs)

    monkeypatch.setattr(appmod, 'FPDF', RecordingFPDF)
    pdf_response = client.get(f'/api/dashboard/weekly_report/pdf?user_id={uid}')
    assert pdf_response.status_code == 200
    assert pdf_response.content_type == 'application/pdf'
    assert 'SOME CONCERN' in captured
    assert any(text.startswith('Risk Score: 34%') for text in captured)
    assert any('2 sessions' in text for text in captured)


def test_openapi_lists_every_runtime_api_route():
    """Keep the mobile/backend contract index from silently falling behind Flask."""
    import re
    from pathlib import Path
    import app as appmod

    spec_text = (Path(appmod.__file__).with_name('openapi.yaml')
                 .read_text(encoding='utf-8'))
    documented = set(re.findall(r'^  (/api/[^:]+):\s*$', spec_text, re.MULTILINE))

    def canonical(rule):
        return re.sub(r'<(?:[^:>]+:)?([^>]+)>', r'{\1}', rule)

    runtime = {
        canonical(rule.rule)
        for rule in appmod.app.url_map.iter_rules()
        if rule.rule.startswith('/api/')
    }
    assert documented == runtime
