# Model Validation Plan — from synthetic to real-data credibility

> **STATUS (2026-07-05): the public-dataset tier of this plan has been EXECUTED** — and
> went further than planned (retraining, not just evaluation). What remains open is the
> human-study tier (IGDS9-SF survey), whose full recipe below is still current.
>
> Executed and now documented in the paper (§4.2, §6, ablations) — do not redo:
> - **Chat**: trained on general corpus + **CONDA** train split + **Davidson** offensive-
>   language tweets; evaluated on CONDA's held-out validation split. PR-AUC 0.834; alert
>   precision 0.950 at the re-derived threshold **0.90**. Scripts: `ml/eval_chat_conda.py`
>   (eval + retrain), `ml/ablation_studies.py`.
> - **Voice**: trained on **RAVDESS + CREMA-D + EMO-DB + URDU** (9,817 clips, 154 speakers,
>   3 languages) through the serving extractor; **speaker-independent** held-out accuracy
>   0.574 (the honest protocol — random splits inflated it by ~9 points). Script:
>   `ml/train_voice_real.py`. TESS was assessed and skipped (2 elderly speakers,
>   credential-walled mirrors).
> - **Label-side stepping stone**: the open **IGDS9-SF Latin-America dataset (n=11,191)**
>   grounds the severity base rate (6.4% ≥36) and validates the chat-channel premise
>   (toxic-speech involvement ↔ higher IGD severity, r=+0.156). Script: `ml/analyze_igds.py`.
> - **Behaviour distribution grounding**: play-time bands + peer percentiles from the
>   **Gamers & Anxiety** survey (n=13,464). Script: `ml/analyze_survey.py`.
>
> **What this document is now for:** the remaining piece — construct-validating the
> behaviour model against IGDS9-SF collected from *real users of this system* (or a
> survey population). That recipe follows, unchanged and still accurate.

---

## ⚡ FAST PATH — the one-week, zero-budget, solo-student version

Everything below this box is the full methodology; this is the minimal sequence that
actually gets the missing number (construct validity of the behaviour model) with
nothing but a Google Form, WhatsApp, and one script run. Total hands-on effort ≈ 3–4
hours spread over a week.

| Day | Action (time) |
|---|---|
| **Day 0** | Build the Google Form by pasting `SURVEY_IGDS9SF.md` verbatim — consent header, Q1–Q11 (incl. the six gaming-pattern questions + attention check), IGDS9-SF grid. Link it to a Sheet. (~45 min) |
| **Day 0** | One-line email to the project guide: "anonymous 18+ survey on gaming habits for the capstone, no personal data — flagging for your records." (~5 min) |
| **Day 0–1** | Blast the link: class/section groups, hostel groups, college gaming groups (BGMI/Valorant squads are the highest-yield audience), club Discords, plus 5 friends asked to forward to *their* groups. Personal follow-ups roughly double completion. (~30 min) |
| **Day 3–4** | One reminder ping in the same groups. Target **75–100 raw responses** so that after dropping non-gamers and attention-check failures you keep ≥50. (~10 min) |
| **Day 6–7** | Sheet → File → Download → CSV → save as `data/survey/responses.csv` → run `python ml/eval_behavior_survey.py`. It prints + writes JSON: local prevalence (with CI), hours↔severity check, **behaviour-model score ↔ IGDS9-SF correlation (the construct-validity headline)**, and data-driven RISK_T1/T2 suggestions. Paste the numbers into the paper/model card. (~30 min) |

