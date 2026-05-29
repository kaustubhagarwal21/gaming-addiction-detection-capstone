"""
Demo seed data — PES Capstone PW26_SJ_05
Usage:  python backend/seed_demo.py
Creates 15 historical sessions showing a realistic risk-escalation pattern.
Re-running is safe: existing sessions for user_id=1 are cleared first.
"""
import sqlite3, os, random, hmac, hashlib
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'gaming_addiction.db')

# Must match app.py's PIN hashing so seeded PINs authenticate. With no env set,
# both sides fall back to the same dev secret, so the demo works out of the box.
PIN_PEPPER = (os.environ.get('PIN_PEPPER') or os.environ.get('AUTH_SECRET')
              or 'dev-insecure-secret-DO-NOT-USE-IN-PRODUCTION')


def hash_pin(pin):
    return hmac.new(PIN_PEPPER.encode(), str(pin).strip().encode(), hashlib.sha256).hexdigest()


def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SESSION_PLAN = [
    # (days_ago, dur_min, game,         risk_cat,   risk_score, hour, chats,                                        emotion)
    (28, 75,  'Minecraft',   'casual',   0.15, 16, [],                                                           'neutral'),
    (26, 90,  'Minecraft',   'casual',   0.18, 15, [],                                                           'neutral'),
    (24, 60,  'Among Us',    'casual',   0.12, 17, ['gg', 'nice shot'],                                          'neutral'),
    (22, 105, 'BGMI',        'casual',   0.22, 16, ['lets go', 'good game'],                                     'excited'),
    (20, 80,  'Minecraft',   'casual',   0.20, 15, [],                                                           'neutral'),
    (18, 95,  'BGMI',        'casual',   0.25, 17, ['wp guys', 'gg'],                                            'excited'),
    (16, 120, 'COD Mobile',  'at_risk',  0.38, 21, ['wtf', 'noob team'],                                        'frustrated'),
    (14, 150, 'BGMI',        'at_risk',  0.42, 22, ['stupid', 'this game sucks'],                               'frustrated'),
    (12, 135, 'COD Mobile',  'at_risk',  0.45, 20, ['trash', 'idiot teammates'],                                'frustrated'),
    (10, 180, 'BGMI',        'at_risk',  0.52, 23, ['hate this', 'so dumb'],                                    'angry'),
    (8,  160, 'COD Mobile',  'at_risk',  0.55, 22, ['so stupid', 'noob'],                                       'angry'),
    (6,  240, 'BGMI',        'addicted', 0.72, 23, ['trash game', 'die noob', 'stupid'],                        'angry'),
    (4,  220, 'COD Mobile',  'addicted', 0.78, 1,  ['kys loser', 'wtf man', 'stupid game'],                     'angry'),
    (2,  270, 'BGMI',        'addicted', 0.81, 0,  ['rage quit', 'hate this game'],                             'angry'),
    (1,  300, 'COD Mobile',  'addicted', 0.85, 23, ['trash team', 'loser', 'idiot', 'die'],                     'angry'),
]

PRIYA_PLAN = [
    # (days_ago, dur_min, game,         risk_cat,  risk_score, hour, chats,                        emotion)
    (25, 60,  'Candy Crush',  'casual',  0.10, 15, [],                                           'neutral'),
    (22, 45,  'Minecraft',    'casual',  0.14, 16, ['lets build', 'nice'],                       'excited'),
    (19, 55,  'Roblox',       'casual',  0.17, 17, ['fun game', 'cool'],                         'excited'),
    (16, 90,  'Roblox',       'casual',  0.22, 21, ['one more round', 'so fun'],                 'excited'),
    (13, 120, 'Roblox',       'at_risk', 0.38, 22, ['nooo', 'not fair', 'ugh'],                  'frustrated'),
    (10, 140, 'Roblox',       'at_risk', 0.44, 21, ['why', 'this is dumb', 'so annoying'],       'frustrated'),
    (7,  160, 'Roblox',       'at_risk', 0.51, 23, ['stupid', 'hate losing', 'not stopping'],    'angry'),
    (4,  180, 'Roblox',       'at_risk', 0.56, 22, ['need to win', 'cant stop', 'one more'],     'angry'),
    (2,  200, 'Roblox',       'at_risk', 0.60, 23, ['so addicted', 'just one more', 'tired'],    'angry'),
    (1,  210, 'Roblox',       'at_risk', 0.63, 0,  ['cant sleep', 'need to play', 'one more'],   'angry'),
]

