# Demo Runbook — Gaming Addiction Detection (PW26_SJ_05)

A reliable, repeatable script for demoing both apps live. Follow top to bottom.

---

## 0. One-time setup (before the demo)

- Phone connected to the laptop via **USB**, USB debugging ON.
- Both apps installed (ChildApp + ParentApp).
- In **each app → Settings → Server URL = `http://127.0.0.1:5000/`** → Save.
  (This works through the adb tunnel and is immune to WiFi/IP changes.)

## 1. Start everything (one command)

From the `backend` folder:

```powershell
.\demo_setup.ps1 -Seed
```

This opens the adb tunnel, reloads the demo narrative, and starts the backend.
Leave that window open. You should see "all models loaded".

**Demo PINs:**
| Who | PIN |
|-----|-----|
| Child — Arjun (the addiction story) | **1234** |
| Child — Priya (milder Roblox story) | **5678** |
| Parent (sees both children) | **0000** |

> If you DON'T want to reset data (e.g. to show a session you just played live),
> run `.\demo_setup.ps1` without `-Seed`.

## 2. Quick health check (10 seconds)

In a second terminal:
```powershell
curl http://127.0.0.1:5000/api/health
```
Expect `"models_loaded": true`. If the phone can't reach it, re-run `adb reverse tcp:5000 tcp:5000`.

---

## 3. Demo flow (suggested narrative)

### A. Parent side — the "wow" (start here)
1. Open **ParentApp** → log in with **0000** → pick **Arjun**.
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
| App shows network error | Re-run `adb reverse tcp:5000 tcp:5000` (USB tunnel dropped) |
| Backend not responding | Restart it: `python3.11 app.py` |
| Phone unplugged / reconnected | Re-run the `adb reverse` line |
| Data looks wrong / want a clean slate | `python3.11 seed_demo.py` then refresh the app |
| Session won't auto-start | Confirm UsageStats + Accessibility permissions are ON in ChildApp |

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
- **Privacy:** raw audio is processed and discarded after feature extraction; capture
  is scoped to active gaming sessions of known games only.
- **Security:** login issues a signed bearer token (HMAC); every request carries it and
  the server authorizes by ownership — a parent can read only their own children's data
  (cross-account access returns 403), and PINs are stored as keyed hashes, never plaintext.
  The token check runs in **shadow mode** by default so the demo is unaffected; start the
  backend with `.\demo_setup.ps1 -Enforce` (or `AUTH_ENFORCE=1`) to require tokens and see
  un-authenticated requests rejected. Both apps must be reinstalled with token support first.
