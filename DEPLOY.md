# Deployment — Gaming Addiction Detection (PW26_SJ_05)

The backend runs on **SQLite locally** and **Postgres in production**, selected
automatically by the `DATABASE_URL` env var. The same code path serves both; see
`backend/.env.example` for all environment variables.

---

## A. Deploy to Render (recommended)

Render gives the Docker web service, HTTPS, and a stable URL from one blueprint
file ([render.yaml](render.yaml)). The durable database is an external Postgres
instance (currently Neon) supplied through `DATABASE_URL`.

1. **Push the branch you want to deploy to GitHub**:
   ```bash
   git push origin HEAD
   ```
2. In Render → **New → Blueprint** → pick the repo. It reads `render.yaml` and
   provisions the web service. `AUTH_SECRET` / `PIN_PEPPER` are generated for you
   and `AUTH_ENFORCE=1` is set. In the service's Environment tab, set the
   `DATABASE_URL` secret to the durable Postgres connection string; the blueprint
   intentionally declares it with `sync: false` and cannot fill it automatically.
3. Wait for the first build (installs librosa/sklearn — a few minutes). Health:
   `https://<service>.onrender.com/api/health` → `models_loaded: true`.
4. In **both apps → Settings → Server URL** set `https://<service>.onrender.com/`
   and Save. (No more `adb reverse` / IP juggling.)

Notes: the free web instance cold-starts after idle (~30–60 s first hit while the
models load). Database retention, capacity, and backups are controlled by the
external Postgres provider and its selected plan.

---

## B. Test the Postgres path locally (before deploying)

Requires Docker Desktop running.

```bash
cd backend
docker compose up --build        # API on http://localhost:5000 backed by Postgres
```

Or run just the auth/authorization smoke test against a throwaway Postgres:

```bash
docker run -d --name gad-pg -p 5433:5432 \
  -e POSTGRES_DB=gaming_addiction -e POSTGRES_USER=gaming_app -e POSTGRES_PASSWORD=dev \
  postgres:16-alpine
DATABASE_URL=postgresql://gaming_app:dev@localhost:5433/gaming_addiction \
  AUTH_ENFORCE=1 AUTH_SECRET=local-smoke-secret PIN_PEPPER=local-smoke-pepper \
  python scripts/pg_smoketest.py
docker rm -f gad-pg
```

`pg_smoketest.py` checks: login issues a token, no-token → 401, own data → 200,
cross-user → 403, parent sees both children, and the Postgres dashboard/report
date queries run.

---

## C. Local dev (unchanged)

`./demo_setup.ps1` still works exactly as before — SQLite + adb tunnel, shadow
auth. Add `-Enforce` to require tokens once both apps are reinstalled with token
support. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).

## D. Build the signed release APKs (distribution package)

The apps are distributed as **sideloaded signed release APKs** (not Play Store —
the AccessibilityService chat capture is Play-restricted; see the report).

Signing credentials live in `android/<App>/keystore.properties` + a `capstone-release.jks`
keystore, both **gitignored** (never committed). To build:

```
cd android/ChildApp  && ./gradlew :app:assembleRelease
cd android/ParentApp && ./gradlew :app:assembleRelease
```

Output: `app/build/outputs/apk/release/app-release.apk` (signed with the
`PES Capstone PW26_SJ_05` key; APK Signature Scheme v2). Install with
`adb install -r app-release.apk`. The release build uses the strict HTTPS-only
network-security config, so it talks only to the cloud backend over TLS.

If `keystore.properties` is absent (fresh clone without the secret), the release
build falls back to unsigned and debug builds are unaffected.
