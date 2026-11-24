# Demo Runbook — Gaming Addiction Detection (PW26_SAS-03)

A reliable, repeatable script for demoing both apps live. Follow top to bottom.

---

## Review 3 demo — 6 minutes

**Slot:** [slot: fill in] (department window 23–27 Nov 2026). **Deck:** slide 17
*Project Demonstration* (order 300, Khushee, 35 s) is the map; switch to the phones after
it and resume at slide 18 *Test Plan and Strategy* (Kanak). Criterion: "demonstration
complete in all aspects": UI, module-wise functionality, integration.

**Roles:** Khushee drives (child phone, the clock, every cue); Vidisha holds the parent
phone and narrates the ParentApp; Kanak at the laptop (health page open, backup video
cued); Kaustubh takes model questions (score v2, SHAP). Mirror both phones to the
projector (scrcpy over USB, tested the day before) or hold each up at its beat.

**Live or seeded (say it before anyone asks).** *Seeded* by `backend/seed_demo.py` at the
morning reseed: Arjun's 16 and Priya's 11 sessions (the last one "earlier today") and their
scores, which are written by hand in `SESSION_PLAN` / `PRIYA_PLAN` and are not model outputs;
their chat lines, voice emotions, risk alerts, 14 days of check-ins, the Mira conversation
and the streaks. *Live*: every screen (read from the cloud server as you tap); the factors
card (SHAP computed by the deployed model on the latest session's behaviour row); verdicts
and the agreement banner; the weekly PDF (generated on request); the nudge; the whole
Roblox session from detection to score; the score-version note; the Logout PIN check; the
permission alert. The app says Low / Some / High concern, and so do we. Never "addicted".

### Pre-flight — in this order

0. **Both phones on and online first**: ChildApp signed in as Arjun and running, ParentApp
   signed in (FAM789 + 0000) on Arjun. Step 3 explains why this comes first.
1. **Score v2 is live** (true since 23 Nov 2026): open
   `https://gaming-addiction-api.onrender.com/api/model_card` → `"score_version": 2`
   and the fusion note "Score version 2 removed the earlier game-genre multiplier…".
   The first request after a sleep takes ~40 s (step 4 says why).
2. **Reseed the demo family on the morning of the slot** (§2, cloud commands). The seed
   anchors each child's "earlier today" session to the moment it runs, so the Today cards
   and the 14-day trend end on the review day. Open no game on the child phone while it
   runs, because it deletes every session of ids 1 and 3, an open one included.
   - **Does a reseed make the demo children get the one-time score-version note? Yes:
     once per child, on that child's next score.** `seed_demo.py` deletes every alert of
     ids 1 and 3 (any earlier `score_update` note with them). It also writes their history
     predictions without `score_version`, so the whole history is stored as NULL, which
     means score v1. After every v2 score, `_maybe_insert_score_v2_notice`
     (backend/app.py) adds the note if the child has no `score_update` alert yet and has
     at least one NULL-version prediction. The seeded rows already carry scores, so
     nothing re-scores them, and Arjun's next score is the live Roblox session. The note
     lands during that session, on the first accepted voice segment (a live re-score) or
     at the latest at session end. Priya gets hers only if she plays.
   - **What the panel sees:** the note is severity low and is never pushed (the
     ParentApp's poller may show a quiet notification). It has no Accurate / False alarm
     buttons. The partial unique index `idx_alerts_one_score_update` makes it at most one
     per child.
   - **Exception:** the check is cached in the server process (`_SCORE_V2_NOTICE_SETTLED`;
     the free plan runs one gunicorn worker). If Arjun was already scored in that process
     before the reseed, for example by a same-day rehearsal, no note appears until the
     worker restarts. It restarts after a free-tier sleep (~15 min with no requests) or
     after ~500–550 requests. The ChildApp's 3-minute heartbeat keeps the server awake,
     so a sleep only happens when the phones are off.
   - **Keep the note; don't clear it.** It is the versioned change working as promised:
     genre multiplier gone, parents told once instead of a silent swap. It is also exactly
     what a family with pre-23-Nov history receives. Clearing it doesn't work: deleting
     the row only re-arms it for a later score. So rehearse the live loop the day before,
     then let the server sleep once (phones off overnight). After the reseed, open no game
     on the child phone until the live loop.
   - **Vidisha's line when the note appears:** "This is the one-time note every parent
     whose child was scored before 23 November gets: version 2 dropped the game-genre
     adjustment because our survey found no evidence for it. It cannot repeat, and it
     isn't an alert to rate." If it doesn't appear, skip the line; if asked, open the
     model card (step 1).
3. **End-to-end check, then remove what it leaves behind.** Use the same PowerShell window,
   from `backend/`, with the §2 variables still set:
   ```powershell
   python scripts/cloud_e2e.py     # every check must pass (exit code 0)
   # now open Arjun, then Priya, once in the ParentApp (then back to Arjun), then:
   python -c "from app import get_db; db=get_db(); cur=db.cursor(); cur.execute('DELETE FROM reflections WHERE user_id=? AND note=?', (1, 'e2e check')); n=cur.rowcount; cur.execute('DELETE FROM alerts WHERE user_id IN (1, 3) AND type IN (?, ?)', ('login', 'offline')); print('reflections deleted:', n, 'alerts deleted:', cur.rowcount); db.commit(); db.close()"
   $env:DATABASE_URL=""; $env:PIN_PEPPER=""; $env:SEED_DEMO_FORCE=""
   ```
   - **Why after the reseed:** its logins prove the reseeded PINs work, so a wrong
     `PIN_PEPPER` fails here and not in front of the panel. It creates no session and no
     score, so it never triggers the note.
   - **What it leaves:** an "e2e check" check-in dated today; an info alert "Arjun signed
     in to the monitoring app" in the parent feed; one Mira exchange ("i cant stop
     playing", which is on-story, so leave it); and Arjun's daily limit set to 3 h. The
     command removes the first two.
   - **Why the command also removes `offline` alerts:** reading a feed while the child
     phone has been silent ≥15 min (outside 22:00–07:00) raises a high "monitoring app
     hasn't checked in" alert and push. That is why step 0 puts the phones online first,
     and why you open both children before the cleanup.
4. **Wake the backend at T-30 min and again at T-2 min.** Open
   `https://gaming-addiction-api.onrender.com/api/health` until it shows
   `"models_loaded": true` (or GitHub → Actions → keep-backend-warm → Run workflow).
   Cold start is ~40 s; warm requests take ~210 ms from Bengaluru.
   - **Why it sleeps:** Render's free plan spins the service down after ~15 min without
     requests. The scheduled keepalive (`.github/workflows/keepalive.yml`) has been off
     since 30 Jul 2026. Its 14-minute ping kept Render awake 24/7, and the open Postgres
     connections stopped Neon from ever scaling to zero. That used up the free 100
     CU-hour monthly allowance and paused the database. A wake before a demo costs
     minutes of Neon compute, not the month.
   - **Why twice:** T-30 leaves time to react, or to switch to the laptop backend
     (§0 Option B). T-2 covers a slot that slipped.
   - **Also at T-30:** pull to refresh the ParentApp; the strip should read "Monitoring
     active".
5. **Phones (check at T-30).**
   - **Both:** charged, with chargers; on the venue Wi-Fi (open the health URL in each
     phone's browser; a phone hotspot is the fallback); latest release APKs installed.
   - **Child phone:**
     - Usage access ON and Accessibility ON for Gaming Detector.
     - **Gaming Wellbeing Keyboard** enabled *and* selected as the active keyboard. Roblox
       draws its own chat box, so only this keyboard captures it.
     - Microphone and notifications allowed; Do Not Disturb and battery saver off.
     - Roblox signed in, a chat-enabled experience ready, game volume low (the speech
       gate needs ≥35% speech frames).
   - **Parent phone:** notifications allowed, Arjun selected.
6. **Backup video** on the laptop desktop as a local file, tested to play offline. It
   should follow the same order as the script below, so switching to it keeps the story.

### The 6 minutes

| Time | Criterion | Who | Do — and say | Live / seeded |
|------|-----------|-----|--------------|---------------|
| 0:00–0:15 | — | Khushee | Slide 17: "One box per criterion. Arjun's history is seeded demo data; today's session is live." Switch to the phones. | — |
| 0:15–0:40 | UI · module: scoring with SHAP reasons | Vidisha, parent phone | Dashboard, Arjun: Today's band (fresh reseed: Some concern, ~55%, from the seeded morning session); the 14-day trend climbing to High concern (85% yesterday); strip "Monitoring active". Scroll to *Latest session factors & daily signals*: ▲ raises, ▼ lowers, with each factor's share. These are SHAP attributions. | Seeded history; factors live |
| 0:40–1:00 | Module: alerts + verdicts | Vidisha | Alerts → "Arjun reached High concern — score 85%." → *Accurate* → agreement banner. Operational alerts have no rating buttons, by design. | Seeded alert; live verdict |
| 1:00–1:20 | Module: what capture produced | Vidisha | Chat Analysis: typed vs spoken lines, toxicity bands, a Hinglish / Devanagari line. Emotion Insights: the voice emotion mix. | Seeded |
| 1:20–1:35 | Module: transparency | Vidisha | Settings → *What we can and can't see*, scrolled slowly. (*How the risk score works* is the live model card; its accuracy is on simulated labels.) | Static text |
| 1:35–2:00 | UI (child) | Khushee, child phone | ChildApp Home (today vs goal, streak) → Daily check-in → Mira: one line, show the reply. | Live |
| 2:00–2:15 | Integration 1 · module: session auto-start | Khushee → Vidisha | Open Roblox and tap nothing: the session starts in ~10 s. Parent phone (pull to refresh if needed): strip "Playing Roblox now" and a "just started playing Roblox" alert. | Live |
| 2:15–2:45 | Integration 2 · modules: keyboard capture, on-device STT | Khushee | In Roblox chat, type one line on the Wellbeing Keyboard ("ugh this team is so bad bhai"). Say one English sentence near the phone, a little frustrated ("I keep losing, just one more game"). | Live |
| 2:45–3:20 | Integration 3 · module: weekly PDF (fills the wait) | Khushee, then Vidisha | Close Roblox (swipe it away). ~25 s later the session ends by itself and the child phone shows the scored notification. Meanwhile Vidisha: Weekly Report → Download PDF. | Live (PDF generated now) |
| 3:20–4:00 | Integration 4: score v2 + reasons reach the parent | Vidisha | Pull to refresh: the new Roblox session and its band; the factors card now explains *this* session. Chat Analysis top rows: the typed line and the transcript of the sentence. If the score-version note is in Alerts, use the step-2 line. | Live |
| 4:00–4:20 | Integration 5: verdict | Vidisha | Alerts → this session's risk alert (raised only at Some or High concern) → *Accurate* or *False alarm* → the banner updates. | Live |
| 4:20–4:40 | Integration 6: nudge back | Vidisha → Khushee | Dashboard → Send a nudge → "Time to take a break" → it lands on the child phone in ~12 s. | Live |
| 4:40–4:55 | Module: tamper (PIN) | Khushee | ChildApp → Logout → the parent PIN is demanded; a wrong one is refused (server-verified). Cancel. | Live |
| 4:55–5:25 | Module: tamper (the fast one) | Khushee → Vidisha | Android Settings → Accessibility → Gaming Detector → OFF. Within seconds: "Monitoring degraded — chat capture off" + a `permission` alert. Back ON: the warning clears. | Live |
| 5:25–6:00 | Buffer, close | Khushee | "Every module, live, end to end." Back to slide 18. | — |

- **Behind schedule?** Cut Emotion Insights, then the check-in, then Mira. Never cut the
  live loop or the permission alert.
- **Inputs:** stay on-story: frustrated, not offensive. Calm inputs still work, but they
  enter the fused score as low chat and voice scores. The session can then land at Low
  concern, which by design raises no alert. A toxicity alert needs a chat score ≥ 0.95,
  so there is no need to provoke one in front of the panel.
- **"Where is score v2 on screen?"** The ParentApp doesn't print the version. The evidence
  is the one-time note, the model card (`score_version: 2`) and the `score_version`
  stored on every new prediction.
- **"Why did Today barely move?"** The headline is the duration-weighted roll-up of the
  whole day, so a two-minute session can't outweigh the seeded 95-minute one.

| If, during the 6 minutes… | Do |
|---------------------------|----|
| No session 20 s after opening Roblox | Check Usage access and that the ChildApp is running; else say so, play the backup video's live part, then do the tamper steps live |
| Typed line missing from Chat Analysis | The Wellbeing Keyboard wasn't active: switch keyboards, retype |
| No transcript | Speak closer and longer, game quieter, in English |
| No risk alert for the live session | It scored Low concern, so by design no alert; say so (a rating was shown at 0:40) |
| No score-version note | Arjun was already scored in this server process (pre-flight step 2); skip the line |
| Server spinning > 60 s, or Wi-Fi down | Phone hotspot; else the backup video |

---

## 0. Two ways to run — pick one

### Option A — Cloud (Render) — RECOMMENDED
Nothing to start. The backend is deployed at **https://gaming-addiction-api.onrender.com**
(Docker on Render's free plan + Neon Postgres + HTTPS, auth enforced). It is **not**
always-on. The free plan sleeps after ~15 min without requests, and the scheduled
keepalive has been off since 30 Jul 2026, because keeping Render awake used up Neon's free
compute allowance (Review 3 pre-flight, step 4).
- Both apps **already default to this URL** (Settings → Server URL).
- The phone just needs **internet** (WiFi or mobile data) — no laptop, no USB, no adb.
- **Pre-warm before presenting:** the first request after a sleep takes ~40 s. Open
  `https://gaming-addiction-api.onrender.com/api/health` in a browser and wait until it
  shows `"models_loaded": true`. For Review 3, do this at T-30 min and again at T-2 min.
  Then it's fast (~210 ms warm from Bengaluru).

### Option B — Local (laptop backend over USB) — offline fallback
- Phone connected via **USB**, USB debugging ON; both apps installed (signed APKs:
  [GitHub release](https://github.com/kaustubhagarwal21/gaming-addiction-detection-capstone/releases/latest)).
- In **each app → Settings → Server URL = `http://127.0.0.1:5000/`** → Save.
- Quit Docker Desktop (frees port 5000), then from `backend/`:
  ```powershell
  .\demo_setup.ps1 -Seed        # adb tunnel + reseed + start backend (leave window open)
  ```

## 1. Demo logins (same for cloud or local)

The demo family is set up exactly like a **real registered family** — so this is the
actual product flow, not a shortcut.

| Who | App | How to sign in |
|-----|-----|----------------|
| Child — Arjun (escalates to High concern) | Child app | PIN **1234** |
| Child — Priya (milder Roblox story) | Child app | PIN **5678** |
| Parent (sees both children) | Parent app | Family code **FAM789** + Parent PIN **0000** |

> A real family creates this themselves in the Child app (**Create an account** → it
> shows the family code), then signs into the Parent app with that code + PIN. The demo
> family just comes pre-seeded with code **FAM789**.

## 2. Health check + (re)seed
- **Health** — Cloud: open `https://gaming-addiction-api.onrender.com/api/health` →
  `"models_loaded": true`.  Local: `curl http://127.0.0.1:5000/api/health`
  (re-run `adb reverse tcp:5000 tcp:5000` if the phone can't reach it).
- **Reseed the Arjun/Priya demo data** if it's missing or you wiped it:
  - Local: `python seed_demo.py`
  - Cloud (the live Neon database behind Render): the script touches **only user ids 1
    and 3**. It overwrites their names + PINs with the published demo credentials and
    deletes all their data, so it refuses to run on Postgres unless you force it. On this
    deployment ids 1 and 3 are the demo family (FAM789). Check that before forcing: the
    `python -c` line prints them. Never force it on a database where they are not. From
    `backend/`:
    ```powershell
    $env:DATABASE_URL="<Neon URL: Render dashboard → Environment → DATABASE_URL>"; $env:PIN_PEPPER="<Render PIN_PEPPER>"; $env:SEED_DEMO_FORCE="1"
    python -c "from app import get_db; db=get_db(); cur=db.cursor(); cur.execute('SELECT user_id, name, family_code FROM users WHERE user_id IN (1, 3)'); print([dict(r) for r in cur.fetchall()])"
    python seed_demo.py
    $env:DATABASE_URL=""; $env:PIN_PEPPER=""; $env:SEED_DEMO_FORCE=""
    ```
    For Review 3, keep the variables set until the e2e check and cleanup are done
    (pre-flight step 3), then run the last line.

---

## 3. Demo flow (suggested narrative)

> This is the long-form reference. For Review 3, run the 6-minute script at the top, not
> this order. The script keeps the outline (parent tour, child + live loop, tamper) but moves
> four beats: the transparency screen joins the parent tour (1:20); the weekly PDF moves out
> of the tour (A.7) into the session-end wait (2:45–3:20); the nudge now closes the live loop
> (4:20); and the Logout-PIN check moves from the child tour (B.6) to after the nudge
> (4:40–4:55). The deck's slide-17 notes, the briefing and the backup video follow the script.

### 0. Onboarding — how a real family signs up (optional, ~30s)
Shows it's a real product, not canned accounts. (The seeded Arjun/Priya family below
was created exactly this way — they just come pre-loaded with rich history.)
1. **ChildApp → Create an account**: enter a child name/age + a child PIN, **leave the
   family code blank** → it generates and shows a **family code** to use in the Parent app.
2. **ParentApp**: sign in with that **family code + the parent PIN** → the child appears.
3. (Adding a sibling later? Set them up in the ChildApp using the *same* family code.)
   *(This creates a real account; delete it afterwards via ChildApp → Settings → Delete My Data.)*

Then switch to the pre-seeded family for the data-rich story:

### A. Parent side — the "wow" (start here)
1. Open **ParentApp** → sign in with family code **FAM789** + PIN **0000** → pick **Arjun**.
2. **Dashboard**: the concern band for the latest active day, plus weekly hours, the
   14-day trend rising to High concern (85% yesterday), contributing factors — and the
   **live status strip** in the header ("🟢 Monitoring active", and "🎮 Playing … now"
   whenever a session is live). After a fresh reseed the band reads Today, Some concern
   ~55%, from the seeded morning session, because the headline is that day's
   duration-weighted roll-up.
3. **Alerts**: high-risk alerts with friendly ages ("2h ago"). **Rate one** — tap
   *Accurate* or *False alarm* on a risk alert → the **agreement banner** appears at the
   top ("based on your N verdicts…"). This is the feedback loop the paper describes.
4. **Send a nudge**: Dashboard → *Send a nudge* → pick "Time to take a break 🙂" → it
   pops up as a notification on the child's phone within ~12 s. Two-way, not just watching.
5. **Emotion Insights**: real emotion breakdown (angry/frustrated/excited) from voice.
6. **Chat Analysis**: avg toxicity + flagged messages (typed ⌨️ vs voice 🎙️ tagged).
7. **Weekly Report → Download PDF**: generates a shareable PDF report.
8. (Optional) Switch child → **Priya** (no re-login needed) for a milder pattern.

### B. Child side — how it's captured
1. Open **ChildApp** (Arjun is logged in).
2. **Home**: today-vs-goal progress, streak, "try instead" suggestions.
3. **Dashboard**: the child's own view — streak, risk, history.
4. **Mira (counselor)**: send a message → typing indicator → supportive reply.
5. **Daily check-in**: submit mood/sleep/energy → streak celebration.
6. (Optional tamper point) Tap **Logout** → it demands the **parent PIN** (server-verified;
   wrong PIN refused) — the child can't quietly stop monitoring.

### C. Live capture (required for Review 3: this is the integration criterion)
1. Open **Roblox** → within ~10 s a session auto-starts (no tapping).
2. Type a chat message in-game, speak a sentence.
3. Close Roblox → ~25 s later the session auto-ends with a risk notification.
4. Back in ParentApp dashboard → pull to refresh → the new session appears (during
   play, the header strip showed "🎮 Playing Roblox now · N min" live).
5. (Behind the scenes) `python verify_captures.py --limit 0` shows the captured
   chat + voice transcript + fused emotion for that session.

### D. Tamper watchdog (strong closer — optional, needs ~15 min lead time)
Force-stop the ChildApp (Android Settings → Apps → Force stop) ~15 min **before** Q&A;
during Q&A, show the ParentApp: the header strip reads "🔴 No check-in for N min" and an
**offline alert** ("monitoring app hasn't checked in…") sits in the alerts feed —
uninstall/kill/offline detection working live.

### D2. Capture-permission tamper (fast tamper demo — no lead time)
With both apps open, on the ChildApp phone turn **Accessibility OFF** (Settings →
Accessibility → Gaming Detector). Within seconds the ChildApp's change-triggered heartbeat
reports it; the ParentApp dashboard strip shows "⚠️ Monitoring degraded — chat capture off"
and a **`permission` alert + push** arrives ("…turned off chat capture (Accessibility) —
monitoring is now degraded"). Turn it back on → the warning clears (no duplicate alert is
raised while it stays off). Demonstrates that silently disabling a capture path is treated
as a tamper event, not just a passive badge.

---

## 4. If something breaks (recovery)

| Symptom | Fix |
|---------|-----|
| **Cloud:** first request slow / times out | Free tier woke from sleep — wait ~40 s and retry; pre-warm via the health URL (Review 3: T-30 and T-2 min) |
| **Cloud:** network error on phone | Confirm the phone has WiFi/mobile data; open the health URL in the phone's browser |
| **Cloud:** login fails after reseed | The seed used the wrong `PIN_PEPPER` — reseed with Render's exact `PIN_PEPPER` value |
| Parent login: "Invalid family code or PIN" | Use **family code FAM789 + PIN 0000**; ensure you installed the **latest ParentApp** (older builds had no family-code field) |
| **Local:** app shows network error | Re-run `adb reverse tcp:5000 tcp:5000` (USB tunnel dropped) |
| **Local:** backend not responding | Restart it (`.\demo_setup.ps1`) — and quit Docker Desktop so port 5000 is free |
| Data looks wrong / want a clean slate | Re-seed (see §2) then pull-to-refresh the app |
| Session won't auto-start | Confirm UsageStats + Accessibility permissions are ON in ChildApp |
| ChildApp "keeps stopping" | Fixed — voice mic service now degrades gracefully on Android 14; reinstall the latest APK |

---

## 5. Honest talking points (for Q&A)

- **Architecture:** multimodal 3-model ensemble — behavioral telemetry (10 objective
  features, server-computed from session history; 10 psychometric proxies serve as
  UI-level explanations), chat toxicity (calibrated Logistic Regression on
  word+char_wb TF-IDF, trained on real gaming-domain corpora — CONDA + Davidson —
  with **alert precision 0.956 (recall 0.428) at the deployed 0.95 threshold on held-out
  real gaming chat**), and voice emotion
  (HistGradientBoosting on 36 acoustic features, trained on 4 real speech corpora /
  154 speakers / 3 languages, **speaker-independent** evaluation; fused with lexical
  valence from on-device Vosk transcription).
- **Ensemble weighting (40/30/30):** a clinically-motivated *prior* — behavior dominant
  per DSM-5 IGD / ICD-11 Gaming Disorder; weights re-normalize by data availability.
  The chat channel's premise is empirically supported twice over (toxic-speech
  involvement ↔ higher IGDS9-SF severity: r=+0.156 in the LatAm dataset, n=11,191;
  ρ=+0.323 replicated in our own survey, n=103); weight *fitting* awaits real labels
  via the feedback loop.
- **External validation (lead with this if asked "does it work?"):** an anonymous adult
  IGDS9-SF survey (134 raw / 104 usable) scored through the deployed pipeline — the
  served risk score tracks the clinical instrument at **ρ = 0.317** [0.137, 0.478],
  **leads the self-reported screen-time baseline** it replaces in 97.4% of paired
  resamples (hours: ρ = 0.147, CI spanning zero), and survives partialling the
  baseline out (ρ = 0.303, CI excluding zero). The signal sits in the *pattern* features, not
  the volume ones: the pattern − volume contrast is +0.199 [+0.019, +0.380], which excludes
  zero (a secondary analysis; the primary is the ρ = 0.317). Report §8.8; paper §6.10.
- **Known limitations (state these proactively):** the behaviour model's *training
  labels* are still synthetic screening priors, so the 91.6% accuracy is a
  synthetic-distribution number and the survey does not upgrade it — what the survey
  validates is that the score *means* something, not how accurate it is at a clinical
  cut-off (uncomputable here: one disordered-range respondent in 104 usable). The voice corpora
  are acted adult speech, a proxy for child gaming speech; and the ensemble weights are
  priors, not fitted. The feedback loop + drift monitor + validation plan are exactly the
  instruments that address these with pilot data.
- **Genre multiplier (no longer a limitation).** The same survey found no genre effect
  (Kruskal–Wallis p = 0.598, at only 32% power, so underpowered rather than disproven). It
  was removed from the served score as score version 2, deployed 23 Nov 2026. Parents whose
  child has earlier history get a one-time in-app note, and no setting can bring it back.
- **Privacy:** raw audio is processed and discarded after feature extraction (the
  spoken words are transcribed to text and kept, the audio is not); capture is scoped
  to active gaming sessions of any app the device classifies as a game.
- **Security:** login issues a signed bearer token (HMAC); every request carries it and
  the server authorizes by ownership — a parent can read only their own children's data
  (cross-account access returns 403), and PINs are stored as keyed hashes, never plaintext.
  The cloud server runs with `AUTH_ENFORCE=1` (render.yaml): a request without a valid
  token gets 401, and `scripts/cloud_e2e.py` checks both guards (the 401 and the
  cross-account 403). A local backend defaults to **shadow mode**, which verifies and logs
  but doesn't reject; start it with `.\demo_setup.ps1 -Enforce` to enforce locally too.
