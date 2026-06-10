# Testing Guide — Gaming Addiction Detection (PW26_SJ_05)

How to verify the whole system, in three layers: automated backend tests, a live
cloud check, and an on-device manual checklist. Run the automated layers any time
(before a demo, after any change); the manual layer needs a phone.

---

## 1. Automated backend tests (run from `backend/`)

| Command | What it proves | Expected |
|---|---|---|
| `python -m pytest tests/ -q` | 35-test suite: API contracts, dashboards, feedback, auth shadow mode — isolated throwaway DB | `35 passed` |
| `python scripts/functional_sweep.py` | **56 checks in production mode** (`AUTH_ENFORCE=1`, real tokens): registration/family joins, role guards (child token can't change family PIN / delete data), consent, session lifecycle + observation mode, chat de-dupe + toxicity alert + auto language-nudge, full nudge lifecycle (delivered exactly once), real WAV voice upload (silence floor, raw-audio deletion, late re-score), stale-session self-healing, heartbeat watchdog **with child-local quiet hours**, tamper events (logout clears monitoring status; re-login alerts the parent), feedback agreement + re-rating, dashboards/PDF, parent-controlled deletion | `56/56 checks passed` |
| `python scripts/cloud_e2e.py` | **25 checks against the LIVE Render deployment**: every screen's endpoint with real parent/child tokens, PDF bytes, cross-user 403 / no-token 401 guards | `25/25 passed` |

Notes
- The first `cloud_e2e` call may take ~30–60 s if the free instance was asleep.
- `cloud_e2e` exercises the seeded demo family (`FAM789` / `0000`); reseed via
  `seed_demo.py` if logins fail (see DEMO_RUNBOOK §2).

---

## 2. Live deployment health

- `https://gaming-addiction-api.onrender.com/api/health` → `"models_loaded": true`.
- After a deploy, confirm the Render dashboard's latest deploy is your commit.
- Watch for Render **memory-limit emails**: heavy voice load is capped now
  (audio-analysis semaphore + 4 gunicorn threads + worker recycling at ~200
  requests), so one of those emails appearing again is a regression signal.

---

## 3. On-device manual checklist

Use a real phone (emulators lack UsageStats/mic/accessibility realism). Install the
signed release APKs from `android/*/app/build/outputs/apk/release/app-release.apk`.

### Child app

- [ ] **Install + first launch** — onboarding shows, no crash. *(A launch crash on
      Android 12+ — IME settings SecurityException — was found on-device and fixed;
      any relapse here is critical.)*
- [ ] **Register** a child (leave family code blank) → family-code dialog appears;
      note the code.
- [ ] **Consent dialog** → I Agree → permission chain walks through Usage access,
      Notification access, Accessibility, Wellbeing Keyboard (enable + select),
      battery exemption, optional Device Admin. Each "Skip" advances, nothing loops.
- [ ] **Home** shows "Hi, <name>", today-vs-goal progress, streak line, mindful
      break, "try instead" shuffle.
- [ ] **Settings (via parent-PIN gate)** → the **family code card** shows the code;
      tapping it copies to clipboard. (Accounts created before v1.1: log out and
      back in once so the app learns the code from the server.)
- [ ] **Parent-PIN gate**: menu → Logout → wrong PIN is rejected with a toast;
      correct PIN logs out AND raises a logout alert in the Parent app; the Parent
      dashboard stops showing "Monitoring active". Logging back in raises a
      "signed in — monitoring active again" alert and the strip turns green.
- [ ] **After logout, nothing captures**: open a game while logged out → no
      monitoring notification, no new session in the Parent app, typing captures
      nothing (the keyboard still types normally — it just records nothing).
- [ ] **Mira**: send "i cant stop playing" → typing indicator ("…") → craving-
      specific reply; Send button disabled while waiting (no double-send).
- [ ] **Daily check-in**: tap a face, sliders, submit → celebration dialog +
      check-in streak increments (once per day).
- [ ] **Auto session start**: open a real game (e.g. Roblox) → within ~10 s the
      monitoring notification appears; Parent app/status shows playing.
- [ ] **Typed chat capture**: with the Wellbeing Keyboard active, type a sentence
      into the game's chat → it appears in Parent → Chat Analysis (⌨️ tag).
- [ ] **Voice capture**: speak near the phone during the session → voice events +
      🎙️ STT lines appear (verified working on real hardware already).
- [ ] **Auto session end**: leave the game (Home / screen off) → ~25 s later the
      session ends with a risk notification; backend shows duration + risk.

### Parent app

- [ ] **Login** with family code + family PIN → child appears (multi-child families
      get the child picker).
- [ ] **Dashboard**: risk band + score with the day label ("Today · N sessions"),
      **live status strip** ("🟢 Monitoring active", "🎮 Playing X now · N min"
      during a live session), weekly hours, late-night count, trend chart, "Why
      this risk level" SHAP factors, signals-analysed ticks.
- [ ] **No notification loop**: with the dashboard open near a band boundary, the
      "Risk Level Changed" notification must NOT repeat every minute. *(This exact
      loop was found on-device and fixed — dashboard and poller used different risk
      definitions; re-notify now also has a 30-min per-level cooldown.)*
- [ ] **Alerts**: friendly ages ("2h ago"); rate one Accurate/False alarm → buttons
      become a "thanks" line; the **agreement banner** appears at the top.
- [ ] **Send a nudge** (preset or custom) → notification pops on the child phone
      within ~20 s, exactly once.
- [ ] **Set a daily limit** → child Home switches to "of your X h daily limit";
      child gets a limit nudge.
- [ ] **Emotion Insights / Chat Analysis / Weekly Report / PDF** all load with the
      captured data; PDF opens/shares.
- [ ] **Switch child** (multi-child) → dashboard re-targets AND subsequent alert
      notifications are about the new child.
- [ ] **Tamper drill**: force-stop the Child app ~20 min → dashboard strip shows
      "🔴 No check-in for N min" and an offline alert appears (suppressed during
      child-local night hours, 22:00–07:00, by design).

### Cleanup after testing

Parent app → Settings → **Remove child from family** (deletes the test account and
all its data; the child PIN stops working).

---

## What device testing already caught (fixed — watch for regressions)

1. **Launch crash on Android 12+** — reading `ENABLED_INPUT_METHODS` throws for
   target SDK > 33; now uses `InputMethodManager` (fix `85a4a51`).
2. **512 MB OOM under live voice load** — concurrent librosa analyses; now
   semaphore-capped + retuned gunicorn (fix `9baa9d8`).
3. **Repeating "Risk Level Changed" notification** — dashboard/poller fought over
   `lastRiskLevel` with different risk definitions (fix `6c7fcb8`).

These three are exactly the class of issue only real-device testing finds — rerun
this checklist after any significant change.