**Deliberately skipped on the fast path** (state each as future work — naming them is a
strength, not a weakness): minors/parent-proxy sampling (needs guardian consent + ethics
clearance), the clinician-anchored tier, and telemetry-linked Mode A at scale. If 3–5
gamer friends will install the ChildApp on their own phones for a week (adults
self-monitoring, consenting via the app's own flow), that micro-Mode-A is the only way
to say anything about the *ensemble weights* — nice bonus, fine to skip.

**Guardrails that still apply even in fast mode:**
- **Correlation is the primary endpoint, not classification.** At the ~6% disordered
  base rate, 50–100 responses contain only ~3–6 disordered-range cases — ROC/AUC and
  sensitivity/specificity are statistically meaningless at that count. Report Spearman ρ
  with a bootstrap CI; the script refuses to print caseness metrics below 10 positives.
- **Blinding (only if any Mode-A linkage is done):** the IGDS9-SF must be completed
  *before* the respondent sees any app dashboard/risk output, or the label is
  contaminated by the prediction it is supposed to validate.
- **Keep label streams separate:** pilot families who submit in-app parent verdicts must
  not also anchor the survey validation of thresholds tuned on those verdicts — that
  re-introduces the leakage class the chat eval already had fixed once.
- Threshold fitting = band the IGDS totals (<21 / 21–31 / ≥32), grid-search RISK_T1/T2
  maximizing quadratic-weighted kappa, bootstrap the CI, deploy via env vars (same
  mechanism `tune_from_feedback.py` uses). The script does this automatically.

---

## The remaining principle

| Model | Real-data label source | Status |
|---|---|---|
| Chat toxicity | Public toxicity + gaming corpora | ✅ **done** (trained + held-out evaluated) |
| Voice emotion | Public speech-emotion corpora | ✅ **done** (4 corpora, speaker-independent) |
| Behaviour / addiction | **IGDS9-SF** collected from real users | ⏳ **open** — needs a small survey/study |

---

## Tier 2 — Validate the BEHAVIOUR model against a clinical instrument (the differentiator)

This is the headline ("AI-driven addiction screening"), and the only honest way to validate
it is a **construct-validity study**: real users produce behavioural data, and a recognised
screening instrument provides the **ground-truth label**.

### Step 1 — The gold-standard label: IGDS9-SF
**Internet Gaming Disorder Scale – Short-Form** (Pontes & Griffiths, 2015) — 9 items mapping
the 9 DSM-5 IGD criteria, free for academic use.
- Reference: Pontes, H. M., & Griffiths, M. D. (2015). *Measuring DSM-5 Internet Gaming
  Disorder: Development and validation of a short psychometric scale.* **Computers in Human
  Behavior, 45**, 137–143.
- Official scale + scoring: <https://www.halleypontes.com/igds9sf/>
- Alternative: **GAS-7** (Lemmens et al., 2009).

**Scoring:** each item 1 (Never) → 5 (Very often); total 9–45 (use as the continuous label).
For a binary label, the DSM-5-style cutoff is endorsing **≥5 of 9** items at "Very often (5)"
= *disordered gamer*.

### Step 2 — Two ways to get the features (choose, or do both)
- **Mode A — telemetry-linked (gold standard):** participant **uses the app** for ~1–2 weeks
  (real telemetry → your 20 features) **and** fills the IGDS9-SF; link the two with a join key
  (their `family_code`). Strongest, but high friction → small N.
- **Mode B — survey-only (high volume):** the form collects IGDS9-SF **plus self-reported
  behavioural items** (hours/day, late-night play, etc.). Weaker (self-report bias) but far
  higher completion → realistic via WhatsApp.

> **Recommended: Mode B for volume + a small Mode A subset.** Report both.

### Step 3 — Recruitment & ethics
- **Recruit adults (18+)**, not minors — the problematic-gaming construct still applies, and
  it avoids COPPA / minor-IRB complexity. State the population caveat in the paper.
- **Ethics:** check PES's policy. Anonymous low-risk surveys are often exempt, but confirm;
  if approval is quick, get it — having it is a credibility marker, not a hurdle. Always
  include a consent preamble (see Google Form section).
- **Target N:** ≥ 50 for a minimally credible correlation; **100+** is good.

### Step 4 — Analysis
- **Spearman / Pearson correlation** between the model's risk score and the IGDS9-SF total —
  the core construct-validity number.
- Binarise at the cutoff → **ROC-AUC, sensitivity, specificity** for "flags disordered gamers".
- **Calibration** on the real labels (a reliability curve; you already do isotonic calibration).

### Step 5 — Report honestly
Small N, confidence intervals, convenience-sampling + self-report limitations, population
caveat (adults). A moderate correlation (e.g. ρ ≈ 0.5–0.7) on N≈30–100, **honestly framed**,
is a real empirical validation — exactly what is missing today.

### Bonus — a real TRAINING set, not just validation
With 100+ responses you can **retrain/fine-tune** a behaviour model (cross-validated) on a
reduced *self-report* feature set and report honest held-out metrics. "Validated/retrained on
N real respondents labelled with a DSM-5-based instrument" is a far stronger narrative than
synthetic data — this is the actual ~9.5 move.

---

## The Google Form (practical recipe)

### Create it
1. Go to <https://forms.google.com> → blank form.
2. Settings ⚙ → **Responses** → "Collect email addresses": **Off** (keep it anonymous);
   "Limit to 1 response": optional (requires sign-in — trade-off vs anonymity).
3. Mark the consent checkbox and all IGDS9-SF items **Required**.
4. Link responses to a Sheet (Responses tab → green Sheets icon) for easy CSV export later.
5. **Send → 🔗 link → Shorten URL** → paste the link into this doc and the WhatsApp message.

> **Form link (paste here once created):** `__________________________`

### Form contents (sections)

**0. Consent (required checkbox)**
> *You're invited to a short (~5 min), anonymous survey for an academic capstone project on
> gaming habits at PES University. Participation is voluntary; you may stop anytime. No
> personally identifying information is collected. Data is used only for academic research
> and reported in aggregate. You must be **18 or older** to take part. Questions:
> [your email].*
> ☐ I am 18+ and consent to participate.

**1. Eligibility**
- Age (number, gate 18+). · "Do you play video games?" (Yes/No → end if No).

**2. Demographics (minimal)**
- Age band · platform (Mobile / PC / Console) · main game(s).

**3. Self-reported behavioural features** (map to the 20 features as far as self-report allows)
- Average hours gaming per **day**; days per **week**; **longest** single session (hrs).
- How often you play **past your intended bedtime** (Never→Very often).
- How often gaming **replaces** study/work/sleep.
- Late-night play frequency (after midnight). · Money spent per month (band).
- (Add 1–2 attention checks, e.g. "Select 'Often' for this item.")

**4. IGDS9-SF — the label** (1 = Never … 5 = Very often; *use the official wording*)
1. Preoccupation — you think about gaming a lot even when not playing.
2. Withdrawal — you feel restless/irritable/anxious when you can't play.
3. Tolerance — you need to spend increasing time gaming to feel satisfied.
4. Loss of control — you've tried and failed to cut down/stop.
5. Displacement — you've lost interest in other hobbies because of gaming.
6. Continuation — you keep gaming despite knowing it causes problems.
7. Deception — you've lied to others about how much you game.
8. Escapism — you game to escape or relieve a negative mood.
9. Conflict — you've risked/lost a relationship, job, or study opportunity due to gaming.

**5. Optional app-linkage (Mode A)**
- "If you installed the screening app, enter your **family code**: ____" (the join key).

**6. Debrief / thank you**
- Brief restatement of purpose + contact email.

### Distribution (WhatsApp)
- Short message: the *why* + "~5 min, anonymous, **18+**" + the link. Example:
  > *Help with my PES capstone? A 5-min anonymous survey on gaming habits (18+ only). No
  > personal info collected. 🙏 [link]*
- Ask group admins to **pin** it; personal follow-ups roughly double completion.
- Expect noise — that's why required fields + attention checks matter.

### After collection
- Responses tab → export to **CSV**.
- Score IGDS9-SF (sum the 9 items), build the self-report feature vector, run the model, and
  compute the Tier-2 metrics above — all done in one pass by `ml/eval_behavior_survey.py`
  (delivered; see the FAST PATH box).

---

## Limitations to state explicitly (naming them is a strength)
- **Convenience sampling** (WhatsApp social circle) — non-representative.
- **Self-report bias** (Mode B) — recall + social-desirability effects.
- **Small N** — report confidence intervals; treat as construct validation, not a clinical trial.
- **Adult population** — validates the construct; generalisation to minors is future work.

---

## How this maps to the codebase
- Honest-metrics + model-card infrastructure already exists (`/api/model_card`); the executed
  tier's numbers already flow through it (`chat_metrics_gaming`, real-audio `voice_metrics`).
- Delivered scripts (see TESTING.md's table): `ml/eval_chat_conda.py`, `ml/train_voice_real.py`,
  `ml/analyze_igds.py`, `ml/analyze_survey.py`, `ml/analyze_reflections.py` (risk vs next-day
  self-reports — the weak-label check that activates as soon as a pilot has history),
  `ml/tune_from_feedback.py` and `ml/monitor_drift.py` (the pilot instruments).
- `ml/eval_behavior_survey.py` (delivered): IGDS scoring → prevalence CI → behaviour-model
  correlation → threshold suggestion in one pass over the exported form CSV.
- Cross-reference: paper **Future Work** (data-dependent tier + clinical validation).

## Suggested sequencing (updated)
1. ~~Public-dataset tier~~ — **done** (see status block above).
2. **Start the ethics check + build the Google Form now** — the data-collection window
   is the long pole, so kick it off immediately.
3. **Survey analysis** once ~50–100 responses are in; add the construct-validity numbers
   (and, ideally, a behaviour model retrained on real labels) to the paper/model card.
