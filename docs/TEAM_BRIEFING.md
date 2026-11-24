# Team Briefing — who defends what (PW26_SAS-03)

## ▶ Review 3 — [slot: fill in] (department window 23–27 Nov 2026)

**Deck:** `docs/PES_REVIEW3_DECK.pptx`, 42 slides on the department's Review 3 template, built by
`tools/build_pes_review3_deck.py` from `docs/review3/*.json`. **Everyone presents and is graded
individually**, so each person presents the modules they own. Every slide's speaker notes start
with `[Presenter: …]`, then what to say, the numbers behind the slide and the likely questions.
Open the deck in **Presenter View**. Report draft: `docs/CAPSTONE_REPORT.pdf` (140 pages). It stays
out of the public GitHub repo until the PESU plagiarism check. Cheat sheets: `docs/CHEAT_SHEETS.pdf`,
one page each.

**The project in one sentence (the same words from all four):** *"We built and deployed a screening
system that shows parents how their child plays, not just how long: three models read play, chat
and voice, and in 103 adult gamers our behaviour score tracked a standard gaming-disorder
questionnaire (ρ = 0.317). It screens; it never diagnoses."*

**Budget for 30 minutes (assumed until the slot is announced):** about 21¾ min of non-skippable
slides (1305 s), about 6 min of live demo, and the remaining ~2 min for questions. The whole deck
runs 26½ min (1595 s), so in a 30-minute slot the seven skip-list slides are skipped by default.
Put them back only if the panel gives more time. Panels usually ask questions mid-deck: answer in
one line and move on. Talk time per person (non-skippable / every slide): **Kaustubh** 7:35 / 8:15 ·
**Kanak** 5:35 / 7:35 · **Vidisha** 4:50 / 5:35, plus narrating the ParentApp · **Khushee** 3:45 /
5:10, plus driving the demo.

