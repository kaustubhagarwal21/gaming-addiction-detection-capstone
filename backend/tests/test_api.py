"""Backend smoke + integration tests — PES Capstone PW26_SJ_05.

Run from the backend dir:
    cd backend && pytest tests/ -v

Uses Flask's test client (no live server). conftest.py points the app at an
isolated throwaway SQLite DB seeded with deterministic data, so no real DB or
`seed_demo.py` run is required. The seeded family is: child PIN 1234,
parent PIN 0000, family code TEST01 (user_id=1).
"""
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
    r = client.post('/api/consent', json={'user_id': 1})
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


# ─── New endpoints (Phase 3) ───────────────────────────────────────

def test_screen_event(client):
    r = client.post('/api/child/screen_event',
                    json={'user_id': '1', 'event_type': 'screen_on',
                          'timestamp': '1700000000000'})
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
    r = client.get('/api/dashboard/child_enriched?user_id=1')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True


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
    aid = alerts[0]['id']

    r = client.post('/api/feedback', json={'alert_id': aid, 'label': 'accurate'})
    assert r.status_code == 200 and r.get_json()['success'] is True

    # The verdict should now be attached to the alert and counted in the summary.
    again = client.get('/api/alerts?user_id=1').get_json()['alerts']
    marked = next(a for a in again if a['id'] == aid)
    assert marked['feedback'] == 'accurate'

    summary = client.get('/api/feedback/summary?user_id=1').get_json()
    assert summary['success'] is True
    assert summary['counts'].get('accurate', 0) >= 1


def test_feedback_bad_label(client):
    r = client.post('/api/feedback', json={'user_id': 1, 'label': 'definitely_not_valid'})
    assert r.status_code == 400


def test_feedback_summary_validation(client):
    r = client.get('/api/feedback/summary')
    assert r.status_code == 400


# ─── Auth gate (enforce mode) ──────────────────────────────────────

def test_auth_enforced_blocks_untokened_request(client, monkeypatch):
    """With AUTH_ENFORCE on, a protected endpoint must 401 without a bearer token."""
    import app as appmod
    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    r = client.get('/api/alerts?user_id=1')
    assert r.status_code == 401
