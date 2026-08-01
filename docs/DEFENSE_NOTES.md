# Defense Notes — Anticipated Examiner Questions

Pre-assembled answers for the capstone defense (PW26_SJ_05). Every number below is
reproducible from a script in this repo; the source is cited next to each claim.
The strategy throughout: **answer honestly, cite the measurement, name the limitation
before the examiner does.**

Primary evidence files:
- `backend/models/model_metadata.json` — all serving-model metrics (written by `ml/retrain_models.py`)
- `docs/ablation_results.json` — ablation tables with bootstrap 95% CIs (written by `ml/ablation_studies.py`)
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
(3) `docs/VALIDATION_PLAN.md` is the runnable path from synthetic to validated once
real pilot data exists. Synthetic-but-grounded, with the validation path scripted, is
the honest ceiling for a college project without IRB-approved child data.

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
union → LogReg → isotonic) reaches PR-AUC 0.834 [0.817, 0.849] on CONDA in-game chat.
A transformer needs GPU or slow CPU inference; we serve on a 512 MB free-tier instance
scoring every chat message in real time. The char_wb n-grams are the cheap trick that
buys robustness to gamer spelling ("noooob", "f4ggot") — removing them drops PR-AUC to
0.811 (ablation row "- char_wb n-grams").

**Q: The balanced-holdout F1 is 0.92 but realistic precision at 0.5 is 0.205. Which is real?**
Both — and the gap is the most important number in the chat section. At the realistic
~3.5% toxic base rate, a 0.5 threshold floods parents with false alarms (precision
0.205 — roughly four false alarms per real one). That is *why* the alert threshold is
0.90, where in-domain precision is 0.950 at recall 0.491
(`chat_metrics_gaming.at_alert_threshold`). We chose to miss half of toxic messages
rather than train parents to ignore alerts. The threshold is env-tunable
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

**Q: Why alert at 0.90 and not the F1-optimal threshold?**
The CONDA threshold sweep puts best-F1 at 0.85 (P 0.888 / R 0.660) and 0.90 at
P 0.950 / R 0.491. We deliberately sit above best-F1 because the asymmetric cost is
false alarms: a parent who gets three wrong alerts stops reading them. Both points are
in `model_metadata.json`; the threshold is an env var, and the feedback tuner moves it
with real parent responses.

---

## 6. Evaluation methodology

**Q: What makes your evaluation trustworthy?**
Four properties: (1) every serving model is evaluated on held-out data it never
trained on, with seeds recorded; (2) voice uses speaker-independent splits; chat's
headline number is *in-domain* (CONDA) not general-corpus; (3) all ablations carry
bootstrap 95% CIs over 1,000 resamples, so "better" claims are only made when
intervals separate; (4) we report MCC alongside F1 at the alert threshold because F1
ignores true negatives at extreme base rates. The protocol line at the bottom of
`docs/ablation_results.json` states the exact procedure.

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
check. 179 backend tests — run in CI against both SQLite and Postgres 16, the
production dialect — cover the authz matrix, including regression tests for the
alert-ownership gap we found and fixed; 87 Android JVM unit tests guard the
offline-session/capture-health logic, profile validation, risk presentation,
offline queue, WAV, keystroke reconstruction, and alert-triage logic.

**Q: Why sideloaded APKs instead of Play Store?**
The ChildApp needs a NotificationListener + accessibility-adjacent capture that Play
policy treats as high-risk surveillance; the legitimate deployment is a parent
knowingly installing on a family device. Sideload + cloud backend is the honest
distribution story for a capstone, and the paper says so.

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

---

## 10. The closing question

**Q: What's the weakest part of this project?**
Validation. The behaviour model's labels are synthetic (grounded, but synthetic); the
voice model trains on acted adult emotion; chat is the only channel with a real
in-domain evaluation. We know this, we quantified how much each proxy costs where we
could (speaker leakage: 9 points; missing domain data: 32 PR-AUC points), and
`docs/VALIDATION_PLAN.md` is the concrete, scripted path from here to validated. The
project's contribution is not a solved clinical instrument — it's a fully-built,
honestly-measured screening pipeline where every claim traces to a runnable script.

**Q: What would you do with three more months?**
In order: (1) a consented pilot with 10–20 families to replace synthetic behaviour
labels with real ones (the validation plan's Phase 1); (2) child/teen speech
adaptation for the voice model; (3) Postgres + managed hosting to retire the free-tier
constraints; (4) threshold personalisation per family from the feedback tuner's
posterior. Nothing on that list is a new model — the gap is data, not architecture.
