# Demo Video Script — PW26_SAS-03

**Target: 4½–5 minutes.** This is the *backup* for the live demo (DEMO_RUNBOOK → *The 6
minutes*), so it follows the same beats in the same order — if Wi-Fi dies on the day, you
switch to this video at the matching beat and the narrative does not change. Record once,
cleanly; resist the urge to show everything.

**Setup before you press record**
- Backend awake: open `https://gaming-addiction-api.onrender.com/api/health` → `"models_loaded": true`.
- Both phones on and online first, as on the day (DEMO_RUNBOOK pre-flight step 0): ChildApp signed in as **Arjun (PIN 1234)** and running, ParentApp signed in (FAM789 + parent PIN) on Arjun. A child phone silent for 15 min drops a "hasn't checked in" alert into the feed.
- Then reseed the demo family (DEMO_RUNBOOK §2, cloud commands, `SEED_DEMO_FORCE=1`) so the screens match the narration: Some concern, 55%, "Today · 1 session"; Weekly hours 18.8h; Late-night sessions 4; the 14-day trend peaking at High concern, 85%, yesterday. Open no game on the child phone until Part 4. Reseed before every take (or leave 10 minutes between live loops): the server skips the "just started playing" alert when another session began in the last 10 minutes.
- Child phone as in pre-flight step 5: Usage access and Accessibility ON for Gaming Detector, the **Gaming Wellbeing Keyboard** selected, Roblox signed in with a chat-enabled experience ready, game volume low. Device Admin on, so the strip says "Uninstall-protected" rather than a warning.
- Mirror both phones to a laptop with `scrcpy` and record the desktop: from Part 3 on, the beats switch phones (or record each phone and cut on the beats). Do NOT record the parent PIN entry keystrokes on camera — mask or cut.
- Two takes minimum. Keep the one where nothing loads slowly.

Timings are what to aim for, not a metronome. **Bold** = what to say. *Italic* = what to do.

---

## Part 0 — Cold open (0:00–0:30)

*Slide or plain title card: "AI-Driven Gaming Addiction Screening — PW26_SAS-03".*

> **"Parental-control tools tell you how long your child played. They can't tell three hours of healthy play from three hours of compulsive play. This is a screening system that watches *how* a child plays — the late-night sessions, the rapid re-logins, the rising toxicity in chat and voice — and turns it into one signal a parent can act on. Two Android apps, a cloud ML backend, live in production. Arjun's history is seeded demo data; the session you're about to see is real. Let's see it."**

---

## Part 1 — Parent side: the signal (0:30–1:30)

*ParentApp on Arjun's Dashboard, already signed in, as in the live demo. Hold two seconds on the header — "Some concern", "55%", "Today · 1 session", the strip "🟢 Monitoring active" — and on the Weekly hours (18.8h) and Late-night sessions (4) cards.*

> **"This is the parent's view. Today's band for Arjun: Some concern, 55 percent, from one session earlier today. 18.8 hours of play this week, four sessions late at night. Up top, the live status strip: monitoring is active, and when he's in a game it says so, live."**

*Scroll slowly to "Latest session factors & daily signals", then on to the 14-day trend.*

> **"Below: *why*. The latest session's top four factors — an up-arrow raised the score, a down-arrow lowered it, each with its share. Not a black box: these are SHAP attributions, computed live by the deployed model. Further down, the fourteen-day trend climbs from 42 percent to High concern — 85 percent — yesterday, then today's 55. The app says Low, Some or High concern, and so do we."**

*Tap Alerts. Scroll to "Arjun reached High concern — score 85%."*

> **"Alerts reach every guardian in the family in real time — risk, toxic chat, tamper events. And here's the feedback loop:"** *tap ✓ Accurate.* **"A parent rates each risk alert. Those verdicts feed a threshold tuner — the only source of real labels in the system — and the banner shows the agreement rate so far. Operational alerts carry no rating buttons, by design."**

---

## Part 2 — Parent side: chat, voice, transparency (1:30–2:15)

*Open Chat Analysis: the toxicity bands, the "Channel mix" line with its Hindi-script count, and the flagged samples, each tagged ⌨️ Typed or 🎙️ Voice plus a language tag.*

> **"Chat analysis. Every captured message is scored for toxicity by a model trained on real in-game chat — and, because this is built for India, it reads English, romanised Hindi and Devanagari at one threshold, at over 95 percent precision on every register. Each line is tagged typed or spoken, with its script."**

*Open Emotion Insights.*

> **"Voice emotion from acoustic features — angry, frustrated, excited — from a model trained on real speech, evaluated speaker-independently. Speech-to-text runs on the phone; raw audio is deleted after feature extraction, never stored."**

*Open Settings → the "What we can and can't see" screen. Scroll it slowly.*

> **"And this screen is the one I'm proudest of: exactly what the system can and cannot see — including the blind spots. Other players' messages? Never captured, only the child's own words. Spoken Hindi? Not yet. Anything outside a monitored game? Invisible. A monitoring app that hides its blind spots is worse than none."**

---

## Part 3 — Child side: home, check-in, Mira (2:15–2:35)

*Switch to the ChildApp phone. Home (today vs goal, streak) → View my dashboard → Daily Check-in: mood, sleep, energy → Submit. Then Talk to Mira: type one line ("i cant stop playing") and show the reply.*

> **"The child's side. It's not punitive — a wellbeing home screen, a streak, a daily check-in, and Mira, a companion to talk to."**

---

## Part 4 — The live loop (2:35–4:05)

