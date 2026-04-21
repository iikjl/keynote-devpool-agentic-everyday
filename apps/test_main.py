import json
import unittest
from http import HTTPStatus

from apps.main import APP_VERSION, build_response


class BuildResponseTests(unittest.TestCase):
    def test_health_endpoint_returns_public_status_only_by_default(self) -> None:
        status, headers, body = build_response("GET", "/health")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(payload, {"status": "ok"})

    def test_health_endpoint_can_return_uptime_and_version_when_enabled(self) -> None:
        status, headers, body = build_response(
            "GET",
            "/health",
            include_health_details=True,
        )
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["version"], APP_VERSION)
        self.assertIn("uptime", payload)
        self.assertIsInstance(payload["uptime"], (int, float))
        self.assertGreaterEqual(payload["uptime"], 0)

    def test_hello_endpoint_returns_ok_json(self) -> None:
        status, headers, body = build_response("GET", "/hello")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(body), {"message": "hello world"})

    def test_ping_endpoint_returns_ok_json(self) -> None:
        status, headers, body = build_response("GET", "/ping")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(body), {"pong": True})

    def test_ping_endpoint_rejects_non_get_methods(self) -> None:
        status, headers, body = build_response("POST", "/ping")

        self.assertEqual(status, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["Allow"], "GET")
        self.assertEqual(json.loads(body), {"error": "POST is not allowed for /ping"})

    def test_unknown_route_returns_not_found_json(self) -> None:
        status, headers, body = build_response("GET", "/unknown")

        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(
            json.loads(body),
            {"error": "no route matches GET /unknown"},
        )


class MetricsEndpointTests(unittest.TestCase):
    def test_metrics_returns_ok_with_request_count_and_uptime(self) -> None:
        status, headers, body = build_response("GET", "/metrics", request_count=42)
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["request_count"], 42)
        self.assertIn("uptime", payload)
        self.assertIsInstance(payload["uptime"], (int, float))
        self.assertGreaterEqual(payload["uptime"], 0)

    def test_metrics_method_not_allowed_for_post(self) -> None:
        status, headers, body = build_response("POST", "/metrics")

        self.assertEqual(status, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertEqual(headers["Allow"], "GET")


if __name__ == "__main__":
    unittest.main()
