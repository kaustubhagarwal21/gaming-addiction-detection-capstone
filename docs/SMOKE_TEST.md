# End-to-End Smoke Test Guide

Work through this top to bottom. For each step, note **PASS / FAIL / WEIRD** and we'll fix anything broken.

---

## Phase 0 — Pre-flight (5 min)

### 0.1 Backend running

```powershell
cd C:\Users\KAUSTUBH\Desktop\capstone_main\backend
python app.py
```

**Expected:** `Starting Gaming Addiction Detection API on port 5000`

If you see model-loading errors, note which models failed.

### 0.2 Health check from another terminal

```powershell
curl http://localhost:5000/api/health
```

**Expected:** `{"status": "ok", "models_loaded": true}` (or similar).

### 0.3 Seed demo data

```powershell
cd C:\Users\KAUSTUBH\Desktop\capstone_main\backend
python seed_demo.py
```

**Expected:**
- `Seeded 15 sessions for Arjun  (user_id=1, PIN: 1234)`
- `Seeded 10 sessions for Priya  (user_id=3, PIN: 5678)`
- `Parent PIN : 0000  (sees BOTH children)`

### 0.4 Pytest suite still passes

```powershell
cd C:\Users\KAUSTUBH\Desktop\capstone_main\backend
python -m pytest tests/ -v
```

**Expected:** `23 passed`

### 0.5 Phone connected via ADB

```powershell
adb devices
```

**Expected:** `RFCT413G63N    device`

### 0.6 Server URL set correctly in both apps

The phone needs to reach your laptop. Find your laptop's LAN IP:

```powershell
ipconfig | findstr IPv4
```

In **ChildApp** → Settings → set Server URL to `http://<your-ip>:5000/`
In **ParentApp** → Settings → set Server URL to `http://<your-ip>:5000/`

> **Common gotcha:** phone on cell data instead of Wi-Fi, or laptop firewall blocking port 5000. If health check from phone fails, check both.

---

## Phase 1 — ChildApp UI baseline (15 min)

**Goal:** every screen renders without crashes, the new design system is visible.

### 1.1 Login
1. Launch ChildApp
2. **Check:** Hero gradient at top is visible (purple-to-fuchsia)
3. **Check:** Card with PIN input has rounded corners + light shadow
4. Enter PIN `1234`
5. **Check:** Logs in → Home screen

**Note any:** weird overlap, white-on-white text, button cut off.

### 1.2 Home
1. **Check:** Top hero card "Ready to play?" gradient
2. **Check:** "View my dashboard" white button inside the gradient
3. **Check:** Game grid below (2 columns of game tiles)
4. **Check:** Each game tile has rounded card + 🎮 emoji + name

