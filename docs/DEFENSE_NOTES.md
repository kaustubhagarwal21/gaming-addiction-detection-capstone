# Defense Notes — Anticipated Examiner Questions

Pre-assembled answers for the capstone defense (PW26_SAS-03). Every number below is
reproducible from a script in this repo; the source is cited next to each claim.
The strategy throughout: **answer honestly, cite the measurement, name the limitation
before the examiner does.**

Primary evidence files:
- `backend/models/model_metadata.json` — all serving-model metrics (written by `ml/retrain_models.py`)
- `docs/ablation_results.json` — ablation tables with bootstrap 95% CIs (written by `ml/ablation_studies.py`)
- `docs/survey_validation.json`, `docs/survey_extras.json` — the external IGDS9-SF
  construct-validity study (written by `ml/eval_behavior_survey.py`, `ml/eval_survey_extras.py`)
- `docs/PROJECT_PAPER.tex` §4 — dataset audit, evaluation methodology, model selection
- `docs/genre_removal.json` — the score-version-2 record: both formulas, the pilot band shift,
  the parent note, the tests, the migration rehearsal and the deployment
- `docs/hparam_behaviour.json`, `docs/hparam_chat.json`, `docs/hparam_voice.json` — the
  hyperparameter studies (written by `ml/hparam_behaviour.py`, `ml/hparam_chat.py`, `ml/hparam_voice.py`)
