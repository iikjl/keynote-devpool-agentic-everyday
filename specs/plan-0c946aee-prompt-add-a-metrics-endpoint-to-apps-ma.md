# Plan: Add a /metrics Endpoint to the Python App

## Metadata
dw_id: `0c946aee`
prompt: `### Prompt

Add a /metrics endpoint to apps/main.py that returns request count and uptime.
Cover it with a test in apps/test_main.py.`

## Summary
Add or align a `/metrics` route in the existing handler-based Python app so it reports total request count and process uptime as JSON. Update the test suite to cover that contract in the same style as the current `build_response`-focused unit tests, then validate the app with the repository’s Python test workflow.

## Relevant Files
- `README.md` — Provides the project overview and confirms `apps/` is the application layer targeted by this change.
- `apps/main.py` — Contains the HTTP server, shared request handling flow, process uptime state, and the route dispatch logic that must expose `/metrics`.
- `apps/test_main.py` — Holds the Python endpoint tests and is the correct place to add or adjust coverage for the `/metrics` response contract.
- `.github/workflows/tests.yml` — Shows the repository’s existing Python validation path (`pytest apps/ -v`) so the implementation can be verified the same way CI runs it.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Review the current request handling flow
- Inspect how `apps/main.py` tracks process lifetime and routes requests through `build_response` and `AppHandler.handle_method`.
- Confirm whether request counting and uptime data already exist and identify the smallest change needed to make `/metrics` return the requested fields consistently.
- Files to modify: `apps/main.py`

### 2. Add or align the `/metrics` endpoint contract
- Implement or adjust the `/metrics` branch in `build_response` so `GET /metrics` returns HTTP 200 with JSON containing `request_count` and `uptime`.
- Reuse the module-level uptime source and request counter wiring rather than duplicating state, and keep method-not-allowed behavior consistent with the other routes by returning an `Allow: GET` header for unsupported methods.
- Ensure the handler passes the live request count into `build_response` so the endpoint reports current process state.
- Files to modify: `apps/main.py`

### 3. Add automated coverage for `/metrics`
- Add or update a test in `apps/test_main.py` that exercises `build_response("GET", "/metrics", request_count=...)` and asserts the status code, JSON content type, expected `request_count`, and a non-negative numeric `uptime`.
- Add or keep a negative-path assertion for an unsupported method if the route follows the same method gate as the rest of the app.
- Match the current `unittest.TestCase` structure and assertion style used by the existing endpoint tests.
- Files to modify: `apps/test_main.py`

### 4. Run Validation
- Verify the modified Python files compile cleanly.
- Run the Python test suite using the same pytest entry point defined in CI to confirm the new endpoint behavior and catch regressions in the existing routes.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `python -m pytest apps/ -v`
