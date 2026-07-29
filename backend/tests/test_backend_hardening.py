"""Focused regressions for backend integrity/security hardening."""

from datetime import datetime, timedelta
import io

import pytest


def _insert_closed_session(appmod, *, finalization_complete=0,
                           score=None, category=None):
    conn = appmod.get_db()
    now = datetime.now()
    sid = appmod.insert_returning_id(
        conn,
        """INSERT INTO sessions
           (user_id, game_name, start_time, end_time, duration_seconds,
            final_risk_score, risk_category, finalization_complete,
            side_effect_risk_category)
           VALUES (1,'BGMI',?,?,?,?,?,?,?)""",
        ((now - timedelta(minutes=3)).isoformat(), now.isoformat(), 180,
         score, category, finalization_complete,
         category if finalization_complete == 1 else None),
        pk='session_id')
    conn.commit()
    conn.close()
    return sid


def _fake_prediction(appmod, sid, category='at_risk', score=0.5):
    conn = appmod.get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO predictions
           (session_id, behavior_score, chat_score, voice_score,
            final_risk_score, risk_category, confidence, timestamp,
            behavior_present, chat_present, voice_present)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, score, 0.0, score, score, category, 0.8,
         datetime.now().isoformat(), 1, 0, 1))
    c.execute("""UPDATE sessions SET final_risk_score=?, risk_category=?,
                 confidence=0.8 WHERE session_id=?""", (score, category, sid))
    conn.commit()
    conn.close()
    return {
        'risk_category': category,
        'final_risk_score': score,
        'behavior_score': score,
        'chat_score': 0.0,
        'voice_score': score,
        'confidence': 0.8,
        'modalities': {'behavior': True, 'chat': False, 'voice': True},
    }


def test_consent_requires_current_version_and_parent_authorization(client):
    import app as appmod

    base = {'user_id': 1, 'version': appmod.CONSENT_VERSION}
    assert client.post('/api/consent', json=base).status_code == 403
    assert client.post('/api/consent',
                       json={**base, 'parent_pin': 'wrong'}).status_code == 403
    assert client.post('/api/consent',
                       json={**base, 'version': 'legacy',
                             'parent_pin': '0000'}).status_code == 400
    accepted = client.post('/api/consent',
                           json={**base, 'parent_pin': '0000'})
    assert accepted.status_code == 200
    assert accepted.get_json()['consent_version'] == appmod.CONSENT_VERSION


def test_consent_null_legacy_version_is_stale(client):
    import app as appmod

    conn = appmod.get_db()
    conn.execute("""UPDATE users SET consent_given_at=?,
                    consent_version=NULL WHERE user_id=1""",
                 (datetime.now().isoformat(),))
    conn.commit()
    conn.close()
    body = client.get('/api/consent?user_id=1').get_json()
    assert body['consent_given'] is True
    assert body['needs_consent'] is True


def _set_consent(appmod, *, given_at, version):
    conn = appmod.get_db()
    conn.execute(
        '''UPDATE users SET consent_given_at=?, consent_version=? WHERE user_id=1''',
        (given_at, version),
    )
    conn.commit()
    conn.close()


def test_stale_consent_blocks_new_monitoring_collection(client):
    import app as appmod

    _set_consent(
        appmod,
        given_at=(datetime.now() - timedelta(days=1)).isoformat(),
        version='old-policy',
    )
    checks = [
        ('/api/session/start', {'user_id': 1, 'game_name': 'BGMI'}),
        ('/api/child/heartbeat', {'user_id': 1, 'tz_offset_min': 330}),
        ('/api/child/screen_event', {'user_id': 1, 'event_type': 'screen_on'}),
        ('/api/child/notification_event',
         {'user_id': 1, 'package_name': 'com.game'}),
    ]
    for path, payload in checks:
        response = client.post(path, json=payload)
        assert response.status_code == 403, (path, response.get_json())
        assert response.get_json()['consent_required'] is True

    # Restore a current consent timestamp before later shared-DB tests run.
    _set_consent(
        appmod,
        given_at=(datetime.now() - timedelta(minutes=1)).isoformat(),
        version=appmod.CONSENT_VERSION,
    )
    started = client.post(
        '/api/session/start', json={'user_id': 1, 'game_name': 'BGMI'})
    assert started.status_code == 200
    assert client.post(
        f"/api/session/{started.get_json()['session_id']}/end").status_code == 200


