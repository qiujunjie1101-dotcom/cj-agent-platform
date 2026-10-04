import asyncio
import unittest
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from src.middlewares.logging import (
    REQUEST_ID_HEADER,
    RequestLoggingMiddleware,
    get_request_id,
)

LOGGER_NAME = "src.middlewares.logging"


async def asgi_request(
    app: FastAPI,
    method: str = "GET",
    path: str = "/",
    *,
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, str], Any]:
    """最小 ASGI 调用器：项目没装 httpx，直接按 ASGI 协议驱动应用。"""

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "root_path": "",
        "headers": [(b"host", b"testserver"), *(headers or [])],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    try:
        await app(scope, receive, send)
    except Exception:
        # ServerErrorMiddleware 发出 500 后仍会把异常重新抛出，响应已发出则忽略
        if not sent:
            raise

    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    response_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return start["status"], response_headers, body


def build_app(**middleware_kwargs: Any) -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"hello": "world"}

    @app.get("/not-found")
    async def not_found() -> None:
        raise HTTPException(status_code=404, detail="没有")

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("意料之外的错误")

    @app.get("/echo-request-id")
    async def echo_request_id(request: Request) -> dict[str, str | None]:
        return {"request_id": get_request_id(request)}

    app.add_middleware(RequestLoggingMiddleware, **middleware_kwargs)
    return app


class RequestLoggingMiddlewareTests(unittest.TestCase):
    def request(self, app: FastAPI, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return asyncio.run(asgi_request(app, *args, **kwargs))

    def test_successful_request_logged_at_info(self) -> None:
        app = build_app(exclude_paths=None)

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            status, _, _ = self.request(app, "GET", "/ok")

        self.assertEqual(status, 200)
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertEqual(record.levelname, "INFO")
        self.assertIn("GET /ok -> 200", record.getMessage())
        self.assertIn("client=127.0.0.1", record.getMessage())
        self.assertEqual(record.status_code, 200)
        self.assertEqual(record.path, "/ok")

    def test_query_string_is_logged(self) -> None:
        app = build_app(exclude_paths=None)

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            self.request(app, "GET", "/ok", query_string=b"page=1&size=10")

        self.assertIn("/ok?page=1&size=10", captured.records[0].getMessage())
        self.assertEqual(captured.records[0].query_string, "page=1&size=10")

    def test_client_error_logged_at_warning(self) -> None:
        app = build_app(exclude_paths=None)

        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            status, _, _ = self.request(app, "GET", "/not-found")

        self.assertEqual(status, 404)
        self.assertEqual(captured.records[0].levelname, "WARNING")

    def test_unhandled_exception_logs_error_with_traceback(self) -> None:
        app = build_app(exclude_paths=None)

        with self.assertLogs(LOGGER_NAME, level="ERROR") as captured:
            status, _, _ = self.request(app, "GET", "/boom")

        self.assertEqual(status, 500)
        record = captured.records[0]
        self.assertEqual(record.levelname, "ERROR")
        self.assertIsNotNone(record.exc_info)

    def test_excluded_path_is_not_logged(self) -> None:
        app = build_app(exclude_paths={"/health", "/ok"})

        with self.assertNoLogs(LOGGER_NAME, level="DEBUG"):
            status, _, _ = self.request(app, "GET", "/ok")

        self.assertEqual(status, 200)

    def test_incoming_request_id_is_reused_and_echoed(self) -> None:
        app = build_app(exclude_paths=None)

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            _, response_headers, _ = self.request(
                app,
                "GET",
                "/ok",
                headers=[(REQUEST_ID_HEADER.lower().encode(), b"trace-123")],
            )

        self.assertEqual(response_headers[REQUEST_ID_HEADER.lower()], "trace-123")
        self.assertIn("request_id=trace-123", captured.records[0].getMessage())

    def test_request_id_is_generated_and_available_to_handlers(self) -> None:
        app = build_app(exclude_paths=None)

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            _, response_headers, body = self.request(app, "GET", "/echo-request-id")

        record_request_id = captured.records[0].request_id
        self.assertTrue(record_request_id)
        self.assertEqual(response_headers[REQUEST_ID_HEADER.lower()], record_request_id)
        self.assertEqual(body, f'{{"request_id":"{record_request_id}"}}'.encode())

    def test_forwarded_for_is_used_only_when_trusted(self) -> None:
        forwarded = [(b"x-forwarded-for", b"203.0.113.7, 10.0.0.1")]

        with self.assertLogs(LOGGER_NAME, level="INFO") as untrusted:
            self.request(
                build_app(exclude_paths=None), "GET", "/ok", headers=forwarded
            )
        with self.assertLogs(LOGGER_NAME, level="INFO") as trusted:
            self.request(
                build_app(exclude_paths=None, trust_proxy_headers=True),
                "GET",
                "/ok",
                headers=forwarded,
            )

        self.assertIn("client=127.0.0.1", untrusted.records[0].getMessage())
        self.assertIn("client=203.0.113.7", trusted.records[0].getMessage())

    def test_slow_request_is_downgraded_to_warning(self) -> None:
        app = build_app(exclude_paths=None, slow_request_threshold_ms=0)

        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            status, _, _ = self.request(app, "GET", "/ok")

        self.assertEqual(status, 200)
        self.assertEqual(captured.records[0].levelname, "WARNING")

    def test_non_http_scope_passes_through(self) -> None:
        app = build_app(exclude_paths=None)
        called: list[str] = []

        async def run() -> None:
            async def receive() -> dict[str, Any]:
                return {"type": "lifespan.startup"}

            async def send(message: dict[str, Any]) -> None:
                called.append(message["type"])

            await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)

        with self.assertNoLogs(LOGGER_NAME, level="DEBUG"):
            asyncio.run(run())

        self.assertIn("lifespan.startup.complete", called)


if __name__ == "__main__":
    unittest.main()
