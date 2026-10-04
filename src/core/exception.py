"""全局异常处理：统一业务异常 + FastAPI 异常处理器。

所有错误响应统一成这个格式（与 base_schema.Response 保持一致）::

    {"code": 404, "msg": "资源不存在", "data": null}

用法——创建完 FastAPI 应用后注册一次即可::

    from fastapi import FastAPI
    from src.core.exception import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

之后业务代码里直接抛异常就行，不需要在每个路由里 try/except::

    from src.core.exception import NotFoundError

    async def get_user(user_id: int) -> User:
        user = await repo.get(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        return user

HTTP 状态码会跟着异常走（404 就是 404），响应体里的 ``code`` 同时也带着同一个业务码。
如果你们的规范要求「HTTP 永远返回 200，只看 body 里的 code」，把
:func:`register_exception_handlers` 里各处理器传的 ``http_status`` 统一改成 200 即可。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.config import settings
from src.core.logger import get_logger


logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# 业务异常
# --------------------------------------------------------------------------- #
class AppException(Exception):
    """所有业务异常的基类。

    子类用类属性声明默认的 HTTP 状态码、业务码和提示语；实例化时可以覆盖提示语，
    并把结构化的补充信息放进 ``data``::

        raise NotFoundError("用户不存在", data={"user_id": 42})
    """

    #: HTTP 响应状态码
    http_status: int = 400
    #: 响应体里的业务码，默认与 HTTP 状态码一致
    code: int = 400
    #: 默认提示语，实例化时传入 msg 可覆盖
    msg: str = "请求有误"

    def __init__(
        self,
        msg: str | None = None,
        *,
        code: int | None = None,
        data: Any = None,
    ) -> None:
        if msg is not None:
            self.msg = msg
        if code is not None:
            self.code = code
        self.data = data
        super().__init__(self.msg)


class BadRequestError(AppException):
    """请求参数不合法。"""

    http_status = 400
    code = 400
    msg = "请求参数有误"


class UnauthorizedError(AppException):
    """未登录，或登录状态已失效。"""

    http_status = 401
    code = 401
    msg = "未登录或登录状态已过期"


class ForbiddenError(AppException):
    """已登录但没有权限。"""

    http_status = 403
    code = 403
    msg = "没有权限执行该操作"


class NotFoundError(AppException):
    """资源不存在。"""

    http_status = 404
    code = 404
    msg = "资源不存在"


class ConflictError(AppException):
    """资源冲突，例如唯一键重复。"""

    http_status = 409
    code = 409
    msg = "资源已存在或状态冲突"


class ValidationError(AppException):
    """参数校验失败。

    注意：和 pydantic 的 ValidationError 同名。同一个文件里若两个都要用，
    把 pydantic 的那个起个别名导入：``from pydantic import ValidationError as
    PydanticValidationError``。
    """

    http_status = 422
    code = 422
    msg = "参数校验失败"


class InternalError(AppException):
    """服务端内部错误。"""

    http_status = 500
    code = 500
    msg = "服务器内部错误"


# --------------------------------------------------------------------------- #
# 异常处理器
# --------------------------------------------------------------------------- #
def error_response(
    *,
    code: int,
    msg: str,
    http_status: int,
    data: Any = None,
) -> JSONResponse:
    """按统一格式构造错误响应。

    注意 ``data`` 必须是可 JSON 序列化的内容，传 ORM 对象会序列化失败。
    """

    return JSONResponse(
        status_code=http_status,
        content={"code": code, "msg": msg, "data": data},
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """业务异常：属于预期内的分支，记 warning 即可，不需要堆栈。"""

    logger.warning(
        "%s %s -> [%s] %s", request.method, request.url.path, exc.code, exc.msg
    )
    return error_response(
        code=exc.code,
        msg=exc.msg,
        http_status=exc.http_status,
        data=exc.data,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """请求参数校验失败（FastAPI 自动抛出的 422）。"""

    # loc 的第一段是参数来源（body / query / path），对调用方没意义，去掉
    details = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())[1:]) or "-",
            "message": error.get("msg", ""),
        }
        for error in exc.errors()
    ]
    logger.warning("%s %s -> 参数校验失败 %s", request.method, request.url.path, details)
    return error_response(
        code=ValidationError.code,
        msg=ValidationError.msg,
        http_status=ValidationError.http_status,
        data=details,
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """数据库约束冲突，最常见的是唯一键重复。"""

    logger.warning("%s %s -> 数据库约束冲突: %s", request.method, request.url.path, exc.orig)
    return error_response(
        code=ConflictError.code,
        msg=ConflictError.msg,
        http_status=ConflictError.http_status,
    )


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """其它数据库错误，统一按 500 处理并记录堆栈。"""

    logger.exception("%s %s -> 数据库错误", request.method, request.url.path)
    return error_response(
        code=InternalError.code,
        msg=InternalError.msg,
        http_status=InternalError.http_status,
        # 仅在调试模式下回传细节，生产环境不泄漏内部信息
        data=f"{type(exc).__name__}: {exc}" if settings.app_debug else None,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """框架自身抛出的 HTTPException（路由不存在、方法不允许等），统一成同样的格式。"""

    return error_response(
        code=exc.status_code,
        msg=str(exc.detail),
        http_status=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：没被上面任何处理器接住的异常。

    这里必须把完整堆栈打进日志，否则线上出问题只剩一句"服务器内部错误"没法查。
    """

    logger.exception("%s %s -> 未处理异常", request.method, request.url.path)
    return error_response(
        code=InternalError.code,
        msg=InternalError.msg,
        http_status=InternalError.http_status,
        data=f"{type(exc).__name__}: {exc}" if settings.app_debug else None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """把所有异常处理器注册到 FastAPI 应用上。

    Starlette 按异常类型精确匹配，注册顺序不影响结果；更具体的类型会优先命中，
    只有都没命中时才落到 ``Exception`` 兜底。
    """

    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # IntegrityError 是 SQLAlchemyError 的子类，必须单独注册，否则会被后者吞掉
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


__all__ = [
    "AppException",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "InternalError",
    "NotFoundError",
    "UnauthorizedError",
    "ValidationError",
    "error_response",
    "register_exception_handlers",
]
