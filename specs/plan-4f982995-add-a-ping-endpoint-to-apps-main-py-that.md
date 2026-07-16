# Plan: Add a Ping Endpoint to apps/main.py

## Metadata
dw_id: `4f982995`
prompt: `Add a /ping endpoint to apps/main.py that returns {"pong":
  true}.`

## Summary
Add a new `GET /ping` route to the existing standard-library HTTP app in `apps/main.py`, keeping it consistent with the current `build_response` routing pattern and JSON response helpers. Extend the Python test suite so the new endpoint's success response and method handling are covered, then validate the full `apps/` test surface to catch regressions in existing routes.

## Relevant Files
- `README.md` — Confirms the repo structure and that `apps/main.py` is the Python application entry point.
- `apps/main.py` — Contains the current request router, JSON response helper, and server entry point where the new `/ping` endpoint must be added.
- `apps/test_main.py` — Holds the existing `unittest` coverage for `build_response`; update it to assert the `/ping` contract and any related method restrictions.
- `.github/workflows/tests.yml` — Shows the repository's existing CI validation command (`pytest apps/ -v`), which should be included in the implementation validation step.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Add `/ping` routing to the Python app
- Update `build_response` in `apps/main.py` to recognize the `/ping` path alongside the existing `/health`, `/hello`, and `/metrics` routes.
- Return HTTP 200 with the JSON payload `{"pong": true}` for `GET /ping`, reusing the existing `json_response(...)` helper so headers and body encoding stay consistent with the rest of the app.
- Mirror the app's current route conventions for unsupported methods by returning `405 Method Not Allowed` and `Allow: GET` for non-GET requests to `/ping`.
- Files to modify: `apps/main.py`

### 2. Extend automated coverage for the new endpoint
- Add a test case in `apps/test_main.py` that calls `build_response("GET", "/ping")` and asserts the HTTP status, JSON content type header, and decoded body equal `{"pong": True}`.
- Add a negative-path test for a non-GET request to `/ping` so the new route follows the same method-handling contract as the existing GET-only endpoints.
- Keep the test additions aligned with the current `unittest.TestCase` style already used in the file.
- Files to modify: `apps/test_main.py`

### 3. Run Validation
- Run the focused unit tests for `apps/test_main.py` to confirm the new `/ping` behavior.
- Run the repository-standard Python test command over `apps/` to ensure the new endpoint does not break existing route coverage.
- Optionally start the local server and issue a manual request to `/ping` for an end-to-end smoke check of the HTTP response.

## Validation Commands
- `uv run python -m unittest apps.test_main`
- `python -m pytest apps/ -v`
- `PORT=8000 uv run apps/main.py`
- `curl -i http://127.0.0.1:8000/ping`
