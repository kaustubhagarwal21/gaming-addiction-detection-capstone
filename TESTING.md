# Testing Guide — Gaming Addiction Detection (PW26_SJ_05)

How to verify the whole system, in three layers: automated backend tests, a live
cloud check, and an on-device manual checklist. Run the automated layers any time
(before a demo, after any change); the manual layer needs a phone.

---

## 1. Automated backend tests (run from `backend/`)

| Command | What it proves | Expected |
|---|---|---|
| `python -m pytest tests/ -q` | 180-test suite: API/OpenAPI contracts, dashboards and canonical risk roll-ups, credential-version revocation, parent/child authorization, strict request validation, consent, session finalization/backfill races, notifications/FCM identity and stale-token pruning, feedback/export/deletion privacy (incl. verdicts on risk-revision and toxicity-streak alerts), SQLite/Postgres compatibility, PDF generation, and ML/audio/text helper regressions — isolated throwaway DB | `180 passed` |
| `python scripts/functional_sweep.py` | **82 checks in production mode** (`AUTH_ENFORCE=1`, real tokens): registration/family joins, role guards, Family-PIN-authorized current-version consent, session lifecycle + observation mode + idempotent re-end, chat de-dupe/toxicity/nudges, WAV voice upload and late re-score, stale-session healing, heartbeat/tamper/permission alerts, feedback re-rating, dashboards/PDF, and parent-controlled deletion | `82/82 checks passed` |
| `python scripts/cloud_e2e.py` | **25 checks against the LIVE Render deployment**: every screen's endpoint with real parent/child tokens, PDF bytes, cross-user 403 / no-token 401 guards | `25/25 passed` |
| `python scripts/concurrency_smoke.py` | 288 mixed requests / 24 threads against a real threaded server (chat scoring + live predictions included) — re-run after any change to per-request cost | `zero server errors` (last: p50 66 ms, p95 684 ms) |
| `docker build -t capstone-backend .` then run `/api/health` | Production image builds, starts as the non-root user, can create its local SQLite fallback, and loads every model | `"status":"ok", "models_loaded":true` |
| `python scripts/pg_smoketest.py` with a throwaway Postgres 16 `DATABASE_URL` | Production database dialect, schema initialization, login, family authorization, and parent/child role guards | `ALL PASSED` |
| `schemathesis run backend/openapi.yaml --url http://127.0.0.1:5058 --max-examples 15` (app booted with `AUTH_ENFORCE=1`) | **Property-based API fuzz** over all 53 documented operations — generates cases nobody wrote. Found the mark_read auth-precedence bug | `no Server error findings` (see docs/API_FUZZ_REPORT.md for the triage of spec-completeness findings) |
| `python -m pip_audit -r backend/requirements.txt` | Dependency CVE audit against the PyPI advisory DB | only the accepted dev-only `pytest` advisory |
| `python -m bandit -r backend/ ml/ -ll` | **Python security static analysis** (the backend counterpart to MobSF on the apps) | 43 findings, all verified false positives — see docs/API_FUZZ_REPORT.md before "fixing" any SQL warning |
| `python -m detect_secrets scan --all-files` | Committed-credential scan (this repo is public) | no tracked private key / keystore / server secret |
| `python -m pytest tests/ -q --cov=. --cov-report=term-missing` | Statement coverage of the 180-test suite | **75%** overall, 80% of served code |

Notes
- The first `cloud_e2e` call may take ~30–60 s if the free instance was asleep.
- `cloud_e2e` exercises the seeded demo family (`FAM789` / `0000`); reseed via
  `seed_demo.py` if logins fail (see DEMO_RUNBOOK §2).
- **CI**: `.github/workflows/ci.yml` runs the pytest suite on **both SQLite and
  Postgres 16** (the production dialect), plus Android Lint + JVM unit tests for both
  apps, on every push/PR to `main`. `.github/workflows/drift.yml` runs the drift
  monitor against the production DB every Monday (red on PSI > 0.2).

### Android JVM unit tests (run from `android/ChildApp/` or `android/ParentApp/`)

