# Demo Prep Runbook — PW26_SJ_05

How to get from "cold repo" to "demo-ready" — written for a demo **months out**, where
the free cloud setup will NOT survive on its own. Do the one-time DB migration once, then
follow the T-minus checklist before each demo.

---

## 0. Why this exists (the two free-tier traps)

1. **Render free Postgres is deleted ~30 days after creation.** Your seeded children,
   sessions, alerts, and feedback will be **gone** by the demo. → migrate to a durable DB
   (below). One-time.
2. **Render free web service sleeps after ~15 min idle** (30–60 s cold start). Not a crash,
   but the first screen can look broken / return 503. → warm it up before the demo (and/or
   the keep-alive workflow).

There was also a real crash cause (now fixed): the backend ran **2 gunicorn workers on
512 MB** and OOM-killed under load (each worker grew its own copy of the ML stack + SHAP),
producing 50x errors (501/503). It now runs **1 worker + recycling** (`Dockerfile`), which
fits the free tier. If you ever move to a bigger plan, set `WEB_CONCURRENCY` to raise it.

---

## 1. One-time: move to a durable database (Neon — recommended)

The app is `DATABASE_URL`-driven (SQLite ⇆ Postgres), so this is **config only, no code**.

**Neon beats Supabase here:** Neon auto-suspends when idle but **auto-resumes on the next
connection** (no manual step). Supabase free **pauses after 7 days and needs manual
un-pausing** — bad for a long-dormant demo.

1. Create a free project at <https://neon.tech> — pick a region near Render (**Singapore**).
2. Copy the **pooled** connection string. Make sure it ends with `?sslmode=require`, e.g.
   `postgresql://USER:PASS@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
3. In the Render dashboard → your web service → **Environment** → set `DATABASE_URL` to that
   string (replace the old Render-Postgres value). Save → it redeploys.
4. Re-seed the new DB (see step 2 of the checklist).

(Alternative: keep Render Postgres but **upgrade it to a paid plan** (~$7/mo) so it isn't
deleted. Simplest, but costs money. Same re-seed step applies.)

---

## 2. T-minus checklist

### ~1 week before (T-7)
- [ ] Durable DB is in place (`DATABASE_URL` points at Neon/paid Postgres, not free Render PG).
- [ ] Re-seed it. Easiest: Render dashboard → web service → **Shell** tab →
      `python seed_demo.py` (uses the service's `DATABASE_URL` + `PIN_PEPPER`).
      Re-running is safe/idempotent (it clears each child first).
- [ ] Re-enable the **keep-backend-warm** GitHub Action if it was auto-disabled
      (Actions tab → enable; or just push any commit — scheduled workflows reactivate).
- [ ] Build fresh **signed release APKs** (`DEPLOY.md` §D) and install on the demo phone(s).

### ~1 day before (T-1)
- [ ] Warm the backend: open `https://gaming-addiction-api.onrender.com/api/health`
      (or just open the app) — wait for `models_loaded: true`.
- [ ] Run the end-to-end smoke test (proves the whole pipeline on the live DB):
      `cd backend && python scripts/cloud_e2e.py` — expect all green.
- [ ] Log in on both apps: Child = **Arjun / PIN 1234** (or Priya / 5678);
      Parent = **family code FAM789 / PIN 0000** → sees both children.
- [ ] Open ParentApp → a child → Alerts → confirm the **feedback buttons** show on alerts.

### Demo day (T-0)
- [ ] **Warm up 2–3 min before you present** (open the app once; the first call wakes both
      the Render service and Neon). Don't start cold in front of the audience.
- [ ] Have a fallback: a short screen-recording of the working flow, in case of campus Wi-Fi.

---

## 3. If you see 501 / 502 / 503 during the demo

| Symptom | Cause | Fix |
|---|---|---|
| First request hangs ~30–60 s then works | Render free **cold start** (was asleep) | Warm up before; keep-alive workflow |
| Repeated 5xx under heavy use | Was the **2-worker OOM** (now fixed to 1 worker) | Confirm latest `Dockerfile` is deployed |
| All endpoints fail, DB errors | DB **deleted/paused** or `DATABASE_URL` wrong | Check Neon is active; verify env var; re-seed |
| Slow but working | Free CPU + cold models | Acceptable for a demo; warm up first |

**Quick health probe:** `curl https://gaming-addiction-api.onrender.com/api/health`
→ expect `{"status":"ok","models_loaded":true}`.

---

## 4. Don't-forget list
- `DATABASE_URL` (durable DB) + `PIN_PEPPER` + `AUTH_SECRET` must stay set on Render
  (PIN_PEPPER/AUTH_SECRET are auto-generated+persisted by `render.yaml`; don't rotate them
  or existing PIN hashes/tokens break).
- The signing keystore (`android/*/capstone-release.jks`, `keystore.properties`) is
  gitignored — keep a private backup; you need it to rebuild signed APKs.
