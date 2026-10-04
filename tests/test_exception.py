import asyncio
import json
import unittest
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.core.exception import (
    AppException,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
    register_exception_handlers,
)


async def asgi_request(app: FastAPI, method: str, path: str) -> tuple[int, Any]:
    """最小 ASGI 调用器。

    项目没装 httpx，FastAPI 的 TestClient 用不了，这里直接按 ASGI 协议驱动应用，
    不引入额外依赖。
    """

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
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
        # Starlette 的 ServerErrorMiddleware 即使已经用兜底处理器发出了 500 响应，
        # 之后仍会把异常重新抛出（好让服务器记日志、让 TestClient 能选择性地抛）。
        # 响应已经发出去的话就忽略这次抛出，跟真实服务器的行为一致。
        if not sent:
            raise

    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(body.decode("utf-8"))


def build_app() -> FastAPI:
    """构造一个覆盖各类异常的测试应用。"""

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"hello": "world"}

    @app.get("/not-found")
    async def not_found() -> None:
        raise NotFoundError("用户不存在", data={"user_id": 42})

    @app.get("/unauthorized")
    async def unauthorized() -> None:
        raise UnauthorizedError

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise ForbiddenError

    @app.get("/custom-code")
    async def custom_code() -> None:
        raise AppException("自定义业务错误", code=10086, data={"k": "v"})

    @app.get("/validate")
    async def validate(page: int = Query(..., description="必填")) -> dict[str, int]:
        return {"page": page}

    @app.get("/duplicate")
    async def duplicate() -> None:
        raise IntegrityError("INSERT ...", {}, Exception("Duplicate entry"))

    @app.get("/db-down")
    async def db_down() -> None:
        raise SQLAlchemyError("connection refused")

    @app.get("/http-exception")
    async def http_exception() -> None:
        raise HTTPException(status_code=418, detail="我是茶壶")

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("意料之外的错误")

    return app


class ExceptionHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_app()

    def request(self, method: str, path: str) -> tuple[int, Any]:
        return asyncio.run(asgi_request(self.app, method, path))

    def test_normal_response_is_untouched(self) -> None:
        status, body = self.request("GET", "/ok")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"hello": "world"})

    def test_app_exception_uses_its_own_status_and_code(self) -> None:
        status, body = self.request("GET", "/not-found")

        self.assertEqual(status, 404)
        self.assertEqual(body, {"code": 404, "msg": "用户不存在", "data": {"user_id": 42}})

    def test_subclass_defaults(self) -> None:
        for path, expected in (
            ("/unauthorized", 401),
            ("/forbidden", 403),
            ("/duplicate", 409),
        ):
            with self.subTest(path=path):
                status, body = self.request("GET", path)

                self.assertEqual(status, expected)
                self.assertEqual(body["code"], expected)
                self.assertIsNone(body["data"])

    def test_app_exception_accepts_custom_code(self) -> None:
        status, body = self.request("GET", "/custom-code")

        self.assertEqual(status, 400)  # http_status 用基类默认值
        self.assertEqual(body["code"], 10086)
        self.assertEqual(body["msg"], "自定义业务错误")
        self.assertEqual(body["data"], {"k": "v"})

    def test_validation_error_lists_fields(self) -> None:
        status, body = self.request("GET", "/validate")

        self.assertEqual(status, 422)
        self.assertEqual(body["code"], ValidationError.code)
        self.assertEqual(body["msg"], ValidationError.msg)
        self.assertEqual(body["data"][0]["field"], "page")

    def test_integrity_error_wins_over_sqlalchemy_error(self) -> None:
        """IntegrityError 是 SQLAlchemyError 的子类，必须命中更具体的那个。"""

        status, body = self.request("GET", "/duplicate")

        self.assertEqual(status, 409)
        self.assertEqual(body["code"], ConflictError.code)

    def test_other_sqlalchemy_error_returns_500(self) -> None:
        status, body = self.request("GET", "/db-down")

        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 500)
        self.assertEqual(body["msg"], "服务器内部错误")

    def test_http_exception_keeps_status_and_detail(self) -> None:
        status, body = self.request("GET", "/http-exception")

        self.assertEqual(status, 418)
        self.assertEqual(body, {"code": 418, "msg": "我是茶壶", "data": None})

    def test_unknown_route_is_normalized(self) -> None:
        status, body = self.request("GET", "/no-such-route")

        self.assertEqual(status, 404)
        self.assertEqual(body["code"], 404)
        self.assertEqual(body["msg"], "Not Found")

    def test_unhandled_exception_returns_generic_message(self) -> None:
        status, body = self.request("GET", "/boom")

        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 500)
        self.assertEqual(body["msg"], "服务器内部错误")


if __name__ == "__main__":
    unittest.main()
