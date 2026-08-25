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

---

## 1. Problem framing

**Q: Is this a diagnostic tool for gaming addiction?**
No, and we never claim it is. It is a *screening and awareness* system: it surfaces
behavioural signals to a parent who then decides what to do. The model card served at
`/api/model_card` and the paper both state this. IGD diagnosis requires a clinician;
our contribution is the sensing + fusion pipeline, honestly evaluated.

**Q: Why three channels (behaviour, chat, voice) instead of one good model?**
Because they fail independently. Behaviour needs days of telemetry; chat only exists
when the child types; voice only when they speak. The fusion (§6 below) treats each as
an optional witness — any subset degrades gracefully to the channels present. The
ablation tables show each channel's marginal value is measurable, not decorative.

---

## 2. Behaviour model

**Q: Why Random Forest and not a neural network / gradient boosting?**
We ran the bake-off (`ml/retrain_models.py` trains and compares candidates) rather
than assuming. On 10 tabular features with 23,000 training rows, RF (200 trees, depth 6)
reached 0.916 test accuracy / 0.918 macro-F1 with 5-fold CV of 0.921 ± 0.002. Deep
models buy nothing on small tabular data, cost more to serve on a 512 MB instance, and
lose the SHAP-friendly structure we use for parent-facing explanations.

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
survey (n=104 usable) shows the *served score* tracking the clinical instrument at ρ = 0.317,
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
union → LogReg → isotonic) reaches PR-AUC 0.825 [0.807, 0.841] on CONDA in-game chat. Measured against a real transformer (2026-08-04): off-the-shelf Jigsaw toxic-BERT (detoxify, ~110M params) reads PR-AUC 0.709 on the same split — 12 points BELOW the domain-trained classical pipeline; at >=0.95 precision its recall is 0.12; the deployed pipeline reads 0.29 at an even higher 0.97 precision. Domain data beats model capacity, measured.
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
per-message recall 0.87 at its 0.6 bar). The threshold is env-tunable
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
covers; the ML generalises beyond any list. Ablation: removing fusion drops
recall-at-alert from 0.491 to 0.434 and MCC from 0.633 to 0.591 at essentially the
same precision. For an Indian deployment context, the lexicon is load-bearing, not
decorative.

**Q: What was the single biggest chat improvement?**
Domain data. Removing CONDA (in-game chat) from training collapses PR-AUC from 0.834
to 0.513 — worse than every architecture choice combined. The original general-corpus,
word-only model scored 0.557. Lesson we state in the paper: data > architecture.

---

## 4. Voice model

**Q: Does the voice channel transcribe speech or classify emotion?**
Both, as two separate paths. (1) On-device Vosk (Indian-English `en-in` model)
transcribes speech locally; transcripts enter the *chat* pipeline tagged
`voice_stt`, so spoken abuse is caught by the same toxicity model. (2) 15-second
audio segments are uploaded, the server extracts 36 acoustic features
(`backend/audio_features.py`), and HistGradientBoosting classifies emotion
(angry/excited/frustrated/neutral). Raw audio is deleted after feature extraction
(`app.py`, voice upload route) — only features and the label are retained.

**Q: 57.4% accuracy is barely better than random. Why present it?**
Because it's the *honest* number and we know exactly why it's not higher. Chance on
4 classes is 25%, so 0.574 / macro-F1 0.568 is meaningfully above chance but far from
production-grade — and we say so. The instructive part: with naive random splits the
same model scores ~0.657. That ~9-point gap is **speaker leakage** — the model
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
URDU beats English-only, 0.562 vs 0.546) and using the full 36-feature set (vs the
17-feature prefix: 0.562 vs 0.499). Augmentation was tested and found ~neutral
(0.566 without vs 0.562 with) — we report that negative result rather than hiding it.

**Q: Why is the voice weight lowest in the fusion?**
Because it's the weakest measured channel — the 40/30/30 behaviour/chat/voice prior
reflects measured reliability, and a missing channel contributes nothing rather than
a fake neutral score.

---

## 5. Fusion and alerting

**Q: How do you combine three channels?**
Weighted fusion with a 40/30/30 prior (behaviour dominates: it's the best-measured
channel and always present after a few sessions). Channels that produced no data this
session are renormalised out instead of being imputed. Session chat risk is the *max*
of per-message calibrated confidences, not an average — one credible threat matters
more than a hundred clean messages diluting it.

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
we split eval into a separate `--eval-csv` and note it as a fixed pitfall.

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
scoring and live predictions) passes with **zero 5xx errors** — p50 80 ms, p95 609 ms,
175 req/s on the dev machine (re-run 2026-07-30 with the current heavier chat
vectorizer). The script is permanent and re-runnable; the same check against the
deployed Render instance is the remaining step after each deploy. The DB layer is
dual-dialect (SQLite/Postgres) so outgrowing SQLite is a config change, not a rewrite.

