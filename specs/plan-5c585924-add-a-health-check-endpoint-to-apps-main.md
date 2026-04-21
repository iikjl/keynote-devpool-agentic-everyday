# Plan: Add a Health Check Endpoint to apps/main.py

## Metadata
dw_id: `5c585924`
prompt: `Add a health check endpoint to apps/main.py`

## Summary
Replace the current placeholder Python entry point with a minimal HTTP application that exposes a dedicated `/health` endpoint. Structure the implementation so the endpoint is easy to validate automatically and manually without introducing unnecessary dependencies that are not already established in the repository.

## Relevant Files
- `README.md` — Read for the project overview and current expectations around how the Python application is organized and run.
- `apps/main.py` — Modify the Python application entry point to host an HTTP server and serve the new health check route.
- `apps/test_main.py` — Create automated tests for the health check response contract and basic non-health route behavior.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Reshape the Python entry point into a minimal web app
- Replace the current `print(...)` placeholder in `apps/main.py` with a small, importable HTTP server implementation that can be started from the command line.
- Choose an implementation approach that matches the current repo state; since no Python web framework or package manifest is present, prefer the Python standard library unless the implementation phase explicitly introduces and wires a dependency.
- Structure the server code so the request handling logic can be tested without relying only on manual curl checks.
- Files to modify: `apps/main.py`

### 2. Add the `/health` endpoint contract
- Implement a `GET /health` route that returns HTTP 200 and a minimal machine-readable payload indicating the app is healthy.
- Set explicit response headers and status handling so the endpoint has a stable contract for probes and smoke checks.
- Define predictable behavior for unsupported routes and methods to avoid ambiguous server responses during validation.
- Files to modify: `apps/main.py`

### 3. Add automated coverage for the new endpoint
- Create `apps/test_main.py` with tests that exercise the health check behavior through the chosen server or handler abstraction.
- Assert the success status code, response body, and content type for `/health`, and include at least one negative-path assertion for a non-health route.
- Keep the test approach dependency-light so it can run with the repository’s current Python setup.
- Files to create: `apps/test_main.py`

### 4. Run Validation
- Verify the Python files compile cleanly.
- Run the automated tests for the new endpoint behavior.
- Start the application locally and confirm `GET /health` responds successfully over HTTP.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `uv run python -m unittest apps.test_main`
- `PORT=8000 uv run apps/main.py`
- `curl -i http://127.0.0.1:8000/health`
