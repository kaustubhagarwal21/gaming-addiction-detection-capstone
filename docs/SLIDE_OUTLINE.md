# Defense Slide Outline — PW26_SJ_05

Paste-ready content for the PES capstone template. Each slide: the **on-slide
bullets** (keep them this short — the notes carry the words), any **figure/table**
to place, and **speaker notes** (~60 s each; 14 slides ≈ 15 min). Every number is
from `backend/models/model_metadata.json` or `docs/ablation_results.json`; the
matching Q&A prep is `docs/DEFENSE_NOTES.md` (section refs given per slide).

Figures live in `docs/figures/` (pr_chat.pdf, cm_behaviour.pdf, cm_voice.pdf —
export to PNG for PowerPoint via any PDF viewer, or re-run `ml/make_figures.py`).

---

## Slide 1 — Title
**On slide:**
- AI-Driven Gaming Addiction Screening for Children
- Multi-modal: behaviour + chat + voice
- PW26_SJ_05 · <team member names + SRNs> · Guide: <guide name>

**Notes:** One sentence: "We built and deployed a complete parent-facing screening
system — two Android apps and a cloud ML backend — and evaluated it the way ML
should be evaluated: real data where it exists, honest numbers where it doesn't."

---

## Slide 2 — Problem & Scope
**On slide:**
- IGD: WHO-recognised (ICD-11); parents notice late, from the outside
- Existing tools: self-report questionnaires OR blunt screen-time blockers
- Ours: passive multi-signal **screening** for parents
- NOT a diagnostic instrument — a "talk to your child / seek help" signal

**Notes:** Set the scope before an examiner sets it for you: screening, not
diagnosis — diagnosis needs a clinician. The gap we fill: questionnaires need the
child's honest cooperation; screen-time counters can't tell 3 hours of healthy play
from 3 hours of compulsive play. Behaviour patterns, in-game communication, and
voice stress together can. (DEFENSE_NOTES §1)

---

## Slide 3 — System Overview
**On slide:** *(one architecture diagram, minimal text)*
- ChildApp (passive capture) → Flask backend on cloud → ParentApp (dashboard + alerts)
- 3 ML models + fusion served in real time
- SQLite dev / Postgres (Neon) production, API on Render

**Notes:** Walk the diagram left to right: ChildApp captures session telemetry,
game-chat notifications, and gated mic segments; the backend scores each channel
and fuses them; ParentApp polls for dashboards and receives alerts. Mention it is
LIVE — deployed, not localhost — and sideload-distributed by design, since a
notification-listener app is legitimately a family-consent install, not a Play
Store product. (DEFENSE_NOTES §8)

---

## Slide 4 — Why Three Channels
**On slide:**
- Channels fail independently: behaviour needs days; chat/voice only when present
- Fusion prior 40/30/30 (behaviour/chat/voice), renormalised over present channels
- Weights follow measured reliability — voice lowest for a reason

**Notes:** A missing channel contributes nothing rather than a fake neutral score —
the earlier version imputed missing modalities and diluted real signal. Behaviour
dominates because it is always eventually present and best-measured. Say now: "the
voice weight is lowest because we measured it as the weakest channel — slide 7
shows that number honestly." (DEFENSE_NOTES §1, §5)

---

## Slide 5 — Behaviour Model
**On slide:**
- Random Forest (200×depth-6) on **10 objective features**
- 91.6% test acc · macro-F1 0.918 · 5-fold CV 0.921 ± 0.002
- Isotonic calibration: Brier 0.134 → 0.128
- Labels synthetic — grounded on real psychometrics (n = 11,191 + 13,464)

**Figure:** cm_behaviour.pdf (confusion matrix)

