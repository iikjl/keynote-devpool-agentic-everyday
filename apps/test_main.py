import io
import json
import unittest
from http import HTTPStatus

from apps.main import APP_VERSION, AppHandler, build_response


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


class AnalysisEndpointTests(unittest.TestCase):
    def test_analysis_endpoint_returns_summary_statistics(self) -> None:
        status, headers, body = build_response(
            "POST",
            "/analysis",
            request_json={"numbers": [0, 1, 2, 2, 4, 4, 4]},
        )
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["count"], 7)
        self.assertEqual(payload["sum"], 17)
        self.assertEqual(payload["minimum"], 0)
        self.assertEqual(payload["maximum"], 4)
        self.assertEqual(payload["mean"], 2.4285714285714284)
        self.assertEqual(payload["median"], 2)
        self.assertEqual(payload["quartiles"], {"q1": 1.5, "q2": 2, "q3": 4})
        self.assertEqual(payload["zero_count"], 1)
        self.assertEqual(payload["maximum_value_count"], 3)
        self.assertEqual(
            payload["deviations"],
            {
                "range": 4,
                "interquartile_range": 2.5,
                "variance": 2.2448979591836733,
                "standard_deviation": 1.498298354528788,
            },
        )

    def test_analysis_requires_json_object_body(self) -> None:
        status, _, body = build_response("POST", "/analysis")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(body),
            {"error": "request body must be a JSON object"},
        )

    def test_analysis_rejects_non_object_json_payload(self) -> None:
        status, _, body = build_response("POST", "/analysis", request_json=[1, 2, 3])

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(body),
            {"error": "request body must be a JSON object"},
        )

    def test_analysis_requires_numbers_field(self) -> None:
        status, _, body = build_response("POST", "/analysis", request_json={})

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(body),
            {"error": "request body must include a 'numbers' field"},
        )

    def test_analysis_requires_numbers_to_be_a_list(self) -> None:
        status, _, body = build_response(
            "POST",
            "/analysis",
            request_json={"numbers": "not-a-list"},
        )

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(body),
            {"error": "'numbers' must be a list of numbers"},
        )

    def test_analysis_rejects_empty_numbers(self) -> None:
        status, _, body = build_response(
            "POST",
            "/analysis",
            request_json={"numbers": []},
        )

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(body),
            {"error": "'numbers' must not be empty"},
        )

    def test_analysis_rejects_non_numeric_values(self) -> None:
        status, _, body = build_response(
            "POST",
            "/analysis",
            request_json={"numbers": [1, "two", True]},
        )

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(body),
            {"error": "'numbers' must contain only finite numeric values"},
        )

    def test_analysis_method_not_allowed_for_get(self) -> None:
        status, headers, body = build_response("GET", "/analysis")

        self.assertEqual(status, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertEqual(headers["Allow"], "POST")
        self.assertEqual(
            json.loads(body),
            {"error": "GET is not allowed for /analysis"},
        )


class RequestBodyParsingTests(unittest.TestCase):
    def make_handler(self, raw_body: bytes) -> AppHandler:
        handler = AppHandler.__new__(AppHandler)
        handler.headers = {"Content-Length": str(len(raw_body))}
        handler.rfile = io.BytesIO(raw_body)
        return handler

    def test_parse_json_request_returns_error_for_malformed_json(self) -> None:
        handler = self.make_handler(b'{"numbers": [1, 2,}')

        request_json, request_json_error = handler.parse_json_request("POST")

        self.assertIsNone(request_json)
        self.assertEqual(request_json_error, "request body must be valid JSON")


if __name__ == "__main__":
    unittest.main()