```
.\gradlew.bat testDebugUnitTest
```
110 tests across the two apps (79 Child, 31 Parent) pin the pure decision logic:
offline-session backfill and persisted capture-health rules
(OfflineSessionLogic/CaptureHealthLogic), profile-edit validation
(`ProfileValidation`), auth revision/origin handling, server URL validation,
notification routing/unread totals, the shared risk-label presentation
(`RiskPresentation`, both apps), the offline chat queue's
delivered-or-deliberately-dropped semantics (`ChatQueueLogic`), the WAV container
header the voice channel depends on (`WavUtil`), IME keystroke-to-sentence
reconstruction incl. the word-vs-key regression and Devanagari matra handling
(`KeystrokeBuffer`), the dual-language STT segment picker incl. the genuinely-mixed
window, junk-hypothesis and same-utterance cases (`TranscriptPicker`), the full
layout-transition table of the Wellbeing Keyboard incl. the stuck-keyboard
guarantee (`KeyboardLayoutMachine`: QWERTY reachable from every page in one
press), and the
parent-alert triage rules incl. regressions for the sibling high-water-mark and
risk-flap bugs (`AlertTriage`).

### ML training / evaluation scripts (run from the project root)

| Command | What it does |
|---|---|
| `python ml/retrain_models.py` | Retrains behaviour (10 objective features) + chat (with isotonic calibration layer) + voice; **merges** into `model_metadata.json` |
| `python ml/calibrate_behavior.py` | Fits the behaviour isotonic calibrator; reports the Brier improvement |
| `python ml/eval_chat_voice.py` | Honest chat metrics (balanced + realistic imbalanced, PR-AUC/Brier); skips voice if the deployed voice model is real-audio-trained |
| `python ml/train_voice_real.py --jobs 8` | Trains the voice model on real speech (RAVDESS/CREMA-D/EMO-DB/URDU under `data/voice/`); `--smoke` self-tests without data |
| `python ml/eval_chat_conda.py` | In-domain gaming-chat evaluation on the held-out CONDA validation split (threshold sweep, PR-AUC) → `chat_metrics_gaming`. Do NOT pass `--csv data/conda/CONDA_train.csv` — that would score the model on its own training data |
| `python ml/fetch_hindi_clean.py` | Rebuilds the clean-Hindi counterweight (8,000 Hindi Wikipedia sentences, both scripts) that drains the measured Devanagari toxicity prior |
| `python ml/fetch_hasoc_hindi.py` | Rebuilds the HASOC 2019 Hindi corpus files deterministically (80% → `data/chat_extra/`, 20% held out; registration-gated upstream, not redistributed in this repo) |
| `python ml/eval_chat_hindi.py` | Held-out Devanagari/Hindi abuse evaluation (HASOC 2019 20% split, never trained on) → `chat_metrics_hindi` |
| `python ml/eval_calibration.py` | Direct calibration evidence: top-label ECE + reliability diagrams for both calibrated channels, on the calibrators' own held-out splits → `calibration_eval` + `docs/figures/reliability.pdf` |
| `python ml/monitor_drift_evidently.py` | Optional Evidently companion to the drift monitor: 20+ maintained drift tests incl. small-sample-appropriate ones; HTML report + JSON. Primary PSI/KS monitor stays authoritative for CI |
| `python ml/smoke_spoken_hindi.py` | Offline spoken-Hindi chain smoke test (gTTS → Vosk Hindi STT → served pipeline); de-risks the future Hindi-recogniser swap. Needs `pip install vosk gtts`, ffmpeg, and the vosk-model-small-hi-0.22 download (see docstring) |
| `python ml/tune_from_feedback.py` | Converts parent-feedback verdicts into conservative threshold recommendations (`threshold_tuning.json`) + labelled CSV export |
| `python ml/analyze_reflections.py` | Correlates daily risk vs next-day mood/sleep/energy self-reports (Spearman) |
| `python ml/ablation_studies.py` | One-component-at-a-time ablations for all three channels (bootstrap 95% CIs) → `docs/ablation_results.json`; `--only chat\|voice\|behaviour` re-runs a section |
| `python ml/make_figures.py` | Regenerates the paper's figures (PR curve, confusion matrices) into `docs/figures/` |
| `python ml/analyze_igds.py` | IGDS9-SF open dataset (n=11,191): severity base rate + toxicity-involvement vs IGD severity (chat-channel premise validation) |
| `python ml/analyze_fusion_sensitivity.py` | Stress-tests the fusion priors on stored pilot predictions (weight simplex sweep, genre-effect sweep, threshold sweep) after proving exact replication of served scores; writes `docs/fusion_sensitivity.json` |
| `python ml/calibrate_thresholds_prevalence.py` | Prevalence-anchored RISK_T2 calibration (IGDS9-SF disordered-range rate), population-gated below 10 children |
| `python ml/analyze_voice_shadow.py` | Offline evaluation of the voice domain-shift mitigations (abstain-margin sweep, BBSE prior correction) on shadow-logged probability vectors from live pilot audio |
| `python ml/monitor_drift.py` | Score-distribution drift monitor (PSI + KS, band shares, modality-presence rates) — recent window vs reference; the pilot-phase health check |

