# Plan: Add an /analysis endpoint for numeric summary statistics

## Metadata
dw_id: `f3b4c15b`
prompt: `Add a /analysis endpoint. It will get a list of numbers. From that list we want statistical implication about the deviations, the mean, median, how many 0 values how many maximum values, quertiles etc.`

## Summary
Add a new `/analysis` API route to the existing Python HTTP server in `apps/main.py` so callers can submit a list of numbers and receive a structured statistical summary. The work needs both endpoint logic and tests because the current server only routes on method/path and does not yet expose a body-driven endpoint for computed results.

## Relevant Files
- `README.md` — Confirms the project layout and that `apps/` contains the application code being extended.
- `apps/main.py` — Contains the standard-library HTTP server, route dispatch, and response helpers that will need to be extended for a body-driven `/analysis` endpoint.
- `apps/test_main.py` — Holds the existing unit tests around `build_response` and should be expanded to cover the new analysis request/response contract and error cases.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Define the `/analysis` request and response contract within the existing server pattern
- Confirm the new endpoint should be modeled as `POST /analysis` with a JSON request body because the feature needs to receive an arbitrary list of numbers.
- Decide the exact payload shapes before coding, including a request such as `{"numbers": [1, 2, 3]}` and a response that includes at minimum the count, mean, median, quartiles, minimum, maximum, zero-value count, maximum-value count, and deviation metrics.
- Specify error responses for malformed JSON, missing `numbers`, non-list payloads, non-numeric items, and empty input so the endpoint has a stable contract.
- Files to modify: None

### 2. Refactor request handling in `apps/main.py` so routes can consume JSON input
- Extend `AppHandler.handle_method` to read the request body for methods that can send payloads, decode JSON, and pass the parsed data into the response-building path.
- Update `build_response` and/or introduce a small helper so route handling can receive both the request path and a parsed JSON payload without breaking the existing `/health`, `/hello`, and `/metrics` behavior.
- Keep the current JSON response helper and method-not-allowed pattern intact so the new endpoint matches the existing style.
- Files to modify: `apps/main.py`

### 3. Implement the statistical analysis logic for `/analysis`
- Add the `/analysis` route in `apps/main.py`, returning `405 Method Not Allowed` for unsupported methods and a JSON analysis payload for valid `POST` requests.
- Compute the requested statistics from the submitted number list, including central tendency (`mean`, `median`), spread/deviation values, quartiles, counts of zeroes, counts of items equal to the maximum value, and any supporting summary fields needed to interpret the result clearly.
- Prefer standard-library facilities for deterministic calculations and document any assumptions for quartile and deviation formulas directly in the code only if the implementation would otherwise be unclear.
- Files to modify: `apps/main.py`

### 4. Extend automated tests for the new endpoint and edge cases
- Add tests in `apps/test_main.py` that cover a successful analysis request and assert the expected statistical fields and representative values.
- Add negative tests for invalid JSON/body shapes, empty lists, non-numeric members, and unsupported methods so the endpoint contract is enforced explicitly.
- Preserve the existing route tests to ensure the body-handling refactor does not regress `/health`, `/hello`, `/metrics`, or unknown-route behavior.
- Files to modify: `apps/test_main.py`

### 5. Run Validation
- Compile the updated Python modules to catch syntax or typing mistakes introduced by the routing refactor.
- Run the Python unit tests for all existing and new route behavior.
- Start the local server and issue a real `POST /analysis` request with sample JSON to confirm the endpoint contract end to end.

## Validation Commands
- `uv run python -m py_compile apps/main.py apps/test_main.py`
- `uv run python -m unittest apps.test_main`
- `PORT=8000 uv run apps/main.py`
- `curl -i -X POST http://127.0.0.1:8000/analysis -H 'Content-Type: application/json' -d '{"numbers":[0,1,2,2,4,4,4]}'`
