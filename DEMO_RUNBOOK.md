# Demo Runbook — Gaming Addiction Detection (PW26_SJ_05)

A reliable, repeatable script for demoing both apps live. Follow top to bottom.

---

## 0. Two ways to run — pick one

### Option A — Cloud (Render) — RECOMMENDED, always-on
Nothing to start. The backend runs 24/7 at **https://gaming-addiction-api.onrender.com**
(Docker + managed Postgres + HTTPS, auth enforced).
- Both apps **already default to this URL** (Settings → Server URL).
- The phone just needs **internet** (WiFi or mobile data) — no laptop, no USB, no adb.
- **Pre-warm before presenting:** the free tier sleeps after ~15 min idle, so the first
  request takes ~30–60s to wake. A minute before the demo, open
  `https://gaming-addiction-api.onrender.com/api/health` in a browser and wait until it
  shows `"models_loaded": true`. Then it's fast.

### Option B — Local (laptop backend over USB) — offline fallback
- Phone connected via **USB**, USB debugging ON; both apps installed.
- In **each app → Settings → Server URL = `http://127.0.0.1:5000/`** → Save.
- Quit Docker Desktop (frees port 5000), then from `backend/`:
  ```powershell
  .\demo_setup.ps1 -Seed        # adb tunnel + reseed + start backend (leave window open)
  ```

## 1. Demo logins (same for cloud or local)

The demo family is set up exactly like a **real registered family** — so this is the
actual product flow, not a shortcut.

| Who | App | How to sign in |
|-----|-----|----------------|
| Child — Arjun (the addiction story) | Child app | PIN **1234** |
| Child — Priya (milder Roblox story) | Child app | PIN **5678** |
| Parent (sees both children) | Parent app | Family code **FAM789** + Parent PIN **0000** |

> A real family creates this themselves in the Child app (**Create an account** → it
> shows the family code), then signs into the Parent app with that code + PIN. The demo
> family just comes pre-seeded with code **FAM789**.

## 2. Health check + (re)seed
- **Health** — Cloud: open `https://gaming-addiction-api.onrender.com/api/health` →
  `"models_loaded": true`.  Local: `curl http://127.0.0.1:5000/api/health`
  (re-run `adb reverse tcp:5000 tcp:5000` if the phone can't reach it).
- **Reseed the Arjun/Priya demo data** if it's missing or you wiped it:
  - Local: `python seed_demo.py`
  - Cloud: from `backend/`, set the Render external DB URL + pepper, then seed:
    ```powershell
    $env:DATABASE_URL="<render external DB url>"; $env:PIN_PEPPER="<render PIN_PEPPER>"
    python3.11 seed_demo.py
    $env:DATABASE_URL=""; $env:PIN_PEPPER=""
    ```

---

## 3. Demo flow (suggested narrative)

### 0. Onboarding — how a real family signs up (optional, ~30s)
Shows it's a real product, not canned accounts. (The seeded Arjun/Priya family below
was created exactly this way — they just come pre-loaded with rich history.)
1. **ChildApp → Create an account**: enter a child name/age + a child PIN, **leave the
   family code blank** → it generates and shows a **family code** to use in the Parent app.
2. **ParentApp**: sign in with that **family code + the parent PIN** → the child appears.
3. (Adding a sibling later? Set them up in the ChildApp using the *same* family code.)
   *(This creates a real account; delete it afterwards via ChildApp → Settings → Delete My Data.)*

Then switch to the pre-seeded family for the data-rich story:

### A. Parent side — the "wow" (start here)
1. Open **ParentApp** → sign in with family code **FAM789** + PIN **0000** → pick **Arjun**.
2. **Dashboard**: addicted, 85% risk, ~17h/week, 14-day rising trend chart, contributing factors.
3. **Alerts**: high-risk alerts firing.
4. **Emotion Insights**: real emotion breakdown (angry/frustrated/excited) from voice.
5. **Chat Analysis**: avg toxicity + flagged messages.
6. **Weekly Report → Download PDF**: generates a shareable PDF report.
7. (Optional) Switch child → **Priya** to show a milder, different pattern.

### B. Child side — how it's captured
1. Open **ChildApp** (Arjun is logged in).
2. **Dashboard**: the child's own view — streak, risk, history.
3. **Mira (counselor)**: send a message → supportive reply.
4. **Daily check-in**: submit mood/sleep/energy.

### C. Live capture (the impressive part — optional)
1. Open **Roblox** → within ~5s a session auto-starts (no tapping).
2. Type a chat message in-game, speak a sentence.
3. Close Roblox → ~20s later the session auto-ends with a risk notification.
4. Back in ParentApp dashboard → pull to refresh → the new session appears.
5. (Behind the scenes) `python verify_captures.py --limit 0` shows the captured
   chat + voice transcript + fused emotion for that session.

---

## 4. If something breaks (recovery)

| Symptom | Fix |
|---------|-----|
| **Cloud:** first request slow / times out | Free tier woke from sleep — wait ~30–60s and retry; pre-warm via the health URL |
| **Cloud:** network error on phone | Confirm the phone has WiFi/mobile data; open the health URL in the phone's browser |
| **Cloud:** login fails after reseed | The seed used the wrong `PIN_PEPPER` — reseed with Render's exact `PIN_PEPPER` value |
| Parent login: "Invalid family code or PIN" | Use **family code FAM789 + PIN 0000**; ensure you installed the **latest ParentApp** (older builds had no family-code field) |
| **Local:** app shows network error | Re-run `adb reverse tcp:5000 tcp:5000` (USB tunnel dropped) |
| **Local:** backend not responding | Restart it (`.\demo_setup.ps1`) — and quit Docker Desktop so port 5000 is free |
| Data looks wrong / want a clean slate | Re-seed (see §2) then pull-to-refresh the app |
| Session won't auto-start | Confirm UsageStats + Accessibility permissions are ON in ChildApp |
| ChildApp "keeps stopping" | Fixed — voice mic service now degrades gracefully on Android 14; reinstall the latest APK |

---

## 5. Honest talking points (for Q&A)

- **Architecture:** multimodal 3-model ensemble — behavioral telemetry (20 features,
  server-computed from session history), chat toxicity (TF-IDF + Logistic Regression),
  and voice emotion (GradientBoosting on MFCC + prosodic features, fused with lexical
  valence from on-device Vosk transcription).
- **Ensemble weighting (40/30/30):** a clinically-motivated *prior* — behavior dominant
  per DSM-5 IGD / ICD-11 Gaming Disorder; weights re-normalize by data availability;
  to be calibrated against labeled outcomes via the planned active-learning loop.
- **Known limitations (state these proactively):** models are demo-grade pending real
  labeled data; the voice model is adult-trained so it leans toward arousal detection;
  the weights are priors, not fitted. These are exactly what the active-learning /
  retraining roadmap addresses.
- **Privacy:** raw audio is processed and discarded after feature extraction (the
  spoken words are transcribed to text and kept, the audio is not); capture is scoped
  to active gaming sessions of any app the device classifies as a game.
- **Security:** login issues a signed bearer token (HMAC); every request carries it and
  the server authorizes by ownership — a parent can read only their own children's data
  (cross-account access returns 403), and PINs are stored as keyed hashes, never plaintext.
  The token check runs in **shadow mode** by default so the demo is unaffected; start the
  backend with `.\demo_setup.ps1 -Enforce` (or `AUTH_ENFORCE=1`) to require tokens and see
  un-authenticated requests rejected. Both apps must be reinstalled with token support first.
