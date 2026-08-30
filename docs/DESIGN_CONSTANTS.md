# Design constants — "why that number?" defense reference

Every examiner-pokeable constant in the system, with the honest one-line answer and
whether it is **measured**, a **motivated prior**, or an **engineering choice**. The
distinction matters: a prior is defended by reasoning + a sensitivity check, not by a
p-value, and saying so is stronger than pretending it was fitted. Most of these also
carry the same rationale as an in-code comment.

## The three categories
- **Measured** — derived from data / a bake-off / a sweep; cite the script.
- **Prior** — a reasoned default with no labels to fit it; defended by (a) a citation
  or argument and (b) the fusion-sensitivity analysis that shows how much it actually
  moves outputs (`ml/analyze_fusion_sensitivity.py`, §6.7 of the paper).
- **Engineering** — an operational trade-off (battery, memory, latency, UX); defended
  by the constraint it serves. Doesn't affect the risk score.

---

## Risk / alerting numbers (the ones examiners ask about first)

| Constant | Value | Kind | Answer |
|---|---|---|---|
| `RISK_T1` / `RISK_T2` | 0.33 / 0.67 | Prior | Equal thirds of the [0,1] risk space — a neutral three-band split with no labelled outcomes to fit. The initial snapshot-level sensitivity run found ±0.05 material (up to ~20% band flips; the corrected rerun says up to 26.7%). **First fit attempt made, and declined:** the IGDS9-SF survey's grid search (paper §6.6) returned 0.51/0.83 at quadratic-weighted κ=0.177 (T2 moved 0.12 on one late batch — it encodes the missing severity tail) — but T2≈0.95 is pinned there *because* the sample held one disordered-range respondent, so the fitted value encodes a missing severity tail, not a clinical boundary. Still Priority-1 for prevalence-anchored calibration (`calibrate_thresholds_prevalence.py`) once a cohort with real high scorers exists. Env-overridable, so that change costs one deploy. |
| Ensemble weights | 40/30/30 | Prior | Behaviour-dominant because DSM-5/ICD-11 define the disorder behaviourally; chat/voice are corroborating. An initial, correlated snapshot-level run suggested low sensitivity (≤0.3% band flips), but the audit found repeated-session weighting and omitted grid endpoints; rerun the corrected 37-point, final-session analysis before claiming immateriality. |
| `CHAT_ALERT_T` | 0.95 | Measured | Chosen above the CONDA best-F1 point (0.85: P 0.800/R 0.703) to buy precision 0.956 at recall 0.428 — a deliberate false-alarm-cost trade, not a default. Sweep in `chat_metrics_gaming`; env-tunable; the feedback tuner confirmed it (P(excess FA)=0.001 on 17 real verdicts). |
| `CHAT_ALERT_HIGH_T` | 0.97 | Measured | High-severity marker one sweep-step above the alert cut (P 1.000 / R 0.024 at 0.97). |
| Genre multipliers | 1.25 BR … 0.70 casual | Prior | Literature-motivated (Männikkö et al. 2017: competitive/real-time/social genres show higher problematic-use association than casual/puzzle). Hand-set, not fitted. Material: removing it flips 34.4% of served session bands. **Tested externally and not supported** — across seven genres in the IGDS9-SF survey, mean severity no longer even ordered as the multiplier assumes (Other 19.3 → RPG 16.2, BR mid-table) and Kruskal-Wallis found no significant difference (H=4.59, p=0.598, paper §6.6 — weakening at every n). Read as *underpowered, not disproven*: the test has 32% power at n=103 and needs n≈400 for 90%. Retained-and-flagged rather than removed — a 34% band change is too large to make on a null this weak — and env-tunable so a properly powered result can retire it without code. **The ensemble's least-evidenced component.** |
| Keyword weights | high 0.2 / med 0.1 / phrase 0.3 | Prior | **The softest constant** — ordinally sensible (slur/self-harm phrase > profanity > mild insult) but the absolute scale is heuristic. Bounded influence, though: capped at 0.9 and **noisy-OR-fused** with the ML model (can only raise the score), so a lone medium word barely moves the 0.95 alert cut. The *channel* (not the exact weights) is what the ablation validates: removing keyword fusion drops recall-at-alert 0.363→0.278 (MCC 0.541→0.472). |
| Observation mode | < 3 sessions | Prior | Refuse to assert the top ("addicted"/High concern) band until ≥3 scored sessions exist — don't diagnose on one data point. Conservative by design. |
| Streak "healthy day" | avg ≤ 2.0 h/day + casual | Prior | ~2 h/day is a common pediatric screen-time guideline; a gamification nudge, not a risk input. |
| Noisy-OR fusion | 1−(1−kw)(1−ml) | Measured | Chosen over `max()` in the ablation (combines two independent detectors; +0.085 recall-at-alert (0.363 vs 0.278) at near-equal precision vs no fusion). |
| IGDS9-SF prevalence | 6.4% | Measured | Real disordered-range rate from the IGDS9-SF Latin-America dataset (n=11,191); the anchor for threshold calibration. **Kept, not replaced by our own survey.** The local study (n=104 usable, paper §6.6) measured 1.0% ≥36 — but a convenience sample of Indian university students contains no severity tail, so its rate reflects who answered, not the population. Using 1.1% would push the top-band threshold far higher on the weakest possible evidence. The local number is reported as a finding, not adopted as a constant. |

---

## Engineering constants (operational — do not affect the risk score)

| Constant | Value | Answer |
|---|---|---|
| `GRACE_MS` | 20 s | Absorbs a quick glance away / app-switch so one continuous play bout isn't split; short enough that sitting in another app ends the session. |
| `NEUTRAL_GRACE_MS` | 120 s | Longer grace when the game delegated to an ancillary flow (Google sign-in, Play purchase, rewarded-ad Custom Tab) so a legitimate mid-game handoff isn't counted as leaving. |
| `STALE_SESSION_HOURS` | 6 | A session open longer than this lost its end-event; the watchdog closes it. Also the back-fill duration clamp. Few children game 6 h continuously, so it's a safe abandonment ceiling. |
| `HEARTBEAT_MS` | 3 min | Liveness cadence — battery vs detection-latency trade; the server's silence-alert window is a separate, longer threshold. |
| Audio concurrency | 1 (20 s wait) | Serialise voice feature-extraction to prevent the 512 MB free tier OOM-restarting under parallel uploads (load-tested; the shed segment degrades to low-confidence neutral). |
| `VOICE_VAD_AGGRESSIVENESS` | 3 | webrtcvad's strictest speech/non-speech setting — keeps game music/ambience out of the emotion model. |
| `VOICE_VAD_MIN_SPEECH` | 0.35 | **Data-motivated:** raised from the 0.1 default after the pilot's "77% frustrated" finding traced to game audio passing the gate; require 35% of frames to be actual speech. |
| Chat queue bounds | 50 lines / 24 h | Bounded disk buffer; a day-old chat line is stale. |
| Offline session bounds | 50 / 7 days | A session is worth back-filling longer than a chat line (the server clamps its duration anyway). |

---

## The one-sentence viva posture

*"The engineering constants serve a stated constraint; the alerting numbers and the
fusion are measured against real in-domain data; and the remaining priors — thresholds,
genre weights, ensemble weights — we didn't just assert, we measured how much each one
actually moves the output, so our calibration roadmap is ranked by evidence rather than
guesswork. Then we took the top two to an external instrument and let it answer: the
genre multiplier didn't reach significance and the refitted thresholds encoded our
sample's missing severity tail, so we changed neither — and said so."* Then, if pushed
on any single number, name its category and give the row above.
