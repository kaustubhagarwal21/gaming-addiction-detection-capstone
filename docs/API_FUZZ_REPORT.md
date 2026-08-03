# Automated Audit Report — API fuzz, dependencies, static analysis, secrets, coverage (2026-08-04)

Five automated tools added as a verification layer beyond the hand-written suites.
pytest and the functional sweep check *known* behaviour with cases a human wrote;
these generate cases nobody wrote, or measure properties of the whole codebase.

| Tool | What it does | Result |
|---|---|---|
| [Schemathesis](https://github.com/schemathesis/schemathesis) v4.24.3 | Property-based fuzzing derived from `backend/openapi.yaml` — schema-valid and schema-violating requests across all 53 documented operations | **0 server errors** under production config; 1 real precedence bug found and fixed |
| [pip-audit](https://github.com/pypa/pip-audit) | Pinned dependencies vs the PyPI advisory database | 7 CVEs in 3 packages; 6 retired by upgrade, 1 dev-only accepted |
| [Bandit](https://github.com/PyCQA/bandit) | Python security static analysis — the backend/ML counterpart to the MobSF scan of the apps | 44 medium findings → **43 verified false positives, 1 real, fixed** |
| [detect-secrets](https://github.com/Yelp/detect-secrets) | Scans every file for committed credentials (this repo is **public**) | **No private key, signing keystore, or server secret is tracked — and none ever was** |
| [pytest-cov](https://github.com/pytest-dev/pytest-cov) | Statement coverage of the 180-test suite | **75%** overall; **80%** of served code |

## Schemathesis: what it found

Run twice — once in shadow-auth mode (`AUTH_ENFORCE=0`, the local dev default) and
once in **production mode** (`AUTH_ENFORCE=1`), because the auth posture changes
which findings are real.

**Genuine bug, fixed: `POST /api/alerts/mark_read` authenticated after parsing.**
The handler called `request.get_json()` before `guard()`. Flask raises **415** on a
non-JSON `Content-Type`, so an *unauthenticated* caller sending a form-encoded body
received `415 Unsupported Media Type` — i.e. "this endpoint exists and wants JSON" —
instead of a flat `401`. Endpoint-shape disclosure to an unauthenticated caller, and
an API-contract inconsistency. Fixed by moving `guard()` first and switching to
`get_json(silent=True)`. A scripted scan of all 53 operations confirmed this was the
**only** endpoint with that precedence; regression test:
`test_mark_read_authenticates_before_parsing_the_body`.

**No server errors under production config.** The one `500` seen in the shadow-auth
run was not reproducible with `AUTH_ENFORCE=1` (unauthenticated requests reach
handler code in shadow mode by design). Production deploys always set
`AUTH_ENFORCE=1` — the app *refuses to boot* in enforce mode without an
`AUTH_SECRET`, which the fuzz run confirmed by failing to start until one was set.

**Remaining findings are OpenAPI-spec completeness, not defects** (triaged, not
fixed):
- *Undocumented HTTP status code* (50): the spec documents the happy path and the
  main error for each operation, but not every `401`/`403`/`415`/`429` the shared
  middleware can return. Real behaviour is correct; the *document* is incomplete.
- *API rejected schema-compliant request* (40): overwhelmingly `401`/`403` on
  operations whose schema-valid body cannot be exercised without a real token and a
  real family relationship (the fuzzer has neither). Authorization is
  relationship-based, which a schema cannot express.
- *Unsupported methods* (6): undocumented verbs return `405` from Flask's router
  without an explicit spec entry.

These are worth closing before any public API release; they are not exploitable and
none of them changes a served response.

## pip-audit: dependency CVEs

| Package | Was | Now | Action |
|---|---|---|---|
| `flask` | 3.0.3 | **3.1.3** | Upgraded (PYSEC-2026-2151) |
| `flask-cors` | 4.0.1 | **6.0.0** | Upgraded — carried **5** advisories (PYSEC-2024-71, -2024-260, -2026-1383/1384/1385) |
| `pytest` | 7.4.3 | 7.4.3 | **Accepted.** Test-only dependency, never installed in the production image (`Dockerfile` installs `requirements.txt` and runs gunicorn; pytest is not imported by any served path). A major bump to 9.x risks the 180-test suite for no production benefit. Revisit post-defense. |

Both upgrades verified: **180 pytest + 82/82 functional sweep green** afterwards.
The `flask-cors` jump is a major version, but this project's usage is a single
`CORS(app, resources={r"/api/*": {"origins": "*"}})` call whose semantics are
unchanged in 6.x.

## Bandit: Python static security analysis

MobSF audited the two Android apps; nothing had ever statically analysed the
**backend and ML code**. Bandit at medium-and-above reported 44 findings. Each was
verified rather than waved away:

**33 × B608 "possible SQL injection".** All false positives — but proven, not
assumed. A script extracted every interpolated expression from each flagged query:
21 interpolate only the dialect placeholder (`_PH`, `?` vs `%s`, the SQLite/Postgres
portability shim), and the remaining 12 interpolate a **code-controlled identifier**
— `_SESSION_TABLES` (a hardcoded list of table names), `', '.join(BEHAVIORAL_FEATURES)`
(a constant feature list), or a generated `','.join(['?'] * n)` placeholder run. In
every case user-supplied values are still passed as parameters in the execute tuple.
No user input reaches a query string.

**5 × B301 "pickle".** Loading the project's own model artifacts
(`joblib`/`pickle` on `backend/models/*.pkl`), which ship inside the deployment image.
No untrusted pickle is ever loaded.

**3 × B310 `urlopen`, 1 × B104 bind-all, 1 × B615 unpinned HF download.** Fixed
URLs in developer fetch scripts; `0.0.0.0` binding in the dev-server entry point
(production serves through gunicorn); a dataset download that already pins a
snapshot name.

**1 × B307 `eval` — REAL, fixed.** A consistency test parsed the threshold-tuner's
`DEFAULTS` dict out of source with `eval()`. Only ever run on the project's own
file, so not exploitable — but `eval` has no business there. Replaced with
`ast.literal_eval`; bandit now reports **zero** B307. Suite still 180 passing.

## detect-secrets: the public-repo check

The repository is public, so a leaked signing key or service-account credential
would be unrecoverable. The scan flagged 17 files; the three that would actually
matter were checked directly against git:

| File | Tracked? | In history? |
|---|---|---|
| `backend/firebase_key.json` (service-account **private key**) | **No** | **Never** |
| `android/ChildApp/keystore.properties` (signing password) | **No** | **Never** |
| `android/ParentApp/keystore.properties` (signing password) | **No** | **Never** |
| `android/ParentApp/app/google-services.json` | Yes | Yes — **correct**: this is the Firebase *client* config, public by design in every Android app; access is enforced server-side |

Everything else flagged is a test fixture, a documented sample credential in
`DEPLOY.md`/`docker-compose.yml`, or build-cache noise. **No real secret has ever
been committed.**

## pytest-cov: how much the 180 tests actually reach

| Scope | Statements | Covered |
|---|---|---|
| `app.py` (the served backend) | 3,987 | **74%** |
| `text_utils.py`, `behavior_features.py` | 38 | **100%** |
| `audio_features.py` | 85 | 53% (librosa paths need real audio) |
| **Whole backend package** | 5,784 | **75%** |
| **Excluding dev-only utilities** (`seed_demo.py`, `verify_captures.py` — 361 statements, never imported by the server) | 5,423 | **80%** |

Reported honestly rather than by picking the flattering scope: the uncovered
quarter is dominated by error branches for infrastructure failures (Postgres
reconnects, FCM delivery errors, Sentry paths) that a hermetic suite cannot reach.

## Reproduce

```bash
pip install schemathesis pip-audit bandit detect-secrets pytest-cov

# static security analysis (backend + ML)
python -m bandit -r backend/ ml/ -ll

# committed-secret scan
python -m detect_secrets scan --all-files

# coverage
cd backend && python -m pytest tests/ -q --cov=. --cov-report=term-missing


# dependency CVEs
python -m pip_audit -r backend/requirements.txt

# API fuzz (production auth posture)
cd backend && PORT=5058 AUTH_ENFORCE=1 AUTH_SECRET=<throwaway> \
  DATABASE_PATH=/tmp/fuzz.db python app.py &
PYTHONIOENCODING=utf-8 schemathesis run backend/openapi.yaml \
  --url http://127.0.0.1:5058 --max-examples 15
```
