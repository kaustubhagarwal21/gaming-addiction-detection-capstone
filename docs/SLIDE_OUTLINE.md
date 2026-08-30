# Defense Slide Outline — PW26_SAS-03

Paste-ready content for the PES capstone template. Each slide: the **on-slide
bullets** (keep them this short — the notes carry the words), any **figure/table**
to place, and **speaker notes** (~60 s each; 17 slides ≈ 16 min). Every number is
from `backend/models/model_metadata.json`, `docs/ablation_results.json`, or
`docs/survey_extras.json`; the matching Q&A prep is `docs/DEFENSE_NOTES.md`
(section refs given per slide).

Figures live in `docs/figures/` (pr_chat.pdf, cm_behaviour.pdf, cm_voice.pdf —
export to PNG for PowerPoint via any PDF viewer, or re-run `ml/make_figures.py`).

---

## Slide 1 — Title
**On slide:**
- AI-Driven Gaming Addiction Screening for Children
- Multi-modal: behaviour + chat + voice
- PW26_SAS-03 · <team member names + SRNs> · Guide: Prof. Shridevi Sawant

**Notes:** One sentence, identical from all four of us: "a deployed, multimodal screening system for parents that measures how a child plays, not just how long — externally validated against a clinical instrument, with its limitations named before you ask."

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
- In-domain (CONDA game chat): **PR-AUC 0.825** [0.807, 0.841]; off-the-shelf toxic-BERT reads only 0.709 on the same split — domain data beats model capacity
- At alert threshold 0.95: precision **0.956**, recall 0.428 — >=0.95 precision on EVERY register at one threshold
- **NEW: dual-script Hindi path** (HASOC 2019 + clean-wiki counterweight, Devanagari + romanised): held-out precision **0.968 / 0.958** per script — was (near) zero before adoption
- Hinglish + Devanagari lexicon (bsdk, चूतिया…) — load-bearing for India

**Figure:** pr_chat.pdf (PR curve)

**Notes:** The threshold story is the strongest 60 s of the talk: at the realistic
~3.5% toxic base rate, threshold 0.5 gives precision 0.235 — a parent gets ~3
false alarms per real one and stops reading alerts. At the deployed 0.95, precision is 0.956 at
recall 0.428: we consciously trade recall to keep alerts credible (the session-level
streak alert recovers coverage; per-message recall 0.82 at its 0.6 bar).
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
- Random splits said 0.657 → **8.3 pts was speaker leakage** — we report the honest number
- Headroom measured: frozen w2v2 embeddings + same classifier → **0.776** (vs 0.553 on the same split) — quantifies the ceiling a deployable distillation (Wav2Small, 72K) could reach

**Figure:** cm_voice.pdf (confusion matrix)

**Notes:** Pre-empt "57% is weak": chance on 4 classes is 25%; the interesting part
is the 8.3-point gap — with random splits the model memorised *voices*, not emotions,
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
- Alert at 0.95 — deliberately above best-F1 (0.85): false alarms cost trust
- Parent feedback loop tunes thresholds (Beta posterior)

**Notes:** Max-not-mean: one credible threat matters more than a hundred clean
messages diluting it. Sitting above best-F1 is a *choice*, not an accident — the
asymmetric cost is parents ignoring alerts. Show you know both operating points:
0.85 → P 0.800/R 0.703; 0.90 → P 0.888/R 0.623. (DEFENSE_NOTES §5)

---

## Slide 8b — Built for India (the differentiator)
**On slide:**
- Indian kids' game chat is **code-mixed**: English + romanised Hindi + Devanagari
- Typed abuse in **all three registers** detected at **≥0.95 precision** (held-out)
- Native **Devanagari keyboard** so Hindi is captured even in canvas games (Roblox)
- **Accent-fairness audited** (Svarah, 6,656 clips / 117 speakers): **0 false alerts**
  in 9.6 h of benign speech across every accent group; WER gap named honestly
  (Dravidian 35% → Tibeto-Burman 61%, a coverage gap, not an accusation gap)
- Honest capture matrix shown to parents — including the blind spots

