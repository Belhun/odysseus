# AGENTS.md

## Cursor Cloud specific instructions

Odysseus is a single self-hosted FastAPI app (entry point `app.py`). There is one
service to run; everything else (chat, agents, research, documents, email, notes,
calendar) lives inside that one process. Setup, run, test, and lint commands are
documented in `CONTRIBUTING.md` and `docs/setup.md`; use those as the source of
truth. The notes below cover only the non-obvious gotchas for this environment.

### Running the app

- The startup update script keeps `venv/` populated from `requirements.txt`. Run
  the dev server from the venv: `./venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 7000`,
  then open `http://localhost:7000`. `--reload` enables hot reload during development.
- A dev admin account is seeded into `data/auth.json` (gitignored, persists in the
  VM snapshot): username `admin`, password `odysseus-dev-pass`. It was created by
  running `./venv/bin/python setup.py` with `ODYSSEUS_ADMIN_USER` /
  `ODYSSEUS_ADMIN_PASSWORD`. If `data/` is ever wiped, re-run `setup.py` (it
  creates `data/` dirs, the SQLite DB, and the admin user; safe to re-run).

### Expected, non-fatal startup conditions

- `ChromaDB is not reachable at localhost:8100` / `ToolIndex init failed`: ChromaDB
  is optional. The app degrades to a keyword fallback for vector memory/tool
  selection. This is not a failure; only Docker Compose runs ChromaDB.
- `Built-in: Browser is not available` (Playwright MCP): optional. Run
  `npx -y @playwright/mcp@latest --version` once and restart to enable it.
- No LLM is configured by default, so Chat/Agent and AI-backed Tasks features
  fail with "No model endpoint configured". For non-LLM end-to-end testing use
  Notes, Documents, or Calendar, which persist data without a model. Configure a
  model under Settings to exercise chat/agent flows.

### Lint and test

- "Lint" here is syntax checking, not a style linter:
  `./venv/bin/python -m compileall -q app.py core routes src services scripts tests`
  and `node --check` on `static/app.js` + `static/js/**/*.js` (see `.github/workflows/ci.yml`).
- Tests: `./venv/bin/python -m pytest -q`. The full suite is large (~4000 tests,
  ~90s). For focused runs see `tests/README.md` (`tests/run_focus.py`, area/sub
  markers).
- Known flaky: `tests/test_upload_handler_atomicity.py` has 2 timing/cache-dependent
  tests (`test_partial_write_recovery_via_bak`, `test_smoke_info_lookup_after_bak_recovery`)
  that can fail on fast filesystems because the in-memory mtime cache returns the
  latest write before the truncated-file `.bak` fallback runs. CI marks the pytest
  job `continue-on-error` for exactly these "environment-dependent" failures, so a
  green pytest run is not gating; investigate only failures your change introduces.