| Slides | Presenter | What | Target time |
|---|---|---|---|
| 1–4 | **Vidisha** | Title, outline · Abstract: we screen how a child plays, not just how long · Suggestions from Review 2 (seven rows; row 7 is the panel's Gemini Nano remark) | 1:50 |
| 5 | **Khushee** | Gemini Nano studied: private and promising, not yet usable on children's phones | 0:45 |
| 6–7 | **Kanak** | System architecture: three tiers, the two apps meet only at the server · seven modules, one pipeline | 1:15 |
| 8–9 | **Khushee** | ChildApp detects installed games and captures only inside them · Algorithm 1, end-to-end workflow | 1:30 |
| 10–12 | **Kaustubh** | Algorithm 2, behaviour score · Algorithm 3, chat · *training data (skip)* | 1:35 (+0:40) |
| 13 | **Khushee** | *Algorithm 4, voice channel (skip)* | (+0:45) |
| 14–15 | **Kanak** | *Backend: one request checks, scores and alerts (skip)* · Algorithm 5, fusion: no genre factor in score v2 | 0:50 (+0:45) |
| 16 | **Vidisha** | ParentApp explains each score; parents rate risk and chat alerts | 0:40 |
| 17 + demo | **Khushee** drives, **Vidisha** narrates the ParentApp | Demo map, then the live loop: child phone → cloud → parent phone (sequence below) | 0:35 + ~6:00 |
| 18–19 | **Kanak** | Test timeline: manual checks → automated layers in CI · five functional layers, all open-source tools | 1:35 |
| 20 | **Khushee** | Non-functional tests: measured, bugs found, one feature kept off | 0:55 |
| 21 | **Kanak** | Test environment and who tested what; the gaps are named | 0:45 |
| 22–27 | **Kaustubh** | Results vs estimates · comparative · chat ablation · all-model ablation · hyperparameters · survey validation | 4:45 |
| 28 | **Khushee** | *Device cost: default capture is light, Hindi + English speech-to-text failed our gate (skip)* | (+0:40) |
| 29 | **Kanak** | *Weights barely move bands; dropping genre moved a third, hence versioning (skip)* | (+0:45) |
| 30–32 | **Vidisha** | Fairness, limits and implications · applicability in other domains · *benefits and limits (skip)* | 1:35 (+0:45) |
| 33–34 | **Kanak** | Timeline: system complete, genre change landed three weeks late · Project Report status | 1:10 |
| 35 | **Vidisha** | Conclusion and future work | 0:45 |
| 36–40 | **Kaustubh** | References (point at them, do not read) · IEEE draft · targeted conferences/journals | 1:15 |
| 41–42 | **Kanak** | *Any other information (skip)* · Thank You | (+0:30) |

Target times are each slide's `seconds` in `docs/review3/*.json`. Title, outline, references and
thank-you have no budget of their own (a few seconds each). "(+…)" = only if time allows.

**Skip list** (the slides marked `skip_if_short`). The owner says one line instead and the deck jumps.
In Presenter View, type the slide number and press Enter. Jumps: **11 → 15**, **27 → 30**, **31 → 33**,
**40 → 42**.

| Slide | Owner | Say instead |
|---|---|---|
| 12 Training data | Kaustubh | "Behaviour labels are simulated because no public dataset pairs phone logs with severity; chat and voice learned from real corpora, and real game chat mattered most." |
| 13 Algorithm 4, voice | Khushee | "A speech gate drops clips without speech, the server turns each clip into an emotion and deletes the audio, and voice scores 0.574 on speakers it never heard." |
| 14 Backend request | Kanak (opening slide 15) | "Every session upload passes a token check and a consent check, and at session end the server computes, scores and alerts once." |
| 28 Device cost | Khushee | "The default costs 14% of one core; Hindi plus English failed our own gate, so it stays off." |
| 29 System pilot | Kanak | "Shifting the fusion weights barely moves bands, but dropping the genre weight moved 34.4% of pilot bands, so every score now stores its version." |
| 32 Benefits and limits | Vidisha | "The method transfers, the trained models do not: without real gaming chat our chat PR-AUC fell from 0.825 to 0.511, so each new domain needs its own data, consent, ethics review and validation." |
| 41 Any other information | Kanak (on the Thank You slide) | "Consent is versioned, raw audio is deleted, and parents can export or delete their child's data." |

**Live demo (~6 min; the timed script "The 6 minutes" at the top of DEMO_RUNBOOK; the recorded video,
which follows the same order, if the network fails).** Khushee drives the ChildApp (Arjun, PIN 1234).
Vidisha narrates the ParentApp (family code FAM789, PIN 0000). Kanak stands by on the backend (laptop
fallback: DEMO_RUNBOOK §0, Option B). Kaustubh takes model questions by name.
1. Parent tour on seeded data (Vidisha): Arjun's dashboard — after a fresh reseed, Today: Some concern,
   ~55%; the 14-day trend reached High concern (85%) yesterday — and the *Latest session factors &
   daily signals* card (the SHAP top-4 reasons). Rate the seeded alert "Arjun reached High concern —
   score 85%." *Accurate* → agreement banner. Chat Analysis, Emotion Insights, then Settings → *What we
   can and can't see*.
2. Child phone (Khushee): Home → daily check-in → one line to Mira.
3. Khushee opens Roblox: the session starts within ~10 s (Vidisha: strip "Playing Roblox now"). She
   types a chat line, speaks a sentence and closes the game; the session ends ~25 s later. During that
   wait Vidisha downloads the weekly PDF.
4. Vidisha pulls to refresh: the new session, its band and its reasons; she rates this session's alert
   (raised only at Some or High concern), then sends a nudge, which reaches the child's phone in ~12 s.
5. Khushee: Logout → the parent PIN is demanded and a wrong one refused. Then Accessibility off: the
   ParentApp shows "Monitoring degraded — chat capture off" and a permission alert arrives; back on.
Behind schedule: cut Emotion Insights, then the check-in, then Mira — never the live loop or the
permission alert.

Say it once, on slide 17: Arjun's earlier history is seeded demo data (the seed script wrote those
past scores; no real child appears). Today's session is live and scored by the deployed models
(score version 2).

**Before the review — checklist**
- [ ] **Guide first (all):** show the PPT and the complete report draft (`docs/CAPSTONE_REPORT.pdf`)
      to Prof. Sawant, incorporate her corrections, rebuild both, and get her approval *before* the
      slot. On slide 4 (row 6) and slide 34, say exactly where it stands on the day. Never claim an
      approval she has not given.
- [ ] **Slide 4, Suggestions from Review 2:** row 7 is the panel's Gemini Nano remark. If anyone
      recalls another remark, add a row in `docs/review3/10_abstract_suggestions.json` (the panel's
      words · feasibility · the slide that shows progress) and rebuild the deck.
