# Adult Gaming Survey (IGDS9-SF) — ready to paste into a Google Form

Purpose: collect a **local (Indian) severity base rate** and an hours-vs-severity
relationship from adult gamers, to anchor the risk-band calibration
(`ml/calibrate_thresholds_prevalence.py --prevalence …`) and to locally replicate the
grounding the system currently borrows from the IGDS9-SF Latin-America dataset
(§4.2 / §4.4 of the paper).

**Scope rules (important):**
- **Adults only (18+), reporting on their own gaming.** Surveying minors needs guardian
  consent and likely ethics clearance — keep this clean by restricting to adults. Still
  mention it to your guide; PES may want a nod even for an anonymous survey.
- **Anonymous.** No names, no email collection (turn OFF "Collect email addresses" in
  Google Forms settings), no identifying data.
- This survey does **not** validate the fusion weights — that needs IGDS9-SF scores
  linked to a monitored child's telemetry (the in-app instrument, future work). It only
  supplies the population **prevalence** anchor and the hours–severity check.

---

## Form header (paste as the description)

> This is an anonymous academic survey on gaming habits for a PES University capstone
> project (PW26_SJ_05). It takes ~3 minutes. You must be **18 or older**. There are no
> right or wrong answers, and no personal or identifying information is collected. By
> continuing you consent to your anonymous responses being used for research.

---

## Screening + demographics

**Q1. Are you 18 years or older?**  (Multiple choice — if "No", end the form)
- Yes  ·  No

**Q2. Your age group** (Multiple choice)
- 18–20  ·  21–24  ·  25–29  ·  30–39  ·  40+

**Q2b. Do you currently play video games?**  (Multiple choice — if "No", end the form)
- Yes  ·  No

> Keep this wording exactly. The analysis script uses `currently play video games`
> as the eligibility gate; a looser phrase collides with Q3 below (which also
> contains "do you play video games") and would drop every response. The dry-run
> test `ml/tests/test_survey_parsing.py` guards this.

**Q3. On average, how many hours per week do you play video games (phone/PC/console)?**
(Multiple choice)
- Less than 2  ·  2–5  ·  6–10  ·  11–20  ·  21–35  ·  More than 35

**Q4. Which type of game do you play most?** (Multiple choice)
- Battle Royale (BGMI/Free Fire/PUBG)  ·  FPS (Valorant/COD)  ·  MOBA (Mobile Legends/Wild Rift)
- RPG / open-world  ·  Strategy  ·  Sandbox (Minecraft/Roblox)  ·  Casual (Candy Crush/Ludo)  ·  Other

---

## Gaming-pattern questions (feed the behaviour model — keep the exact bands)

These six questions self-report the model's objective features, so
`ml/eval_behavior_survey.py` can score every respondent with the real behaviour model
and correlate it against their IGDS9-SF total (the construct-validity number). The
band wordings below are what the script parses — paste them verbatim.

**Q5. On a typical day you play, about how many hours do you game?** (Multiple choice)
- Less than 1  ·  1–2  ·  2–3  ·  3–5  ·  More than 5

**Q6. How many days per week do you usually game?** (Multiple choice)
- 0  ·  1  ·  2  ·  3  ·  4  ·  5  ·  6  ·  7

**Q7. How long is a typical single gaming session?** (Multiple choice)
- Under 30 minutes  ·  30–60 minutes  ·  1–2 hours  ·  2–4 hours  ·  More than 4 hours

**Q8. How often do you game after midnight?** (Multiple choice)
- Never  ·  Rarely  ·  Sometimes  ·  Often  ·  Very often

**Q9. In a typical week, how many gaming sessions run longer than 3 hours?** (Multiple choice)
- 0  ·  1–2  ·  3–5  ·  6 or more

**Q10. After ending a session, how often do you start another within 15 minutes?** (Multiple choice)
- Never  ·  Rarely  ·  Sometimes  ·  Often  ·  Very often

**Q11. What is the longest run of consecutive days you've gamed recently?** (Multiple choice)
- 1–2 days  ·  3–6 days  ·  1–2 weeks  ·  More than 2 weeks

**Attention check (place between Q8 and Q9):** "For quality control, please select
'Often' for this question." (same Never→Very often options; the analysis script drops
respondents who fail it.)

---

## IGDS9-SF — the 9 items

Instructions to paste above the block:
> These questions ask about your gaming over the **past 12 months**. Answer each on the
> scale: **1 = Never, 2 = Rarely, 3 = Sometimes, 4 = Often, 5 = Very often.**

Use a **"Multiple choice grid"** in Google Forms: rows = the 9 statements below,
columns = 1 / 2 / 3 / 4 / 5. (Set the grid to "require a response in each row".)

1. I feel **preoccupied** with my gaming — I think about previous gaming sessions or the next one when I'm not playing.
2. I feel **more irritable, anxious or sad** when I try to cut down or stop gaming.
3. I feel the need to spend **increasing amounts of time** gaming to feel satisfied.
4. I have **tried to reduce or stop** gaming without success.
5. I have **lost interest in previous hobbies** or other activities because of gaming.
6. I have **continued gaming despite knowing it was causing problems** with people around me.
7. I have **deceived family members or others** about how much I game.
8. I game to **escape or relieve a negative mood** (e.g., helplessness, guilt, anxiety).
9. I have **jeopardised or lost** an important relationship, job, or study/career opportunity because of gaming.

**Optional item (mirrors the chat-channel premise, §4.4):**
- In the past 12 months, how often have you sent or received **toxic/abusive messages**
  in game chat?  (same 1–5 scale)

---

## Scoring (for your analysis, not shown to respondents)

- Sum the 9 items → total **9–45** (higher = more severe). This is the standard IGDS9-SF
  total (Pontes & Griffiths, 2015).
- **Disordered-gaming indication:** total **≥ 36** — the same cutoff used for the 6.4%
  base rate the paper cites from the Latin-America dataset. Your **local prevalence** =
  (respondents with total ≥ 36) / (total respondents).
- Feed that number in: `python ml/calibrate_thresholds_prevalence.py --prevalence <p>`
  once the cohort has enough children; and cross-check hours (Q3) vs total score for the
  hours–severity direction (`ml/analyze_igds.py` is the methodology template).
- **One-command analysis:** export the linked Sheet as CSV to `data/survey/responses.csv`
  and run `python ml/eval_behavior_survey.py` — it scores the IGDS totals, computes the
  local prevalence with a CI, runs every respondent through the real behaviour model via
  the gaming-pattern answers (Q5–Q11), and prints the construct-validity correlation plus
  threshold suggestions ready for the paper.

**Sample-size note:** at a ~6% true prevalence you need well over 100 responses before
the base-rate estimate is tight — with 150 responses expect only ~9 in the disordered
range, so report it **with a confidence interval**, never as a point fact.

**Citation (put in the form footer and the paper):** Pontes, H. M., & Griffiths, M. D.
(2015). *Measuring DSM-5 Internet Gaming Disorder: Development and validation of a short
psychometric scale.* Computers in Human Behavior, 45, 137–143. (IGDS9-SF is free for
research use with attribution.)
