#!/usr/bin/env -S uv run python

import json
import math
import os
import statistics
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Tuple

APP_VERSION = "1.0.0"
PROCESS_START_TIME = time.monotonic()
REQUEST_COUNT: int = 0

Response = Tuple[HTTPStatus, Dict[str, str], bytes]
JsonPayload = Dict[str, object]


def json_response(status: HTTPStatus, payload: JsonPayload) -> Response:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    return status, headers, body


def method_not_allowed_response(path: str, method: str, allow: str) -> Response:
    status, headers, body = json_response(
        HTTPStatus.METHOD_NOT_ALLOWED,
        {"error": f"{method} is not allowed for {path}"},
    )
    headers["Allow"] = allow
    return status, headers, body


def bad_request_response(message: str) -> Response:
    return json_response(HTTPStatus.BAD_REQUEST, {"error": message})


def is_numeric_value(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def normalize_number(value: int | float) -> int | float:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def build_analysis_response(
    request_json: object | None,
    request_json_error: str | None,
) -> Response:
    if request_json_error is not None:
        return bad_request_response(request_json_error)
    if not isinstance(request_json, dict):
        return bad_request_response("request body must be a JSON object")
    if "numbers" not in request_json:
        return bad_request_response("request body must include a 'numbers' field")

    numbers = request_json["numbers"]
    if not isinstance(numbers, list):
        return bad_request_response("'numbers' must be a list of numbers")
    if not numbers:
        return bad_request_response("'numbers' must not be empty")
    if any(not is_numeric_value(value) for value in numbers):
        return bad_request_response(
            "'numbers' must contain only finite numeric values"
        )

    numeric_values = [float(value) for value in numbers]
    minimum = min(numeric_values)
    maximum = max(numeric_values)
    median = statistics.median(numeric_values)
    if len(numeric_values) == 1:
        q1 = median
        q3 = median
    else:
        # Use inclusive quartiles and population variance/stddev for stable API output.
        q1, _, q3 = statistics.quantiles(numeric_values, n=4, method="inclusive")

    payload: JsonPayload = {
        "count": len(numeric_values),
        "sum": normalize_number(sum(numeric_values)),
        "minimum": normalize_number(minimum),
        "maximum": normalize_number(maximum),
        "mean": normalize_number(statistics.fmean(numeric_values)),
        "median": normalize_number(median),
        "quartiles": {
            "q1": normalize_number(q1),
            "q2": normalize_number(median),
            "q3": normalize_number(q3),
        },
        "zero_count": sum(1 for value in numeric_values if value == 0),
        "maximum_value_count": sum(1 for value in numeric_values if value == maximum),
        "deviations": {
            "range": normalize_number(maximum - minimum),
            "interquartile_range": normalize_number(q3 - q1),
            "variance": normalize_number(statistics.pvariance(numeric_values)),
            "standard_deviation": normalize_number(
                statistics.pstdev(numeric_values)
            ),
        },
    }
    return json_response(HTTPStatus.OK, payload)


def build_response(
    method: str,
    path: str,
    *,
    request_json: object | None = None,
    request_json_error: str | None = None,
    include_health_details: bool = False,
    request_count: int = 0,
) -> Response:
    if path == "/health":
        if method == "GET":
            payload: JsonPayload = {"status": "ok"}
            if include_health_details:
                payload["uptime"] = round(time.monotonic() - PROCESS_START_TIME, 3)
                payload["version"] = APP_VERSION
            status, headers, body = json_response(
                HTTPStatus.OK,
                payload,
            )
            headers["Cache-Control"] = "no-store"
            return status, headers, body
        return method_not_allowed_response(path, method, "GET")

    if path == "/hello":
        if method == "GET":
            return json_response(HTTPStatus.OK, {"message": "hello world"})
        return method_not_allowed_response(path, method, "GET")

    if path == "/metrics":
        if method == "GET":
            return json_response(
                HTTPStatus.OK,
                {
                    "request_count": request_count,
                    "uptime": round(time.monotonic() - PROCESS_START_TIME, 3),
                },
            )
        return method_not_allowed_response(path, method, "GET")

    if path == "/analysis":
        if method == "POST":
            return build_analysis_response(request_json, request_json_error)
        return method_not_allowed_response(path, method, "POST")

    return json_response(
        HTTPStatus.NOT_FOUND,
        {"error": f"no route matches {method} {path}"},
    )


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.handle_method("GET")

    def do_HEAD(self) -> None:
        self.handle_method("HEAD")

    def do_POST(self) -> None:
        self.handle_method("POST")

    def do_PUT(self) -> None:
        self.handle_method("PUT")

    def do_PATCH(self) -> None:
        self.handle_method("PATCH")

    def do_DELETE(self) -> None:
        self.handle_method("DELETE")

    def do_OPTIONS(self) -> None:
        self.handle_method("OPTIONS")

    def handle_method(self, method: str) -> None:
        global REQUEST_COUNT
        REQUEST_COUNT += 1
        request_json, request_json_error = self.parse_json_request(method)
        self.respond(
            *build_response(
                method,
                self.path,
                request_json=request_json,
                request_json_error=request_json_error,
                include_health_details=os.environ.get("HEALTH_DETAILS") == "1",
                request_count=REQUEST_COUNT,
            )
        )

    def parse_json_request(self, method: str) -> Tuple[object | None, str | None]:
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None, None

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return None, None

        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8")), None
        except UnicodeDecodeError:
            return None, "request body must be valid UTF-8 JSON"
        except json.JSONDecodeError:
            return None, "request body must be valid JSON"

    def respond(
        self,
        status: HTTPStatus,
        headers: Dict[str, str],
        body: bytes,
    ) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

def run_server(port: int | None = None) -> None:
    server_port = port or int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", server_port), AppHandler)
    print(f"Serving on http://127.0.0.1:{server_port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