**Figure:** *(optional)* screenshot of the ParentApp "hi" language badge + a flagged
Devanagari line, from the seeded demo (`तू चूतिया है` at 0.96).

**Notes:** This is what makes it *ours*, not a re-skin of a US parental-control
app. English-only toxicity models miss most Indian gaming abuse. We measured the
gap and closed it: a script-prior bug (a Devanagari corpus with a 53% offensive
rate taught the model that *Devanagari itself* looked toxic) surfaced from our own
smoke test, and a clean-Hindi Wikipedia counterweight fixed it — clean Hindi now
scores low, abuse scores high, in both scripts. The keyboard matters because a
third-party Hindi keyboard inside a canvas game is invisible to capture; ours
isn't. And we tell parents exactly what we can and can't see — a monitoring app
that hides its blind spots is worse than none. (DEFENSE_NOTES: Hindi Q&A)

---

## Slide 9 — Evaluation Methodology (the ML-rigour slide)
**On slide:**
- Held-out only, seeds recorded; voice = speaker-independent; chat = in-domain
- Ablations: one component removed per row, bootstrap 95% CIs (1,000 resamples)
- MCC + PR-AUC alongside F1 (base rates are extreme)
- Biggest finding: remove CONDA domain data → PR-AUC 0.825 → **0.511**
- Direct calibration proof: ECE 0.062 → **0.015** (behaviour), 0.031 → 0.012 (chat) — not just Brier

**Table:** 3-row mini-ablation (full 0.825 / − char_wb 0.794 / − CONDA 0.511) —
full 8-row table in `docs/ablation_results.json` and the paper; reliability.pdf
for the ECE claim.

**Notes:** This slide is what separates the project from "we trained a model."
Every design choice has a measured counterfactual. The headline lesson: data >
architecture — losing domain data costs 31 PR-AUC points, more than every
architecture choice combined — and three transformer benchmarks (Detoxify on
chat, w2v2 on voice, MuRIL on Hindi) confirm it: capacity helps in-distribution,
domain and register fit decide. Also mention the reported *negative* result: voice
augmentation was measured and found neutral — we say so instead of hiding it.
(DEFENSE_NOTES §6)

---

## Slide 9b — External Validation: does the score actually mean anything?
**On slide:**
- Anonymous adult IGDS9-SF survey — **134 raw → 104 usable**, scored through the *deployed* pipeline
- **ρ = 0.317** [0.137, 0.478] vs the clinical instrument — CI excludes zero
- **Leads the screen-time baseline it replaces**: hours ρ = 0.147 (CI spans zero); paired **Δρ = +0.167** [−0.002, +0.341], ahead in 97.4 % of resamples — the CI grazes zero, so the partial carries the claim
- Not a screen-time proxy: partial ρ = **0.303** [0.110, 0.476] with hours removed
- Signal is in **pattern** features (0.330) not **volume** (0.128) — formal paired contrast **+0.199 [+0.019, +0.380]**, excludes zero
- Two results *against* us: genre multiplier **p = 0.598**; 4 of 5 proxy names track nothing

**Table:** the 4-row summary (construct validity / hours baseline / paired delta /
partial) — pull from `docs/survey_extras.json`. If you have room for a second visual,
the per-feature ρ table from paper §6.6 Table 4 is the strongest single image here:
all five pattern features above all five volume features, no interleaving.

**Notes:** This is the slide the whole project builds toward, so protect its time.
Every other number in the deck is measured *inside* our own training distribution;
this one is measured outside it, against an instrument we didn't design, on people
who never touched the app. Lead with the comparison, not the magnitude — 0.32 sounds
modest until you say the baseline every commercial parental-control tool ships reaches
0.147 with a confidence interval spanning zero, and that the score keeps its correlation
when hours is partialled out (0.303, CI excluding zero). Then pre-empt the two questions that always follow. *Why no
sensitivity/specificity?* One respondent scored in the disordered range; the script
refuses to print caseness metrics below ten positives, and that guard was written
before we saw the data. *Why did you keep the genre multiplier if it failed?* Because
the null is underpowered (32%), not decisive, and removing it flips 34% of served
bands — so it stays flagged and env-tunable rather than defended. Close on the two
negative results: volunteer them. A validation study that only confirms isn't one.
(DEFENSE_NOTES §10)