def test_reconsent_does_not_authorize_queued_data_for_an_old_session(client):
    import app as appmod

    _set_consent(
        appmod,
        given_at=(datetime.now() - timedelta(minutes=10)).isoformat(),
        version=appmod.CONSENT_VERSION,
    )
    started = client.post(
        '/api/session/start', json={'user_id': 1, 'game_name': 'BGMI'})
    sid = started.get_json()['session_id']

    _set_consent(
        appmod,
        given_at=(datetime.now() - timedelta(days=1)).isoformat(),
        version='old-policy',
    )
    assert client.post(
        f'/api/session/{sid}/chat',
        json={'message': 'queued text', 'source': 'ocr'},
    ).status_code == 403

    # Even after accepting the new policy, this session predates that acceptance.
    _set_consent(
        appmod,
        given_at=datetime.now().isoformat(),
        version=appmod.CONSENT_VERSION,
    )
    queued_posts = [
        (f'/api/session/{sid}/behavioral', {}),
        (f'/api/session/{sid}/chat',
         {'message': 'queued text', 'source': 'ocr'}),
        (f'/api/session/{sid}/voice',
         {'emotion': 'neutral', 'intensity': 0.1, 'duration_seconds': 1}),
        (f'/api/session/{sid}/predict', {}),
    ]
    for path, payload in queued_posts:
        assert client.post(path, json=payload).status_code == 403

    # Cleanup is always allowed so an old client cannot leave an immortal open session.
    ended = client.post(f'/api/session/{sid}/end')
    assert ended.status_code == 200
    assert ended.get_json()['consent_required'] is True
    assert ended.get_json()['prediction']['risk_label'] == 'unknown'
    conn = appmod.get_db()
    assert conn.execute(
        'SELECT COUNT(*) AS n FROM behavioral_data WHERE session_id=?', (sid,)
    ).fetchone()['n'] == 0
    assert conn.execute(
        'SELECT COUNT(*) AS n FROM predictions WHERE session_id=?', (sid,)
    ).fetchone()['n'] == 0
    assert conn.execute(
        'SELECT finalization_complete FROM sessions WHERE session_id=?', (sid,)
    ).fetchone()['finalization_complete'] == 1
    conn.close()


def test_backfill_interval_must_start_after_current_consent(client):
    import app as appmod

    now = datetime.now()
    body = {
        'user_id': 1,
        'game_name': 'Offline Game',
        'start_time': (now - timedelta(minutes=5)).isoformat(),
        'end_time': (now - timedelta(minutes=4)).isoformat(),
        'client_key': 'pre-consent-backfill',
    }
    _set_consent(
        appmod, given_at=now.isoformat(), version=appmod.CONSENT_VERSION)
    assert client.post('/api/session/backfill', json=body).status_code == 403

    _set_consent(
        appmod,
        given_at=(now - timedelta(minutes=10)).isoformat(),
        version=appmod.CONSENT_VERSION,
    )
    body['client_key'] = 'post-consent-backfill'
    assert client.post('/api/session/backfill', json=body).status_code == 200


def test_reconsent_handoff_closes_old_session_without_deriving_prediction(client):
    import app as appmod

    _set_consent(
        appmod,
        given_at=(datetime.now() - timedelta(minutes=10)).isoformat(),
        version=appmod.CONSENT_VERSION,
    )
    old = client.post(
        '/api/session/start', json={'user_id': 1, 'game_name': 'Old Game'})
    old_sid = old.get_json()['session_id']

    _set_consent(
        appmod,
        given_at=datetime.now().isoformat(),
        version=appmod.CONSENT_VERSION,
    )
    new = client.post(
        '/api/session/start', json={'user_id': 1, 'game_name': 'New Game'})
    assert new.status_code == 200

    conn = appmod.get_db()
    old_row = conn.execute(
        '''SELECT end_time, finalization_complete FROM sessions
           WHERE session_id=?''',
        (old_sid,),
    ).fetchone()
    pred_count = conn.execute(
        'SELECT COUNT(*) AS n FROM predictions WHERE session_id=?', (old_sid,)
    ).fetchone()['n']
    conn.close()
    assert old_row['end_time'] is not None
    assert old_row['finalization_complete'] == 1
    assert pred_count == 0
    assert client.post(
        f"/api/session/{new.get_json()['session_id']}/end").status_code == 200


