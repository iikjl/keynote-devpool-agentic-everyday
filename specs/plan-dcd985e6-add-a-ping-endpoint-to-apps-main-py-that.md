# Plan: Add a Ping Endpoint to apps/main.py

## Metadata
dw_id: `dcd985e6`
prompt: `Add a /ping endpoint to apps/main.py that returns {"pong":
  true}.`

## Summary
Add a new `/ping` route to the existing standard-library HTTP server in `apps/main.py`, following the same `build_response` routing and JSON response patterns already used by `/health`, `/hello`, and `/metrics`. Extend the current unit tests in `apps/test_main.py` so the new endpoint has an explicit contract and existing route behavior remains covered.

## Relevant Files
- `README.md` — Provides the project overview and confirms `apps/` contains the application entry points.
- `apps/main.py` — Contains the current HTTP server, shared JSON response helper, and route dispatch logic where `/ping` must be added.
- `apps/test_main.py` — Holds the existing route-level unit tests and should be extended to cover the new `/ping` endpoint while preserving current coverage.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Review the existing Python route conventions
- Confirm how `build_response` handles known routes, unsupported methods, and unknown paths so the new endpoint matches the existing API style.
- Reuse the current JSON response helper and header conventions instead of introducing a new routing abstraction or response shape.
- Files to modify: None

### 2. Add the `/ping` route in `apps/main.py`
- Update `build_response` so `GET /ping` returns HTTP 200 with the JSON payload `{"pong": true}`.
- Keep non-`GET` requests to `/ping` consistent with other read-only endpoints by returning the existing method-not-allowed pattern and `Allow: GET`.
- Preserve the current behavior of `/health`, `/hello`, `/metrics`, and unknown routes.
- Files to modify: `apps/main.py`

### 3. Extend automated coverage for `/ping`
- Add a unit test in `apps/test_main.py` that asserts the `/ping` endpoint returns HTTP 200, the JSON content type, and the exact body `{"pong": true}`.
- Add or update a negative-path assertion for an unsupported method on `/ping` so the endpoint follows the same contract as the other GET-only routes.
- Keep the existing tests for the other endpoints intact so the change guards against regressions outside `/ping`.
- Files to modify: `apps/test_main.py`

### 4. Run Validation
- Compile the Python application and test module to catch syntax issues.
- Run the route-level unit tests that exercise `build_response`.
- Start the server locally and send a request to `/ping` to verify the HTTP contract end to end.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `uv run python -m unittest apps.test_main`
- `PORT=8000 uv run apps/main.py`
- `curl -i http://127.0.0.1:8000/ping`
