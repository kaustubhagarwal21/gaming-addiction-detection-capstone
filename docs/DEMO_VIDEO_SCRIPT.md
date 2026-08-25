# Demo Video Script — PW26_SAS-03

**Target: 4½–5 minutes.** This is the *backup* for the live demo (DEMO_RUNBOOK §3),
so it follows the same beats in the same order — if Wi-Fi dies on the day, you
switch to this video and the narrative does not change. Record once, cleanly;
resist the urge to show everything.

**Setup before you press record**
- Backend awake: open `https://gaming-addiction-api.onrender.com/api/health` → `"models_loaded": true`.
- Reseed the demo family (`SEED_DEMO_FORCE=1 python seed_demo.py` per DEMO_RUNBOOK §2) so Arjun has fresh 14-day history.
- ChildApp logged in as **Arjun (PIN 1234)**, ParentApp signed out. Both phones on the same Wi-Fi.
- Screen-record the **ParentApp phone** for Parts 1–2, the **ChildApp phone** for Parts 3–4 (or use `scrcpy` for both to a laptop and record the desktop). Do NOT record the parent PIN entry keystrokes on camera — mask or cut.
- Two takes minimum. Keep the one where nothing loads slowly.

Timings are what to aim for, not a metronome. **Bold** = what to say. *Italic* = what to do.

---

## Part 0 — Cold open (0:00–0:20)

*Slide or plain title card: "AI-Driven Gaming Addiction Screening — PW26_SAS-03".*

> **"Parental-control tools tell you how long your child played. They can't tell three hours of healthy play from three hours of compulsive play. This is a screening system that watches *how* a child plays — the late-night sessions, the rapid re-logins, the rising toxicity in chat and voice — and turns it into one signal a parent can act on. Two Android apps, a cloud ML backend, live in production. Let's see it."**

---

## Part 1 — Parent side: the signal (0:20–1:50)

*Open ParentApp. Sign in with family code FAM789 + parent PIN (mask keystrokes). Pick Arjun.*

> **"This is the parent's view. Sign in with the family code and the parent PIN — the child never knows this PIN, which matters in a minute."**

*Land on the Dashboard. Let it sit for two seconds so the risk band, weekly hours, and 14-day trend are visible. Point at the header strip.*

> **"Arjun is showing High concern — around 85 percent — about seventeen hours a week, and the fourteen-day trend is rising. Up top, the live status strip: monitoring is active, and when he's in a game it says so, live. Below: *why*. Contributing factors — late-night play, rapid re-logins, binge sessions — these are SHAP attributions on measured behaviour, in plain language. Not a black box, and not a diagnosis: the wording says 'concern', never 'addicted'."**

*Tap Alerts. Scroll to a risk alert.*

> **"Alerts arrive in real time to every guardian in the family — risk, toxic chat, tamper events — with friendly ages. And here's the feedback loop:"** *tap Accurate on one.* **"A parent rates each alert. Those verdicts feed a threshold tuner — the only source of real labels in the system — and the banner shows the agreement rate so far."**

*Dashboard → Send a nudge → "Time to take a break". Cut to the ChildApp phone showing the notification arrive (~12 s; trim the wait).*

> **"It's two-way. A nudge from the parent lands on the child's phone as a notification in about ten seconds — guidance, not just surveillance."**

---

## Part 2 — Parent side: chat, voice, transparency (1:50–2:40)

*Open Chat Analysis. Scroll to a flagged Devanagari or Hinglish line.*

> **"Chat analysis. Every captured message is scored for toxicity by a model trained on real in-game chat — and, because this is built for India, it reads English, romanised Hindi and Devanagari at one threshold, at over 95 percent precision on every register. Each line is tagged typed or spoken, and shows its language."**

*Open Emotion Insights.*

> **"Voice emotion from acoustic features — angry, frustrated, excited — from a model trained on real speech, evaluated speaker-independently. Speech-to-text runs on the phone; raw audio is deleted after feature extraction, never stored."**

