"""请求日志中间件：为每个 HTTP 请求生成 request_id，并记录访问日志。

主要能力：

- 复用调用方传入的 ``X-Request-ID``，没有则自动生成，并写回响应头；
- 通过 :func:`get_request_id` 让业务代码拿到当前请求的 request_id；
- 按结果分级：5xx / 未处理异常记 ERROR，4xx 记 WARNING，处理偏慢记 WARNING，其余记 INFO；
- 支持 ``exclude_paths`` 跳过健康检查等路径，支持按需信任反向代理的 ``X-Forwarded-For``。

用法::

    from fastapi import FastAPI
    from src.middlewares.logging import RequestLoggingMiddleware

    app = FastAPI()
    app.add_middleware(
        RequestLoggingMiddleware,
        exclude_paths={"/health", "/metrics"},
        trust_proxy_headers=True,
    )
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.core.logger import get_logger


REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_SLOW_REQUEST_THRESHOLD_MS = 500.0

logger = get_logger(__name__)


def get_request_id(request: Request) -> str | None:
    """返回当前请求的 request_id；若中间件未处理该请求则返回 None。"""

    return getattr(request.state, "request_id", None)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的访问日志，并维护 request_id。"""

    def __init__(
        self,
        app: ASGIApp,
        *,
        exclude_paths: Iterable[str] | None = None,
        trust_proxy_headers: bool = False,
        slow_request_threshold_ms: float = DEFAULT_SLOW_REQUEST_THRESHOLD_MS,
    ) -> None:
        super().__init__(app)
        self.exclude_paths = frozenset(exclude_paths or ())
        self.trust_proxy_headers = trust_proxy_headers
        self.slow_request_threshold_ms = slow_request_threshold_ms

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 交给外层（ServerErrorMiddleware / 全局异常处理器）继续处理，这里只负责记录
            self._log_request(
                request,
                request_id=request_id,
                status_code=500,
                duration_ms=(time.perf_counter() - started) * 1000,
                exc_info=True,
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        self._log_request(
            request,
            request_id=request_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    def _client_host(self, request: Request) -> str:
        """取客户端地址；开启代理信任时优先使用 X-Forwarded-For 的第一段。"""

        if self.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "-"

    def _log_request(
        self,
        request: Request,
        *,
        request_id: str,
        status_code: int,
        duration_ms: float,
        exc_info: bool = False,
    ) -> None:
        path = request.url.path
        query_string = request.url.query
        target = f"{path}?{query_string}" if query_string else path
        client = self._client_host(request)

        if exc_info or status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400 or duration_ms >= self.slow_request_threshold_ms:
            level = logging.WARNING
        else:
            level = logging.INFO

        logger.log(
            level,
            "%s %s -> %s | client=%s | request_id=%s | %.1fms",
            request.method,
            target,
            status_code,
            client,
            request_id,
            duration_ms,
            exc_info=exc_info,
            extra={
                "status_code": status_code,
                "path": path,
                "query_string": query_string,
                "request_id": request_id,
                "duration_ms": round(duration_ms, 3),
                "client": client,
            },
        )


__all__ = [
    "DEFAULT_SLOW_REQUEST_THRESHOLD_MS",
    "REQUEST_ID_HEADER",
    "RequestLoggingMiddleware",
    "get_request_id",
]