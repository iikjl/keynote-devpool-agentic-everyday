# Plan: Add a Hello World Endpoint to apps/main.py

## Metadata
dw_id: `b1baf8c2`
prompt: `Add a hello world endpoint to apps/main.py`

## Summary
Extend the existing standard-library HTTP server in `apps/main.py` with a dedicated hello world route while preserving the current `/health` behavior and response conventions. Update the Python tests so the new endpoint has a clear, stable contract and the change can be validated without introducing new dependencies.

## Relevant Files
- `README.md` — Provides the project overview and confirms that `apps/` contains the application entry points.
- `apps/main.py` — Contains the current HTTP server, route dispatch, and JSON response helpers where the new endpoint should be added.
- `apps/test_main.py` — Holds the existing route-level unit tests and should be extended to cover the new hello world endpoint alongside current behavior.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Review the existing Python route structure
- Confirm how `build_response` currently maps request methods and paths to JSON responses.
- Identify the existing response shape, status handling, and headers so the new endpoint follows the same pattern.
- Files to modify: None

### 2. Add the hello world route to the server
- Update `apps/main.py` so `build_response` recognizes a dedicated hello world endpoint, preferably `GET /hello`.
- Return an HTTP 200 JSON response with a simple, explicit payload such as `{"message": "hello world"}` while keeping unsupported methods and unknown routes consistent with the current server behavior.
- Preserve the existing `/health` endpoint and shared response helper usage instead of introducing a separate routing approach.
- Files to modify: `apps/main.py`

### 3. Extend automated test coverage
- Add or update tests in `apps/test_main.py` to assert the hello world endpoint status code, content type, and JSON body.
- Keep the existing `/health` and unknown-route assertions intact so the change verifies the new endpoint without regressing current behavior.
- Files to modify: `apps/test_main.py`

### 4. Run Validation
- Compile the Python application and test module to catch syntax issues.
- Run the Python unit tests covering route behavior.
- Start the app locally and issue a request to the hello world endpoint to verify the HTTP contract end to end.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `uv run python -m unittest apps.test_main`
- `PORT=8000 uv run apps/main.py`
- `curl -i http://127.0.0.1:8000/hello`
