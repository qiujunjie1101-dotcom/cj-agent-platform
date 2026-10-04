"""通用异步仓储基类，封装单表的增删改查。

设计约定：

- 仓储**只 flush，不 commit**。事务边界由调用方掌握——在 Web 请求里就是
  :func:`src.infra.database.get_db_session`，它会在请求正常结束时统一提交、
  出错时统一回滚。仓储主动 commit 会把这个边界打散，导致一个请求里的多次
  写操作无法一起回滚。
- ``create`` / ``update`` 之后会 ``refresh``。MySQL 不支持 INSERT ... RETURNING，
  服务器侧生成的字段（``id``、``created_at`` 等）在 flush 后处于过期状态；
  异步下直接访问过期属性会抛 ``MissingGreenlet``，所以这里显式取回。
- 查询条件统一用关键字参数传递，下划线命名见 :data:`FILTER_OPERATORS`。

用法::

    class UserRepository(BaseRepository[User]):
        model = User

    async def handler(session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.create(nickname="cj")
        await repo.list(status="active", id__gt=10, order_by="-created_at", limit=20)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, Select, false, func, inspect, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_model import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)

# 支持的过滤运算符：字段名__运算符=值，例如 nickname__like="%c%"
# 不写运算符时默认按相等匹配。
FILTER_OPERATORS: dict[str, Callable[[Any, Any], ColumnElement[bool]]] = {
    "eq": lambda column, value: column == value,
    "ne": lambda column, value: column != value,
    "gt": lambda column, value: column > value,
    "ge": lambda column, value: column >= value,
    "lt": lambda column, value: column < value,
    "le": lambda column, value: column <= value,
    "in": lambda column, value: column.in_(value),
    "notin": lambda column, value: column.not_in(value),
    "like": lambda column, value: column.like(value),
    "ilike": lambda column, value: column.ilike(value),
    "isnull": lambda column, value: column.is_(None) if value else column.is_not(None),
}


class BaseRepository(Generic[ModelT]):
    """单表增删改查的通用实现，子类只需声明 ``model``。

    ::

        class UserRepository(BaseRepository[User]):
            model = User
    """

    #: 由子类指定，或通过构造函数传入
    model: type[ModelT]

    def __init__(
        self, session: AsyncSession, model: type[ModelT] | None = None
    ) -> None:
        self.session = session
        if model is not None:
            self.model = model
        if getattr(self, "model", None) is None:
            raise TypeError(
                f"{type(self).__name__} 必须指定 model 属性，或通过构造函数传入"
            )

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @property
    def _mapper(self) -> Any:
        return inspect(self.model)

    def _resolve_column(self, name: str) -> Any:
        """把字段名解析成映射列，字段不存在时给出明确报错。"""

        columns = self._mapper.columns
        if name not in columns:
            raise ValueError(f"{self.model.__name__} 上不存在字段：{name}")
        return columns[name]

    def _build_conditions(self, filters: dict[str, Any]) -> list[ColumnElement[bool]]:
        """把 ``字段名[__运算符]=值`` 形式的过滤条件翻译成 SQL 表达式。"""

        conditions: list[ColumnElement[bool]] = []
        for key, value in filters.items():
            name, _, operator = key.partition("__")
            operator = operator or "eq"
            if operator not in FILTER_OPERATORS:
                allowed = ", ".join(sorted(FILTER_OPERATORS))
                raise ValueError(f"不支持的过滤运算符 {operator!r}，可选：{allowed}")

            column = self._resolve_column(name)

            # 空集合的 IN / NOT IN 交给 SQLAlchemy 会生成冗余表达式，这里直接短路。
            if operator in {"in", "notin"} and isinstance(value, (list, tuple, set)):
                if not value:
                    conditions.append(false() if operator == "in" else true())
                    continue

            conditions.append(FILTER_OPERATORS[operator](column, value))
        return conditions

    def _apply_filters(
        self, statement: Select[Any], filters: dict[str, Any]
    ) -> Select[Any]:
        conditions = self._build_conditions(filters)
        return statement.where(*conditions) if conditions else statement

    def _apply_order_by(self, statement: Select[Any], order_by: Any) -> Select[Any]:
        """支持 ``"created_at"`` / ``"-created_at"``（前缀 ``-`` 表示倒序）或列表达式。"""

        if order_by is None:
            return statement

        expressions = [order_by] if isinstance(order_by, str) else list(order_by)
        clauses: list[ColumnElement[Any]] = []
        for expression in expressions:
            if isinstance(expression, str):
                descending = expression.startswith("-")
                column = self._resolve_column(expression.lstrip("+-"))
                clauses.append(column.desc() if descending else column.asc())
            else:
                clauses.append(expression)
        return statement.order_by(*clauses) if clauses else statement

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    async def get(self, pk: Any) -> ModelT | None:
        """按主键查询，命中会话标识映射时不会产生额外 SQL。"""

        return await self.session.get(self.model, pk)

    async def get_by(self, **filters: Any) -> ModelT | None:
        """按条件查询单条记录，无条件时返回表中第一条。"""

        statement = self._apply_filters(select(self.model), filters).limit(1)
        return (await self.session.execute(statement)).scalars().first()

    async def list(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        order_by: Any = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        """按条件查询列表。

        ``order_by`` 缺省时结果顺序由数据库决定；需要分页请显式排序，
        否则翻页可能出现重复或漏行。
        """

        statement = self._apply_filters(select(self.model), filters)
        statement = self._apply_order_by(statement, order_by)
        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return (await self.session.execute(statement)).scalars().all()

    async def count(self, **filters: Any) -> int:
        """统计满足条件的记录数。"""

        statement = self._apply_filters(
            select(func.count()).select_from(self.model), filters
        )
        return (await self.session.execute(statement)).scalar_one()

    async def exists(self, **filters: Any) -> bool:
        """判断是否存在满足条件的记录，比 ``count`` 更省资源。"""

        statement = self._apply_filters(
            select(self.model).limit(1), filters
        )
        return (await self.session.execute(statement)).scalars().first() is not None

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    async def create(self, **values: Any) -> ModelT:
        """新增一条记录并回填服务器侧生成的字段。"""

        instance = self.model(**values)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> Sequence[ModelT]:
        """批量新增，插入阶段只 flush 一次。

        注意：为了让 ``id`` / ``created_at`` 等服务器侧字段立即可读，这里仍会对每条
        记录做一次 ``refresh``。SQLAlchemy 没有批量 refresh 接口，所以省下的是插入
        开销；如果不需要回读这些字段，直接 ``session.add_all`` 更划算。
        """

        instances = [self.model(**values) for values in items]
        if not instances:
            return instances
        self.session.add_all(instances)
        await self.session.flush()
        for instance in instances:
            await self.session.refresh(instance)
        return instances

    async def update(self, instance: ModelT, **values: Any) -> ModelT:
        """更新给定实例的字段，返回同一个实例。"""

        for field, value in values.items():
            # 校验字段名，避免把拼错的字段悄悄挂成普通属性
            self._resolve_column(field)
            setattr(instance, field, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update_by_id(self, pk: Any, **values: Any) -> ModelT | None:
        """按主键更新，记录不存在时返回 ``None``。"""

        instance = await self.get(pk)
        if instance is None:
            return None
        return await self.update(instance, **values)

    async def delete(self, instance: ModelT) -> None:
        """删除给定实例。"""

        await self.session.delete(instance)
        await self.session.flush()

    async def delete_by_id(self, pk: Any) -> bool:
        """按主键删除，返回是否真的删掉了记录。"""

        instance = await self.get(pk)
        if instance is None:
            return False
        await self.delete(instance)
        return True

    async def refresh(self, instance: ModelT) -> ModelT:
        """从数据库重新读取实例，用于拿回被触发器或默认值改动的字段。"""

        await self.session.refresh(instance)
        return instance


__all__ = ["FILTER_OPERATORS", "BaseRepository"]
