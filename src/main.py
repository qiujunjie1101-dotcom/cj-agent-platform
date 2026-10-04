"""应用入口：创建并配置 FastAPI 应用。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.core.config import settings
from src.core.exception import register_exception_handlers
from src.core.logger import get_logger
from src.infra.database import async_engine
from src.middlewares.logging import RequestLoggingMiddleware
from src.modules.user.api import router as user_router



logger = get_logger(__name__)


# 生命周期感知方法
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动时初始化并探测资源，关闭时释放资源。"""

    logger.info("应用启动：%s (env=%s)", settings.app_name, settings.app_env)
    try:
        # 探测数据库连通性；连不上只告警，不阻断启动
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("数据库连接正常：%s:%s", settings.mysql_host, settings.mysql_port)
    except Exception:
        logger.exception("数据库连接失败，应用仍会启动")

    try:
        yield
    finally:
        await async_engine.dispose()
        logger.info("应用关闭：数据库连接池已释放")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # 注册中间件（后添加的更靠外层；日志中间件放最外层，便于记录所有请求）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    # 注册异常处理器
    register_exception_handlers(app)

    # 注册路由
    @app.get("/")
    async def read_root() -> dict[str, str]:
        return {"Hello": "World"}

    # 注册用户路由
    app.include_router(user_router, prefix="/api/v1")

    return app


app = create_app()