*Open Settings → the "What we can and can't see" screen. Scroll it slowly.*

> **"And this screen is the one I'm proudest of: exactly what the system can and cannot see — including the blind spots. Games inside a browser? Invisible. In-game voice chat holding the microphone? We go quiet, not wrong. A monitoring app that hides its blind spots is worse than none."**

---

## Part 3 — Child side: capture, live (2:40–3:50)

*Switch to the ChildApp phone. Show Home briefly (today vs goal, streak).*

> **"The child's side. It's not punitive — a wellbeing home screen, a streak, a check-in, a companion to talk to."**

*Open Roblox. Wait for the session to auto-start — the ParentApp strip (picture-in-picture or cut) reads "Playing Roblox now".*

> **"Now the capture. Open a game — nothing to tap — and within seconds a session starts. The parent's dashboard shows it live."**

*Type one chat line in-game using the Wellbeing Keyboard — include a Hindi word if the game allows text. Say one sentence aloud near the phone.*

> **"Our custom keyboard captures typed chat even in canvas games where accessibility can't read the screen — Roblox is exactly that case — and it has a native Devanagari layout. Speak, and the on-device recogniser transcribes it into the same toxicity model."**

*Close Roblox. Wait ~25 s (trim) for the session-end notification with the risk band.*

> **"Leave the game, and about twenty seconds later the session closes itself and is scored."**

*Cut to ParentApp → pull to refresh → the new session appears.*

> **"And there it is on the parent's side — session, duration, band, contributing factors."**

---

## Part 4 — Anti-tamper (3:50–4:20)

*On the ChildApp, tap Logout. The parent-PIN dialog appears. Enter a wrong PIN → "Incorrect parent PIN".*

> **"A child can't quietly stop monitoring: logout, settings and uninstall protection are all behind the parent's PIN, verified on the server."**

*Turn Accessibility OFF for Gaming Detector in Android Settings. Cut to ParentApp: strip reads "Monitoring degraded — chat capture off", and a permission alert lands.*

> **"Disable a capture permission and the parent knows within seconds — a degraded-monitoring warning and an alert, not a silent gap. Turn it back on, and it clears."**

*(Optional, only if you pre-staged it 15 min earlier: show the "No check-in for N min" offline alert.)*

> **"Force-stop the app entirely and a server-side watchdog raises an offline alert. Even over USB with developer tools, we couldn't remove the app past the uninstall block without the parent PIN — that one we found out the hard way."**

---

## Part 5 — Close (4:20–4:50)

*Cut to a still: the validation slide (deck slide 12) or the paper's §6.6 table.*

> **"Does the score mean anything? We tested it outside our own training data: an anonymous survey — 134 responses, 104 usable — scored through this exact deployed pipeline against a validated clinical instrument. Correlation 0.32, significant, and it carries information self-reported screen time doesn't: partial out the hours — the baseline every commercial tool ships — and the correlation barely moves. The signal comes from *how* people play, not how long. The same study also told us two things we didn't want to hear, and we published both."**

*Title card: repo URL, team, guide.*

> **"Every number in this video is one script in a public repository, and seven CI tests fail the build if the paper and the data ever disagree. Reproducibility and honesty as features. Thank you."**

---

## Editing notes
- Total spoken words ≈ 620 → ~4½ min at a calm pace. If over 5 min, cut Part 0's second sentence and the optional watchdog beat first.
- Trim every wait (session start ~5 s, nudge ~12 s, session end ~25 s) with a hard cut, not a speed-up — speed-ups look like something's being hidden.
- Never show the parent PIN being typed. Mask or cut.
- Keep the "What we can and can't see" screen and the wrong-PIN moment — panels remember the honesty beats more than the feature beats.
- Export at 1080p; put the file next to the deck (`docs/`) **but do not commit it** — link it from the release notes if you want it public.