---

## 2. Live deployment health

- `https://gaming-addiction-api.onrender.com/api/health` → `"models_loaded": true`.
- After a deploy, confirm the Render dashboard's latest deploy is your commit.
- Watch for Render **memory-limit emails**: heavy voice load is capped now
  (serialised audio analysis with bounded queueing + 4 gunicorn threads + worker
  recycling at ~500 requests), so one of those emails appearing again is a regression signal.

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
- [ ] **Consent dialog** → I Agree → enter the Family PIN → server confirms the
      current consent version → permission chain walks through Usage access,
      Notification access, Accessibility, optional Device Admin, battery exemption,
      Wellbeing Keyboard (enable + select). Each "Skip" advances, nothing loops.
      Device Admin + battery come BEFORE the keyboard steps on purpose — they used
      to sit after, so skipping the keyboard hid the anti-uninstall offer entirely.
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
- [ ] **Devanagari typing (v2.4.0-beta)**: tap the हिं key → Devanagari layout;
      type a Hindi word (consonants page + अआ vowels/matras page), matras render
      combined (कुत्ते not क ु त ् त े); ABC returns to QWERTY; captured Hindi
      text reaches Chat Analysis and is scored (dual-script model).
- [ ] **Hindi + English voice (v2.4.0-beta, parent-gated Settings toggle,
      default OFF)**: enable → next session speaks one Hindi and one English
      sentence near the phone → each yields ONE 🎙️ line in the correct language
      (never two lines for one utterance); watch CPU/battery — two Vosk models
      are resident. Toggle OFF → behaviour identical to v2.3.11.
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
      loop was found on-device — dashboard and poller used different risk
      definitions. The band-comparison notification was ultimately removed entirely:
      notifications now come only from durable alert rows, deduplicated by alert id.)*
- [ ] **Alerts**: friendly ages ("2h ago"); rate one Accurate/False alarm → buttons
      become a "thanks" line; the **agreement banner** appears at the top.
- [ ] **Send a nudge** (preset or custom) → notification pops on the child phone
      within ~12 s, exactly once.
- [ ] **Set a daily limit** → child Home switches to "of your X h daily limit";
      child gets a limit nudge.
- [ ] **Emotion Insights / Chat Analysis / Weekly Report / PDF** all load with the
      captured data; PDF opens/shares.
- [ ] **Switch child** (multi-child) → dashboard re-targets AND subsequent alert
      notifications are about the new child.
- [ ] **Tamper drill**: force-stop the Child app → strip stops claiming "playing"
      within ~10 min, the orphaned session auto-closes by ~12 min, and the offline
      alert lands at ~15 min (plus an instant FCM push). Suppressed during
      child-local night hours, 22:00–07:00, by design.

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

4. **Round 2 (user field-testing)**: session stuck "running" after a swipe-away
   (heartbeat-aware close + one-open invariant), Device Admin never offered when the
   keyboard was skipped (chain reordered), uninstall alert dying with the process
   (synchronous send + FCM push), slow refresh/alerts (tighter polls + push).

These are exactly the class of issue only real-device testing finds — rerun
this checklist after any significant change.
