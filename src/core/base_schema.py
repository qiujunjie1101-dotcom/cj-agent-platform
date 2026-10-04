"""统一响应结构。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """统一响应体：``code`` 业务码、``msg`` 提示语、``data`` 响应数据。

    用法::

        Response(code=0, msg="ok")
        Response[User](code=0, msg="ok", data={"id": 1})
    """

    code: int
    msg: str
    data: T | None = None


__all__ = ["Response"]