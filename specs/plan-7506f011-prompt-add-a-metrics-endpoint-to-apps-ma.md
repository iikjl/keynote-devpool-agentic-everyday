# Plan: Add /metrics endpoint with request count and uptime

## Metadata
dw_id: `7506f011`
prompt: `### Prompt

Add a /metrics endpoint to apps/main.py that returns request count and uptime.
Cover it with a test in apps/test_main.py.`

## Summary
Add a `/metrics` endpoint to `apps/main.py` that returns a JSON payload with the total number of requests processed and the server uptime in seconds. The endpoint follows the existing routing pattern (`build_response`) and the test mirrors the style of existing tests in `apps/test_main.py`.

## Relevant Files

- `apps/main.py` — Main application file; needs a request counter, uptime calculation, and a new `/metrics` route inside `build_response`.
- `apps/test_main.py` — Existing test file; needs new test cases for the `/metrics` endpoint covering the happy path and method-not-allowed behaviour.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Add a module-level request counter to `apps/main.py`
- Add a module-level integer variable `REQUEST_COUNT: int = 0` just below `PROCESS_START_TIME`.
- This counter will be incremented on every request.

### 2. Increment the counter on every request
- In `AppHandler.handle_method`, increment `global REQUEST_COUNT` before calling `build_response`.
- Use `global REQUEST_COUNT` declaration at the top of the method body.

### 3. Add a `request_count` parameter to `build_response`
- Add `request_count: int = 0` as a keyword-only parameter to `build_response` (alongside the existing `include_health_details`).
- Pass the live counter value when calling `build_response` from `handle_method`.

### 4. Implement the `/metrics` route inside `build_response`
- After the `/hello` block and before the final 404 fallback, add:
  ```python
  if path == "/metrics":
      if method == "GET":
          return json_response(
              HTTPStatus.OK,
              {
                  "request_count": request_count,
                  "uptime": round(time.monotonic() - PROCESS_START_TIME, 3),
              },
          )
      status, headers, body = json_response(
          HTTPStatus.METHOD_NOT_ALLOWED,
          {"error": f"{method} is not allowed for {path}"},
      )
      headers["Allow"] = "GET"
      return status, headers, body
  ```

### 5. Add tests for `/metrics` in `apps/test_main.py`
- Import nothing new — `build_response` is already imported.
- Add a test class `MetricsEndpointTests(unittest.TestCase)` with these test methods:
  - `test_metrics_returns_ok_with_request_count_and_uptime`: Call `build_response("GET", "/metrics", request_count=42)`, assert `status == HTTPStatus.OK`, `payload["request_count"] == 42`, `"uptime"` is present and is a non-negative number.
  - `test_metrics_method_not_allowed_for_post`: Call `build_response("POST", "/metrics")`, assert `status == HTTPStatus.METHOD_NOT_ALLOWED`, `headers["Allow"] == "GET"`.

### 6. Run Validation
- Run the existing test suite to confirm no regressions and that the new tests pass.

## Validation Commands
```bash
# From the repository root
python -m pytest apps/test_main.py -v
# or with unittest directly
python -m unittest discover -s . -p "test_*.py" -v
```
