# Plan: Add a Ping Endpoint to apps/main.py

## Metadata
dw_id: `9688e67e`
prompt: `Add a /ping endpoint to apps/main.py that returns {"pong": true}.`

## Summary
Add a new `/ping` route to the existing standard-library HTTP server in `apps/main.py` so it returns a small JSON readiness-style response without changing the current routing approach. Extend the existing Python route tests in `apps/test_main.py` so the new endpoint is covered alongside the current `/health`, `/hello`, `/metrics`, and unknown-route behavior.

## Relevant Files
- `README.md` — Confirms the repo structure and that `apps/` contains the Python application entry point.
- `apps/main.py` — Contains the current `build_response` routing logic, shared JSON response helper, and HTTP handler that must be updated for the new `/ping` endpoint.
- `apps/test_main.py` — Holds the existing `unittest` coverage for route behavior and should be extended to verify the `/ping` response contract and allowed methods.
- `.github/workflows/tests.yml` — Shows the repository-level test command (`pytest apps/ -v`) that should still pass after the change.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Review the existing Python route and test structure
- Confirm how `build_response` dispatches by request path and method, and note the current JSON payload and header conventions used by existing endpoints.
- Review `apps/test_main.py` to mirror the current assertion style and decide where the new `/ping` tests fit without disturbing existing coverage.
- Files to modify: None

### 2. Add the `/ping` route to the server
- Update `apps/main.py` so `build_response` recognizes `GET /ping` and returns an HTTP 200 response with the JSON body `{"pong": true}`.
- Reuse the existing `json_response` helper and keep unsupported methods for `/ping` consistent with the current pattern by returning `405 Method Not Allowed` with the appropriate `Allow` header.
- Preserve the existing behavior for `/health`, `/hello`, `/metrics`, and unmatched routes.
- Files to modify: `apps/main.py`

### 3. Extend automated test coverage for `/ping`
- Add tests in `apps/test_main.py` for the happy-path `GET /ping` response, asserting the status code, content type, and parsed JSON body.
- Add a method-not-allowed test for a non-GET request to `/ping` so the new route matches the behavior of the other single-method endpoints.
- Keep the existing tests intact so the suite continues to protect current behavior while adding the new contract.
- Files to modify: `apps/test_main.py`

### 4. Run Validation
- Compile the updated Python modules to catch syntax or import issues.
- Run the route test suite directly and through the repo's pytest command to verify the new endpoint and guard against regressions.
- Start the server locally and send a request to `/ping` to confirm the endpoint behaves correctly over HTTP, not just through unit tests.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `uv run python -m unittest apps.test_main`
- `python -m pytest apps/ -v`
- `PORT=8000 uv run apps/main.py`
- `curl -i http://127.0.0.1:8000/ping`