### 1.3 Dashboard (the big one)
1. From home, tap "View my dashboard"
2. **Check:** Hero gradient with risk level + 3 stats inside (Sessions / Total / Avg/Day)
3. **Check:** Streak card visible (if seeded — Arjun should have streak data)
4. **Check:** Time limit card visible (might be empty if no limit set — that's OK)
5. **Check:** "Talk to Mira" purple CTA card
6. **Check:** "Daily Check-in" outlined CTA card with heart icon
7. **Check:** 14-day risk trend chart renders
8. **Check:** Recent sessions list (5 most recent)

### 1.4 Counselor (Mira)
1. From dashboard, tap "Talk to Mira"
2. **Check:** Screen opens with avatar card at top
3. **Check:** History shows seeded conversation (6 messages: hey mira / tired / etc.)
4. **Check:** Input bar with circular send button at bottom
5. Type "hi" and tap send
6. **Check:** Your message bubble appears on right (purple)
7. **Check:** Mira's reply bubble appears on left (light grey)
8. Type "i feel tired" and send
9. **Check:** Mira's response mentions sleep

### 1.5 Daily Check-in
1. Back to dashboard, tap "Daily Check-in"
2. **Check:** 5 emoji moods are tappable
3. Tap an emoji → it scales up, others fade
4. Drag sleep + energy sliders
5. Type a note
6. Tap "Save check-in"
7. **Check:** Toast appears, you return to dashboard

### 1.6 Settings
1. From home, ⋮ menu → Settings
2. **Check:** Settings page lists server URL field

**Phase 1 report:** Any screen that crashes, has broken layout, or doesn't match the above — list it.

---

## Phase 2 — ParentApp UI baseline (10 min)

### 2.1 Login
1. Launch ParentApp
2. **Check:** Hero gradient (indigo) at top
3. **Check:** Login card overlaps gradient slightly
4. Enter PIN `0000`

### 2.2 Child select
1. **Check:** Hero gradient header
2. **Check:** Both kids (Arjun, Priya) listed with avatar circles showing initial
3. Tap Arjun

### 2.3 Parental Dashboard
1. **Check:** Hero gradient with child name + risk level + 2 stats (Weekly hours, Late-night)
2. **Check:** Anomaly card MIGHT appear (yellow, if Arjun's recent data triggers it — fine if not)
3. **Check:** Action button grid: Alerts / Tips / Emotions / Chat / Report / PDF
4. **Check:** Time-limit suggestion card
5. **Check:** Peer comparison card (big percentile number)
6. **Check:** Sleep impact card
7. **Check:** "Why this risk level" card with bullet factors
8. **Check:** Healthy streak card with 3 stats
9. **Check:** 14-day trend chart
10. **Check:** Top games list
11. **Check:** Top recommendation

### 2.4 Alerts
1. Tap "Alerts"
2. **Check:** List of alerts (seeded with high-risk alerts for Arjun)
3. **Check:** Severity badge on each (color-coded)

### 2.5 PDF Report
1. Back to dashboard, tap "PDF"
2. **Check:** Downloads, share sheet opens
3. **Check:** PDF actually contains data (open it)

### 2.6 Multi-child switch
1. Back arrow → child select
2. Tap Priya
3. **Check:** Dashboard updates with Priya's data

**Phase 2 report:** Same — list anything broken.

---

## Phase 3 — Direct capture verification (20 min)

These are the **data pipeline** features — the things that make this project different from a basic dashboard demo.

### 3.1 UsageStats permission + auto-session detection

1. ChildApp Home screen
2. Android Settings → Apps → Special access → Usage data access → ChildApp → toggle ON
3. Now open any installed game (e.g. download "Subway Surfers" if you don't have one)
4. Wait 30–60 seconds (poll interval)
5. Open ChildApp Home → **Check:** "Session in progress" banner appears
6. Close game, wait 5 min
7. **Check:** Session auto-ends

> **If session doesn't auto-start:** check Constants.KNOWN_GAMING_PACKAGES — the game's package name must be in there.

### 3.2 Notification listener (craving signal)

1. Android Settings → Apps → Special access → Notification access → ChildApp → toggle ON
2. Get a notification from any game (open one and let it post a notification, or any installed game)
3. **Check via backend:**
   ```powershell
   curl http://localhost:5000/api/dashboard/parent?user_id=1 | findstr notif
   ```
4. **Check:** event was logged in DB:
   ```powershell
   cd backend
   python -c "import sqlite3; c=sqlite3.connect('gaming_addiction.db'); print(c.execute('SELECT * FROM notification_events ORDER BY id DESC LIMIT 5').fetchall())"
   ```

### 3.3 Screen events (zero-permission)

1. With ChildApp logged in, lock the phone
2. Wait 5 sec, unlock
3. **Check DB:**
   ```powershell
   python -c "import sqlite3; c=sqlite3.connect('gaming_addiction.db'); print(c.execute('SELECT * FROM screen_events ORDER BY id DESC LIMIT 5').fetchall())"
   ```
4. **Expected:** screen_off, screen_on, unlocked events for user_id=1

### 3.4 Keyboard chat capture (Accessibility)

1. Android Settings → Accessibility → ChildApp → toggle ON
2. Start a manual session in ChildApp (tap any game from home)
3. Switch to any chat app (WhatsApp, SMS, Discord)
4. Type something like "lol this game is trash"
5. Hit send
6. End session in ChildApp
7. **Check DB:**
   ```powershell
   python -c "import sqlite3; c=sqlite3.connect('gaming_addiction.db'); print(c.execute('SELECT message, source FROM chat_messages ORDER BY id DESC LIMIT 5').fetchall())"
   ```
8. **Expected:** Your message appears with `source='keyboard'`

> **If nothing captured:** the accessibility service may need re-enabling after each app update. Also, package allowlist in ChatAccessibilityService.

### 3.5 Voice recording + Vosk STT

1. Start a session
2. Make sure microphone permission is granted (Settings → Apps → ChildApp → Permissions)
3. **Speak loudly and clearly:** "I am really angry at this stupid game right now"
4. Wait 30 sec
5. End session
6. **Check DB:**
   ```powershell
   python -c "import sqlite3; c=sqlite3.connect('gaming_addiction.db'); print(c.execute('SELECT message, source FROM chat_messages WHERE source=\"voice_stt\" ORDER BY id DESC LIMIT 3').fetchall())"
   python -c "import sqlite3; c=sqlite3.connect('gaming_addiction.db'); print(c.execute('SELECT emotion, intensity FROM voice_events ORDER BY id DESC LIMIT 3').fetchall())"
   ```
7. **Expected:**
   - chat_messages has `source='voice_stt'` with text close to what you said
   - voice_events has an emotion detected (likely "angry" or "frustrated")

> **If Vosk silently fails:** check logcat for "vosk" — model may have failed to extract from assets on first run.

**Phase 3 report:** Tell me which captures worked vs failed.

---

## Phase 4 — ML model sanity check (15 min)

### 4.1 Behavior model

The seeded data has known risk classes. Let's verify the latest session for Arjun is classified `addicted`:

```powershell
python -c "import sqlite3; c=sqlite3.connect('gaming_addiction.db'); print(c.execute('SELECT session_id, game_name, final_risk_score, risk_category FROM sessions WHERE user_id=1 ORDER BY session_id DESC LIMIT 3').fetchall())"
```

**Expected:** Most recent sessions for Arjun should be `addicted` with risk_score > 0.7.

### 4.2 Live prediction during a session

1. Start a session in ChildApp (any game)
2. Wait 30 seconds
3. **Check:** "Live: Risk X%" updates in the gradient header

### 4.3 Chat toxicity

Test the chat classifier directly:

```powershell
curl -X POST http://localhost:5000/api/analyse/chat -H "Content-Type: application/json" -d "{\"text\": \"you are such a loser idiot kys\"}"
```

**Expected:** Toxicity score >= 0.7

```powershell
curl -X POST http://localhost:5000/api/analyse/chat -H "Content-Type: application/json" -d "{\"text\": \"good game everyone, nice match\"}"
```

**Expected:** Toxicity score < 0.3

### 4.4 Voice emotion

```powershell
python -c "
from app import voice_model, VOICE_RISK
print('Voice classes:', voice_model.classes_ if voice_model else 'NOT LOADED')
print('Risk map:', VOICE_RISK)
"
```

**Expected:** Lists classes like ['angry', 'happy', 'neutral', ...] and maps them to risk weights.

### 4.5 SHAP per-prediction (top factors)

End a session and check the result screen:
1. Look at "WHY THIS SCORE" card
2. **Expected:** 3 bullet points like `• Late-night ratio: 0.65 (28% impact)`

If absent, the `top_factors` field isn't being populated by `run_prediction`. Note it.

### 4.6 Anomaly detection

```powershell
curl http://localhost:5000/api/anomalies?user_id=1
```

**Expected:** Either a list of anomalies, or `{"success": true, "anomalies": []}` (depends on seeded data spread).

---

## Phase 5 — End-to-end scenarios (20 min)

These exercise multiple subsystems at once. **This is what the demo evaluators will care about most.**

### Scenario A: "A normal session"
1. ChildApp → start "Minecraft" session
2. Play for ~3 minutes (just keep phone unlocked, talk normally)
3. End session
4. **Check session result screen:** risk = casual, breakdown shows low scores
5. **Check ParentApp dashboard refreshed:** new session appears in recent

### Scenario B: "A high-risk session"
1. Set phone time forward to 11 PM (Settings → Date/Time → manual)
2. Start a session
3. **Speak with anger** repeatedly: "I hate this game, this is so stupid, why am I losing"
4. Type toxic chat in WhatsApp: "kys noob idiot"
5. End session after 2-3 min
6. **Expected:**
   - Risk = at_risk or addicted
   - Voice score elevated
   - Chat score elevated
   - "Top factors" shows late_night_play_ratio high
7. **Check ParentApp:**
   - Alert appears in alerts screen
   - Anomaly card may appear on dashboard

### Scenario C: "Healthy week"
1. Trigger streak update: end a session with low risk
2. **Check:** Streak card on child dashboard reflects update
3. **Check:** Self-awareness message updated

### Scenario D: "Parent intervenes"
1. ParentApp → Time-limit suggestion card → tap "Apply this limit"
2. Enter 2 hours
3. **Check:** Limit saved, child app's "Today's Limit" card shows it after refresh

---

## Phase 6 — Reporting

Tell me which phase / step failed, copy-paste any error from:

- **Backend terminal** (where `python app.py` is running)
- **Logcat** on phone:
  ```powershell
  adb -s RFCT413G63N logcat -t 200 | findstr -i "gamingdetector parentmonitor exception"
  ```

That's the full smoke test. **Don't try to do all of this in one sitting** — split it across 2-3 sessions. Start with Phase 0-2 (just verify the apps look right and you can log in to both).

---

## Quick troubleshooting table

| Symptom | Likely cause |
| --- | --- |
| App crashes on launch | Server URL not set, or backend not running |
| "Cannot reach server" toast | Phone not on same Wi-Fi, or firewall blocking port 5000 |
| Dashboard empty | seed_demo.py not run yet, or wrong user_id |
| Chat capture silent | Accessibility service not enabled, or app updated since enable |
| Voice capture silent | Microphone permission denied, or Vosk model failed to extract |
| Auto-session not detecting | Usage stats permission not granted, or game package not in KNOWN_GAMING_PACKAGES |
| Notification listener silent | Notification access not granted in system settings |
| PDF download fails | `fpdf2` not installed in backend env |
| ML scores all 0.5 | Model files not loaded — check backend startup logs |