*Open Roblox and tap nothing; trim the ~10 s wait. Cut to the ParentApp (pull to refresh if needed): the strip reads "🎮 Playing Roblox now", and the alert "Arjun just started playing Roblox." is in.*

> **"Now the capture, live. Open a game — nothing to tap — and within about ten seconds a session starts. The parent's dashboard shows it live, with a just-started alert."**

*In Roblox chat, type one line on the Wellbeing Keyboard: "ugh this team is so bad bhai". Then say one English sentence near the phone, a little frustrated: "I keep losing, just one more game".*

> **"Our custom keyboard captures typed chat even in canvas games where accessibility can't read the screen — Roblox is exactly that case — and its Devanagari layout is in beta. Speak, and the on-device recogniser transcribes it into the same toxicity model."**

*Close Roblox (swipe it away). During the ~25 s wait, on the ParentApp: Save PDF (next to Report) → the share sheet opens with the weekly report. Cut back to the ChildApp phone as "Roblox session ended" lands, with this session's band.*

> **"Leave the game, and about twenty-five seconds later the session closes itself and is scored. Meanwhile the parent saves this week's report — a PDF the server builds on request."**

*ParentApp: pull to refresh. The header reads "Today · 2 sessions"; the factors card now explains this session; Roblox leads "Recently played" under Top games. Then Chat Analysis: the typed line and the transcript are the top rows.*

> **"Pull to refresh. Today now counts two sessions and barely moves — the headline weighs the whole day by duration. The factors card now explains the session that just ended. And in Chat Analysis, on top: the typed line, and the spoken sentence, tagged voice."**

*Alerts → this session's alert, "Gaming pattern reached … concern — score …%" → ✓ Accurate or ✗ False alarm. The banner updates.*

> **"This session's own alert, with its band and score. Alerts are raised only at Some or High concern — a Low session stays quiet, by design. Rate it, and the banner updates."**

*(Only if the one-time score-version note is also in Alerts: hold on it for a beat.)*

> **"That note goes once to every parent whose child was scored before 23 November: version 2 of the score dropped the game-genre adjustment, because our survey found no evidence for it. Nothing to rate."**

*Dashboard → Send a nudge to your child → "Time to take a break 🙂". Cut to the ChildApp phone as the notification lands (~12 s; trim the wait).*

> **"And it's two-way. A nudge from the parent lands on the child's phone as a notification in about twelve seconds — guidance, not just surveillance."**

---

## Part 5 — Anti-tamper (4:05–4:30)

*On the ChildApp, tap Logout → "Parent PIN required". Enter a wrong PIN → Unlock → "Incorrect parent PIN"; Arjun stays signed in. (Cancel, if the dialog is still open.)*

> **"A child can't quietly stop monitoring: logout and settings sit behind the parent's PIN — which the child never knows — verified on the server."**

*Turn Accessibility OFF for Gaming Detector in Android Settings. Cut to ParentApp: the strip reads "Monitoring degraded — chat capture off", and the alert "Arjun turned off chat capture (Accessibility) — monitoring is now degraded." lands. Turn it back ON: the warning clears.*

> **"Disable a capture permission and the parent knows within seconds — a degraded-monitoring warning and an alert, not a silent gap. Turn it back on, and it clears."**

*(Optional, a separate take after the main one: force-stop the ChildApp, wait 15 min outside 22:00–07:00, then show the strip "No check-in for …" and the offline alert.)*

> **"Force-stop the app entirely and a server-side watchdog raises an offline alert. Even over USB with developer tools, we couldn't remove the app past its uninstall block — that one we found out the hard way."**

---

## Part 6 — Close (4:30–5:00)

*Cut to a still: Review 3 deck slide 27, "How adults play tracks the IGDS9-SF", or the survey table in report §8.8 (PROJECT_PAPER §6.10, "External construct validation").*

> **"Does the score mean anything? We tested it outside our own training data: an anonymous survey of adult gamers — 134 responses, 104 usable — with the deployed behaviour model scoring how each person plays, set against the IGDS9-SF, a validated nine-item questionnaire. Correlation 0.32, significant, and it carries information self-reported screen time doesn't: partial out the hours — the baseline every commercial tool ships — and the correlation barely moves. The signal comes from *how* people play, not how long. The same study also told us two things we didn't want to hear, and we published both."**

*Title card: repo URL, team, guide.*

> **"Every number in this video is one script in a public repository, and research-integrity tests in CI fail the build if the paper's survey numbers and the data ever disagree. Reproducibility and honesty as features. Thank you."**

---

## Editing notes
- Total spoken words ≈ 700 → ~5 min at a calm pace. If over 5 min, cut the optional watchdog beat and Part 0's second sentence first, then follow the runbook's "Behind schedule?" order: Emotion Insights, then the check-in, then Mira. Never cut the live loop or the permission alert.
- Trim every wait (session start ~10 s, session end ~25 s, nudge ~12 s) with a hard cut, not a speed-up — speed-ups look like something's being hidden.
- Note where Part 4 starts: if no session starts on the day, the runbook plays this video's live part, then does the tamper steps live.
- Inputs stay on-story: frustrated, not offensive. A session that lands at Low concern raises no alert, by design, so Part 4 has nothing to rate: retake.
- Never show the parent PIN being typed. Mask or cut.
- Keep the "What we can and can't see" screen and the wrong-PIN moment — panels remember the honesty beats more than the feature beats.
- Export at 1080p as a local file on the presenting laptop's desktop, tested to play offline (DEMO_RUNBOOK pre-flight step 6), **but do not commit it** — link it from the release notes if you want it public.