def test_unknown_delete_scope_does_not_wipe_data(client):
    import app as appmod

    conn = appmod.get_db()
    before = conn.execute(
        'SELECT COUNT(*) AS n FROM sessions WHERE user_id=1').fetchone()['n']
    conn.close()
    response = client.post('/api/user/delete_data',
                           json={'user_id': 1, 'scope': 'surprise'})
    assert response.status_code == 400
    conn = appmod.get_db()
    after = conn.execute(
        'SELECT COUNT(*) AS n FROM sessions WHERE user_id=1').fetchone()['n']
    conn.close()
    assert after == before


def test_finalization_stays_committed_when_push_fails(client, monkeypatch):
    import app as appmod

    sid = _insert_closed_session(appmod)
    monkeypatch.setattr(appmod, '_save_behavioral_snapshot',
                        lambda session_id: None)
    monkeypatch.setattr(
        appmod, 'run_prediction',
        lambda session_id, explain=False:
            _fake_prediction(appmod, session_id, 'addicted', 0.8))
    monkeypatch.setattr(
        appmod, '_push_high_risk',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('network down')))

    prediction = appmod._finalize_session_once(sid)
    assert prediction['risk_category'] == 'addicted'
    conn = appmod.get_db()
    row = conn.execute(
        """SELECT finalization_complete, side_effect_risk_category
           FROM sessions WHERE session_id=?""", (sid,)).fetchone()
    count = conn.execute(
        'SELECT COUNT(*) AS n FROM predictions WHERE session_id=?',
        (sid,)).fetchone()['n']
    conn.close()
    assert row['finalization_complete'] == 1
    assert row['side_effect_risk_category'] == 'addicted'
    assert count == 1


