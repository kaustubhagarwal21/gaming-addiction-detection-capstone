# Model Validation Plan — from synthetic to real-data credibility

> **Why this doc exists.** The system is engineered to a production standard, but the three
> ML models are trained on **synthetic / illustrative** data (stated honestly in the paper).
> That is the single biggest limitation a panel or reviewer can raise. This plan is the
> concrete, costed path to replace "trained on synthetic data" with **"validated against
> real, labelled data — honestly reported."** Done even partially, it is the change that
> moves the capstone from *methodologically sound* to *empirically validated*.
>
> It expands, with datasets/links/how-to, the directions summarised in the paper's
> **Future Work** (Tier 1/2/3). Nothing here changes the deployed system; it is an
> evaluation + (optional) retraining programme.

---

## The principle

Each of the 3 models needs **at least one evaluation on real, labelled data**:

| Model | Real-data label source | Difficulty |
|---|---|---|
| Chat toxicity (TF-IDF + LogReg) | Public toxicity datasets | **Easy** — download & evaluate |
| Voice emotion (GradientBoosting) | Public speech-emotion datasets | **Easy** — download & evaluate |
| Behaviour / addiction (RandomForest) | A **validated psychometric instrument** (IGDS9-SF) collected from real users | **Medium** — needs a small survey/study |

Do them in that order: the first two need **no recruitment** and can be done in days; the
third is the headline and needs a small human study (a Google Form is the practical way).

---

## Tier 1 — Validate chat + voice on PUBLIC datasets (no recruitment, ~1–2 weeks)

No human subjects, no ethics overhead. Download labelled data → run the **existing**
trained model → report honest metrics next to the synthetic ones.

### 1A. Chat toxicity model

**Datasets (pick one or both):**
- **Jigsaw Toxic Comment Classification Challenge** (large, standard benchmark) —
  <https://www.kaggle.com/c/jigsaw-toxic-comment-classification-challenge/data>
- **CONDA** — in-game (gaming chat) toxicity, domain-matched, the better fit —
  <https://github.com/usydnlp/CONDA>

**How to:**
1. Download the dataset CSV(s).
2. Write `backend/scripts/eval_chat_real.py`: load comments + their toxic/non-toxic labels →
   run them through the **same** TF-IDF + LogisticRegression pipeline the server uses →
   collect predictions.
3. Compute and print: **precision, recall, F1, ROC-AUC**, and a **confusion matrix** at the
   production threshold (0.75).
4. (Optional) sweep the threshold and report a precision–recall curve to justify 0.75.

**Report:** add a "real-data" column to the chat results table in the paper / model card,
beside the synthetic numbers. If real-data F1 is lower (it usually is), **say so** — an
honestly reported drop is more credible than a perfect synthetic score.

### 1B. Voice emotion model

**Datasets (free, widely cited):**
- **RAVDESS** — 24 actors, 8 emotions — <https://zenodo.org/record/1188976>
  (Kaggle mirror: <https://www.kaggle.com/datasets/uwrfkaggler/ravdess-emotional-speech-audio>)
- **CREMA-D** — 91 actors, more naturalistic — <https://github.com/CheyneyComputerScience/CREMA-D>
  (Kaggle: <https://www.kaggle.com/datasets/ejlok1/cremad>)
- **TESS** — clean studio set, easy starter — <https://www.kaggle.com/datasets/ejlok1/toronto-emotional-speech-set-tess>

**How to:**
1. Download a dataset (start with RAVDESS or TESS — smallest).
2. Write `backend/scripts/eval_voice_real.py`: extract the **same acoustic features** the
   server pipeline uses (apply the existing RMS silence floor) → run the GradientBoosting
   model → collect predictions. Map the dataset's emotion labels onto the model's classes
   (angry / frustrated / excited / neutral) — document the mapping.
3. Compute: **per-class precision/recall, macro-F1, confusion matrix** on real human speech.

**Report:** same as 1A — real metrics alongside the synthetic `0.9925`, with the honest
note that the synthetic figure was internal-validity only.

> **Effort/payoff:** ~1–2 weeks, low risk. Alone it moves **2 of 3 models** from synthetic
> to real-validated — the highest return for the time. Start here.

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
  compute the Tier-2 metrics above. (I can write `backend/scripts/eval_behavior_survey.py`
  to do scoring → correlation → AUC/sensitivity/specificity → calibration in one pass.)

---

## Limitations to state explicitly (naming them is a strength)
- **Convenience sampling** (WhatsApp social circle) — non-representative.
- **Self-report bias** (Mode B) — recall + social-desirability effects.
- **Small N** — report confidence intervals; treat as construct validation, not a clinical trial.
- **Adult population** — validates the construct; generalisation to minors is future work.

---

## How this maps to the codebase
- Honest-metrics + model-card infrastructure already exists (`/api/model_card`), so each eval
  script just loads real data, runs the trained model, computes metrics, and the numbers slot
  into the model card / paper evaluation tables.
- Suggested new scripts: `eval_chat_real.py`, `eval_voice_real.py`, `eval_behavior_survey.py`
  under `backend/scripts/`.
- Cross-reference: paper **Future Work** (Tier 1 voice/RAVDESS; Tier 3 clinical validation).

## Suggested sequencing (if the deadline is tight)
1. **Tier 1 now** — highest ROI, no recruitment; banks 2/3 models on real data within a week.
2. **Start the ethics check + build the Google Form in parallel** — the data-collection window
   is the long pole, so kick it off immediately.
3. **Tier 2 analysis** once ~50–100 responses are in; add the real-data validation (and,
   ideally, a retrained behaviour model) to the paper/model card.