**Q: How is the API secured?**
Signed HMAC bearer tokens (itsdangerous), role-separated: parent-only routes call
`deny_non_parent()`, per-user access calls `guard(user_id)`. `AUTH_ENFORCE` supports
a shadow mode (log violations without breaking clients) → enforce rollout. Rate
limiting via Flask-Limiter; tokens of deleted accounts are rejected by an existence
check. 180 backend tests — run in CI against both SQLite and Postgres 16, the
production dialect — cover the authz matrix, including regression tests for the
alert-ownership gap we found and fixed; 110 Android JVM unit tests guard the
offline-session/capture-health logic, profile validation, risk presentation,
offline queue, WAV, keystroke reconstruction, and alert-triage logic.

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
`derive_psychometrics`, same fitted scaler, same calibrated forest, same risk formula
— so what we correlate is the score a parent would actually have seen. Result:
**Spearman ρ = 0.317, 95% CI [0.137, 0.478]**. The interval excludes zero.

**Q: 0.35 is a weak correlation. Why should that impress us?**
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
Composites: pattern ρ = 0.330 [0.154, 0.489], volume ρ = 0.128 [−0.083, 0.328] (CI
includes zero). Two volume features are inert: `daily_play_time_hours` (+0.066) and
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

**Q: Your genre multiplier failed the test. Why is it still in the product?**
Kruskal-Wallis across seven genres: H = 4.59, **p = 0.598** — and the group ordering
no longer even matches the multiplier's assumption. We report it as a null
because a validation study that can only confirm isn't one. But the honest reading is
*underpowered, not disproven* — resampling gives the test 32% power at this n, 90%
only near n ≈ 400. Removing the multiplier flips 34.4% of served session bands (paper
§6.5 sensitivity analysis), so we're not making a change that large on a null this
weak. It stays flagged as the ensemble's least-evidenced component, first in line for
the larger cohort, and its magnitude is an environment variable — so a future result
retires it without a code change.

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
deployed 0.33/0.67. We declined. T2 sits at 0.95 precisely *because* the sample has
almost no disordered-range respondents — the fitted value encodes the sample's missing
tail, not a clinical boundary (the pre-batch fit read T2 = 0.95 — one late batch of
22 moved it by 0.12, which is the demonstration) — and κ = 0.177 is fair agreement
at best. The tuner is
env-var wired and reversible in one deploy; it stays unused until a cohort with a real
severity tail earns it. Same discipline as the parent-feedback threshold tuner: the
mechanism ships, the change waits for evidence.

**Q: Both sides of your correlation are self-report from the same person. Isn't this just common-method variance? And doesn't it validate a formula on survey answers, not your sensing pipeline?**
Both halves are fair and we say so in the paper (§6.6 (iii), IEEE §IV.B). Precisely: the study validates the served risk *formula* applied to self-reported pattern answers mapped to band midpoints — the exact serving path, but with recalled bands as inputs rather than measured telemetry. So it is not yet an end-to-end validation of passive sensing; the telemetry-linked per-child cohort is. On CMV: yes, part of a self-report-vs-self-report association can be method inflation (Podsakoff et al. 2003). Three things bound it without eliminating it — and these are the answer, so have them cold: (1) the **hours baseline is self-reported on the same form**, so it shares any method inflation, and the model still leads it in 97.4% of paired
resamples (Δρ = +0.167, CI grazing zero) — a *within-method* contrast; (2) **pattern features beat volume features on the same form** — a *between-feature* contrast that shared method cannot manufacture, and exactly the design premise; (3) the predictor items are behavioural *frequencies*, not attitudes, which typically attenuates method effects rather than inflating them. And on "0.32 is modest": ~10% shared variance, wide CI at n = 103 — but 0.3–0.5 is the normal range for brief behavioural screeners against full instruments (e.g. PHQ-2 vs PHQ-9), so "modest" is "expected", and we claim construct carriage, not clinical accuracy. Never say "it's fine"; say "it's bounded, here's how, and here's the study that closes it."

**Q: These are adults. Your product monitors children.**
Correct, and it's the study's biggest external-validity gap — we state it in the paper
before anyone asks. Three specific consequences: prevalence and thresholds don't
transfer; the respondents *self-reported* their patterns in bands where the app
*measures* them (both coarsening and recall error attenuate the correlation); and the
design is cross-sectional, so it says nothing about trajectory. What it does establish
transfers regardless of age: the pipeline's output tracks a validated instrument, and
pattern features carry signal volume features don't. The per-child cohort — guardian
IGDS9-SF scores linked to telemetry — is stage two, and it needs ethics approval.

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
proxy costs where we could (speaker leakage: 9 points; missing domain data: 32 PR-AUC
points), and `docs/VALIDATION_PLAN.md` is the scripted path onward. The contribution is
not a solved clinical instrument — it's a fully-built, honestly-measured screening
pipeline where every claim traces to a runnable script, including the two claims the
validation study **refused** to support.

**Q: What would you do with three more months?**
In order: (1) a consented pilot with 10–20 families to replace synthetic behaviour
labels with real ones and, critically, to reach a cohort with a genuine severity tail —
that single change unlocks the caseness metrics §10 currently cannot compute;
(2) re-run the genre test at n ≈ 400 where it has 90% power, and act on the answer
either way; (3) child/teen speech adaptation for the voice model; (4) threshold
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
latency: concurrency smoke p50 66 ms / p95 684 ms at 24 threads, zero server errors;
server memory hardened after a real 512 MB OOM under live voice load. DEVICE functional
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