---

## Slide 10 — Dataset Audit
**On slide:**
- Adopted (eleven): Gamers & Anxiety (13,464) · IGDS9-SF LatAm (11,191) · CONDA · Davidson · **HASOC 2019 Hindi** · **clean-Hindi Wikipedia** · RAVDESS + CREMA-D + EMO-DB + URDU (9,817 clips)
- Rejected **with evidence**: Kaggle "Predict Online Gaming Behavior" (synthetic, engagement ≠ addiction), "Mobile App Usage" (3/10 features, credential-walled)
- **Reality-checked** one hand-set prior against real phone telemetry (StudentLife, CC-BY): heavy-band late-night sits above the 90th percentile of normal student use
- Full audit table in paper §4.2, every adoption by measured trial

**Notes:** We downloaded and inspected the rejected sets rather than dismissing
them from their descriptions — provenance analysis showed one is synthetically
generated with engagement labels, not addiction labels. Examiners like rejected-
with-reasons more than adopted-without-reasons. (DEFENSE_NOTES §7)

---

## Slide 11 — Engineering Quality
**On slide:**
- **291 automated tests + 7 research-integrity guards in CI**: 181 backend (run on BOTH SQLite & Postgres 16) + 110 Android JVM
- Load-verified: 288 concurrent requests, **0 errors**, p50 66 ms
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

## Slide 13 — Limitations & What's Still Open
**On slide:**
- Training labels still **synthetic** — the 91.6% is a synthetic-distribution number, and the survey does **not** upgrade it
- Validated: the score's **meaning** (§9b). Not validated: its **accuracy at the clinical cut-off**
- Blocker is named and quantified: 1 disordered-range respondent in 104 usable → need **~157 usable** at the 6.4% base rate
- Adults, self-reported, cross-sectional — the deployment target is adolescents, measured, over time
- Voice trained on acted adult emotion; gap quantified (leakage 8.3 pts; missing domain data 31 PR-AUC pts)
- One remaining tier: **per-child cohort** (guardian IGDS9-SF + telemetry) — needs ethics approval

**Notes:** The framing shifted this year and the slide should show it: the weakest
part *used* to be that nothing was externally validated; now it's that validation is
**partial in a specific, nameable way**. Draw the line explicitly — construct validity
is measured, caseness accuracy is not, and we will not blur them. That distinction is
the thing a sharp examiner is probing for, so say it first. Then: "the contribution is
not a solved clinical instrument — it is a fully built, honestly measured screening
pipeline where every claim traces to a runnable script, including the two claims our
own validation study refused to support." (DEFENSE_NOTES §10, §11)

---

## Slide 14 — Conclusion + Demo
**On slide:**
- Deployed end-to-end system · 3 real-data-grounded models · every choice ablated
- **Externally validated**: ρ = 0.317 vs IGDS9-SF, leading the screen-time baseline in 97 % of paired resamples
- Reproducible: every number on these slides = one script in the repo
- Future: per-child cohort (ethics-gated) → child-speech adaptation → per-family thresholds
- **Live demo** (backup video ready)

**Notes:** Close on the differentiator: reproducibility and honesty as features —
now with the strongest possible evidence for it, a validation study we ran on
ourselves that returned two results we did not want. Then demo per
`DEMO_RUNBOOK.md`; if Wi-Fi/devices misbehave, switch to the video without
apologising. Future work is deliberately data-first, not model-first — "the gap is
data, not architecture."

---

## Timing & Q&A prep
- 17 slides in the built deck ≈ 16 min (slides 5–9b are the core — protect their time; **9b is the
  single highest-value slide in the deck**, it is the only externally-anchored evidence).
- If forced to cut: merge 4+5, and 13 into 14 (built-deck numbering). Do **not** cut 9b (deck slide 12).
- Q&A: `docs/DEFENSE_NOTES.md` — read it the night before; it maps 1:1 to these slides.