def test_closed_voice_segment_is_durably_rescored(client, monkeypatch):
    import app as appmod

    sid = _insert_closed_session(
        appmod, finalization_complete=1, score=0.2, category='casual')
    conn = appmod.get_db()
    conn.execute(
        """INSERT INTO predictions
           (session_id, final_risk_score, risk_category, confidence, timestamp,
            behavior_present, chat_present, voice_present)
           VALUES (?,?,?,0.8,?,1,0,0)""",
        (sid, 0.2, 'casual', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        appmod, 'run_prediction',
        lambda session_id, explain=False:
            _fake_prediction(appmod, session_id, 'at_risk', 0.5))

    response = client.post(
        f'/api/session/{sid}/voice',
        json={'emotion': 'angry', 'intensity': 0.8, 'duration_seconds': 10})
    assert response.status_code == 200
    conn = appmod.get_db()
    state = conn.execute(
        """SELECT voice_rescore_pending, side_effect_risk_category
           FROM sessions WHERE session_id=?""", (sid,)).fetchone()
    alerts = conn.execute(
        """SELECT COUNT(*) AS n FROM alerts
           WHERE session_id=? AND type='risk'""", (sid,)).fetchone()['n']
    conn.close()
    assert state['voice_rescore_pending'] == 0
    assert state['side_effect_risk_category'] == 'at_risk'
    assert alerts == 1


def test_voice_and_chat_reject_poisoning_inputs(client):
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    assert client.post(
        f'/api/session/{sid}/voice',
        json={'emotion': 'made_up', 'intensity': 0.2,
              'duration_seconds': 10}).status_code == 400
    assert client.post(
        f'/api/session/{sid}/voice',
        json={'emotion': 'angry', 'intensity': float('nan'),
              'duration_seconds': 10}).status_code == 400
    assert client.post(
        f'/api/session/{sid}/voice',
        data={'audio': (io.BytesIO(b'x' * (2 * 1024 * 1024)), 'large.wav')},
        content_type='multipart/form-data').status_code == 413
    assert client.post(
        f'/api/session/{sid}/chat',
        json={'message': 'hello', 'source': 'made_up'}).status_code == 400
    assert client.post(
        f'/api/session/{sid}/chat',
        json={'message': True, 'source': 'ocr'}).status_code == 400


def test_behavioral_rejects_nonfinite_and_out_of_range(client):
    sid = client.post('/api/session/start',
                      json={'user_id': 1, 'game_name': 'BGMI'}).get_json()['session_id']
    assert client.post(
        f'/api/session/{sid}/behavioral',
        json={'late_night_play_ratio': float('nan')}).status_code == 400
    assert client.post(
        f'/api/session/{sid}/behavioral',
        json={'daily_play_time_hours': 25}).status_code == 400


def test_alert_unread_total_and_mark_read_validation(client):
    import app as appmod

    conn = appmod.get_db()
    c = conn.cursor()
    ids = []
    for i in range(55):
        ids.append(appmod._insert_alert(
            c, 1, 'test', f'alert {i}', 'info'))
    conn.commit()
    expected = conn.execute(
        'SELECT COUNT(*) AS n FROM alerts WHERE user_id=1 AND read=0').fetchone()['n']
    conn.close()

    feed = client.get('/api/alerts?user_id=1').get_json()
    assert len(feed['alerts']) == 50
    assert feed['unread_count'] == expected
    parent = client.get('/api/dashboard/parent?user_id=1').get_json()
    assert parent['unread_alert_count'] == expected
    marked = client.post(
        '/api/alerts/mark_read',
        json={'alert_ids': [ids[0], ids[0], ids[1]]})
    assert marked.status_code == 200
    assert marked.get_json()['marked_count'] == 2
    assert client.post(
        '/api/alerts/mark_read',
        json={'alert_ids': [True]}).status_code == 400


def test_dashboards_expose_served_risk_thresholds(client):
    import app as appmod

    expected = {
        'some_concern': appmod.RISK_T1,
        'high_concern': appmod.RISK_T2,
    }
    assert client.get(
        '/api/dashboard/user?user_id=1').get_json()['risk_thresholds'] == expected
    assert client.get(
        '/api/dashboard/parent?user_id=1').get_json()['risk_thresholds'] == expected


@pytest.mark.parametrize('path', [
    '/api/user/profile',
    '/api/dashboard/user',
    '/api/dashboard/parent',
    '/api/child/status',
    '/api/dashboard/weekly_report',
    '/api/dashboard/weekly_report/pdf',
    '/api/child/reflections',
])
def test_user_scoped_gets_require_explicit_user_id(client, path):
    assert client.get(path).status_code == 400


def test_query_integer_bounds_do_not_expand_unbounded(client):
    assert client.get(
        '/api/sessions?user_id=1&limit=-1').status_code == 200
    assert client.get(
        '/api/dashboard/user?user_id=1&days=999999999999999999999').status_code == 200
    assert client.get(
        '/api/child/reflections?user_id=1&days=999999999999999999999').status_code == 200


@pytest.mark.parametrize(
    ('path', 'body'),
    [
        ('/api/child/heartbeat', {'tz_offset_min': 330}),
        ('/api/child/tamper', {'event': 'logout'}),
        ('/api/verify_parent_pin', {'pin': '0000'}),
        ('/api/child/screen_event', {'event_type': 'screen_on'}),
        ('/api/child/notification_event', {'package_name': 'com.game'}),
        ('/api/parent/set_limit', {'daily_limit_hours': 2}),
        ('/api/parent/nudge', {'message': 'Take a break'}),
        ('/api/counselor/chat', {'message': 'hello'}),
        ('/api/child/reflection', {'mood_rating': 3}),
    ],
)
def test_all_user_scoped_posts_reject_nonpositive_or_fractional_ids(
        client, path, body):
    for invalid_id in (0, -1, True, 1.5):
        response = client.post(path, json={**body, 'user_id': invalid_id})
        assert response.status_code == 400, (path, invalid_id, response.get_json())


@pytest.mark.parametrize('offset', [-841, 841, 330.5, True, 'not-a-timezone'])
def test_heartbeat_rejects_invalid_timezone_offsets(client, offset):
    assert client.post(
        '/api/child/heartbeat',
        json={'user_id': 1, 'tz_offset_min': offset},
    ).status_code == 400


@pytest.mark.parametrize('field', [
    'device_admin', 'perm_usage', 'perm_accessibility', 'perm_keyboard',
    'voice_capture',
])
@pytest.mark.parametrize('value', [-1, 2, 0.5, '1'])
def test_heartbeat_rejects_non_boolean_health_flags(client, field, value):
    assert client.post(
        '/api/child/heartbeat',
        json={'user_id': 1, field: value},
    ).status_code == 400


def test_reflection_uses_child_ui_one_to_five_scale(client):
    assert client.post(
        '/api/child/reflection',
        json={'user_id': 1, 'mood_rating': 6}).status_code == 400
    assert client.post(
        '/api/child/reflection',
        json={'user_id': 1, 'mood_rating': 4}).status_code == 200


@pytest.mark.parametrize('payload', [
    {'user_id': 1, 'label': True},
    {'user_id': 1, 'label': 'accurate', 'note': 123},
    {'user_id': 0, 'label': 'accurate'},
    {'alert_id': -1, 'label': 'accurate'},
])
def test_feedback_rejects_malformed_scalars(client, payload):
    assert client.post('/api/feedback', json=payload).status_code == 400


def test_feedback_on_old_risk_alert_snapshots_that_sessions_prediction(client):
    import app as appmod

    old_sid = _insert_closed_session(appmod)
    _fake_prediction(appmod, old_sid, 'at_risk', 0.42)
    conn = appmod.get_db()
    old_pred = conn.execute(
        'SELECT id FROM predictions WHERE session_id=? ORDER BY id DESC LIMIT 1',
        (old_sid,),
    ).fetchone()['id']
    alert_id = appmod._insert_alert(
        conn.cursor(), 1, 'risk', 'Older risk alert', 'medium',
        session_id=old_sid,
    )
    conn.commit()
    conn.close()

    # A later, unrelated prediction must not become the training snapshot for the old
    # alert the parent is actually rating.
    new_sid = _insert_closed_session(appmod)
    _fake_prediction(appmod, new_sid, 'addicted', 0.91)

    response = client.post(
        '/api/feedback',
        json={'alert_id': alert_id, 'label': 'accurate'},
    )
    assert response.status_code == 200
    conn = appmod.get_db()
    row = conn.execute(
        '''SELECT prediction_id, risk_category, risk_score FROM feedback
           WHERE alert_id=?''',
        (alert_id,),
    ).fetchone()
    conn.close()
    assert row['prediction_id'] == old_pred
    assert row['risk_category'] == 'at_risk'
    assert row['risk_score'] == pytest.approx(0.42)


def test_toxicity_feedback_does_not_snapshot_unrelated_fused_risk(client):
    import app as appmod

    sid = _insert_closed_session(appmod)
    _fake_prediction(appmod, sid, 'addicted', 0.88)
    conn = appmod.get_db()
    alert_id = appmod._insert_alert(
        conn.cursor(), 1, 'toxicity', 'Toxic message', 'high',
        session_id=sid,
    )
    conn.commit()
    conn.close()

    assert client.post(
        '/api/feedback',
        json={'alert_id': alert_id, 'label': 'false_alarm'},
    ).status_code == 200
    conn = appmod.get_db()
    row = conn.execute(
        '''SELECT prediction_id, risk_category, risk_score FROM feedback
           WHERE alert_id=?''',
        (alert_id,),
    ).fetchone()
    conn.close()
    assert dict(row) == {
        'prediction_id': None,
        'risk_category': None,
        'risk_score': None,
    }


def test_feedback_upsert_preserves_one_verdict_per_alert(client):
    import app as appmod

    sid = _insert_closed_session(appmod)
    _fake_prediction(appmod, sid, 'at_risk', 0.51)
    conn = appmod.get_db()
    alert_id = appmod._insert_alert(
        conn.cursor(), 1, 'risk', 'Risk alert', 'medium', session_id=sid,
    )
    conn.commit()
    conn.close()

    assert client.post(
        '/api/feedback',
        json={'alert_id': alert_id, 'label': 'accurate'},
    ).status_code == 200
    assert client.post(
        '/api/feedback',
        json={'alert_id': alert_id, 'label': 'false_alarm'},
    ).status_code == 200

    conn = appmod.get_db()
    rows = conn.execute(
        'SELECT label FROM feedback WHERE alert_id=?', (alert_id,),
    ).fetchall()
    conn.close()
    assert [row['label'] for row in rows] == ['false_alarm']


def test_feedback_rejects_alert_types_without_a_supported_training_target(client):
    import app as appmod

    conn = appmod.get_db()
    alert_id = appmod._insert_alert(
        conn.cursor(), 1, 'login', 'Monitoring resumed', 'info',
    )
    conn.commit()
    conn.close()
    assert client.post(
        '/api/feedback',
        json={'alert_id': alert_id, 'label': 'accurate'},
    ).status_code == 400


def test_anomaly_detection_groups_sessions_by_child_local_day(client):
    import app as appmod

    conn = appmod.get_db()
    uid = appmod.insert_returning_id(
        conn,
        '''INSERT INTO users
           (name, age, pin, parent_pin, pin_hash, parent_pin_hash, family_code,
            tz_offset_min, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        ('Timezone child', 14, '', '', appmod.hash_pin('765432'),
         appmod.hash_pin('765431'), 'TZTEST01', 840, datetime.now().isoformat()),
        pk='user_id',
    )
    c = conn.cursor()
    shift = appmod._tz_shift_min(c, uid)
    local_today = appmod._local_now(c, uid).date()
    # Place every session just after CHILD midnight. With this large positive offset,
    # their stored server dates are the preceding dates; SQL SUBSTR grouping/server
    # "today" therefore misses the 10-hour child-local-today spike.
    for days_ago in range(7, -1, -1):
        local_start = datetime.combine(
            local_today - timedelta(days=days_ago),
            datetime.min.time(),
        ) + timedelta(minutes=30)
        stored_start = local_start - timedelta(minutes=shift)
        duration = 10 * 3600 if days_ago == 0 else 3600
        c.execute(
            '''INSERT INTO sessions
               (user_id, game_name, start_time, end_time, duration_seconds)
               VALUES (?,?,?,?,?)''',
            (uid, 'Timezone Game', stored_start.isoformat(),
             (stored_start + timedelta(seconds=duration)).isoformat(), duration),
        )
    conn.commit()
    conn.close()

    anomalies = appmod._detect_anomalies(uid, force=True)
    spike = next(a for a in anomalies if a['kind'] == 'spike_daily_hours')
    assert "Today's playtime (10.0h)" in spike['message']


def test_fcm_payload_carries_alert_identity_and_high_priority(monkeypatch):
    import app as appmod

    captured = {}

    class FakeMessaging:
        class AndroidConfig:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class Message:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        @staticmethod
        def send(message):
            return 'ok'

    monkeypatch.setattr(appmod, '_ensure_firebase', lambda: True)
    monkeypatch.setattr(appmod, '_firebase_msg', FakeMessaging)
    result = appmod._send_fcm_push(
        'token', 'Title', 'Body', event_type='permission',
        child_id=1, child_name='Child', alert_id=42, severity='high',
        family_code='TEST01')
    assert result == 'ok'
    assert captured['data']['alert_id'] == '42'
    assert captured['data']['type'] == 'permission'
    assert captured['data']['severity'] == 'high'
    assert captured['data']['family_code'] == 'TEST01'
    assert captured['android'].kwargs['priority'] == 'high'


def test_invalid_fcm_token_is_pruned_from_current_and_legacy_stores(monkeypatch):
    import app as appmod

    dead = 'dead-fcm-token'
    conn = appmod.get_db()
    conn.execute('UPDATE users SET fcm_token=? WHERE user_id=1', (dead,))
    conn.execute('DELETE FROM guardian_devices WHERE fcm_token=?', (dead,))
    conn.execute(
        'INSERT INTO guardian_devices (family_code, fcm_token, updated_at) '
        'VALUES (?,?,?)',
        ('TEST01', dead, '2026-01-01T00:00:00'),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        appmod,
        '_send_fcm_push',
        lambda token, *args, **kwargs: 'invalid' if token == dead else 'ok',
    )
    appmod._push_to_family('TEST01', 'Title', 'Body')

    conn = appmod.get_db()
    assert conn.execute(
        'SELECT 1 FROM guardian_devices WHERE fcm_token=?', (dead,)
    ).fetchone() is None
    assert conn.execute(
        'SELECT fcm_token FROM users WHERE user_id=1'
    ).fetchone()['fcm_token'] is None
    conn.close()


@pytest.mark.parametrize(
    ('path', 'payload'),
    [
        ('/api/user/fcm_token', [1]),
        ('/api/user/fcm_token', {'user_id': 'not-an-id', 'fcm_token': 'token'}),
        ('/api/user/fcm_token', {'user_id': True, 'fcm_token': 'token'}),
        ('/api/user/fcm_token', {'user_id': 1, 'fcm_token': {'nested': 'value'}}),
        ('/api/user/fcm_token', {'user_id': 1, 'fcm_token': 'x' * 4097}),
        ('/api/user/fcm_token/unregister', [1]),
        ('/api/user/fcm_token/unregister', {'fcm_token': False}),
        ('/api/user/fcm_token/unregister', {'fcm_token': 'x' * 4097}),
    ],
)
def test_fcm_token_endpoints_reject_malformed_values_without_500(
        client, path, payload):
    assert client.post(path, json=payload).status_code == 400


def test_parent_token_sees_sibling_registered_after_login(client, monkeypatch):
    import app as appmod

    login = client.post(
        '/api/user/login',
        json={'pin': '0000', 'role': 'parent', 'family_code': 'TEST01'})
    token = login.get_json()['token']
    sibling = client.post(
        '/api/register',
        json={'name': 'Later sibling', 'age': 12, 'pin': '876543',
              'parent_pin': '0000', 'family_code': 'TEST01'})
    assert sibling.status_code == 200
    sibling_id = sibling.get_json()['user_id']
    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    roster = client.get(
        '/api/parent/children',
        headers={'Authorization': f'Bearer {token}'})
    assert roster.status_code == 200
    assert sibling_id in {child['user_id'] for child in roster.get_json()['children']}
    conn = appmod.get_db()
    conn.execute('DELETE FROM users WHERE user_id=?', (sibling_id,))
    conn.commit()
    conn.close()


def test_pin_rotation_revokes_pre_rotation_tokens(client, monkeypatch):
    import app as appmod

    login = client.post(
        '/api/user/login',
        json={'pin': '0000', 'role': 'parent', 'family_code': 'TEST01'})
    old_token = login.get_json()['token']
    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    headers = {'Authorization': f'Bearer {old_token}'}
    changed = client.post(
        '/api/user/update',
        json={'user_id': 1, 'parent_pin': '9998'}, headers=headers)
    assert changed.status_code == 200
    assert client.get('/api/alerts?user_id=1', headers=headers).status_code == 401

    replacement = client.post(
        '/api/user/login',
        json={'pin': '9998', 'role': 'parent', 'family_code': 'TEST01'})
    replacement_headers = {
        'Authorization': f"Bearer {replacement.get_json()['token']}"}
    restored = client.post(
        '/api/user/update',
        json={'user_id': 1, 'parent_pin': '0000'},
        headers=replacement_headers)
    assert restored.status_code == 200


@pytest.mark.parametrize(
    ('login_payload', 'rotate_sql', 'rotate_params'),
    [
        (
            {'pin': '1234', 'role': 'child'},
            'UPDATE users SET auth_version=auth_version+1 WHERE user_id=?',
            (1,),
        ),
        (
            {'pin': '0000', 'role': 'parent', 'family_code': 'TEST01'},
            'UPDATE users SET family_auth_version=family_auth_version+1 '
            'WHERE family_code=?',
            ('TEST01',),
        ),
    ],
)
def test_login_token_uses_version_read_with_authenticated_pin(
        client, monkeypatch, login_payload, rotate_sql, rotate_params):
    """A rotation after the credential SELECT cannot upgrade an old-PIN login.

    Besides closing the race, passing this version into mint_token avoids borrowing a
    second Postgres connection while the login handler still owns its first one.
    """
    import app as appmod

    real_mint = appmod.mint_token
    conn = appmod.get_db()
    if login_payload['role'] == 'parent':
        row = conn.execute(
            'SELECT family_auth_version AS v FROM users WHERE family_code=? LIMIT 1',
            (login_payload['family_code'],),
        ).fetchone()
    else:
        row = conn.execute(
            'SELECT auth_version AS v FROM users WHERE user_id=1',
        ).fetchone()
    initial_version = int(row['v'] or 0)
    conn.close()

    def rotate_after_auth(*args, **kwargs):
        # The handler must pass the version from its authentication SELECT rather than
        # asking mint_token to re-read whichever version is current now.
        assert kwargs.get('credential_version') == initial_version
        conn = appmod.get_db()
        conn.execute(rotate_sql, rotate_params)
        conn.commit()
        conn.close()
        return real_mint(*args, **kwargs)

    monkeypatch.setattr(appmod, 'mint_token', rotate_after_auth)
    login = client.post('/api/user/login', json=login_payload)
    assert login.status_code == 200

    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    response = client.get(
        '/api/dashboard/user?user_id=1',
        headers={'Authorization': f"Bearer {login.get_json()['token']}"},
    )
    assert response.status_code == 401
