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
| `RISK_T1` / `RISK_T2` | 0.33 / 0.67 | Prior | Equal thirds of the [0,1] risk space — a neutral three-band split with no labelled outcomes to fit. **Sensitivity-tested:** ±0.05 flips up to ~20% of bands, so it *is* material and is priority-1 for prevalence-anchored calibration (`calibrate_thresholds_prevalence.py`). Env-overridable. |
| Ensemble weights | 40/30/30 | Prior | Behaviour-dominant because DSM-5/ICD-11 define the disorder behaviourally; chat/voice are corroborating. **Sensitivity-tested:** perturbing within ±0.15 changes ≤0.3% of bands — provably immaterial, so the "unvalidated weights" worry is measurably a non-issue. |
| `CHAT_ALERT_T` | 0.90 | Measured | Chosen above the CONDA best-F1 point (0.85: P 0.888/R 0.660) to buy precision 0.950 at recall 0.491 — a deliberate false-alarm-cost trade, not a default. Sweep in `chat_metrics_gaming`; env-tunable; the feedback tuner confirmed it (P(excess FA)=0.001 on 17 real verdicts). |
| `CHAT_ALERT_HIGH_T` | 0.95 | Measured | High-severity marker one sweep-step above the alert cut (P 0.987 at 0.95). |
| Genre multipliers | 1.25 BR … 0.70 casual | Prior | Literature-motivated (Männikkö et al. 2017: competitive/real-time/social genres show higher problematic-use association than casual/puzzle). Hand-set, not fitted. **Sensitivity-tested and MATERIAL** (removing it flips 36% of bands, doubling 51% — the casual 0.70 discount is load-bearing), so it is priority-1 for calibration alongside the thresholds. |
| Keyword weights | high 0.2 / med 0.1 / phrase 0.3 | Prior | **The softest constant** — ordinally sensible (slur/self-harm phrase > profanity > mild insult) but the absolute scale is heuristic. Bounded influence, though: capped at 0.9 and **noisy-OR-fused** with the ML model (can only raise the score), so a lone medium word barely moves the 0.90 alert cut. The *channel* (not the exact weights) is what the ablation validates: removing keyword fusion drops recall 0.491→0.434. |
| Observation mode | < 3 sessions | Prior | Refuse to assert the top ("addicted"/High concern) band until ≥3 scored sessions exist — don't diagnose on one data point. Conservative by design. |
| Streak "healthy day" | avg ≤ 2.0 h/day + casual | Prior | ~2 h/day is a common pediatric screen-time guideline; a gamification nudge, not a risk input. |
| Noisy-OR fusion | 1−(1−kw)(1−ml) | Measured | Chosen over `max()` in the ablation (combines two independent detectors; +0.057 recall at equal precision vs no fusion). |
| IGDS9-SF prevalence | 6.4% | Measured | Real disordered-range rate from the IGDS9-SF Latin-America dataset (n=11,191); the anchor for threshold calibration, replaceable by the local survey. |

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
guesswork."* Then, if pushed on any single number, name its category and give the row
above.
