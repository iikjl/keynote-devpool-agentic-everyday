#!/usr/bin/env -S uv run python

import json
import os
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


def build_response(
    method: str,
    path: str,
    *,
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
        status, headers, body = json_response(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": f"{method} is not allowed for {path}"},
        )
        headers["Allow"] = "GET"
        return status, headers, body

    if path == "/hello":
        if method == "GET":
            return json_response(HTTPStatus.OK, {"message": "hello world"})
        status, headers, body = json_response(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": f"{method} is not allowed for {path}"},
        )
        headers["Allow"] = "GET"
        return status, headers, body

    if path == "/ping":
        if method == "GET":
            return json_response(HTTPStatus.OK, {"pong": True})
        status, headers, body = json_response(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": f"{method} is not allowed for {path}"},
        )
        headers["Allow"] = "GET"
        return status, headers, body

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
        self.respond(
            *build_response(
                method,
                self.path,
                include_health_details=os.environ.get("HEALTH_DETAILS") == "1",
                request_count=REQUEST_COUNT,
            )
        )

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
