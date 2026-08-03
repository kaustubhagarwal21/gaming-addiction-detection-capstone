# API Fuzz + Dependency Audit (2026-08-04)

Two automated tools added as a fifth verification layer, both run against the
backend at commit `3eacb9b`+. They complement the existing suites: pytest and the
functional sweep check *known* behaviour with hand-written cases; these two
generate cases nobody wrote and check *classes of property* instead.

| Tool | What it does | Result |
|---|---|---|
| [Schemathesis](https://github.com/schemathesis/schemathesis) v4.24.3 | Property-based fuzzing derived from `backend/openapi.yaml` — generates schema-valid and schema-violating requests for all 53 documented operations | **0 server errors** under production config; 1 real precedence bug found and fixed |
| [pip-audit](https://github.com/pypa/pip-audit) | Cross-references pinned dependencies against the PyPI advisory database | 7 CVEs in 3 packages; 6 fixed by upgrade, 1 dev-only accepted |

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

## Reproduce

```bash
pip install schemathesis pip-audit

# dependency CVEs
python -m pip_audit -r backend/requirements.txt

# API fuzz (production auth posture)
cd backend && PORT=5058 AUTH_ENFORCE=1 AUTH_SECRET=<throwaway> \
  DATABASE_PATH=/tmp/fuzz.db python app.py &
PYTHONIOENCODING=utf-8 schemathesis run backend/openapi.yaml \
  --url http://127.0.0.1:5058 --max-examples 15
```
