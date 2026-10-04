from src.core.config import settings
from src.infra.database import async_engine


def test_database_engine_uses_async_driver_and_debug_echo() -> None:
    assert async_engine.url.drivername == "mysql+aiomysql"
    assert async_engine.echo is settings.app_debug