- [ ] **Slot:** replace "[slot: fill in]" here, in `docs/review3/TEAM_MESSAGE.txt` and on the cheat
      sheets once the department publishes it.
- [ ] **Demo data, morning of (Khushee; DEMO_RUNBOOK "Pre-flight", steps 0–3, in that order):** there
      is nothing to deploy, because score v2 has been live since 23 Nov. Phones online first. Reseed
      (DEMO_RUNBOOK §2: `DATABASE_URL` and `PIN_PEPPER` exactly as on Render, plus `SEED_DEMO_FORCE=1`;
      whoever holds the Render dashboard passes the values privately, never in the group). Then, with
      the variables still set, run `python scripts/cloud_e2e.py` from `backend/` — every check must
      PASS, and its logins prove the reseeded PINs work. Then run the runbook's one-line cleanup (step
      3): it deletes the 'e2e check' check-in and the 'login' / 'offline' alerts; the Mira exchange is
      on-story and stays. Clear all three variables last.
- [ ] **Phones (Khushee):** both charged, on the room Wi-Fi, latest signed APKs from the GitHub
      release, permissions on (usage access, Accessibility, microphone, notifications). ChildApp signed
      in as Arjun; ParentApp signed in with FAM789.
- [ ] **Backup video** on the laptop desktop, in the same order as the live demo.
- [ ] **Wake the backend 30 min before and again 2 min before:** open
      `https://gaming-addiction-api.onrender.com/api/health` and wait for `"models_loaded": true`.
      The free tier sleeps after ~15 min idle and takes ~40 s to wake. The keep-alive ping has been
      off since 30 Jul on purpose, to save the Neon free quota. Alternative: Actions →
      *keep-backend-warm* → Run workflow.
- [ ] **Everyone:** learn your slides' notes and every pseudocode line on your algorithm slides
      (Khushee 9 and 13, Kaustubh 10–11, Kanak 15; slide 14 is a walk-through, learn its function names), with the function names in the code reference
      under each box. Read your cheat-sheet page and the question table below.
- [ ] **Kaustubh:** run `python -m pytest ml/tests/ -q` the morning of (7 guards), so you can say
      "green this morning".

**New questions this review invites** (the owner answers; anyone else hands over by name)

