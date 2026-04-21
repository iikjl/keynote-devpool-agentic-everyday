# Plan: Add a /metrics endpoint to the Python app

## Metadata
dw_id: `0391cf22`
prompt: `### Prompt

Add a /metrics endpoint to apps/main.py that returns request count and uptime.
Cover it with a test in apps/test_main.py.`

## Summary
Add a GET-only `/metrics` route to the Python app so it exposes basic runtime observability: total request count and process uptime. Implement the endpoint inside the existing `build_response` router in `apps/main.py`, then cover the new behavior in `apps/test_main.py` using the current `unittest` style.

## Relevant Files
- `README.md` — Project overview and confirmation that `apps/` is the application layer to update.
- `apps/main.py` — Main Python HTTP server; contains the route dispatching, process start timestamp, and request handling flow that the new `/metrics` endpoint must extend.
- `apps/test_main.py` — Existing unit test file for `build_response`; add coverage for the new `/metrics` behavior here.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Extend the request lifecycle in `apps/main.py`
- Review the existing module-level state used by the server and reuse `PROCESS_START_TIME` as the uptime baseline.
- Add or confirm a module-level request counter and ensure `AppHandler.handle_method` increments it for every incoming request before calling `build_response`.
- Pass the live request count into `build_response` through a keyword argument so the route logic can return it without duplicating state access.
- Files to modify: `apps/main.py`

### 2. Add the `/metrics` route to the central response builder
- In `build_response`, add a new `if path == "/metrics"` branch that matches the existing route structure used for `/health` and `/hello`.
- For `GET`, return JSON with `request_count` and `uptime`, where uptime is derived from `time.monotonic() - PROCESS_START_TIME` and rounded consistently with the rest of the file.
- For non-GET methods, return `405 Method Not Allowed` and set the `Allow: GET` header to match the current endpoint conventions.
- Files to modify: `apps/main.py`

### 3. Add focused tests for the new metrics behavior
- Add a new test case in `apps/test_main.py` that calls `build_response("GET", "/metrics", request_count=<known value>)` and asserts the response status, JSON content type, echoed request count, and a non-negative numeric uptime.
- Add a second test that exercises a disallowed method such as `POST` and asserts the `405` status plus `Allow: GET`.
- Keep the tests aligned with the existing `unittest.TestCase` structure and direct `build_response` unit-testing style already used in the file.
- Files to modify: `apps/test_main.py`

### 4. Run Validation
- Run the Python app test suite covering `apps/test_main.py`.
- Optionally smoke-test the live server by starting `apps/main.py` and requesting `/metrics` to confirm the endpoint shape matches the unit-tested contract.

## Validation Commands
```bash
uv run python -m unittest apps.test_main
PORT=8000 uv run python apps/main.py
curl -s http://127.0.0.1:8000/metrics
```
