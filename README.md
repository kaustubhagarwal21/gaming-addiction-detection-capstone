# Gaming Addiction Detection & Parental Monitoring

**PES University Capstone — PW26_SJ_05**
Team: Kaustubh Agarwal · Kanak Goyal · Khushee P Kiran · Vidisha Murali

A screening system that helps parents understand a child's gaming habits. A **Child app**
quietly collects gaming behaviour (session times, in-game chat, voice tone) on the child's
phone; a **cloud backend** runs a 3-model ML ensemble (behaviour + chat-toxicity + voice-emotion)
to produce a *screening* risk signal with an explanation; a **Parent app** shows the risk,
alerts, trends, and lets the parent confirm whether an alert was accurate.

> It's a **screening / awareness** tool, not a clinical diagnosis. See [PRIVACY.md](PRIVACY.md)
> and the honest-evaluation sections of the project paper ([docs/PROJECT_PAPER.tex](docs/PROJECT_PAPER.tex)).

---

## TL;DR for a teammate

```bash
git clone https://github.com/kaustubhagarwal21/gaming-addiction-detection-capstone.git
```
1. Open **`android/ChildApp`** in Android Studio → let Gradle sync → **Run** on a phone/emulator.
2. Open **`android/ParentApp`** the same way → **Run**.
3. They already point at the **live cloud backend** — no backend setup needed.
4. Log in with the demo accounts below.

That's it for normal development. You only need extra files (signing key, DB creds) for
specific tasks — see [Secrets](#secrets-not-in-the-repo).

---

## Repository layout

| Folder | What it is |
|---|---|
| `android/ChildApp/` | Child Android app (`com.pes.gamingdetector`) — monitoring + wellness |
| `android/ParentApp/` | Parent Android app (`com.pes.parentmonitor`) — dashboard + alerts |
| `backend/` | Flask REST API + ML models (`app.py`), tests, `seed_demo.py` |
| `ml/` | Model training / evaluation scripts |
| `data/` | Training datasets |
| `docs/` | Project paper (LaTeX) |
| `capstone/` | Capstone report documents (deliverables) |

---

## Prerequisites

- **Android Studio** (latest) with an Android SDK — for the apps.
- A device or emulator running **Android 8.0+ (API 26)**. A real phone is best (the Child
  app uses usage-stats / accessibility / mic that emulators don't fully support).
- **Python 3.11+** — only if you want to run the backend locally (optional).

---

## 1. Get the code

Ask **Kaustubh** to add you as a **collaborator** on the GitHub repo (Settings → Collaborators),
then:
```bash
git clone https://github.com/kaustubhagarwal21/gaming-addiction-detection-capstone.git
cd gaming-addiction-detection-capstone
```

---

## 2. Run the Android apps

Open each app as its own project in Android Studio:
- **`android/ChildApp`** and **`android/ParentApp`** (open them separately, not the repo root).

Android Studio will auto-create `local.properties` (your SDK path) and download Gradle
dependencies. Then press **Run ▶**. Or from the command line:
```bash
cd android/ChildApp  && ./gradlew installDebug    # ./gradlew.bat on Windows
cd android/ParentApp && ./gradlew installDebug
```

The apps default to the **deployed backend** (`https://gaming-addiction-api.onrender.com/`),
so they work immediately. You can override this in each app's **Settings → Server URL** if you
run the backend locally.

> ⏱️ **First request may take 30–60 s.** The free cloud backend sleeps when idle and
> cold-starts on the first hit. Just wait — it's not broken.

### Demo logins (seeded data)
| App | Account | Credentials |
|---|---|---|
| Child | Arjun (14) | PIN **1234** |
| Child | Priya (12) | PIN **5678** |
| Parent | sees both children | Family code **FAM789**, PIN **0000** |

---

## 3. Run the backend locally (optional)

Only needed if you're working on the API/ML. By default it uses a local SQLite DB — **no
secrets required**.
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # Windows (use source .venv/bin/activate on mac/linux)
pip install -r requirements.txt
python seed_demo.py        # optional: load Arjun/Priya demo data
python app.py              # serves on http://localhost:5000
```
Then point the apps' **Settings → Server URL** at your machine (e.g. `http://10.0.2.2:5000/`
for an emulator, or your LAN IP for a real device).

### Tests
```bash
cd backend
pytest tests/ -v           # 35 tests, isolated DB — no real data needed
```

---

## Secrets (not in the repo)

`.gitignore` deliberately keeps secrets out of git, so cloning won't include them. You only
need these for specific tasks — **ask Kaustubh** and never commit them:

| File / value | Needed for | Note |
|---|---|---|
| `local.properties` | nothing — Android Studio generates your own | don't copy anyone else's |
| `capstone-release.jks` + `keystore.properties` | building **signed release** APKs | debug builds self-sign; you rarely need this |
| `DATABASE_URL` (Neon) + `PIN_PEPPER` | running the backend against the **shared cloud DB** | local dev uses SQLite and needs neither |

---

## Just want to *run* the apps (no coding)?

Install the prebuilt signed APKs on an Android phone (enable "Install unknown apps"):
- `android/ChildApp/app/build/outputs/apk/release/app-release.apk`
- `android/ParentApp/app/build/outputs/apk/release/app-release.apk`

They talk to the live cloud backend — no GitHub or build tools needed.

---

## More docs
- [DEPLOY.md](DEPLOY.md) — cloud deployment + building signed release APKs
- [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) — demo walkthrough
- [TESTING.md](TESTING.md) — automated test layers + on-device manual checklist
- [docs/PROJECT_PAPER.tex](docs/PROJECT_PAPER.tex) — the full project paper: architecture, models, honest metrics, limitations
- [PRIVACY.md](PRIVACY.md) — privacy & data handling

<!-- contributors recompute nudge: 2026-06-14 -->