| Question | Owner | One-line answer |
|---|---|---|
| Is the project complete? | Kanak | Yes: both apps, the server and the three models are deployed and live with score version 2. What remains is data (the child study, which needs ethics approval first) and the IEEE submission by 31 Jan 2027. |
| What is your test plan, and why these tests? | Kanak | Five functional layers (unit, API integration on SQLite and Postgres 16, contract, production-mode sweep, live-cloud end-to-end) plus non-functional checks (load, fuzzing and security scans, accent audit, phone drill). Each layer catches bugs the others miss. 300 automated tests and 7 research-integrity guards run on every push. |
| Test environment, and who tested what? | Kanak, then each owner | Laptop (SQLite), GitHub Actions (SQLite and Postgres 16), Render + Neon, real phones. Kanak: backend suites, fuzzing, load test, CI. Khushee: ChildApp tests, phone and tamper drills. Vidisha: ParentApp tests, consent, export and deletion checks. Kaustubh: model evaluation, ablations, guards. |
| Walk me through this code. | Owner of the slide | Read the code box top to bottom, one line at a time, then the "In plain words" column. Name the functions in the code reference under the box (Algorithm 5: `run_prediction()`, `risk_category()`, `_maybe_create_alert()`). |
| Explain the architecture. | Kanak | Three tiers. The ChildApp captures on the child's phone, the Flask server on Render (Docker, 512 MB) with Neon Postgres scores, and the ParentApp explains. The two apps meet only at the server, the one place that checks tokens, roles and consent. |
| What does this ablation show, for every model? | Kaustubh | Data and features carry accuracy. Chat without real gaming chat falls from PR-AUC 0.825 to 0.511, the largest effect. Behaviour gets 70.2% from screen time alone and 91.6% from the 10 features (simulated labels); 10 derived proxies add only 0.3 points. Voice with 17 instead of 36 tone features falls from 0.562 to 0.499. Behaviour alone agrees with the fused decision in only 67.7% of pilot sessions. |
| Did you tune hyperparameters? | Kaustubh | Yes: 188 settings, cross-validated on training data only, each test set touched once. Chat's pick is worse on gaming chat (−0.0100 [−0.0167, −0.0035]). Voice shows no detectable gain (+0.0021 [−0.0117, +0.0154]). Selected on gaming chat alone, the search picks our C = 1. Behaviour gains +0.0113 [+0.0063, +0.0165] on simulated labels but not on the real survey (ρ 0.295 vs our 0.317); we report it and do not adopt it (a 24× larger model, plus re-validation and a fairness re-audit). |
| Are the results as expected? | Kaustubh | Behaviour (91.6% on simulated labels vs the 80–90% estimate) and survey size (103 scored vs ≥ 50) met the estimates. Three misses have measured causes: one disordered-range respondent (so no cut-off accuracy), no genre effect (weight removed), and Hindi + English speech-to-text failed our phone gate (off by default). |
| Comparative analysis — against what? | Kaustubh; commercial apps: Vidisha | Simpler and bigger baselines on the same held-out data. Behaviour: screen time alone (70.2%). Chat: off-the-shelf toxic-BERT (0.709) and our first model (0.516), against 0.825. Voice: wav2vec2 embeddings 0.776 vs our 0.553 on the matched split, but too big for the server. Real adults: score 0.317 vs hours 0.147. Commercial apps publish no error rates, so we compare capabilities. |
| Limitations, and what they imply? | Vidisha | Limits: behaviour accuracy is on simulated labels; the survey had adults only, with one disordered-range respondent; weights and cut-offs are hand-set priors; browser games and spoken Hindi are blind spots; Tibeto-Burman speakers see 60.8% word errors. So a band opens a conversation, no alert does not mean no abuse, and every score change is versioned. |
| Why did the genre removal take until now? | Kanak (why remove it: Kaustubh) | Honestly, it slipped past the 19 Oct–2 Nov window and landed on 23 Nov, three weeks late: [team: reason]. It shipped as a versioned change: a stored score version, a one-time parent note, 8 new tests and a migration rehearsed on Postgres 16. |
| Did you look into Gemini Nano, as suggested? | Khushee (accuracy and the test plan: Kaustubh) | The shared sentence below. Never claim Nano was tested on a phone. |
| Where will you publish? | Kaustubh | IEEE COMPSAC 2027, Digital Health symposium (deadline 31 Jan 2027, decision 7 Apr), with the 6-page draft. Backup HealthCom 2027 (8 Jun); INDICON 2027 as a budget fallback; IEEE Access for a longer version. Health venues that expect ethics-committee approval are avoided for now. |
| Plagiarism status of the report? | Kanak | Not checked yet [team: update if done]. The department checks plagiarism only at the PESU library (limit 15%), and we go after the guide's corrections. Until then the report stays out of the public repo. |
| What changed since Review 2? | Vidisha | The genre weight is gone (score version 2, live since 23 Nov, one-time note to parents). We studied the panel's Gemini Nano question and built a full test plan (300 automated tests, 7 guards). We added ablations for every model and hyperparameter studies, drafted the 140-page report, re-synced both papers and chose COMPSAC. |

**Same answer from all four:**
- **Genre weight:** *"Done — removed on 23 Nov 2026. The served score is version 2, and parents
  with older scores got a one-time note."* (Why late: Kanak. Why remove: Kaustubh.)
- **Gemini Nano** (`docs/gemini/defense_qa.md`): *"We studied Gemini Nano against Google's own
  documentation and it is genuinely good for privacy, but today its terms exclude apps used by
  children, it only works while its own app is on screen, and it does not run on our test phone or
  on Samsung's A, M and F phones — so we keep our validated models and will benchmark Nano as soon
  as that changes."*
- Never "addicted" or "diagnosis": say "screening", "concern", "signal".

---

*Everything below is the Review 2 (13 Oct) and earlier briefing, kept for reference. Where it
differs from the Review 3 section above or from `tools/project_numbers.py` (for example the
backend test count, now 190 of 300 automated tests), the Review 3 section wins.*

## ▶ Review 2 — Tue 13 Oct 2026, 3:00–3:30 pm, Room B204 (with Prof. Sawant)