PSY_LEVEL = {'casual': 2.5, 'at_risk': 5.5, 'addicted': 8.5}


def seed_child(c, conn, user_id, name, plan):
    """Seed sessions for one child."""
    c.execute("DELETE FROM alerts WHERE user_id=?", (user_id,))
    c.execute("""DELETE FROM voice_events WHERE session_id IN
                 (SELECT session_id FROM sessions WHERE user_id=?)""", (user_id,))
    c.execute("""DELETE FROM chat_messages WHERE session_id IN
                 (SELECT session_id FROM sessions WHERE user_id=?)""", (user_id,))
    c.execute("""DELETE FROM behavioral_data WHERE session_id IN
                 (SELECT session_id FROM sessions WHERE user_id=?)""", (user_id,))
    c.execute("""DELETE FROM predictions WHERE session_id IN
                 (SELECT session_id FROM sessions WHERE user_id=?)""", (user_id,))
    c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.commit()

    now = datetime.now()
    inserted = 0
    for days_ago, dur_min, game, risk_cat, risk_score, hour_start, chats, emotion in plan:
        start_dt = (now - timedelta(days=days_ago)).replace(
            hour=hour_start, minute=random.randint(0, 29), second=0, microsecond=0)
        end_dt = start_dt + timedelta(minutes=dur_min)
        psy = PSY_LEVEL[risk_cat]
        lnr = 0.65 if (hour_start >= 22 or hour_start < 6) else 0.08

        c.execute('''INSERT INTO sessions
                     (user_id, game_name, start_time, end_time, duration_seconds,
                      final_risk_score, risk_category, confidence)
                     VALUES (?,?,?,?,?,?,?,?)''',
                  (user_id, game, start_dt.isoformat(), end_dt.isoformat(),
                   dur_min * 60, risk_score, risk_cat, 0.78))
        sid = c.lastrowid

        daily = (dur_min / 60.0) * (1.3 if risk_cat == 'addicted' else 1.0)
        weekly = daily * (6 if risk_cat == 'addicted' else 4 if risk_cat == 'at_risk' else 3)
        c.execute('''INSERT INTO behavioral_data
                     (session_id, daily_play_time_hours, weekly_play_time_hours, sessions_per_day,
                      avg_session_duration_min, late_night_play_ratio, days_played_per_week,
                      longest_play_streak_days, binge_sessions_per_week,
                      avg_break_between_sessions_min, rapid_relogin_ratio,
                      urge_to_continue_score, loss_of_time_awareness_score,
                      control_loss_score, craving_score, tolerance_score,
                      missed_sleep_days_per_week, fatigue_after_play_score,
                      routine_disruption_score, neglect_responsibilities_score,
                      gaming_priority_score, timestamp)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (sid, daily, weekly,
                   1.5 if risk_cat == 'casual' else 3.0 if risk_cat == 'at_risk' else 5.0,
                   float(dur_min), lnr,
                   4 if risk_cat == 'casual' else 6 if risk_cat == 'at_risk' else 7,
                   3 if risk_cat == 'casual' else 8 if risk_cat == 'at_risk' else 20,
                   0.3 if risk_cat == 'casual' else 2.0 if risk_cat == 'at_risk' else 5.5,
                   180 if risk_cat == 'casual' else 90 if risk_cat == 'at_risk' else 25,
                   0.05 if risk_cat == 'casual' else 0.25 if risk_cat == 'at_risk' else 0.6,
                   psy, psy, psy, psy, psy,
                   0 if risk_cat == 'casual' else 2.0 if risk_cat == 'at_risk' else 5.0,
                   2.0 if risk_cat == 'casual' else 5.0 if risk_cat == 'at_risk' else 8.5,
                   2.0 if risk_cat == 'casual' else 5.0 if risk_cat == 'at_risk' else 8.0,
                   2.0 if risk_cat == 'casual' else 5.0 if risk_cat == 'at_risk' else 8.0,
                   2.0 if risk_cat == 'casual' else 5.0 if risk_cat == 'at_risk' else 8.5,
                   start_dt.isoformat()))

        b_s = min(0.95, risk_score * 1.1)
        c_s = min(0.9, len(chats) * 0.12 + risk_score * 0.25)
        v_s = 0.75 if emotion == 'angry' else 0.45 if emotion == 'frustrated' else 0.15
        c.execute('''INSERT INTO predictions
                     (session_id, behavior_score, chat_score, voice_score,
                      final_risk_score, risk_category, confidence, timestamp)
                     VALUES (?,?,?,?,?,?,?,?)''',
                  (sid, round(b_s, 3), round(c_s, 3), round(v_s, 3),
                   risk_score, risk_cat, 0.78, end_dt.isoformat()))

        for msg in chats:
            tox = 0.75 if any(w in msg for w in ['kys','die','trash','loser','idiot','stupid']) else 0.4
            c.execute('''INSERT INTO chat_messages (session_id, message, source, confidence, timestamp)
                         VALUES (?,?,?,?,?)''', (sid, msg, 'keyboard', tox, start_dt.isoformat()))

        if emotion != 'neutral':
            intensity = 0.88 if emotion == 'angry' else 0.60
            c.execute('''INSERT INTO voice_events (session_id, emotion, intensity, duration_s, timestamp)
                         VALUES (?,?,?,?,?)''',
                      (sid, emotion, intensity, float(dur_min * 30), start_dt.isoformat()))

        if risk_cat == 'addicted':
            c.execute('''INSERT INTO alerts (user_id, type, message, severity, read, created_at)
                         VALUES (?,?,?,?,?,?)''',
                      (user_id, 'risk',
                       f'High addiction risk detected for {name} — score {int(risk_score * 100)}%.',
                       'high', 0, end_dt.isoformat()))
        elif risk_cat == 'at_risk' and risk_score > 0.50:
            c.execute('''INSERT INTO alerts (user_id, type, message, severity, read, created_at)
                         VALUES (?,?,?,?,?,?)''',
                      (user_id, 'risk',
                       f'At-risk patterns detected for {name} — score {int(risk_score * 100)}%.',
                       'medium', 1, end_dt.isoformat()))
        inserted += 1

    conn.commit()
    return inserted


def seed_extras(c, conn, user_id, name):
    """Seed reflections, counselor messages, and screen events for richer demo."""
    now = datetime.now()

    # Clear existing
    for table in ('reflections', 'counselor_messages', 'screen_events',
                  'notification_events', 'anomalies'):
        try:
            c.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        except Exception:
            pass

    # 14 days of daily reflections (mood, sleep, energy)
    for d in range(14, 0, -1):
        dt = now - timedelta(days=d)
        # Mood degrades as risk escalates
        if d > 10:
            mood, sleep_q, energy = 4, 4, 4
        elif d > 6:
            mood, sleep_q, energy = 3, 3, 3
        else:
            mood, sleep_q, energy = 2, 2, 2
        notes_pool = {
            4: ['Great day', 'Felt good', 'Productive'],
            3: ['Okay day', 'Bit tired', 'Played a lot'],
            2: ['Stayed up too late', 'Couldn\'t stop playing', 'Skipped homework'],
        }
        note = random.choice(notes_pool.get(mood, ['—']))
        c.execute('''INSERT INTO reflections
                     (user_id, mood_rating, sleep_quality, energy_level, note, created_at)
                     VALUES (?,?,?,?,?,?)''',
                  (user_id, mood, sleep_q, energy, note, dt.isoformat()))

    # Sample counselor conversation
    counselor_seq = [
        ('user',      'hey mira'),
        ('assistant', "Hi! I'm Mira — your gaming wellness companion. How are you feeling today?"),
        ('user',      'tired, couldnt stop last night'),
        ('assistant', "Sounds like you've been pushing hard. Sleep is when your brain locks in everything you've learned — including your gaming reflexes. Want to talk about your sleep this week?"),
        ('user',      'i keep wanting to play even when im tired'),
        ('assistant', "That pull to play again is real — it's literally a dopamine signal. Try this: set a 5-minute timer, do something with your hands (cook, draw, stretch). Most cravings fade in under 10. Want me to set a check-in?"),
    ]
    base = now - timedelta(days=2)
    for i, (role, content) in enumerate(counselor_seq):
        c.execute('''INSERT INTO counselor_messages (user_id, role, content, created_at)
                     VALUES (?,?,?,?)''',
                  (user_id, role, content, (base + timedelta(minutes=i * 2)).isoformat()))

    # Screen events: late-night wake patterns
    for d in range(14, 0, -1):
        dt = now - timedelta(days=d)
        # 2-4 events per day, more late-night ones for recent days
        late_count = 0 if d > 10 else 1 if d > 6 else 3
        for h in [9, 13, 18, 21]:
            ts = dt.replace(hour=h, minute=random.randint(0, 59))
            c.execute("INSERT INTO screen_events (user_id, event_type, timestamp) VALUES (?,?,?)",
                      (user_id, 'screen_on', ts.isoformat()))
        for _ in range(late_count):
            late_hr = random.choice([23, 0, 1, 2])
            ts = dt.replace(hour=late_hr, minute=random.randint(0, 59))
            c.execute("INSERT INTO screen_events (user_id, event_type, timestamp) VALUES (?,?,?)",
                      (user_id, 'screen_on', ts.isoformat()))

    # Gaming app notifications
    for d in range(7, 0, -1):
        dt = now - timedelta(days=d)
        for _ in range(random.randint(2, 8) if d < 5 else random.randint(0, 3)):
            ts = dt + timedelta(hours=random.randint(8, 22), minutes=random.randint(0, 59))
            c.execute("""INSERT INTO notification_events
                         (user_id, package_name, game_name, notification_title, timestamp)
                         VALUES (?,?,?,?,?)""",
                      (user_id, 'com.tencent.ig', 'BGMI',
                       random.choice(['New event!', 'Your friend is online',
                                      'Daily reward ready', 'Match starting']),
                       ts.isoformat()))

    conn.commit()


def seed():
    conn = get_db()
    c    = conn.cursor()

    # Ensure the keyed-hash columns exist even if seeding runs before the updated
    # app.py has migrated the DB (app.py adds these the same way).
    for col in ('pin_hash', 'parent_pin_hash'):
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT NULL")
        except Exception:
            pass

    arjun_pin,  parent_pin = hash_pin('1234'), hash_pin('0000')
    priya_pin              = hash_pin('5678')

    # Child 1: Arjun (user_id=1). PINs stored hashed; plaintext nulled.
    c.execute("SELECT user_id FROM users WHERE user_id=1")
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, name, pin, parent_pin, pin_hash, parent_pin_hash, age) VALUES (1,'Arjun','','',?,?,14)",
                  (arjun_pin, parent_pin))
    else:
        c.execute("UPDATE users SET name='Arjun', pin_hash=?, parent_pin_hash=?, pin='', parent_pin='', age=14 WHERE user_id=1",
                  (arjun_pin, parent_pin))

    # Child 2: Priya (user_id=3) — same parent_pin (hash) links her to the same parent
    c.execute("SELECT user_id FROM users WHERE user_id=3")
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, name, pin, parent_pin, pin_hash, parent_pin_hash, age) VALUES (3,'Priya','','',?,?,12)",
                  (priya_pin, parent_pin))
    else:
        c.execute("UPDATE users SET name='Priya', pin_hash=?, parent_pin_hash=?, pin='', parent_pin='', age=12 WHERE user_id=3",
                  (priya_pin, parent_pin))
    conn.commit()

    n1 = seed_child(c, conn, 1, 'Arjun', SESSION_PLAN)
    n2 = seed_child(c, conn, 3, 'Priya', PRIYA_PLAN)

    # New: enriched demo data
    seed_extras(c, conn, 1, 'Arjun')
    seed_extras(c, conn, 3, 'Priya')

    # Pre-set a streak for Arjun
    c.execute("DELETE FROM streaks WHERE user_id IN (1, 3)")
    c.execute("INSERT INTO streaks (user_id, current_streak, longest_streak, total_healthy_days) VALUES (1, 0, 12, 28)")
    c.execute("INSERT INTO streaks (user_id, current_streak, longest_streak, total_healthy_days) VALUES (3, 3, 9, 22)")
    conn.commit()

    conn.close()

    print(f"Seeded {n1} sessions for Arjun  (user_id=1, PIN: 1234)")
    print(f"Seeded {n2} sessions for Priya  (user_id=3, PIN: 5678)")
    print()
    print("Enriched data: reflections, counselor messages, screen events, notifications")
    print()
    print("Parent PIN : 0000  (sees BOTH children)")
    print()
    print("Arjun:  Casual -> At-risk -> Addicted (4 high-risk alerts)")
    print("Priya:  Casual -> At-risk            (escalating Roblox pattern)")


if __name__ == '__main__':
    seed()