**Notes:** Two attack points, answer both proactively. (1) Why RF, not deep
learning: bake-off on tabular data — RF wins on accuracy-per-cost and gives
SHAP-friendly explanations parents see. (2) Synthetic labels: no public dataset
pairs device telemetry with addiction labels — we audited candidates (slide 10).
Grounding: IGDS9-SF Latin-America (11,191 real MOBA players) fixes severity base
rates; Gamers & Anxiety survey (13,464) grounds behaviour–severity relations. The
20→10 feature cut: the 10 derived proxies are functions of the first 10; keeping
them makes SHAP circular. Ablation: 0.9191 vs 0.9160, CIs overlap — free honesty.
(DEFENSE_NOTES §2)

---

## Slide 6 — Chat Model
**On slide:**
- TF-IDF (word 1–2g + char_wb 3–5g) → LogReg → isotonic; noisy-OR keyword fusion
- In-domain (CONDA game chat): **PR-AUC 0.834** [0.817, 0.849]
- At alert threshold 0.90: precision **0.950**, recall 0.491
- Hinglish + Devanagari lexicon (bsdk, चूतिया…) — load-bearing for India

**Figure:** pr_chat.pdf (PR curve)

**Notes:** The threshold story is the strongest 60 s of the talk: at the realistic
~3.5% toxic base rate, threshold 0.5 gives precision 0.205 — a parent gets ~4
false alarms per real one and stops reading alerts. At 0.90, precision is 0.950 at
recall 0.491: we consciously miss half of toxic messages to keep alerts credible.
Threshold is env-tunable and a Beta-posterior tuner adjusts it from parent
feedback. Why no BERT: 512 MB serving budget, real-time per-message scoring, and
the data ablation (slide 9) shows domain data mattered far more than architecture.
(DEFENSE_NOTES §3, §5)

---

## Slide 7 — Voice Channel (two paths)
**On slide:**
- Path 1: **on-device** Vosk STT (Indian English) → transcript → chat toxicity model
- Path 2: 36 acoustic features → HistGB emotion (real corpora: RAVDESS, CREMA-D, EMO-DB, URDU)
- Speaker-independent accuracy **0.574** (chance = 0.25)
- Random splits said 0.657 → **9 pts was speaker leakage** — we report the honest number

**Figure:** cm_voice.pdf (confusion matrix)

**Notes:** Pre-empt "57% is weak": chance on 4 classes is 25%; the interesting part
is the 9-point gap — with random splits the model memorised *voices*, not emotions,
and the split choice even flipped which model won the bake-off (SVM → HistGB). An
honest 0.574 beats an inflated 0.657 in front of any examiner. Also: transcription
happens on-device; its text and a short WAV segment are sent via HTTPS, and the raw
audio is deleted server-side after feature extraction.
Known gap, stated on slide 13: acted adult emotion ≠ child gaming speech.
(DEFENSE_NOTES §4)

---

## Slide 8 — Fusion & Alerting
**On slide:**
- Weighted fusion 40/30/30 over channels **present** this session
- Session chat risk = **max** of per-message calibrated scores, not the mean
- Alert at 0.90 — deliberately above best-F1 (0.85): false alarms cost trust
- Parent feedback loop tunes thresholds (Beta posterior)

**Notes:** Max-not-mean: one credible threat matters more than a hundred clean
messages diluting it. Sitting above best-F1 is a *choice*, not an accident — the
asymmetric cost is parents ignoring alerts. Show you know both operating points:
0.85 → P 0.888/R 0.660; 0.90 → P 0.950/R 0.491. (DEFENSE_NOTES §5)

---

## Slide 9 — Evaluation Methodology (the ML-rigour slide)
**On slide:**
- Held-out only, seeds recorded; voice = speaker-independent; chat = in-domain
- Ablations: one component removed per row, bootstrap 95% CIs (1,000 resamples)
- MCC + PR-AUC alongside F1 (base rates are extreme)
- Biggest finding: remove CONDA domain data → PR-AUC 0.834 → **0.513**

**Table:** 3-row mini-ablation (full 0.834 / − char_wb 0.811 / − CONDA 0.513) —
full tables in `docs/ablation_results.json` and the paper.