**Deck:** `docs/PES_REVIEW2_DECK.pptx` (built by `tools/build_pes_review2_deck.py` on the
department's Review 2 template). **Everyone presents and is evaluated individually**, so
each person presents the modules they own. Every slide's speaker notes start with
`[Presenter: …]` and say what to say — open the deck in **Presenter View**.

**Budget for the 30 minutes:** ~18 min of slides, ~5 min live demo, ~7 min of questions.

| Slides | Presenter | What | Target |
|---|---|---|---|
| 1–3 | **Vidisha** | Title, outline, Suggestions from Review 1 (**fill the table in first**) | 2 min |
| 4–5 | **Kaustubh** | Proposed approach: the five steps + "is there a need to change it?" | 2¾ min |
| 6 | **Khushee** | Algorithm 1 — end-to-end workflow (starts on the child's phone) | 1¼ min |
| 7–8 | **Kaustubh** | Algorithm 2 (behaviour score) · Algorithm 3 (chat scoring and alerts) | 2 min |
| 9 | **Khushee** | Algorithm 4 — voice channel | 1 min |
| 10–12 | **Kanak** | Algorithm 5 (fusion, band, alert) · Design approach (2 slides) | 3 min |
| 13 + demo | **Khushee** drives, **Vidisha** narrates the ParentApp | Module status, then the live demo (DEMO_RUNBOOK §3; video if Wi-Fi fails) | ¾ + 5 min |
| 14 | **Kanak** | Results and testing table (model-number follow-ups → Kaustubh by name) | 1¼ min |
| 15–16 | **Vidisha** | Applicability in other domains (2 slides) | 2½ min |
| 17 | **Kanak** | Timeline — pending tasks | ¾ min |
| 18 | **Vidisha** | Conclusion | 1 min |
| 19–20 | **Kanak** | References (point at them, do not read) | 10 s |

**If time runs short:** skip slide 12 (alternatives table) and slide 16, and say "details in the notes".
**Before 13 Oct:** fill slide 3 with the Review 1 panel's actual remarks; tell Kaustubh the
final-report and final-evaluation dates so the timeline slide can show them.
**New questions this review invites:** "walk me through your pseudocode" (each algorithm's
owner — the right half of every algorithm slide is the plain-language version), "why is the
genre weight changing?" (Kaustubh — answer below), "what else could this method do?" (Vidisha —
the method transfers, the trained models do not).

---

**Two decks exist — know which one the review wants.** `docs/PES_REVIEW1_DECK.pptx` follows the department's mandated Phase-3 Review-1 template exactly (title / outline / abstract & scope / Phase-1&2 summary with suggestions incorporated / literature inferences / architecture / tasks & tools / individual contribution / demo & testing / Gantt / IEEE references / thank-you) — 12 slides, use this for the formal review. `docs/DEFENSE_DECK.pptx` is the 17-slide technical deck (Phase III rubric map, per-model detail, validation slide) — use it for the final defense or wherever the panel wants depth. Both are generated by `tools/build_*_deck.py` from the same JSONs. **The Individual Contribution slide follows the team's agreed module ownership** (below); module LOC are measured, hours are estimates — if anyone's hours need adjusting, edit `CONTRIB` in `tools/build_pes_deck.py` and rebuild.

Read this the night before. It maps the deck (`docs/DEFENSE_DECK.pptx`, 17 slides,
speaker notes in every slide) and the Q&A bank (`docs/DEFENSE_NOTES.md`) onto the four
of us, so that no question lands on someone who has to say "I'd have to check."
Everyone reads all of DEFENSE_NOTES once; each person *owns* their rows below cold.

**Ground rules for every answer**
1. Cite the measurement, then name the limitation *before* the examiner does.
2. Never say "addicted" / "diagnosis" — say "screening", "concern", "signal".
3. If you don't own the question, hand it over by name ("Kaustubh has that number") —
   a clean hand-off beats a guess every time.
4. Two phrases to keep in your pocket: *"the score's meaning is validated; its accuracy at
   the clinical cut-off is not"* and *"a disclosed boundary beats a privacy regression."*

---

## Kaustubh Agarwal — ML, validation, and the closing arguments
**Slides:** 6 (behaviour), 7 (chat), 8 (voice), 11 (verification), **12 (validation)**, 16 (limitations), 17 (close)
**Owns in DEFENSE_NOTES:** §2 behaviour · §3 chat · §4 voice · §6 evaluation · **§10 external validation (12 of its 13 Q&As — the survey-permission Q&A is Vidisha's)** · §11 closing · the accent-fairness Q&A · (serving/API questions → hand to Kanak by name)
**Numbers to have cold:** 91.6 % (synthetic, say so) · PR-AUC 0.825 (ablation protocol); deployed P 0.956 / R 0.428 @ 0.95 · voice 0.574 speaker-independent (8.3-pt leakage story) · **ρ = 0.317 [0.137, 0.478], hours 0.147, Δρ = +0.167 (CI grazes zero — lean on the partial), partial 0.303** · pattern 0.330 vs volume 0.128, **formally tested: pattern − volume = +0.199 [+0.019, +0.380], excludes zero** (this is the strongest single number — use it whenever the paired Δρ gets attacked) · genre p = 0.598 (32 % power) · 1 disordered respondent → ~157 usable needed · late batch folded in per pre-stated rule (0.352 → 0.317: say it before they do) · Svarah 0 false alerts / 9.6 h, WER 35 → 61 %
**Hardest questions you'll get:** "0.32 is weak" (lead with the baseline comparison) · "why no sensitivity/specificity" (one positive; guard written before the data) · "training data is synthetic" (yes — and here is where the score meets real labels) · "why did you drop the genre multiplier?" (it is gone: removed on 23 Nov 2026 as score version 2. It was never part of the validated score, and its one test found no support, p 0.598 at 32 % power. Removal moved 34.4 % of pilot bands, so every prediction now stores its score version and parents with older scores get a one-time note)

## Khushee P Kiran — ChildApp, capture, and anti-tamper
**Slides:** 4 (system overview & deployment), 10 (Built for India — keyboard/capture half), 14 (system testing — device half)
**Owns in DEFENSE_NOTES:** §8 engineering (Android side) · §9 sensing-blindspots Q&A · §9 clear-app-data / observation-mode Q&A · the battery/latency Q&A · Hindi keyboard/capture parts of the Hindi Q&A
**Numbers to have cold:** ChildApp default path **14 % of one core, 288 / 301 MB**; dual-STT **51–72 %, 399 / 419 MB → fails our gate, hence default OFF** · session auto-start ~10 s, auto-end ~25 s, nudge ~12 s · Galaxy M52, 2 × 15-min Roblox, 2026-08-18 · v2.4.0 signed release, cert unchanged since day one
**Hardest questions you'll get:** "can a child evade it" (yes — browser/webview games; boundary is *installed apps, not games*; closing it needs screen/URL surveillance we refuse) · "keyboard switching" (detected: heartbeat capture bits, parent alert, child self-heal prompt) · "clear app data to reset observation mode" (server-side counter; heartbeat dies → offline alert) · "does adb beat the uninstall block" (no — we tried, `DELETE_FAILED_DEVICE_POLICY_MANAGER`)

## Kanak Goyal — backend, deployment, fusion, and datasets
**Slides:** 5 (why three channels), 9 (fusion & alerting — you own the serving, renormalisation, thresholds and alert path; the weight *design* is Kaustubh's, hand it over by name), 13 (dataset audit), 14 (system testing — backend/CI half)
**Owns in DEFENSE_NOTES:** §1 problem framing · §5 fusion & alerting · §7 datasets · §8 engineering (server side) · the feedback-tuner-drift rebuttal · the MobSF / security-audit Q&A (after §11)
**Numbers to have cold:** 40/30/30 renormalised over present channels · max-not-mean chat · operating points 0.85 → P 0.800 / R 0.703, 0.90 → 0.888 / 0.623, **0.95 → 0.956 / 0.428** · tuner cap ±0.05, human-applied · 190 backend tests on SQLite **and** Postgres 16 (300 automated + 7 guards), 288 concurrent requests 0 errors p50 66 ms · 11 adopted corpora + 2 rejected with evidence + StudentLife reality check
**Hardest questions you'll get:** "why threshold 0.95 not best-F1" (false alarms cost trust; ~1 in 23 wrong vs 1 in 5) · "can an anxious parent drag thresholds down" (capped, floored, human-applied — no automatic loop) · "why RF/LogReg not BERT" (measured: toxic-BERT 0.709 vs 0.825; 512 MB serving budget) · "why did you reject those Kaggle sets" (downloaded and inspected: synthetic provenance, engagement ≠ addiction)

## Vidisha Murali — ParentApp, ethics, privacy, scope, and the India story
**Slides:** 2 (Phase III map — you open, so you frame), 3 (problem & scope), 10 (Built for India — code-mixed chat/fairness half), 15 (privacy & ethics) · the ParentApp screens during the demo (dashboard, verdicts, transparency screen, weekly PDF — you narrate while Khushee drives)
**Owns in DEFENSE_NOTES:** §8 engineering (ParentApp side: dashboard, SHAP reasons, verdicts, transparency screen, weekly PDF) · §9 privacy & consent (mic defence, export/delete symmetry) · **the crisis-paradox Q&A** · the "why children not adults" framing · Hindi dual-script parts of the Hindi Q&A · the ASR-fairness framing (Kaustubh has the numbers, you have the *why it matters*)
**Numbers to have cold:** ParentApp: SHAP top-4 reasons on the dashboard for every score (the weekly PDF shows 3), observation mode refuses the top band until 3 scored sessions, weekly PDF is the same numbers not a new verdict · export scope = deletion scope, 15 tables, credentials excluded · consent versioned, fails closed (403 until re-consent) · raw audio deleted after extraction, STT on-device · typed-chat alert precision ≥ 0.95 in English, Devanagari and romanised Hindi (a chat-model number: the ParentApp's screens are English-only, with no Hindi UI) · survey: adults 18+, anonymous, **guide notified in writing 14 Aug 2026** from the official PES account, all four of us on the mail, design disclosed + explicit "does the department need more approval?" — *not* an ethics-committee determination
**Hardest questions you'll get:** "what does the parent actually see, and can they misread it?" (bands with plain-language reasons, never a diagnosis; observation mode; the transparency screen lists exactly what is captured) · **"did you take permission for the survey?"** (full answer is DEFENSE_NOTES §10, the *"Did you take permission for the survey?"* Q&A — learn it verbatim: the 14 Aug mail, and the timing conceded *first* — it went out while the form was still open, after the main wave; if asked "did she reply?" say only what the record documents and stop — we claim no reply, no approval, no absence-of-objection) · "you alert on swear words but stay silent on self-harm" (name the asymmetry first; it's a refusal to hard-code a contested clinical judgement; the tiered wellbeing-check is documented as a proposal, deliberately not shipped) · "why only children" (a guardian with duty of care is what makes screening the unwilling possible and proportionate; an adult version is a journal or spyware) · "you're recording a child's microphone" (layered: consent → on-device STT → server deletion → VAD gate → export/delete rights)

---

## Run order on the day (16 min + Q&A)
1. **Vidisha** opens: slides 1–3 (title, Phase III map, scope) — ~2½ min
2. **Khushee**: slide 4 (overview/deployment) — ~1 min · **Kanak**: slide 5 (three channels) — ~1 min
3. **Kaustubh**: slides 6–8 (three models) — ~3½ min
4. **Kanak**: slide 9 (fusion) — ~1 min
5. **Vidisha + Khushee**: slide 10 (India: chat/fairness, then keyboard/capture) — ~1½ min
6. **Kaustubh**: slides 11–12 (verification, **validation**) — ~3 min — *protect this time*
7. **Kanak**: slide 13 (datasets) — ~45 s
8. **Kanak + Khushee**: slide 14 (tests/CI, then device numbers) — ~1 min
9. **Vidisha**: slide 15 (privacy & ethics) — ~1 min
10. **Kaustubh**: slides 16–17 (limitations, close) → **demo** (Khushee drives the phones; DEMO_RUNBOOK §3; video is the fallback)

If forced to cut: merge 4+5, and 13 into 14. **Never cut slide 12.**

## The night before — 30-minute drill
- Each person: read your rows aloud once, then have someone else fire your "hardest questions" at you unannounced.
- Kaustubh: re-run `python -m pytest ml/tests/ -q` (7 guards) so you can say "green this morning".
- Khushee: pre-warm the backend (`/api/health` → `models_loaded: true`), reseed if needed (`SEED_DEMO_FORCE=1`), both phones charged and on the venue Wi-Fi, video file on the laptop desktop.
- Everyone: the one-sentence project summary, identical from all four mouths — *"a deployed, multimodal screening system for parents that measures how a child plays, not just how long — in 103 adult gamers its score tracked the IGDS9-SF questionnaire (ρ = 0.317); it screens, never diagnoses, and we name its limitations before you ask."*
