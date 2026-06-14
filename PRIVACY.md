# Privacy Policy — Gaming Wellbeing Monitor (PW26_SJ_05)

_Last updated: 2026-06-14 · Consent version: 2026-06-01_

This is a **parental wellbeing tool**: a parent installs the Child app on their
child's device to understand the child's gaming patterns and emotional wellbeing,
and views insights in the Parent app. It is a **research prototype for a university
capstone** — a screening/awareness aid, **not** a medical or diagnostic device.

This policy explains, in plain language, what the app collects, why, who can see
it, how long it is kept, and how to delete it.

## What is collected (only on the monitored child's device)

**While the child is in a monitored game session:**

- **Gaming activity** — which game is in the foreground (any app the device
  classifies as a game, not just a fixed list) and session start/end times. To
  recognise games, the app checks the *category* of installed apps **locally on the
  device**; the list of installed apps is never uploaded.
- **In-game chat the child types** — text the child enters while playing games,
  used for tone/toxicity signals. We capture what the child types, not the
  messages of other players.
- **Short voice clips during a gaming session** — used to estimate emotional
  arousal/tone. **Raw audio is processed into numeric features and then deleted**
  immediately (it is not stored or sent anywhere) unless a developer explicitly
  enables retention for testing. The **spoken words are also transcribed to text
  and kept** (the transcript, not the audio), so the emotional tone of what was
  said can be read.

**Also collected more broadly (including between sessions), as sleep-disruption and
craving signals:**

- **Screen on/off events** — timing only.
- **Game notifications** — the timing and the **title** of notifications shown by
  games (e.g. event/reward prompts).

**Only when the child chooses to:**

- **Daily check-ins** the child voluntarily submits (mood/sleep/energy).

The app does **not** collect: messages outside games, web browsing,
contacts, photos, location, or keystrokes outside in-game chat fields.

## Why it is collected

To compute wellbeing/risk indicators (time spent, late-night play, tone of
chat/voice) that help a parent notice problematic gaming patterns early. These
indicators are **screening signals, not a diagnosis.**

## Who can see it

Only the **parent linked to that child** (the parent signs in with the family **code +
PIN**). The server authenticates every request with a signed token and authorizes by
ownership — a parent can only access **their own** children's data, never another
family's — and applies a **role** check so parent-only actions and views (the alerts
feed, dashboards, reports, feedback, limits, nudges, PIN change, deletion) cannot be
reached with a child's token. PINs are stored as keyed hashes, never in plaintext. In
production all traffic is over HTTPS.

## How long it is kept (retention)

**Raw audio is always deleted right after feature extraction** — it is never stored.

Everything else collected (sessions, chat text, voice-emotion features, screen and
notification events, predictions and alerts) is **kept while the child's account is
active**, so the dashboards and trends keep working, and the **parent can delete it at
any time** (see *Your rights* below). An operator may additionally enable an age-based
auto-purge (`DATA_RETENTION_DAYS`): when set to *N* days, raw events (chat, voice
features, screen/notification events) older than *N* days are deleted automatically.
This is **off by default**, so unless it is enabled the data is retained until the parent
deletes it or removes the account.

## Your rights — view and delete

The **parent** controls the child's data — from the Parent app's Settings they can:
- **Delete the child's data** — erases all sessions, chats, voice features,
  predictions, alerts and events for that child, keeping the account.
- **Remove the child from the family** — the above, plus the child's account record
  itself (their login then stops working).

The child cannot delete their own monitored data (it's a parental wellbeing tool, so
deletion is parent-controlled). Both actions call `POST /api/user/delete_data` and
take effect immediately and permanently.

## Consent

Setting up monitoring requires the parent to **review and accept** this policy on
first launch (recorded with a timestamp and version). Monitoring does not begin
until consent is given. If the policy changes, consent is requested again.

## Important limitations (stated honestly)

- The ML models are **demo-grade**, trained on limited/illustrative data; the risk
  weighting is a clinically-motivated prior, not a validated clinical instrument.
- Emotion labels (e.g. *frustrated, angry, excited, neutral*) **are** shown, but they
  are **rough, best-effort estimates**: derived from the voice's tone (which mainly
  captures how animated the speech is) combined with a simple keyword reading of the
  transcribed words. They are not accurate emotion recognition or a diagnosis, and the
  tone model is adult-trained.
- This tool is intended for a **parent monitoring their own minor child** with that
  child's awareness, as a wellbeing aid — not covert surveillance.

## Contact

PES University Capstone PW26_SJ_05 — Kaustubh Agarwal, Kanak Goyal,
Khushee P Kiran, Vidisha Murali.