**Notes:** This slide is what separates the project from "we trained a model."
Every design choice has a measured counterfactual. The headline lesson: data >
architecture — losing domain data costs 32 PR-AUC points, more than every
architecture choice combined. Also mention the reported *negative* result: voice
augmentation was measured and found neutral — we say so instead of hiding it.
(DEFENSE_NOTES §6)

---

## Slide 10 — Dataset Audit
**On slide:**
- Adopted: Gamers & Anxiety (13,464) · IGDS9-SF LatAm (11,191) · CONDA · Davidson · RAVDESS + CREMA-D + EMO-DB + URDU (9,817 original clips; 12,864 augmented feature rows)
- Rejected **with evidence**: Kaggle "Predict Online Gaming Behavior" (synthetic, engagement ≠ addiction), "Mobile App Usage" (3/10 features, credential-walled)
- Full audit table in paper §4.2

**Notes:** We downloaded and inspected the rejected sets rather than dismissing
them from their descriptions — provenance analysis showed one is synthetically
generated with engagement labels, not addiction labels. Examiners like rejected-
with-reasons more than adopted-without-reasons. (DEFENSE_NOTES §7)

---

## Slide 11 — Engineering Quality
**On slide:**
- **258 automated tests in CI**: 169 backend (run on BOTH SQLite & Postgres 16) + 89 Android JVM
- Load-verified: 288 concurrent requests, **0 errors**, p50 80 ms
- Weekly drift monitor vs production DB (PSI/KS) — live, verified against Neon
- Signed-token auth, rate limiting, authz regression tests

**Notes:** Two stories if asked: (1) the Postgres CI job caught a real dialect bug
in the drift script the day it was added — exactly the "works locally, fails in
prod" class it exists for; (2) the concurrency smoke is a permanent script, re-run
after any serving-cost change. (DEFENSE_NOTES §8)

---

## Slide 12 — Privacy & Ethics
**On slide:**
- Explicit onboarding consent; revoking capture alerts the parent (no silent failure)
- STT on-device; raw audio deleted after feature extraction; VAD gates the mic
- `/api/user/export` = everything held (credentials excluded); deletion scope **identical** to export
- Parental monitoring of a minor, by design — not covert surveillance

**Notes:** Lead with the strongest fact: what a parent can see is exactly what gets
erased — export and deletion cover the same 15 tables. If pressed on the mic:
layered mitigations in order — consent, on-device transcription, server-side raw
audio deletion, speech-gated capture. (DEFENSE_NOTES §9)

---

## Slide 13 — Limitations & Validation Path
**On slide:**
- Weakest part, stated plainly: **validation**
- Behaviour labels synthetic (grounded); voice trained on acted adult emotion
- Where we could, we *quantified* the gap: leakage 9 pts; missing domain data 32 PR-AUC pts
- `docs/VALIDATION_PLAN.md`: scripted path — pilot → real labels → re-train → re-evaluate

**Notes:** Say it before they do: "the contribution is not a solved clinical
instrument — it is a fully built, honestly measured screening pipeline where every
claim traces to a runnable script." If the pilot has started by defense day, put
its first real numbers HERE. (DEFENSE_NOTES §10)

---

## Slide 14 — Conclusion + Demo
**On slide:**
- Deployed end-to-end system · 3 real-data-grounded models · every choice ablated
- Reproducible: every number on these slides = one script in the repo
- Future: consented family pilot → child-speech adaptation → per-family thresholds
- **Live demo** (backup video ready)

**Notes:** Close on the differentiator: reproducibility and honesty as features.
Then demo per `DEMO_RUNBOOK.md`; if Wi-Fi/devices misbehave, switch to the video
without apologising. Future work is deliberately data-first, not model-first —
"the gap is data, not architecture."

---

## Timing & Q&A prep
- 14 slides ≈ 15 min (slides 5–9 are the core — protect their time).
- If forced to cut: merge 3+4, and 11+12.
- Q&A: `docs/DEFENSE_NOTES.md` — read it the night before; it maps 1:1 to these slides.
