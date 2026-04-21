# Plan: Extend the Python health check endpoint

## Metadata
dw_id: `abcc9a0e`
prompt: `Add a health check endpoint to apps/main.py that returns JSON with status, uptime, and version`

## Summary
Enhance the existing `/health` route in `apps/main.py` so it returns a richer JSON payload with a stable `status`, calculated `uptime`, and an explicit `version` value. Keep the current lightweight standard-library server architecture intact, and update the route-level tests so the new contract is verified without regressing existing endpoints or method handling.

## Relevant Files
- `README.md` — Provides the project overview and confirms that `apps/` contains the application entry points and current lightweight application scope.
- `apps/main.py` — Contains the current HTTP server, JSON response helper, and `/health` route that must be extended to include uptime and version data.
- `apps/test_main.py` — Contains the existing unit tests around `build_response` and should be updated to assert the richer health response while preserving coverage for existing routes.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Review the current health endpoint contract and choose stable metadata sources
- Confirm how `build_response` currently handles `/health`, shared JSON responses, cache headers, and unsupported methods so the enhancement stays consistent with existing routing behavior.
- Decide how to expose version data without introducing new dependencies or packaging changes, most likely via a module-level constant or another explicit value owned by `apps/main.py`.
- Decide how uptime should be measured so it reflects process lifetime predictably, such as capturing application start time at module load and deriving uptime on each health request.
- Files to modify: None

### 2. Extend `apps/main.py` to return status, uptime, and version
- Add the minimal application state needed to calculate uptime for each `GET /health` request while keeping the current standard-library HTTP server structure unchanged.
- Update the `/health` response payload from the current single-field JSON body to a stable object containing `status`, `uptime`, and `version`.
- Preserve the existing response conventions, including JSON content headers, `Cache-Control: no-store`, and current method/route error handling so the change remains behavior-safe outside the payload expansion.
- Files to modify: `apps/main.py`

### 3. Update automated tests for the enriched health response
- Extend `apps/test_main.py` so the health endpoint test asserts the presence and expected values or types for `status`, `uptime`, and `version` instead of only checking `{"status": "ok"}`.
- Make the uptime assertion resilient to runtime variation by validating its existence and numeric or string format according to the implementation decision, rather than hard-coding a brittle exact value.
- Keep the existing `/hello` and unknown-route tests in place so the endpoint enhancement proves no regressions in unrelated routing behavior.
- Files to modify: `apps/test_main.py`

### 4. Run Validation
- Compile the Python application and test module to catch syntax errors introduced by the health payload changes.
- Run the Python unit tests covering route behavior, especially the updated health endpoint assertions.
- Start the application locally and confirm the HTTP `/health` response includes `status`, `uptime`, and `version` in JSON while existing routes continue to behave as expected.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `uv run python -m unittest apps.test_main`
- `PORT=8000 uv run apps/main.py`
- `curl -i http://127.0.0.1:8000/health`
- `curl -i http://127.0.0.1:8000/hello`