- `docs/GEMINI_NANO_FEASIBILITY.md` — the Gemini Nano decision record (Google's pages checked 23 Nov 2026)
- `docs/test_counts.json` (written by `tools/count_tests.py`) and `docs/review3_venues.json` (target venues)
- `tools/project_numbers.py` — the single source of every number the Review 3 deck and the
  report print (`python tools/project_numbers.py` lists them)

---

## Review 3 — questions this review invites

Review 3 runs 23–27 Nov 2026; our slot: **[slot: fill in]**. Everyone presents and is graded individually against four criteria (`docs/templates/REVIEW3_REQUIREMENTS.md`): (1) demonstration — UI, module-wise functionality, integration; (2) results — graphs, tables, comparative analysis, limitations, implications; (3) presentation and viva; (4) depth — ablation study, interpretation of code, system architecture, analysis of results. The department requires the PPT and the complete report draft to be shown to Prof. Shridevi Sawant and approved *before* the review: [team: date shown, her corrections, approval]. Numbers in this section match `tools/project_numbers.py` wherever it carries them, and the rest come from the evidence files above; the one figure newer than `project_numbers.py` (the 23 Nov load-test re-run) is labelled where it appears. Slide numbers refer to the current 42-slide build. Owners: **Kaustubh** — ML models and validation · **Khushee** — ChildApp, capture, anti-tamper, device numbers; drives the demo · **Kanak** — backend, deployment, fusion/alerting, datasets, CI/testing · **Vidisha** — ParentApp, ethics/privacy, scope, applicability; narrates the ParentApp. If a question lands on you outside your module, give the one-line answer yourself, then offer the owner for detail.

### Completeness and the demo

**Q (owner: Kanak; demo: Khushee drives, Vidisha narrates): Is the project complete?**
The system is: every module is built, deployed and integrated, and the demo (slide 17) runs the whole loop live on two real phones and the cloud server. Khushee opens Roblox and the session starts within ~10 s; she types and speaks; she closes it and the session ends ~25 s later; Vidisha shows the score, its reasons and the alert in the ParentApp, rates the alert, and sends a nudge that reaches the child in ~12 s. Built modules: ChildApp — game detection, chat capture through our keyboard and the accessibility path, voice with on-device Vosk, consent, tamper heartbeats, Mira, the daily check-in; backend — three models, fusion, alerting, drift monitor, model card, export and deletion; ParentApp — dashboard, reasons, alerts with ratings, chat and emotion views, nudges, weekly PDF. Documents: the department-format report is drafted (140 pages) and the IEEE draft is complete (6 pages). Name the unfinished parts before anyone asks: the child validation study (not started — it needs ethics-committee approval), the IEEE submission (by 31 Jan 2027), the guide's corrections and the PESU plagiarism check on the report, and a Gemini Nano benchmark (no supported phone). The one-line version: **the system is finished; the evidence about children is not.** Demo hygiene: the history is seeded demo data and today's session is live; wake the server and reseed the demo family that morning (DEMO_RUNBOOK §2); backup video [team: confirm it is recorded].

### Test plan and strategy

**Q (owner: Kanak; Khushee for the phone and fairness rows): What is your test plan and strategy?**
(slides 18–21) Testing grew in layers, dated from git: Phase 2 (Feb–May) scored the models on held-out data with a manual end-to-end checklist; from 29 May the backend suite was rebuilt on a throwaway database, with a live-cloud check, a production-mode sweep and a real-phone checklist; from 6 Jul CI ran on every push; August added fuzzing, security scans, the survey-parser test, the accent audit and the phone drill; late August the paper-vs-data guards joined CI; November added the score-v2 tests. Today CI runs **300 automated tests — 190 backend + 110 Android — plus 7 research-integrity guards** on every push (backend: 190 pass on SQLite; on Postgres 16, 189 pass and the one SQLite-only migration test is skipped).
- **Functional, and why each:** *unit* (pytest, JUnit 4) — exact and fast, so every push runs them; *integration* through the real API on a throwaway database, on SQLite **and** Postgres 16 — production runs Postgres, and SQL that passes on one can fail on the other; *contract* — API spec vs routes, survey form vs parser, both apps' risk labels — parts built separately must not drift apart; *system* in production mode (`functional_sweep.py`, `AUTH_ENFORCE=1`, real tokens; 89/89 on 23 Nov); *end-to-end* against the live deployment (`cloud_e2e.py`, 25 checks).
- **Non-functional:** performance — 288 mixed requests from 24 threads, 0 server errors; security — Schemathesis fuzzing of all 53 documented API operations, bandit, pip-audit, detect-secrets, MobSF on both signed APKs (one real bug, a login checked too late, and six known vulnerabilities fixed; no exploitable high-severity issue); phone cost — Galaxy M52, two 15-minute Roblox sessions; phone function — every screen and the tamper drills by hand; accent fairness — 6,656 Svarah clips through the served speech-to-text and chat scorer; research integrity — the 7 guards fail CI if a paper's survey number drifts from the data.
- **Environment and roles:** laptop (SQLite) → GitHub Actions (SQLite job, Postgres 16 service job, Android Lint + JVM tests) → Render + Neon cloud → real phones. Kanak: backend suites, fuzzing, load test, CI. Khushee: ChildApp tests, phone and tamper drills. Vidisha: ParentApp tests; consent, export and deletion checks. Kaustubh: model evaluation, ablations, guards.
- **Benefits:** each layer caught what the others could not — the fuzzer found the mark-read authorization-order bug, real phones found 3 bugs the API tests missed (one a launch crash), the parser test caught a pre-launch defect that would have dropped every survey response, and the drift monitor's 24 Aug false negative became a regression test.
- **Drawbacks, named:** no automated UI tests on a phone; the load test ran on a laptop, not the live server; no human penetration test; behaviour labels are simulated and the external check used adults; statement coverage was last measured on the earlier 181-test suite (75% overall, 80% of served code).
- **Tools, all open-source:** pytest, JUnit 4 with Gradle, GitHub Actions, Docker (Postgres 16), Schemathesis, bandit, pip-audit, detect-secrets, MobSF, adb for the phone drill.

### Interpreting the code

Each owner opens the file at the line given and walks it top to bottom: say the two-line summary first, then the walk, then expect the follow-up. Line numbers are at HEAD (`e7b9b21`).

**1. `run_prediction(session_id, explain)` — `backend/app.py:2289` (owner: Kanak).**
*Summary:* scores the channels this session actually captured — behaviour from the calibrated forest, chat as the highest stored per-message score, voice from the stored emotions — and fuses them as the 40/30/30 mean renormalised over the channels present, which since score version 2 is the whole score. It bands at 0.33/0.67, never shows High concern before 3 scored sessions, and stores the row with `score_version` 2.
*Walk:* count prior scored sessions (2299–2308) → latest behaviour row; a zero-second session is not evidence (2310–2318) → typed chat only — `voice_stt` is excluded so one utterance is not counted twice (2320–2328) → behaviour: scaler → calibrated forest → `0.5·P(Some) + 1.0·P(High)`, SHAP only when `explain` (2339–2356) → chat: `max` of the stored scores, re-scoring only legacy rows (2367–2381) → voice: model probabilities × `VOICE_RISK` when audio exists, otherwise stored emotion × intensity — the production path, because audio is deleted (2384–2417) → components, renormalised mean, band (2432–2446) → observation-mode cap (2449–2450) → INSERT with modality flags and `score_version` (2474–2489) → `_maybe_insert_score_v2_notice` in its own short transaction, so the note can never cost a score (2490–2493).
*Follow-ups:* "Why max for chat?" — on 707 real CONDA conversations it beat scoring the concatenated text and mean/top-3, and a blob dilutes one toxic line among clean ones (comment at 2359). "Nothing captured?" — score `None`, band unknown; no fake neutral. It runs from `_finalize_session_once` (4131) after `end_session` (4566); one database claim covers features → score → alert, so a retried end never alerts twice. The internal band keys are legacy strings; everything served passes through `RISK_DISPLAY` as Low / Some / High concern.

**2. `compute_behavioral_features(session_id)` — `backend/app.py:2118` (owner: Kaustubh).**
*Summary:* builds the 10 objective features for one session as of its own end, from the sessions that began in the 30 days before it (at most 200), so a backfilled session is reproducible and later play cannot leak in. It then appends the 10 derived proxies (`derive_psychometrics`), which parents see as explanations and the model never sees.
*Walk:* reference clock = the session's end (or now), clamped (2135–2141) → history: same child, began in the 30 days before this session (2142–2147) → local-day shift (2148) → `known_duration` clamps each past session to the reference time (2157–2168) → daily and weekly hours, sessions per day, average duration (2170–2187) → late-night ratio, days played, longest streak, binge sessions ≥ 3 h (2189–2208) → breaks between sessions, including the one just before this session (2210–2236) → rapid-relogin ratio = share of breaks under 15 min (2237–2238) → objective dict + proxies (2240–2252). Volume = daily hours, weekly hours, sessions per day, average duration, days played; pattern = late-night ratio, longest streak, binge sessions, average break, rapid relogin.
*Follow-ups:* "Why the break right before this session?" — restarting minutes after stopping is exactly the rapid-relogin pattern, and pairing only past sessions missed it (comment at 2223). "Why split pattern from volume?" — the survey found the five pattern features carrying the signal: composite contrast +0.199 [+0.019, +0.380].

**3. Chat scoring and the alert path — `save_chat(sid)` `backend/app.py:5157`, with `_ml_toxicity` (2048) and `fuse_toxicity` (2062) (owner: Kaustubh; Kanak for the alert rows).**
*Summary:* each line is scored the moment it arrives: the keyword lexicon and the calibrated TF-IDF + logistic-regression probability are fused by noisy-OR, `1 − (1 − kw)(1 − ml)`, and the score is stored per message. A toxicity alert fires only at ≥ 0.95 (high severity at ≥ 0.97), and three lines at ≥ 0.6 in one session raise one streak alert instead.
*Walk:* `guard_session` + current-consent check (5159–5162) → validation: a non-empty string, ≤ 2,000 characters, source ∈ {keyboard, ime_keystroke, ocr, voice_stt} (5167–5180) → score (5183–5185) → 8-second de-dupe, because our keyboard and the accessibility path can both see one line (5189–5196) → INSERT with the score (5197–5199) → at ≥ `CHAT_ALERT_T`: `_insert_alert(…, 'toxicity', …)` plus at most one pending nudge to the child (5203–5219) → at ≥ `CHAT_STREAK_BAR`: count flagged lines; at 3, `_insert_toxicity_streak_once` (5225–5236) → a line that arrives after the session closed queues the durable late re-score (5242–5253).
*Follow-ups:* "Why noisy-OR, not max?" — two moderate, independent signals are stronger evidence than either; the result never falls below the larger one and equals a lone signal (docstring at 2062). The thresholds are checked at start-up, `0 ≤ CHAT_STREAK_BAR ≤ CHAT_ALERT_T ≤ CHAT_ALERT_HIGH_T ≤ 1` (820). Spoken lines (`voice_stt`) can alert here but are left out of the session's chat score.

**4. The voice pipeline — ChildApp `VoiceRecorderService` → `save_voice(sid)` `backend/app.py:5302` → `analyse_audio` (1955) → `fuse_emotion` (2083) (owner: Khushee; Kaustubh for the model).**
*Summary:* the phone records 16 kHz mono only while the session's game is in front; Vosk transcribes on the phone (the text goes to `/chat` as `voice_stt`) and a 10-s WAV is uploaded. The server stores a clip with too little speech as *missing*, not neutral, turns the rest into 36 acoustic features → HistGradientBoosting → four emotion probabilities, fuses tone (arousal) with the last 20 s of words (valence), keeps the label and probabilities, and deletes the audio.
*Walk:* guard + consent (5304–5307) → 2 MB cap, collision-proof file name (5308–5331) → `analyse_audio`: features → model probabilities, or `None` for a rejected clip (1955–1982) → `capture_valid` (5339) → fuse with recent `voice_stt` words: lexical valence + the trained toxicity score (5344–5361) → delete the WAV; `KEEP_AUDIO` is "0" in `render.yaml` (5362–5372) → INSERT into `voice_events` with the probabilities and `capture_valid` (5406–5410) → re-score at most every 8 s, or queue a late re-score if the session already closed (5428–5440).
*Follow-ups:* "Why fuse words at all?" — the acoustic model separates arousal, not valence: loud-but-calm speech read as angry, and a child's naturally high pitch can read as high arousal (comment at 1985). Deployed accuracy 0.574 on unseen speakers.

**5. ChildApp session auto-start and auto-end — `PassiveMonitorService.checkForegroundGame()` in `android/ChildApp/app/src/main/java/com/pes/gamingdetector/services/PassiveMonitorService.kt:523`, with `performAutoStart` (735), `launchAutoEnd` (829), `performAutoEnd` (853) (owner: Khushee).**
*Summary:* every 5 s while the phone is in use (30 s when it is locked with no session) the service reads the foreground app. With no session it starts one when the phone is unlocked and the foreground app is a game; during a session it ends it after 20 s away from the game (2 min inside a sign-in, purchase or ad flow the game opened), or at once if the child switches to another game, counting play only up to the moment it stopped.
*Walk:* skip while an end is in flight (526) → retry a failed end with the same stored stop time (531–546) → bound a start whose request is still in flight (548–555) → close an offline bout once its game leaves the foreground (557–562) → re-adopt an orphaned session after a service restart (564–581) → maintenance mode: still playing resets the grace timer; another game ends the session now; anything else starts the grace, then `launchAutoEnd(gameLeftAtEpochMs)` (583–622) → detection mode: unlocked + `GameDetector.isGame` + no start in flight → `startingSession` guard → `performAutoStart` (624–651).
*Follow-ups:* measured auto-start ~10 s and auto-end ~25 s — the 20 s grace plus at most one 5 s poll. "Why the unlock check?" — otherwise a session would start while the game is the last app behind the lock screen (comment at 625). The phone sends `ended_seconds_ago`, so its clock never matters.

**6. The authentication guard — `guard(target_uid)` `backend/app.py:357`, with `guard_session` (428) and `deny_non_parent` (413) (owner: Kanak).**
*Summary:* it is a guard function, not a decorator: every protected handler begins `deny = guard(uid)` / `if deny: return deny`. `guard()` verifies the HMAC-signed bearer token (itsdangerous, 30-day TTL), rejects tokens minted before a credential change, authorises the target child through the token's allowed list or a live family-membership check, and treats a deleted account as signed out; production runs `AUTH_ENFORCE=1`, and shadow mode only logs.
*Walk:* `_read_token` (255): no bearer → `None`; expired or bad signature → 401 (366–374) → credential version must be current (`_token_auth_version_current`, 293), else 401 (376–382) → no token → 401 (384–385) → target id must be a positive integer, else 400 (387–391) → in `allowed`, or `_parent_family_allows` (323), else 403 (392–401) → the account still exists (`_user_exists`, 275), else 401 (402–409). `guard_session` looks up the session's owner first (428–435); `deny_non_parent` adds the role check, because a child's own token passes `guard()` for its own id (413–425).
*Follow-ups:* "Why does `_user_exists` fail open while `_parent_family_allows` fails closed?" — the existence probe only detects deleted accounts, and a database hiccup must not lock everyone out; a database error must never *broaden* access. "Why not a decorator?" — the target id comes from a different place in each route (URL, body, or a session's owner), so the check is the explicit first line of each handler.

**7. ParentApp alert triage — `AlertTriage` and `NotificationRouting.channelFor` in `android/ParentApp/app/src/main/java/com/pes/parentmonitor/util/` (owner: Vidisha).**
*Summary:* pure rules with JVM unit tests: a per-child high-water mark picks the new unread alerts, a burst becomes one notification showing the worst severity and the count, and only model assessments (`risk`, `risk_revision`, `toxicity`, `toxicity_streak`) ask the parent "Was this accurate?". Routing sends informational and low-severity events — the score-v2 `score_update` note included — to the quiet Activity channel, and high severity to the urgent one.
*Walk:* `severityRank` → `newAlertsSince` (per-child mark — the sibling bug) → `worstOf` → `notificationTitle` (carries the count) → `isFeedbackEligible` (facts such as login, offline or tamper are not rateable) → `channelFor` (the event type wins over a malformed severity) → `belongsToFamily` (a push for another family is dropped, failing closed; polling is the fallback).

### The architecture

**Q (owner: Kanak): Explain the architecture in 60 seconds.**
(slides 6–7) Three tiers, and the two apps meet only at the server. **ChildApp** (Kotlin, the child's phone): a foreground service checks the foreground app every 5 s, detects installed games itself and opens and closes sessions; chat comes from our Wellbeing Keyboard and the accessibility path; the recorder runs only while the game is in front, Vosk transcribes on the phone and 10-s clips upload; a heartbeat every 3 min feeds the tamper watchdog; nothing is captured without current consent. **Backend** (Flask + gunicorn on Render's free 512 MB tier, Neon Postgres 16; SQLite locally): every upload passes a token check and a consent check; each chat line is scored on arrival (TF-IDF logistic regression + lexicon, noisy-OR, alert at 0.95); each clip becomes 36 features, then an emotion, and the audio is deleted; at session end the 10 behaviour features feed the calibrated forest, and `run_prediction` fuses 40/30/30 over the channels present — score version 2, no genre factor — bands at 0.33/0.67 and writes the alert. **ParentApp** (Kotlin, the parent's phone): polls alerts every 25 s plus data-only push, shows the score with its SHAP reasons, lets the parent rate alerts (ratings become threshold *recommendations* a human applies), sends nudges, builds the weekly PDF, and exports or deletes the family's data. Around it: CI on every push, a weekly drift check, and a model card at `/api/model_card`.

### Ablations and hyperparameters

**Q (owner: Kaustubh): Walk us through every ablation row. What does each one mean?**
(slides 24–25) Protocol (`ml/ablation_studies.py` → `docs/ablation_results.json`): one part removed per row, the model retrained, the same held-out set, bootstrap 95% CIs over 1,000 resamples.
- **Behaviour** (accuracy, held-out **simulated** labels): screen-time hours only 70.2% — the baseline commercial tools ship, and the only row with errors two bands apart (7); volume features only 87.1%; pattern features only 90.2%; the deployed 10 features 91.6% [0.909, 0.923]; all 20 including the derived proxies 91.9% — overlapping intervals, so the proxies add nothing and would make SHAP circular. Pattern beating volume here proves little, because the labels were simulated from the same priors the features encode; the survey's pattern-minus-volume contrast (+0.199 [+0.019, +0.380]) is the external version.
- **Chat** (PR-AUC on the CONDA validation split, *ablation protocol*; the full recipe reads P 0.965 / R 0.363 at 0.95 there — not the deployed operating point): full recipe 0.825 [0.807, 0.841]; − CONDA 0.511, the largest single effect, back to our first general-only model's 0.516 — in-domain data outweighs every other part; − Davidson 0.794, and alert precision drops to 0.895, below the 0.95 bar — slang coverage; − char_wb n-grams 0.794 — misspellings and obfuscation; − keyword list 0.814, small in PR-AUC but alert recall falls 0.363 → 0.278 and MCC 0.541 → 0.472. Three rows score slightly *higher* and are kept on purpose: − calibration 0.837 (isotonic steps coarsen the ranking, but without calibration 0.95 stops meaning about 95 in 100), − HASOC Hindi 0.832 and − clean-Hindi Wikipedia 0.835 (inside the intervals on English-dominant CONDA; their value shows on the 933-row Hindi hold-out, alert precision 0.968 Devanagari and 0.958 romanised).
- **Voice** (accuracy, unseen speakers, 4 classes, chance 0.25; the *ablation* view, not the deployed 0.574): full recipe 0.562 [0.540, 0.584]; 17-feature prefix 0.499 — the 36 features are the lever; English-only corpora 0.546 — slightly worse, intervals overlapping; no augmentation 0.566 — inside the interval, a null we report.
- **Fused score** (production pilot, v1 scores): behaviour alone matches the full band in only 67.7% of 130 sessions, and all of the change comes from dropping voice (dropping chat changed no band) — the extra channels change what parents see.
What it adds up to: accuracy came from data and features; the hyperparameter studies below show tuning moved little.

**Q (owner: Kaustubh): Did you tune the hyperparameters?**
(slide 26) Yes, for all three models, under a protocol that keeps every test set clean. Each grid was searched on training data only — 120 random-forest settings for behaviour (5-fold stratified CV), 14 logistic-regression settings for chat (a validation slice of the training corpora whose duplicates are all removed from training) and 54 gradient-boosting settings for voice (folds grouped by speaker) — 188 in all. Each study first retrained the deployed setting and reproduced the ablation numbers (behaviour 0.9160, chat 0.8246, voice 0.5622), so every comparison is like for like. Each test set was then scored exactly once for two settings, the deployed one and the search winner, with a paired bootstrap of the difference over 1,000 resamples. The hand-set values sit in the middle of their grids (rank 69 of 120, 8 of 14 and 29 of 54). Only behaviour shows a measurable test gain, +0.0113 [+0.0063, +0.0165] accuracy, and it is measured on simulated labels.

**Q (owner: Kaustubh): What did each search find?**
**Behaviour:** CV macro-F1 0.9057–0.9291, with tree depth the main lever (it moves the CV mean by 0.0155; every other setting by at most 0.0041); the deployed setting (200 trees, depth 6, min leaf 20) scores 0.9221; the winner (200 trees, unlimited depth, min leaf 1) adds +0.0113 [+0.0063, +0.0165] test accuracy on 5,750 rows, ahead in 100.0% of resamples — but on real people it does not carry over: scored exactly like the served model on the 103 IGDS9-SF respondents, the winner correlates ρ 0.295 [0.115, 0.456] against the deployed 0.317 [0.137, 0.478], a paired difference of −0.022 [−0.073, +0.027]. **Chat:** validation PR-AUC 0.6751–0.7483 across the 14 settings, C alone moving it by 0.0726; the validation pick, C = 8, is *worse* on held-out gaming chat (7,721 lines): −0.0100 [−0.0167, −0.0035]; at the 0.95 threshold it reads P 0.969 / R 0.336 against the deployed C = 1's 0.965 / 0.363, both under the ablation protocol — it gives up recall. Why the pick misled: only 2,549 of the 35,546 validation texts (7%) were gaming chat; selected on 2,427 gaming-chat texts from CONDA_train alone, the deployed C = 1 ranks 1 of 14 and C = 8 ranks 11. **Voice:** CV macro-F1 0.5402–0.5612; no setting moves it by more than 0.0105, below the CV standard deviation of 0.0180; the winner changes test accuracy on 1,880 clips from 31 unseen speakers by +0.0021 [−0.0117, +0.0154], ahead in only 62.7% of resamples — no detectable gain.

**Q (owner: Kaustubh): Why did you not run a grid search earlier?**
Honestly, the hand-set values looked reasonable, and our effort went into data, features and leakage-free evaluation instead; the ablations show that was the right order. On the same test sets, removing the gaming-chat corpus cuts chat PR-AUC from 0.825 to 0.511, and the earlier 17-feature voice set reaches 0.499 against 0.562, while the largest tuning effect is about one accuracy point. A search is also only meaningful with a leakage-free protocol: folds grouped by speaker for voice, and for chat a validation slice whose duplicates are all removed from training. The studies reuse the ablation code for exactly that reason. The starting points were sensible: C = 1 and the 0.1 learning rate are the library defaults, and the shallow forest was a deliberate choice.

**Q (owner: Kaustubh): Why not deploy the tuned model?**
For chat and voice there is nothing better to deploy. The chat winner, C = 8, is worse on held-out gaming chat (PR-AUC −0.0100 [−0.0167, −0.0035]), and the voice winner differs by +0.0021 [−0.0117, +0.0154], an interval that spans zero. The behaviour winner is better on the test rows, +0.0113 [+0.0063, +0.0165], but those rows carry simulated labels, so the gain measures fit to our simulator, not to children. Adopting it would mean unlimited-depth trees that reproduce their training rows exactly, a model about 24 times larger (1.9 MB against 45.8 MB serialised) and a repeated fairness audit — and on the real survey it is no better (ρ 0.295 against 0.317 for the deployed forest). So we report it as an option and keep the deliberately regularised forest (200 trees, depth 6, min leaf 20).

**Q (owner: Kaustubh): Does the tuned behaviour model work better on real people?**
No. We scored both forests on the 103 IGDS9-SF respondents exactly as the served model is scored, selecting nothing on the survey. The tuned forest correlates ρ 0.295 [0.115, 0.456] with the IGDS9-SF total, the deployed one 0.317 [0.137, 0.478]; the paired difference is −0.022 [−0.073, +0.027] over 2,000 resamples. The interval includes zero, so the survey cannot separate them, and the point estimate favours ours. The +0.0113 is fit to our simulator, not to people.

**Q (owner: Kaustubh): If C = 1 is right, why did your own search pick C = 8?**
Because the selection slice pooled every training corpus, and only 2,549 of its 35,546 texts (7%) were gaming chat, so it rewarded what suits general, non-gaming text. We re-ran the selection on 2,427 gaming-chat texts from CONDA_train alone, with the CONDA validation split still untouched: the deployed C = 1 ranks 1 of 14 and C = 8 ranks 11. Selected on gaming chat, the hand-set value is the tuned value.

**Q (owner: Kaustubh): You searched 188 settings. Isn't reporting the best one just p-hacking?**
It would be if a search had seen a test set or if we had adopted a winner on its test score; neither happened. Selection used training folds or the validation slice only, each test set was scored exactly twice (deployed vs winner) with a paired bootstrap, and we adopted nothing. One winner even lost on its test set (chat), which is what a clean protocol must be able to show.

**Q (owner: Kaustubh): What does the ablation show for each model? (the 30-second version)**
The ablations remove one part at a time, and they show that data and features matter far more than any hyperparameter. Behaviour, on simulated labels: screen-time hours alone reach 70.2%, the five pattern features alone 90.2% and the ten deployed features 91.6%, while all 120 forest settings stay within CV macro-F1 0.9057 to 0.9291. Chat: removing the gaming-chat corpus drops PR-AUC from 0.825 to 0.511 and removing character n-grams to 0.794, whereas the whole range of C moves validation PR-AUC by 0.0726 and the tuned C is worse on test. Voice, on unseen speakers: the 36 features beat the earlier 17 (0.562 against 0.499), while no hyperparameter moves CV macro-F1 by more than 0.0105. The accuracy came from what the models see, not from how they were tuned.

### Results

**Q (owner: Kaustubh): Are the results what you expected? Where they deviate, why?**
(slide 22) We count an estimate only if it was written down before measuring.
- **Behaviour:** the Phase-1 deck expected 80–90% accuracy depending on game type; we reach 91.6% — met, but only on simulated labels, so it checks the method, not real children.
- **Survey:** the validation plan asked for at least 50 adults and expected about 6% in the disordered range; we scored 103, ρ = 0.317 [0.137, 0.478] — size met, but only 1 respondent reached the disordered range, so accuracy at a clinical cut-off cannot be computed (a recruitment problem, not an analysis one).
- **Genre weight:** our Review 2 score assumed genre changes risk (weights 0.70–1.25); the survey found no genre difference (p = 0.598 at 32% power), so score version 2 removed it.
- **Hindi + English speech-to-text:** the gate was fixed on 7 Aug, before measuring (< 2× the default CPU, < 400 MB); it measured 51–72% of a core and 399–419 MB against 14% for the default — failed, so it ships off by default.
- **Chat and voice had no written targets:** deployed chat alerts read P 0.956 / R 0.428 at 0.95 — a chosen trade, rare false accusations and many misses; voice reads 0.574 on unseen speakers, where a random split would have claimed 0.657 by memorising voices.
- **Hyperparameters had no target either:** the hand-set values held up (above).

**Q (owner: Kaustubh): How do your results compare with other methods?**
(slide 23) One comparison per channel on the same held-out data, plus the survey baseline:
- **Behaviour** (simulated labels): screen-time hours alone 70.2% vs our 10 features 91.6%; pattern features 90.2% ahead of volume 87.1%.
- **Chat** (PR-AUC on held-out CONDA, ablation protocol): ours 0.825 vs off-the-shelf toxic-BERT (Jigsaw-trained, about 110M parameters) 0.709 — at ≥ 0.95 precision its recall is 0.12 — vs our own first, general-data model 0.516. Domain data beat model size.
- **Voice**, where we lose: on one matched speaker-independent split, frozen wav2vec2 embeddings reach 0.776 against 0.553 for our 36 hand-made features, but they do not fit the 512 MB server (Future Work: a distilled model). The deployed model reads 0.574 on unseen speakers.
- **Survey** (external, adults): the served behaviour score ρ = 0.317 vs self-reported hours ρ = 0.147 [−0.053, 0.339]; the paired difference +0.167 [−0.002, +0.341] just touches zero, so it is suggestive; the strong comparison is pattern minus volume, +0.199 [+0.019, +0.380].
- **Methodology:** the speaker-independent split reversed the voice model-selection verdict (SVM won the leaky split; HistGradientBoosting wins the honest one).

**Q (owner: Vidisha): What are the limitations, and what are the implications?**
(slide 30) Limitations, each stated in the papers: (1) behaviour accuracy, 91.6%, is on simulated labels — real-child accuracy is unknown; (2) the survey is adult, self-reported and cross-sectional, with one disordered-range respondent, so it shows that the score carries meaning, not clinical accuracy; its secondary analyses are exploratory and not corrected for multiple comparisons (the rank correlation was the pre-designated primary endpoint), and it had no ethics-committee review — the only record is the 14 Aug notification to the guide, sent while the form was open; (3) voice trains on acted adult emotion and reads 0.574; (4) chat alerts trade recall for precision (deployed recall 0.428), so no alert does not mean no abuse; (5) speech recognition is not accent-uniform — 0 false alerts in 9.6 h of benign speech, but word errors from 34.6% (Dravidian) to 60.8% (Tibeto-Burman); (6) fusion weights and cut-offs are hand-set priors; (7) blind spots: browser and cloud-streamed games, in-game voice chat holding the microphone, spoken Hindi off by default; (8) engineering: no automated phone UI tests, a laptop-only load test, a free-tier cold start. Implications: for **parents**, a band opens a conversation — it is a screening signal, not a verdict on the child; for **researchers**, measure how children play, not just how long, and split by speaker; for **deployment**, version every score change, audit every accent group, and expect on-device AI to be limited by terms and background rules as much as by accuracy (Gemini Nano, below).

### Report, paper and venue

**Q (owner: Kanak): What is the status of the project report?**
(slide 34) Drafted in the department format: A4, 1.5 line spacing, 2 cm margins, 12 pt Times New Roman, the department's chapter list (1 Introduction … 9 Conclusion and Future Work), IEEE-style references, Appendix A (abbreviations) and Appendix B (user manual). It is **140 pages** — 13 front-matter pages and 127 body pages — built by `tools/build_report_docx.py` in strict mode (it fails on an unknown number key, a missing figure or a broken reference) and finished by `tools/finalize_report.py` (Word fields, PDF). Every number fills from `tools/project_numbers.py`, the same source as the deck, so the two cannot disagree. New since Review 2: §6.5 the Gemini Nano feasibility study, §8.7 the hyperparameter studies (Table 8.7, Figure 8.8), and score version 2 throughout. Remaining: Prof. Sawant's corrections and approval [team: status], then the **plagiarism check — done only at the PESU library, limit 15%** — and binding and upload. Until that check the report stays out of the public GitHub repository, so the checker cannot match it against a public copy.

**Q (owner: Kaustubh): Where is the IEEE paper, and where will you submit it?**
(slides 39–40) Complete draft, updated 23 Nov 2026 for score version 2: *Measuring How People Play, Not Just How Long: A Multimodal, Privacy-Conscious Gaming-Risk Monitor for Guardians, with Construct-Validity Evidence* — IEEEtran conference format, 6 pages, 31 references, with an anonymous-build switch (`\anontrue`). It claims a deployed three-channel monitor that keeps no raw audio, each channel tested on held-out data with ablations (behaviour labels simulated), the score tracking the IGDS9-SF at ρ = 0.317 in 103 adults, and pattern beating volume by +0.199 [+0.019, +0.380]; and it reports two results against us (the unsupported genre multiplier; four of five parent-facing proxy names not tracking their namesake items). Primary target: **IEEE COMPSAC 2027, Symposium on Digital Health** (Tokyo, 13–16 Jul 2027) — submission **31 Jan 2027** (read on the official call), notification 7 Apr, camera-ready 1 Jun; double-blind; full papers up to 10 pages and short papers 6, so the draft fits and can grow from the report. Why COMPSAC: its call asks for mobile health, health analytics and privacy, and its computing reviewers judge the engineering, not clinical accuracy. Backups: IEEE HealthCom 2027 (8 Jun 2027 — after COMPSAC's decision, so the paper is never under review twice), INDICON 2027 as a budget fallback, and IEEE Access for a longer journal version. We avoid EMBC, ICHI and BHI for now, because they expect ethics-committee approval that our survey lacks. Left before submission: a final proofread and one ethics sentence saying why no ethics-committee review was sought. (The Review 2 plan said mid-November; the target is now COMPSAC's 31 Jan deadline.)

### Speed

**Q (owner: Kanak; Khushee for the phone): How fast is the system?**
(slides 20, 28) **Server, load test** (`backend/scripts/concurrency_smoke.py`: 288 mixed requests from 24 threads against a real threaded server, chat scoring and live predictions included): 0 server errors, median 66 ms, 95th percentile 684 ms in the August run that the deck and report quote; **re-run on score v2, 23 Nov**: 288 requests in 1.6 s, median 64 ms, p95 607 ms, max 819 ms, 0 errors — version 2 added no measurable cost. **Live server:** about 210 ms per warm request from Bengaluru; the gap to the local median is network distance plus the cloud-database round trips. **Cold start, about 40 s:** Render's free instance sleeps after ~15 min idle, and the first request waits for it to boot and load the models. We switched the scheduled keep-alive off on 30 Jul on purpose: keeping Render awake 24/7 held Postgres connections open, so Neon's compute could never scale to zero, and the free 100 CU-hour monthly allowance ran out and paused the database. Both apps tolerate the wait; before the demo we wake it (open the app, call `/api/health`, or run the keep-alive workflow by hand). **Phone** (Galaxy M52): sessions start ~10 s after a game opens and end ~25 s after it closes, a parent nudge arrives in ~12 s, the ChildApp cold-starts in 569 ms, and default monitoring costs 14% of one core and 288–301 MB — about one fifteenth of Roblox's own CPU.

### Since Review 2

**Q (owner: Vidisha; Khushee for item 7): What has changed since Review 2?**
(slides 4–5) Review 2 was on 13 Oct 2026; we made six commitments, and the panel asked us to study one idea:
1. **Genre weight removed — done, 23 Nov 2026**, three weeks after the promised 19 Oct–2 Nov window (score version 2, deployed; the live model card reports `score_version` 2). The full answer is in §10.
2. **Score versioned and parents told — done:** every prediction stores its `score_version`; one-time in-app note.
3. **Report, slides and both papers re-synced to v2 — done** (papers on 23 Nov; the secondary survey analyses are now labelled exploratory; the false claim that an environment variable controlled the genre weight is withdrawn).
4. **IEEE paper — in progress:** the 6-page draft was updated on 23 Nov; submission by 31 Jan 2027.
5. **Child validation** (parents answer the IGDS9-SF, linked to measured play) — **not started**: it needs ethics-committee approval first.
6. **Department-format report — drafted:** 140 pages; the guide's corrections are next.
7. **Panel: could the Gemini Nano API replace our text and voice models? — studied:** not usable now (the terms exclude apps likely to be used by under-18s; no inference while another app is in front; our phones are unsupported). Q&As below; decision record `docs/GEMINI_NANO_FEASIBILITY.md`.

Also new: hyperparameter studies for all three models (188 settings, nothing adopted), an ablation view across all models, the load test re-run on v2, a researched venue list, and 300 automated tests + 7 guards in CI. Deliberately unchanged: no model was retrained (no commit has touched `backend/models/` since 7 Oct), and the survey data is final (25 Aug).

### Gemini Nano — the Review 2 panel's suggestion

Facts are from Google's documentation as checked on 23 Nov 2026 (`docs/GEMINI_NANO_FEASIBILITY.md`, `docs/gemini/defense_qa.md`; report §6.5; slide 5). **We never ran Nano on a phone — never imply otherwise.**

**Q (owner: Kaustubh): Why not replace your chat and voice models with Gemini Nano? Wouldn't an LLM be more accurate?**
It might be on some inputs, but nobody has measured it on gaming chat. We could not measure it either, because our test phone is unsupported. Our chat model is measured:
- PR-AUC is 0.821 on held-out gaming chat as served (0.825 for the recipe under the ablation protocol).
- At the 0.95 alert threshold, precision is 0.956 and recall is 0.428.
- Precision is 0.968 on Devanagari Hindi and 0.958 on romanised Hindi.

That threshold works only because our scores are calibrated probabilities. Nano returns text with no probabilities and may answer differently on another phone or model version. Google publishes no toxicity or Hindi accuracy for it. Size alone is no guarantee: toxic-BERT, a larger general model, reached only 0.709 PR-AUC on the same gaming-chat test. For voice the answer is a firmer no. Our model reads emotion from 36 tone features. The Prompt API takes only text and images, and the speech API returns words, timings and an audio level, not tone. Google's own Nano 4 example is a moderation prompt, so the capability is real. What is missing is calibration, validation and access on our users' phones.

**Q (owner: Kaustubh): Did you actually test Gemini Nano, or only read about it?**
We only read about it, but carefully. We downloaded Google's pages on 23 Nov 2026, checked every quoted sentence, and left out anything we could not confirm. We could not run Nano because no supported phone was available:
- Our Galaxy M52 (Snapdragon 778G) is on no supported list.
- AICore needs Android 14, and the M52 stops at Android 13.
- None of us owns a supported phone.

So we claim no accuracy, latency or battery number for Nano. The test is ready to run:
- **Who and where:** adult team members, a borrowed supported phone and a separate test app.
- **Setup:** a frozen prompt at temperature 0 with a fixed seed.
- **Data:** our held-out CONDA chat and the 933-row Hindi hold-out.
- **Measures:** PR-AUC and precision at the alert threshold, compared with our deployed model on the same lines. Safety-filter refusals count as misses, and we would run our device drill during a game.

We would switch only if Nano reached at least 0.95 precision in English, Devanagari and romanised Hindi, and if the terms and background rules allowed it.

**Q (owner: Khushee): Why can't the ChildApp run Gemini Nano on the phone while the child plays, at least on phones that support it?**
Google permits Gemini Nano inference only when the calling app is the top foreground app, and during play the top app is the game.
- **Foreground services are refused.** Our voice recorder and session monitor run as foreground services. Google's overview says calls from a foreground service get a BACKGROUND_USE_BLOCKED error. Google has documented this since May 2025, when the error was BUSY.
- **Keyboards and accessibility services are untested.** Google says nothing either way about them, and they are how we capture chat. We could not test them without a supported phone.
- **The terms rule out the ChildApp.** The ML Kit GenAI terms exclude apps likely to be accessed by under-18s. That applies on every phone, supported or not.
- **Even supported phones have quotas.** There is a per-app request quota and a long-duration battery quota, both with unpublished limits. The phone is also already running a game. Our own device gate rejected a second speech recogniser on the M52: it used 51–72% of a core, against 14% for the default path.

Nano can fit as a foreground feature on the parent's phone. It would sit behind a capability check, with today's system as the fallback.

**Q (owner: Khushee): Isn't on-device AI better for the child's privacy than sending data to your server?**
Yes. Privacy is the strongest argument for Gemini Nano, and it is why we studied it instead of dismissing it. Part of our voice pipeline already stays on the phone. Vosk turns speech into text on the device. The server receives 10-second clips only while the monitored game is in front, extracts tone features and deletes the audio. But typed lines, transcripts and those clips do reach our server, so Nano would be a real privacy gain. It cannot deliver that gain to our users today:
- The terms exclude apps used by children.
- Inference is blocked while the game is in front.
- Our test phone and Samsung's Galaxy A, M and F phones are not supported.

Until that changes, we limit what the server holds in three ways. Consent fails closed, audio is deleted after feature extraction, and parents can export or delete the data.

**If anyone is asked (every team member, same words):** "We studied Gemini Nano against Google's own documentation, and it is genuinely good for privacy. But today its terms exclude apps used by children, it only works while its own app is on screen, and it does not run on our test phone or on Samsung's A, M and F phones. So we keep our validated models, and we will benchmark Nano as soon as that changes."

---

## 1. Problem framing

**Q: Is this a diagnostic tool for gaming addiction?**
No, and we never claim it is. It is a *screening and awareness* system: it surfaces
behavioural signals to a parent who then decides what to do. The model card served at
`/api/model_card` and the paper both state this. IGD diagnosis requires a clinician;
our contribution is the sensing + fusion pipeline, honestly evaluated.

**Q: Why three channels (behaviour, chat, voice) instead of one good model?**
Because they fail independently. Behaviour needs days of telemetry; chat only exists
when the child types; voice only when they speak. The fusion (§5 below) treats each as
an optional witness — any subset degrades gracefully to the channels present. The
ablation tables show each channel's marginal value is measurable, not decorative.

**Q: Why only children? Why not adults, who are also affected?**
Because of who holds the duty of care. Screening someone who has not asked to be
screened is only proportionate when a guardian is responsible for them — that is what
makes passive capture on a child's phone defensible, and it is bounded by consent that
fails closed, export/delete symmetry and the transparency screen. Point the same system
at an adult and it becomes one of two things: a self-help journal (fine — but then the
person can simply answer the IGDS9-SF themselves) or spyware. An adult self-monitoring
variant would be a different product with a different consent model, not this one with
the age gate removed; the paper's ethics section says exactly this.

---

## 2. Behaviour model

**Q: Why Random Forest and not a neural network / gradient boosting?**
We ran the bake-off (`ml/retrain_models.py` trains and compares candidates) rather
than assuming. On 10 tabular features with 23,000 training rows, RF (200 trees, depth 6)
reached 0.916 test accuracy / 0.918 macro-F1 with 5-fold CV of 0.921 ± 0.002. Deep
models buy nothing on small tabular data, cost more to serve on a 512 MB instance, and
lose the SHAP-friendly structure we use for parent-facing explanations. Since Review 2 we
also grid-searched 120 forest settings on training data only: deeper trees score slightly
better on the simulated test labels (+0.0113 [+0.0063, +0.0165]), which we report and do
not adopt — the depth-6 / min-leaf-20 forest is deliberate regularisation (Review 3
section, hyperparameter Q&As).

**Q: Your training data is synthetic. Isn't the 91.6% accuracy meaningless?**
The number measures *separability of the synthetic distribution*, and we say exactly
that in the paper and in `model_metadata.json` (`data_note`). What we did about it:
(1) no public dataset pairs per-session device telemetry with addiction labels — we
audited six candidates and document why each was rejected (paper §4.2);
(2) we grounded the synthetic generator against real psychometrics — the IGDS9-SF
Latin-America dataset (n=11,191 real MOBA players, `ml/analyze_igds.py`) fixes the
severity base rate, and the Gamers & Anxiety survey (n=13,464, `ml/analyze_survey.py`)
grounds the behaviour–severity relationships;
(3) we then ran the external check rather than only planning it — an adult IGDS9-SF
survey (n=104 usable) shows the served *behaviour* score tracking the clinical instrument at ρ = 0.317,
leading the self-reported screen-time baseline in 97.4% of paired resamples, and
surviving partialling it out (§10). That does **not** upgrade the
91.6%, and we don't claim it does: the accuracy figure is still a synthetic-distribution
number. What it upgrades is the claim that the score *means* something. The honest split
is: separability = synthetic, construct validity = measured, caseness accuracy = still
open. `docs/VALIDATION_PLAN.md` remains the runnable path for the last one.

**Q: Why only 10 features when you compute 20?**
The other 10 are deterministic functions of the first 10 (psychometric proxies derived
in `behavior_features.py`). Feeding them to the model makes SHAP attributions circular
— the model would "explain" a prediction using features computed from the same inputs.
The ablation confirms dropping them is nearly free: all-20 scores 0.9191 vs
objective-10 at 0.916, overlapping 95% CIs [0.9122, 0.9259] vs [0.9087, 0.9233]. We
kept the proxies as UI-level explanations only.

**Q: Are the raw probabilities trustworthy?**
They're isotonic-calibrated on a held-out split the RF never saw (Brier 0.1343 →
0.1275). Calibration only touches the served probability; the underlying RF used for
feature importances is unchanged.

---

## 3. Chat model

**Q: Why logistic regression + TF-IDF and not BERT?**
Measured, not assumed. The deployed recipe (word 1–2 gram + char_wb 3–5 gram TF-IDF
union → LogReg → isotonic) reaches PR-AUC 0.825 [0.807, 0.841] on CONDA in-game chat under the ablation protocol (the served model: 0.821). Measured against a real transformer (2026-08-04): off-the-shelf Jigsaw toxic-BERT (detoxify, ~110M params) reads PR-AUC 0.709 on the same split — 12 points BELOW the domain-trained classical pipeline; at >=0.95 precision its recall is 0.12; the deployed pipeline reads 0.428 at 0.956 precision. Domain data beats model capacity, measured.
A transformer needs GPU or slow CPU inference; we serve on a 512 MB free-tier instance
scoring every chat message in real time. The char_wb n-grams are the cheap trick that
buys robustness to gamer spelling ("noooob", "f4ggot") — removing them drops PR-AUC to
0.794 (ablation row "- char_wb n-grams").

**Q: The balanced-holdout F1 is 0.92 but realistic precision at 0.5 is 0.235. Which is real?**
Both — and the gap is the most important number in the chat section. At the realistic
~3.5% toxic base rate, a 0.5 threshold floods parents with false alarms (precision
0.235 — roughly three false alarms per real one). That is *why* the alert threshold is
0.95 (dual-script HASOC + clean-Hindi-wiki retrain; was 0.90 on the old calibration), where in-domain precision is 0.956 at recall 0.428 — and EVERY register (English, Devanagari, romanised Hinglish) clears 0.95 precision at one shared threshold
(`chat_metrics_gaming.at_alert_threshold`). We chose to miss most single toxic messages
rather than train parents to ignore alerts (the session streak alert recovers coverage:
per-message recall 0.82 at its 0.6 bar, precision 0.63). The threshold is env-tunable
(`CHAT_ALERT_T`) and `ml/tune_from_feedback.py` adjusts it from real parent feedback
using a Beta posterior.

**Eval-leakage fix (2026-07-11, know this if anyone compares to older drafts):** the
general-corpus evaluation (`chat_metrics`) previously rebuilt its "held-out" set from
the general corpus alone while training also included CONDA + chat_extra — so trained
rows leaked into the holdout (~55% of the balanced set). The eval now imports the
trainer's exact corpus assembly, making the holdout genuine. Post-fix: balanced F1
barely moved (0.924→0.917 — the model was never overfit), while realistic precision
@0.5 ROSE from 0.053 to 0.205 and the base rate from 0.7% to 3.5% (the old "realistic"
set was general-corpus-only and unrepresentatively easy). The IN-DOMAIN CONDA_valid
numbers (P 0.950 / R 0.491 at 0.90, PR-AUC 0.834, all ablation deltas) are untouched —
CONDA_valid was never in training, so that eval had no leakage. Older-draft nuance: the
2026-07-06 keyword-punctuation fix shifts three in-domain display cells by 0.001
(P@0.90 0.950→0.949, R 0.491→0.492, best-F1 recall 0.660→0.661); recorded values kept.

**Q: Why fuse a keyword lexicon with an ML model? Isn't that admitting the model is weak?**
It's a noisy-OR of two imperfect detectors: `1-(1-kw)(1-ml)`. The lexicon catches
Hinglish and Devanagari abuse (bsdk, chutya, मादरचोद) that no English-trained corpus
covers; the ML generalises beyond any list. Ablation (0.95 threshold, retrain-from-scratch protocol): removing fusion drops
recall-at-alert from 0.363 to 0.278 and MCC from 0.541 to 0.472 at essentially the
same precision. For an Indian deployment context, the lexicon is load-bearing, not
decorative.

**Q: What was the single biggest chat improvement?**
Domain data. Removing CONDA (in-game chat) from training collapses PR-AUC from 0.825
to 0.511 — worse than every architecture choice combined. The original general-corpus,
word-only model scored 0.516. Lesson we state in the paper: data > architecture.

---

## 4. Voice model

**Q: Does the voice channel transcribe speech or classify emotion?**
Both, as two separate paths. (1) On-device Vosk (Indian-English `en-in` model)
transcribes speech locally; transcripts enter the *chat* pipeline tagged
`voice_stt`, so spoken abuse is caught by the same toxicity model. (2) 10-second
audio segments are uploaded, the server extracts 36 acoustic features
(`backend/audio_features.py`), and HistGradientBoosting classifies emotion
(angry/excited/frustrated/neutral). Raw audio is deleted after feature extraction
(`app.py`, voice upload route) — only features and the label are retained.

**Q: 57.4% accuracy is barely better than random. Why present it?**
Because it's the *honest* number and we know exactly why it's not higher. Chance on
4 classes is 25%, so 0.574 / macro-F1 0.568 is meaningfully above chance but far from
production-grade — and we say so. The instructive part: with naive random splits the
same model scores ~0.657. That 8.3-point gap is **speaker leakage** — the model
memorising voices, not emotions. We switched to speaker-independent evaluation
(GroupShuffleSplit; no speaker in both train and test), reported the lower number,
and the paper documents that the split choice *reversed the model-selection verdict*
(SVM won leaky splits; HistGB wins honest ones). An examiner should prefer an honest
0.574 to an inflated 0.657.

**Q: What have you done to improve the voice model, and how much would it help?**
Measured, not guessed. The 0.574 is bounded by the 36 hand-crafted acoustic
features — not the classifier or the protocol. We proved this: extracted frozen
wav2vec2 embeddings (1024-d) for all 9,780 clips and fed them to the *same*
classifier on the *same* speaker-independent split. Result — 0.553 (36-feat
baseline) → **0.776** with embeddings, **+22 points from representation alone**,
on unseen speakers (`ml/eval_voice_headroom.py`). One honest negative: training on
fine emotion labels then grouping to our 4 classes *underperformed* (0.694) —
fine classes too sparse per speaker under grouped splits, so we report it as a
tried-and-rejected variant. Why not just deploy embeddings? The 512 MB serving
budget — which is exactly why Future Work names Wav2Small (a 72K-param
distillation of this model). This experiment measures the ~20-point prize that
distillation is chasing, turning "a bigger model would help" from assertion into
measurement.

**Q: The training corpora are acted adult emotions (RAVDESS, CREMA-D, EMO-DB, URDU). Children playing games don't sound like that.**
Correct, and it's the stated validation gap (`voice_metrics.note`). Acted corpora are
the best *available* labelled emotional speech; child gaming speech is the target of
the validation plan. Mitigations we measured: training multilingual (adding EMO-DB +
URDU edges out English-only, 0.562 vs 0.546, intervals overlapping) and using the full 36-feature set (vs the
17-feature prefix: 0.562 vs 0.499). Augmentation was tested and found ~neutral
(0.566 without vs 0.562 with) — we report that negative result rather than hiding it.

**Q: Why is the voice weight lowest in the fusion?**
Correct the premise first: voice ties with chat at 30%; behaviour gets 40%, because DSM-5
Internet Gaming Disorder and ICD-11 Gaming Disorder are defined behaviourally, and chat
and voice are corroborating distress signals. The 40/30/30 split is a clinically
motivated *prior*, not a fitted weighting — we have no outcome labels to fit it on — so
what we measured instead is how much it matters: shifting the weights by up to ±0.15
changes a median 0.8% of pilot bands, at worst 10.7%. A missing channel contributes
nothing rather than a fake neutral score.

---

## 5. Fusion and alerting

**Q: How do you combine three channels?**
Weighted fusion with a 40/30/30 prior (behaviour dominates: it's the best-measured
channel and always present after a few sessions). Channels that produced no data this
session are renormalised out instead of being imputed. Session chat risk is the *max*
of per-message calibrated confidences, not an average — one credible threat matters
more than a hundred clean messages diluting it. Since score version 2 (23 Nov 2026) that
renormalised mean *is* the served score: the genre multiplier is gone (§10).

**Q: Why alert at 0.95 and not the F1-optimal threshold?**
The CONDA threshold sweep puts best-F1 near 0.85 (P 0.800 / R 0.703) and the deployed
0.95 at P 0.956 / R 0.428 (0.90 reads P 0.888 / R 0.623, env-selectable). We deliberately sit above best-F1 because the asymmetric cost is
false alarms: a parent who gets three wrong alerts stops reading them. Both points are
in `model_metadata.json`; the threshold is an env var, and the feedback tuner moves it
with real parent responses.

---

## 6. Evaluation methodology

**Q: What makes your evaluation trustworthy?**
Five properties: (1) every serving model is evaluated on held-out data it never
trained on, with seeds recorded; (2) voice uses speaker-independent splits; chat's
headline number is *in-domain* (CONDA) not general-corpus; (3) all ablations carry
bootstrap 95% CIs over 1,000 resamples, so "better" claims are only made when
intervals separate; (4) we report MCC alongside F1 at the alert threshold because F1
ignores true negatives at extreme base rates; (5) the pipeline's *output* is anchored
outside its own training distribution entirely — against the IGDS9-SF clinical
instrument in real respondents (§10), a test the models could and partly did fail.
The protocol line at the bottom of `docs/ablation_results.json` states the exact
procedure.

**Q: Did you tune on the test set?**
No. Thresholds were selected on the sweep and justified by the false-alarm argument,
not by maximising a test metric; the tuner adjusts thresholds *forward* from live
parent feedback, never by re-fitting on evaluation data. The one place we caught
ourselves: an early `eval_chat_conda --retrain` run scored on its own training file —
we split eval into a separate `--eval-csv` and note it as a fixed pitfall. The
hyperparameter studies follow the same rule: searched on training data only, each test
set scored once for two settings, nothing adopted (Review 3 section).

---

## 7. Datasets

**Q: Which datasets did you consider and why did you reject some?**
Full audit table in paper §4.2. Adopted: Gamers & Anxiety survey (n=13,464), IGDS9-SF
LatAm (n=11,191), CONDA (in-game chat, 8,974 labelled eval rows), Davidson hate-speech,
RAVDESS + CREMA-D + EMO-DB + URDU (9,817 original clips; 12,864 augmented feature rows).
Rejected with reasons: Kaggle
"Predict Online Gaming Behavior" (provenance audit shows synthetic generation;
engagement labels, not addiction), Kaggle "Mobile App Usage Behavior" (covers ~3 of
our 10 features; credential-walled so not reproducible). We downloaded and inspected
the rejected ones rather than dismissing them from the description — the audit
evidence is in the paper.

---

## 8. Engineering and deployment

**Q: Can a Flask + SQLite backend on a 512 MB free tier actually handle this?**
Measured: the concurrency smoke (`backend/scripts/concurrency_smoke.py`, 288 mixed
requests across 24 threads against a real threaded server, including per-message chat
scoring and live predictions) passes with **zero 5xx errors** — p50 66 ms, p95 684 ms
on the dev machine in the 2026-08-04 post-retrain run (the figures the deck and report
quote), and p50 64 ms, p95 607 ms, max 819 ms in the 2026-11-23 re-run on score v2 (288
requests in 1.6 s; v2 added no measurable cost). The script is permanent and
re-runnable; the same check against the deployed Render instance is still not done —
live, a warm request takes about 210 ms from Bengaluru and a free-tier cold start about
40 s. The DB layer is dual-dialect (SQLite/Postgres), and production already runs Neon
Postgres 16.

**Q: How is the API secured?**
Signed HMAC bearer tokens (itsdangerous), role-separated: parent-only routes call
`deny_non_parent()`, per-user access calls `guard(user_id)`. `AUTH_ENFORCE` supports
a shadow mode (log violations without breaking clients) → enforce rollout. Rate
limiting via Flask-Limiter; tokens of deleted accounts are rejected by an existence
check. 190 backend tests — run in CI against both SQLite (190 pass) and Postgres 16,
the production dialect (189 pass; the one SQLite-only migration test is skipped) — cover
the authz matrix, including regression tests for the alert-ownership gap we found and
fixed; 110 Android JVM unit tests guard the offline-session/capture-health logic,
profile validation, risk presentation, offline queue, WAV, keystroke reconstruction,
and alert-triage logic. That is 300 automated tests on every push, plus 7
research-integrity guards.

**Q: Why sideloaded APKs instead of Play Store?**
The ChildApp needs a NotificationListener + accessibility-adjacent capture that Play
policy treats as high-risk surveillance; the legitimate deployment is a parent
knowingly installing on a family device. Sideload + cloud backend is the honest
distribution story for a capstone, and the paper says so.

---

**Q: Your weekly drift-monitor CI went red on 24 Aug. What happened?**
It caught us — correctly, and the postmortem made the monitor better. Verified
composition of the two windows: the reference (20 Jul–17 Aug, 1,812 predictions) was
**98.7% the real pilot child** (1,788 rows); the recent week was **99% the developer's
device-drill account** (307 rows from the 18 Aug resource drill — one prediction per
10-s voice segment) plus the same-day demo reseed. Fused-score PSI 2.48; and the
monitor's modality-presence separator did its exact job: `chat_present` 1.1% → 45.2%
(the pilot child's game has no chat; the drill streamed STT transcripts), attributing
the shift to **population/capture-mix, not the model** — nothing deployed had changed
(models trained 4 Jul, last backend deploy 14 Aug). Two actions followed. (1) The
published demo children (ids 1, 3) are now excluded from both windows
(`DRIFT_EXCLUDE_USERS`): `seed_demo.py` rewrites them and re-anchors their history on
every reseed, so their distributions change by construction, not by drift. With them
out, the post-pilot windows hold one real account each — below the 3-child population
floor — and the job reports that honestly instead of failing. (2) The incident exposed
a real **false negative**: chat's verdict said "stable" at PSI 0.000 despite KS p = 0
and a 30× mean shift, because PSI's quantile bins collapse on a near-constant
reference and the old fallback put every non-negative score in one bin. Fixed with a
tolerance-band fallback, flagged `[degenerate ref]` in reports, and regression-tested
on the exact production shape (chat now reads PSI 1.71 DRIFT on that same data). A
monitor that fires on a known perturbation, attributes it correctly, and gets improved
by its own false negative is evidence the system is *monitored*, not decorated.

---

## 9. Privacy and consent

**Q: You're recording a child's microphone. Defend that.**
Layered mitigations, all implemented: (1) explicit onboarding consent, and the child
can revoke any capture permission — revocation triggers a parent alert rather than
silent failure; (2) speech-to-text runs **on-device** (Vosk); (3) uploaded audio
segments are deleted server-side immediately after acoustic-feature extraction — raw
voice is not retained; (4) webrtcvad gates capture to actual speech; (5) parents get
`/api/user/export` (full JSON of everything held, credentials excluded) and
`/api/user/delete_data` (scope identical to export — what you can see is exactly what
gets erased). We also state plainly: this is parental monitoring of a minor, not
covert surveillance of an adult, and the retention wording in the docs was audited to
match actual behaviour.

**Q: What's in the export, and what's deliberately not?**
All 15 user-scoped tables (sessions, behavioural data, chat, voice events,
predictions, alerts, streaks, reflections, …) capped at 20k rows/table with explicit
truncation flags. Excluded: PIN hashes and FCM push tokens (`_EXPORT_EXCLUDE`) —
an export must never become a credential-exfiltration path. Parent-only, rate-limited
5/hour.

**Q: You alert parents about swear words but stay silent when a child tells Mira
they want to hurt themselves. How is that defensible?**
Name the asymmetry before defending it — it's real, it's deliberate, and paper §7 now
states it in exactly those terms. The reasoning: a toxicity alert is low-stakes and
reversible; auto-disclosing a suicidal confidence is neither. It can destroy the one
channel the child chose to trust at the worst possible moment, and clinical guidance
on guardian disclosure of adolescent self-harm ideation is genuinely divided — so we
refused to hard-code a clinical judgement in engineering code. What the child *does*
get, immediately: recall-first detection (deliberately the opposite tuning of the
precision-first toxicity channel) and real helpline signposting (Tele-MANAS 14416).
The likely correct design — offer the child help involving their parent first, else a
non-verbatim "wellbeing check-in suggested" prompt to the parent that discloses
concern without quoting the confidence — is documented in §7 **as a proposal, not
shipped**, because shipping it is precisely the decision that requires clinical
review. If pushed "so you did nothing?": no — we did the thing engineers can defend,
and documented the thing clinicians must decide.

**Q: What are the system's sensing blindspots? / Can a child evade monitoring?**
Volunteer the three real ones (paper §7 "Sensing blindspots, named"), each with its
mitigation: (1) **In-game VOIP holds the mic** (Android exclusive
`VOICE_COMMUNICATION` focus) → our recorder gets silence exactly when the child is
most vocal. The pipeline degrades honestly rather than mis-scoring: silence is
rejected at extraction (silence floor + VAD), no voice event is produced, fusion
renormalises over present channels, and the drift monitor's modality-presence rates
catch sustained regressions. Missing piece (future work): telling the parent *why*
voice is absent. (2) **Keyboard switching** → detected, not silent: the monitor polls
the default-IME setting, heartbeats carry capture bits, the parent sees degraded
monitoring + a one-shot alert, and the child gets a re-enable prompt (built after the
pilot caught an OS reset disabling the keyboard for days). Residue: momentary IME
flips, controllers, dictation. (3) **Games inside another app** → genuinely
invisible, and we keep it that way on purpose. This is ALL of: browser games (poki,
io games), cloud-streaming portals (now.gg streams even Roblox into a tab — the
realistic teenage evasion), and webview mini-games inside messengers/social apps.
One sentence to anchor the answer: **detection is foreground-package-based and never
inspects traffic or content, so the monitoring boundary is "installed apps," not
"games."** Closing it needs screen capture or URL surveillance, both worse than the
gap. Dedicated cloud apps (GeForce NOW, Xbox Game Pass — now on the curated list) ARE
monitorable; behavioural features are timing-based so streaming changes nothing.
"Online vs offline" is irrelevant — an offline installed game is fully monitored, an
online browser game isn't. If pushed "so a kid just uses now.gg?": yes, and we say so
in §7 rather than pretending otherwise; the parent still sees "monitoring healthy,
zero gaming," and the in-posture future mitigation (§7) is a "high screen time, zero
detected gaming" discrepancy nudge — no URLs, no pixels, just the mismatch. Nuance
that usually defuses the Roblox version of this question: plain Roblox in mobile
Chrome isn't playable — roblox.com pushes into the native app, which is on the
curated list and was the pilot's demo game. A disclosed boundary beats a privacy
regression.

**Q: Couldn't a child just clear app data to stay in observation mode forever?**
No — that's a local-state assumption and the state isn't local. Observation mode
counts **server-side** completed, scored sessions per child account (`app.py`:
`COUNT(*) FROM sessions WHERE user_id=? AND end_time IS NOT NULL AND final_risk_score
IS NOT NULL`). Clearing app data resets nothing server-side; it also kills the
heartbeat, which raises an offline tamper alert. Creating a fresh child profile
appears on the parent dashboard, and deletion is parent-role-only. Same family of
question — "can one anxious parent drag the thresholds down?": no, the feedback tuner
caps at ±0.05 per run, refuses to move below a minimum-evidence floor, and writes
recommendations a human applies via env vars — there is no automatic loop to drift.

---

## 10. External validation — the IGDS9-SF survey

Paper §6.6. Reproduce with `python ml/eval_behavior_survey.py data/survey/responses.csv`
and `python ml/eval_survey_extras.py data/survey/responses.csv`; aggregate outputs are
committed as `docs/survey_validation.json` and `docs/survey_extras.json`.

**Q: You say the score means something. What's the evidence?**
An anonymous adult survey (134 raw; 104 usable, 103 scoreable — main wave 7–9 Aug
plus a passive late batch of 22 through 20 Aug, folded in per a rule fixed before
any late data existed) pairing the nine
IGDS9-SF items with seven gaming-pattern questions. Those seven are mapped to the
model's 10 objective features and pushed through the **deployed serving path** — same
`derive_psychometrics`, same fitted scaler, same calibrated forest, same behaviour-channel
formula (0.5·P(Some) + 1.0·P(High)) — so what we correlate is the behaviour score the
server computes; since score version 2 that is exactly the served score for a session
scored on behaviour alone (no genre factor; chat and voice were never part of the study). Result:
**Spearman ρ = 0.317, 95% CI [0.137, 0.478]**. The interval excludes zero.

**Q: 0.32 is a weak correlation. Why should that impress us?**
Two reasons, and we don't oversell it. First, the comparison that matters is not
against 1.0 — it's against the baseline this product exists to replace. Self-reported
hours/week reaches only ρ = 0.147 on the same respondents, CI spanning zero. A paired
bootstrap on the difference gives **Δρ = +0.167, model ahead in 97.4% of resamples** —
say yourself, before they do, that the difference's CI now grazes zero ([−0.002,
+0.341]; it excluded zero pre-batch), so the claim rests on the partial correlation.
Second, we tested whether the score is just screen time wearing a hat: partialling
hours out barely moves it (**ρ = 0.303, CI [0.110, 0.476], excluding zero**). So it
carries severity information volume does not. That's the project's whole design
premise, and it's now measured rather than argued.

**Q: Which features actually carried it?**
All five *pattern* features out-rank all five *volume* features — no interleaving.
Formally tested, not eyeballed: the paired composite difference is **+0.199 [+0.019, +0.380]**, excluding zero (pattern ahead in 98.5% of resamples). Composites: pattern ρ = 0.330 [0.154, 0.489], volume ρ = 0.128 [−0.083, 0.328] (CI
includes zero). Two volume features are inert: `daily_play_time_hours` (+0.052) and
`avg_session_duration_min` (+0.042). This is the first *external* evidence for the
feature engineering; the ablations couldn't produce it because synthetic labels were
generated from the same priors the features encode.

**Q: Why no sensitivity/specificity at the clinical cut-off?**
Because the sample contains **one** respondent in the disordered range (≥36). Caseness
metrics on one positive are noise, and the script refuses to print them below ten
positives *by design* — that guard was written before we saw the data, not after.
Reaching ten needs ~157 usable responses at the literature's 6.4% base rate, and
~1,040 at the 1.0% this convenience sample actually showed. It's a recruitment problem
(reaching a help-seeking population), not an analysis problem. Saying "we can't compute
this yet" is the correct answer; computing it on n=1 would have been the wrong one.

**Q: Why stop recruiting at 112? And didn't more responses arrive after you "closed"?**
We stopped *recruiting* when the numbers stopped moving: across ten snapshots
(n=33 → 87 usable) the headline stayed significant and its lower CI bound rose
steadily. We left the form open, and a passive late batch of 22 arrived 13–20 Aug.
The rule — fixed before any late data existed — was: fold in whatever arrives and
re-run everything, whichever way it moves the numbers. It moved them down: ρ 0.352 →
0.317 (still significant), and the paired delta's CI widened to graze zero. We
updated every document to the attenuated values and kept the pre-batch snapshot on
record. That is what pre-committing to a rule looks like when it costs you something.
The genre test, meanwhile, weakened for the third straight time as n grew (p 0.159 →
0.491 → 0.598) — the effect is smaller than any power analysis assumed, not nearly
significant.

**Q (owner: Kanak for the change, Kaustubh for the test): Your genre multiplier failed the survey test. What did you do about it?**
We removed it from the served score: **score version 2, deployed 23 Nov 2026** (commit
`e9d16c8`, CI green; the live `/api/model_card` reports `score_version` 2). The test:
Kruskal-Wallis across seven genres, H = 4.59, **p = 0.598**, and the group ordering does
not even match the multiplier's assumption. We report it as a null because a validation
study that can only confirm isn't one — but the honest reading is *underpowered, not
disproven*: resampling gives the test 32% power at this n, 90% only near n ≈ 400. The
argument that settled it (team decision, 7 Oct 2026): the validated computation never
included genre — both survey scripts score answers through the behaviour model alone and
import neither `GENRE_RISK_WEIGHTS` nor `GAME_GENRES` — so a hand-set factor from 0.70
(Casual) to 1.25 (Battle Royale) sat outside what we validated, its only test found no
support, and the burden of proof sits on keeping it, not on removing it.
- **The formula, exactly.** v1: `final = clip(g · Σ w_k·s_k / Σ w_k, 0, 1)`, with `g` the
  game's genre weight (1.0 when the game or genre is unlisted). v2:
  `final = clip(Σ w_k·s_k / Σ w_k, 0, 1)` — the same 40/30/30 weights renormalised over the
  channels present, the same three channel scores, the same 0.33/0.67 bands and
  observation-mode cap; only `g` is gone (and the clip no longer does anything, because a
  weighted mean of scores in [0, 1] stays in [0, 1]).
- **Versioned, not a silent swap.** On the production pilot the change moves **34.4%** of
  served bands (45 of 131 sessions; before it: 63 Low, 68 Some, 0 High concern), so a
  child's trend could jump with no change in play. Every prediction row therefore stores
  `score_version` (NULL = v1 history, never back-filled, read back as version 1);
  `ml/analyze_fusion_sensitivity.py` re-scores each stored row with the formula that
  served it, and `ml/monitor_drift.py` compares fused scores only within one version, so
  the change cannot read as drift.
- **The parent note.** Parents of a child with v1 history get one informational note (type
  `score_update`, severity low) on that child's first v2 score — at most once per child
  (partial unique index `idx_alerts_one_score_update` + `INSERT … ON CONFLICT DO NOTHING`),
  never pushed, not rateable, not counted in agreement statistics, and routed to the
  ParentApp's quiet Activity channel. Verbatim (`SCORE_V2_PARENT_NOTICE`, `backend/app.py`):
  *"We updated how the risk score is calculated (score version 2). The game-genre
  adjustment was removed because our validation study found no evidence that the type of
  game changes the risk. Earlier sessions were scored the old way, so the concern level
  from now on may differ from before even if play has not changed. Nothing else about
  monitoring has changed."*
- **The evidence.** `docs/genre_removal.json`; 8 new tests (genre no longer changes the
  served score; live, end and replayed predictions carry their version; the note reaches a
  child with v1 history exactly once and never a child without; it is information, not a
  rateable risk alert; re-running the schema setup and the SQLite migration keep the
  versions; drift compares within one version); 190 backend tests pass on SQLite, 189 +
  the one SQLite-only skip on Postgres 16; the migration was rehearsed on a Postgres 16
  database built by the pre-v2 backend (v1 rows stayed NULL, exactly one note even from a
  cold second worker, a raw duplicate refused).
- **No configuration switch, ever.** No environment variable or setting ever controlled
  the multiplier; an earlier version of this answer claimed one, which was false and is
  withdrawn from every document. It is deliberately not configurable now either: bringing
  genre back would need new evidence (a powered study, n ≈ 400), a code change and a new
  score version.

**Q (owner: Kaustubh): So is the served score now the validated score?**
Only for sessions scored on behaviour alone — say that precisely. The survey validated one
computation, the behaviour channel (`0.5·P(Some) + 1.0·P(High)` from the calibrated
forest), on anonymous adults' self-reported answers mapped to band midpoints: no device
telemetry, no children, no chat or voice, no 40/30/30 fusion, no band thresholds, no
observation-mode cap. When chat or voice is present, the v2 score is still a fusion whose
weights are priors — in the v1 pilot analysis, re-scoring from behaviour alone matched the
served band in only 67.7% of 130 sessions. Removal also does not show that genre has no
effect: p = 0.598 at 32% power is a weak null. And 34.4% is how many bands *moved*, not
how many were wrong — there is no ground truth for those 45 sessions, and the sweep did
not record direction (by construction, a genre weighted above 1.0 — Battle Royale, FPS,
MOBA, MMO, RPG — could only move Some → Low concern, and Strategy, Sandbox or Casual only
Low → Some or Some → High). The case for removal is narrower and stronger than "genre
doesn't matter": the multiplier sat outside the validated computation, and its only test
found no support.

**Q (owner: Kanak): You decided on 7 Oct and committed to it at Review 2. Why did it ship only on 23 Nov?**
Own the slip first: at Review 2 (13 Oct) we promised it for 19 Oct–2 Nov; it landed on 23
Nov, three weeks late, and the timeline slide (33) says so in those words. The reason:
[team: reason]. What the change had to carry — say it only if asked, and not as an excuse:
a versioned column and migration on a live Postgres database, a once-only parent note that
holds even with two server workers, version-aware analysis and drift tools, 8 new tests, a
migration rehearsal on a database built by the pre-v2 backend, and re-syncing both papers,
the report and the deck. Until 23 Nov, parents saw score version 1, with the multiplier.

**Q: Your parent-facing "craving score", "tolerance score" — do those mean anything?**
Mostly no, and we tested it rather than waiting to be asked. Against the IGDS9-SF item
each is *named* after: `craving_score` +0.322 (holds up); the other four read +0.020
to +0.092 — indistinguishable from zero (including `gaming_priority_score`, which was
a marginal +0.162 pre-batch and fell to +0.090). They were never
model inputs — they're UI explanations derived from behaviour — but the clinical-sounding
names overclaim. **And we acted on the finding**: the four discredited labels served to
parents were renamed to describe the behaviour each score is computed from ("Loss of
control" → "Frequent long sessions", "Tolerance buildup" → "Lengthening sessions",
"Neglecting duties" → "Heavy daily play", "Gaming over priorities" → "High daily
hours"); "Gaming cravings" — the one the data supported — keeps its name. Internal keys
and the export schema are unchanged. This is the validation loop closing in the
product: the study found our naming overclaimed, so the served text changed. We'd
rather report evidence against our own naming than have the panel find it.

**Q: The threshold search found better cut-offs. Why didn't you apply them?**
The grid search returns T1 = 0.51, T2 = 0.83 (quadratic-weighted κ = 0.177) vs the
deployed 0.33/0.67. We declined. T2 sits at 0.83 — far above the deployed 0.67 — precisely *because* the sample has
almost no disordered-range respondents — the fitted value encodes the sample's missing
tail, not a clinical boundary (the pre-batch fit read T2 = 0.95 — one late batch of
22 moved it by 0.12, which is the demonstration) — and κ = 0.177 is fair agreement
at best. The tuner is
env-var wired and reversible in one deploy; it stays unused until a cohort with a real
severity tail earns it. Same discipline as the parent-feedback threshold tuner: the
mechanism ships, the change waits for evidence.

**Q: Both sides of your correlation are self-report from the same person. Isn't this just common-method variance? And doesn't it validate a formula on survey answers, not your sensing pipeline?**
Both halves are fair and we say so in the paper (§6.6 (iii), IEEE §IV.B). Precisely: the study validates the served risk *formula* applied to self-reported pattern answers mapped to band midpoints — the exact serving path, but with recalled bands as inputs rather than measured telemetry. So it is not yet an end-to-end validation of passive sensing; the telemetry-linked per-child cohort is. On CMV: yes, part of a self-report-vs-self-report association can be method inflation (Podsakoff et al. 2003). Three things bound it without eliminating it — and these are the answer, so have them cold: (1) the **hours baseline is self-reported on the same form**, so it shares any method inflation, and the model still leads it in 97.4% of paired
resamples (Δρ = +0.167, CI grazing zero) — a *within-method* contrast — though hours is one item and the score aggregates seven, so part of the edge may be differential reliability (Westfall & Yarkoni 2016), which we now state; (2) **pattern features beat volume features on the same form, formally: paired composite difference +0.199 [+0.019, +0.380]** — a *between-feature* contrast that shared method cannot manufacture, and exactly the design premise; (3) the predictor items are behavioural *frequencies*, not attitudes, which typically attenuates method effects rather than inflating them. And on "0.32 is modest": ~10% shared variance, wide CI at n = 103 — but 0.3–0.5 is the normal range for brief behavioural screeners against full instruments (e.g. PHQ-2 vs PHQ-9), so "modest" is "expected", and we claim construct carriage, not clinical accuracy. Never say "it's fine"; say "it's bounded, here's how, and here's the study that closes it."

**Q: These are adults. Your product monitors children.**
Correct, and it's the study's biggest external-validity gap — we state it in the paper
before anyone asks. Three specific consequences: prevalence and thresholds don't
transfer; the respondents *self-reported* their patterns in bands where the app
*measures* them (both coarsening and recall error attenuate the correlation); and the
design is cross-sectional, so it says nothing about trajectory. What it does establish
transfers regardless of age: the pipeline's output tracks a validated instrument, and
pattern features carry signal volume features don't. The per-child cohort — guardian
IGDS9-SF scores linked to telemetry — is stage two, and it needs ethics approval.

**Q: Did you take permission for the survey? Where's the ethics approval?**
The exact record, have it cold: on **14 Aug 2026** Kaustubh mailed Prof. Sawant from
the official PES account (pes1ug23cs291@pesu.pes.edu), cc'ing all three teammates,
disclosing the full design — adults 18+ only, fully anonymous, no names/emails/
identifiers, ~3 minutes, consent statement before starting, participation voluntary —
with the form link and the explicit sentence *"please let us know if the department
requires any additional approval for anonymous surveys of this kind."* That is written
faculty notification with a documented good-faith query, **not** an ethics-committee
or IRB determination, and no paper claims otherwise. Timing, stated honestly before
anyone else does: the mail went out **while the form was open** — after the 7–9 Aug
main wave, before the late batch finished arriving, before close-out, and before any
analysis of the final n = 134 sample; the papers say exactly this. If pressed on "why
not before launch," concede the sequencing plainly *first*: **notification should have
preceded the first collected response; it didn't, and we corrected course mid-window
rather than after the fact.** Only then the mitigations, which now land as mitigation
rather than evasion: the survey is minimal-risk by construction (anonymous, adults-only,
consent-gated, voluntary); from 14 Aug the guide had the full design, the form link,
and the standing written approval query while the form was still open; and the final
n = 134 analysis postdates both the notification and the close-out. **If asked "did she
reply?"** — state only what the record documents: the notification and approval query
were sent from the official account on 14 Aug; we claim no reply, no approval, and no
absence-of-objection, and neither do the papers. Do not improvise beyond that. **If
asked "so you analyzed data before notifying her?"** — yes, interim looks at the
main-wave data existed; every claim in the papers and here is deliberately scoped to
the *final* analysis, which postdates notification and close-out — say that, don't
deny the interim looks. What *does* need prior institutional review — and is gated on
it — is stage two: minors, guardian consent, telemetry-linked IGDS9-SF. (One blemish
to own if the department cross-references: the mail's body cites project code
"PW26_SJ_05" — a stale early code that also lingered in two repo files (since fixed to
PW26_SAS-03); the signature block carries the correct "Team PW26_SAS-03". Own it as a
stale internal code, not concealment.)

**Q: Did you clean, filter, or discard any responses to get this result?**
Every exclusion rule was fixed before analysis and is in the script: under-18 or
non-gamer (20 dropped), failed attention check (10 dropped), incomplete IGDS items (0).
That's 134 → 104. We also ran the headline *without* the 9 respondents who gave the
identical answer to all nine items — ρ = 0.292 [0.104, 0.461], attenuated but still
excluding zero. No response was ever added, edited, or invented.

**Q: Why isn't the raw data in the repo?**
The consent text covered use of anonymous responses *for research*, not public
redistribution. We publish the aggregate JSON from both scripts and the scripts
themselves, so any equivalently-formatted export reproduces every number. Releasing
row-level data would have exceeded what participants agreed to.

---

## 11. The closing question

**Q: What's the weakest part of this project?**
Validation depth — though it is no longer validation *absence*. The behaviour model's
training labels are still synthetic (grounded, but synthetic), so the 91.6% accuracy
figure remains a synthetic-distribution number and the survey does not upgrade it. The
voice model trains on acted adult emotion. What changed is that the pipeline's *output*
now has an external anchor: ρ = 0.317 against IGDS9-SF, leading the screen-time
baseline in 97.4% of paired resamples with the partial correlation excluding zero
(§10). The remaining gap is specific and nameable — no caseness metrics,
because the sample held one disordered-range respondent; adults rather than the
adolescent target; cross-sectional rather than longitudinal. We quantified what each
proxy costs where we could (speaker leakage: 8.3 points; missing domain data: 31 PR-AUC
points), and `docs/VALIDATION_PLAN.md` is the scripted path onward. The contribution is
not a solved clinical instrument — it's a fully-built, honestly-measured screening
pipeline where every claim traces to a runnable script, including the two claims the
validation study **refused** to support.

**Q: What would you do with three more months?**
In order: (1) a consented pilot with 10–20 families to replace synthetic behaviour
labels with real ones and, critically, to reach a cohort with a genuine severity tail —
that single change unlocks the caseness metrics §10 currently cannot compute;
(2) re-run the genre test at n ≈ 400, where it has 90% power — genre comes back into the
score only if that study finds an effect, and then only as a new score version; (3)
child/teen speech adaptation for the voice model; (4) threshold
personalisation per family from the feedback tuner's posterior. Nothing on that list is
a new model — the gap is data, not architecture.

**Q: Does the chat model understand Hindi/Devanagari?**
Yes — BOTH scripts, as of the 2026-08-04 HASOC 2019 adoptions (4,665 labeled Hindi
posts; 80% trained in Devanagari AND a colloquial romanisation, 20% held out).
Before: zero Devanagari coverage, near-blind on romanised beyond the lexicon
(PR-AUC 0.61, recall 0.04). After (incl. the clean-Hindi Wikipedia counterweight
that drains a measured script-level toxicity prior — friendly Devanagari chat
read 0.78-0.88 before it), at the unchanged 0.95 threshold: Devanagari
P 0.968 / R 0.425 (PR-AUC 0.890), romanised P 0.958 / R 0.366 (PR-AUC 0.884) —
>=0.95 precision on every capturable register. CONDA held in-CI through all
three adoptions. Capture paths: our QWERTY keyboard carries romanised Hinglish
(incl. canvas games); Devanagari arrives via system keyboards through the
accessibility path; spoken Hindi is still gated by the English STT.
Second-order finding: the lexicon's alert-recall contribution shrank from +5pp
to <1pp — the trained model now knows what the hand lexicon knew.
`ml/eval_chat_hindi.py` reproduces both views.

**Q: Your speech recogniser is one Indian-English model. Is it fair across India's
accents? Could a mis-transcription falsely accuse a child?**
Measured, not assumed — paper §6.4, `ml/eval_asr_fairness.py`, on Svarah (AI4Bharat,
6,656 clips / 9.6 h / 117 speakers across 65 districts, CC BY 4.0). Every clip was
transcribed with the **deployed** Vosk model and every hypothesis pushed through the
**served** toxicity chain at the 0.95 threshold. Two findings, one good, one honest:
(1) **Zero false toxicity alerts in 9.6 hours of benign speech — in every accent
group** (rule-of-three bound ≤0.045% overall), despite a 38.6% WER giving the system
plenty of raw material to hallucinate profanity from. The precision-first threshold
does exactly what it was designed to do: the chain degrades toward *silence*, never
toward *accusation*. (2) But recognition quality is not accent-uniform: WER runs
34.6% for Dravidian-L1 speakers, 38.1% Indo-Aryan, **60.8% Tibeto-Burman** — the
Northeast (Bodo, Assamese, Nepali) occupies the entire worst tail at ~2× Tamil's
error rate, while gender is balanced (38.4% vs 38.7%). So the equity issue is a
*coverage* gap, not an accusation gap: toxic speech from a Northeast-accented child
is more likely to be *missed*. We say that in the paper, name Northeast-accent
adaptation as the highest-leverage STT improvement, and the audit is a two-command
re-run that gates any future recogniser swap. If asked "why is 38.6% WER acceptable
at all": it's the price of a 50 MB on-device model that keeps raw audio off the
network — a privacy trade stated in §7 — and the fusion treats voice as an optional
witness, never the sole evidence.

**Q: Did you measure battery drain / on-device latency?**
Yes — and the measurement changed a product decision, which is the best kind. SERVER
latency: concurrency smoke p50 66 ms / p95 684 ms at 24 threads (August run) and p50 64 ms /
p95 607 ms on the 23 Nov score-v2 re-run, zero server errors both times; live, ~210 ms per
warm request from Bengaluru and ~40 s on a free-tier cold start; server memory hardened
after a real 512 MB OOM under live voice load. DEVICE functional
latencies: session auto-start ~10 s, auto-end ~25 s, nudge ~12 s, tamper detection
~10–15 min, ChildApp cold start 569 ms (warm ~230 ms). ON-DEVICE RESOURCE COST:
measured 2026-08-18 on a Galaxy M52 5G, two 15-minute Roblox sessions with the
recorder active, per-minute sampling (`TESTING.md` has the full table):

| | English STT (default) | Dual Hindi+English (toggle) |
|---|---|---|
| CPU, averaged | **14 %** of one core | **51–72 %** (~4–5×) |
| RAM (PSS), mean / peak | **288 / 301 MB** | **399 / 419 MB** |
| Thermal throttling | none | none |
| Data / 15-min session | 7.2 MB up | same path |
| *Roblox itself, for scale* | *215 %* | *229 %* |

So the deployed default costs about **1/15th of the game it monitors**. The dual-STT
toggle **failed our own acceptance gate** (RAM > 400 MB peak, CPU far beyond 2×) — which
is exactly why it ships default OFF with "uses more battery" on the toggle, and we can
now say that with a number instead of a caveat. Two honest footnotes: (1) `batterystats`
mAh attribution reads zero on a USB-tethered phone, so we report the CPU-time proxy that
Android's own drain model is derived from; (2) the drill also caught a memory sawtooth
in the voice process — Vosk's streaming recogniser holds an utterance lattice in native
memory until a pause, so quiet play grows it (~30 MB swing) — bounded and released, not a
leak. We tried the textbook fix (`Recognizer.reset()` per segment), re-measured, and **it
did not flatten the curve** — so we did not ship it and say the cause is still open rather
than pretend a two-line patch closed it. It stays under the gate in the default mode and
resets with every session. A measurement that only confirmed what we hoped would be less
convincing than one that failed a feature, found a bug, and then falsified our first
explanation of the bug.

**Q: Has anyone independently audited the app's security?**
An automated independent static audit (MobSF v4.5.1, 2026-08-04) of both signed release
APKs: no exploitable high-severity issue; the single flagged item is the standard
dev-loopback cleartext exception (hardening item: scope it to debug builds). Full
finding-by-finding triage in docs/SECURITY_AUDIT_MOBSF.md. A human pentest remains
future work and is stated as such in §7 of the paper.

**Q (owner: Kanak): Have you re-run the security scans since August?**
Bandit, yes, on 24 Nov 2026. Diffed against the August audit commit, it found 14 findings
in code added since: four high-severity flags for SHA-1 used only to build cache keys in
the new tuning scripts — fixed (`usedforsecurity=False`, same digests) — and ten verified
false positives (an SQL string built from a placeholder and a constant, the project's own
model files loaded with pickle, fixed download addresses in developer scripts). Result:
53 findings, all verified false positives, none high. Triage in docs/API_FUZZ_REPORT.md.
