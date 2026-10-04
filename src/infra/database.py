"""SQLAlchemy 异步数据库连接池与会话管理。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings


# 1. 创建异步数据库连接池
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    pool_timeout=30,  # 获取连接的超时时间，单位秒
    pool_recycle=60 * 5,  # 连接回收时间，单位秒
    pool_pre_ping=True,  # 每次获取连接前检查连接是否有效
)

# 2. 创建异步会话工厂
async_session = async_sessionmaker(
    async_engine,
    expire_on_commit=False,  # 提交事务后，会话中的对象不会过期
    class_=AsyncSession,
)

# 3. 为 FastAPI 依赖注入提供异步数据库会话
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取请求级异步数据库会话。"""

    async with async_session() as session:
        try:
            yield session # 返回的session别人用
            await session.commit() # 用完后自动提交事务
        except Exception as e:
            await session.rollback() # 用完后自动回滚事务
            raise e
        finally:
            await session.close()


__all__ = ["async_engine", "async_session", "get_db_session"]
