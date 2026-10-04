"""基础模型类。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BaseModel(DeclarativeBase):
    """基础模型类，所有模型类都继承自该类。"""

    # id: 主键，自增 BigInteger
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="主键 ID"
    )


class TimestampMixin:
    """时间戳混入类，包含创建时间和更新时间字段。

    注意：它只是混入类，**不继承 BaseModel**。继承 BaseModel 会让 SQLAlchemy 把它
    当成一张真实表去映射，而它没有 __tablename__，定义时就会报 InvalidRequestError。

    用法是把它和 BaseModel 一起继承::

        class User(BaseModel, TimestampMixin):
            nickname: Mapped[str] = mapped_column(String(32))

    用 base 时如果想自己搭一层抽象基类，记得加 __abstract__ = True。
    """

    # 创建时间，插入时由数据库填充。
    # 用 server_default（而不是 default）才能落到 DDL 的 DEFAULT 子句里，
    # 这样手写 SQL 插数据、或用其它工具导入时也不会因为 NOT NULL 缺值而失败。
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, comment="创建时间"
    )
    # 更新时间：插入时同 created_at，之后每次 UPDATE 自动刷新。
    # onupdate 保持 Python 侧写法，由 SQLAlchemy 在 UPDATE 语句里生成 now()。
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )


class SoftDeleteMixin:
    """软删除混入类：删除只打标记，数据留在表里。

    同样是混入类，需要和 BaseModel 一起继承::

        class User(BaseModel, TimestampMixin, SoftDeleteMixin):
            nickname: Mapped[str] = mapped_column(String(32))

    配合 BaseRepository 使用时是自动生效的——``delete`` 会改成打标记，
    查询（``get`` / ``paginate``）会自动过滤掉已删除的记录，
    需要连已删除的一起查就传 ``include_deleted=True``。
    """

    # 是否已删除；建索引，因为几乎每条查询都会带上这个条件
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
        comment="是否已删除",
    )
    # 删除时间，未删除时为 NULL；用可空字段顺便记录什么时候删的
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
        comment="删除时间",
    )
