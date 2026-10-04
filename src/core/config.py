"""项目配置：使用 pydantic-settings 统一读取并校验环境变量。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _url_host(host: str) -> str:
    """为 URL 中的 IPv6 主机地址补充方括号。"""

    return f"[{host}]" if ":" in host and not host.startswith("[") else host


class Settings(BaseSettings):
    """应用运行配置，系统环境变量优先级高于项目根目录的 .env。"""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        validate_default=True,
    )

    # 应用基础配置
    app_name: str = Field(
        default="CJ Agent Platform", min_length=1, validation_alias="APP_NAME"
    )
    app_env: Literal["development", "testing", "production"] = Field(
        default="development", validation_alias="APP_ENV"
    )
    app_debug: bool = Field(
        default=True,
        validation_alias=AliasChoices("APP_DEBUG", "DEBUG"),
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: Literal["text", "json"] = Field(
        default="text", validation_alias="LOG_FORMAT"
    )

    # MySQL
    mysql_host: str = Field(
        default="127.0.0.1", min_length=1, validation_alias="MYSQL_HOST"
    )
    mysql_port: int = Field(
        default=3307, ge=1, le=65535, validation_alias="MYSQL_PORT"
    )
    mysql_database: str = Field(
        default="cj", min_length=1, validation_alias="MYSQL_DATABASE"
    )
    mysql_user: str = Field(
        default="root", min_length=1, validation_alias="MYSQL_USER"
    )
    mysql_password: SecretStr = Field(
        default=SecretStr("root"), validation_alias="MYSQL_PASSWORD", repr=False
    )
    mysql_root_password: SecretStr = Field(
        default=SecretStr("root"),
        validation_alias="MYSQL_ROOT_PASSWORD",
        repr=False,
    )
    database_url: str = Field(
        default="", validation_alias="DATABASE_URL", repr=False, exclude=True
    )

    # Redis
    redis_host: str = Field(
        default="127.0.0.1", min_length=1, validation_alias="REDIS_HOST"
    )
    redis_port: int = Field(
        default=6379, ge=1, le=65535, validation_alias="REDIS_PORT"
    )
    redis_db: int = Field(default=0, ge=0, validation_alias="REDIS_DB")
    redis_password: SecretStr = Field(
        default=SecretStr("redis123456"),
        validation_alias="REDIS_PASSWORD",
        repr=False,
    )
    redis_url: str = Field(
        default="", validation_alias="REDIS_URL", repr=False, exclude=True
    )

    # MinIO
    minio_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        min_length=1,
        validation_alias="MINIO_ENDPOINT",
    )
    minio_root_user: str = Field(
        default="minioadmin", min_length=1, validation_alias="MINIO_ROOT_USER"
    )
    minio_root_password: SecretStr = Field(
        default=SecretStr("minioadmin"),
        validation_alias="MINIO_ROOT_PASSWORD",
        repr=False,
    )
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")

    @field_validator("app_env", "log_format", mode="before")
    @classmethod
    def normalize_lowercase(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.lower()
        if normalized in {"dev", "test", "prod"}:
            return {
                "dev": "development",
                "test": "testing",
                "prod": "production",
            }[normalized]
        return normalized

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.upper()
        if normalized not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise ValueError(f"LOG_LEVEL 必须是以下值之一：{allowed}")
        return normalized

    @model_validator(mode="after")
    def build_service_urls(self) -> "Settings":
        """补齐连接地址，并校验 MinIO 的协议与安全开关一致。"""

        if not self.database_url:
            user = quote(self.mysql_user, safe="")
            password = quote(self.mysql_password.get_secret_value(), safe="")
            database = quote(self.mysql_database, safe="")
            self.database_url = (
                f"mysql+aiomysql://{user}:{password}@"
                f"{_url_host(self.mysql_host)}:{self.mysql_port}/{database}"
                "?charset=utf8mb4"
            )

        if not self.redis_url:
            password = self.redis_password.get_secret_value()
            authentication = f":{quote(password, safe='')}@" if password else ""
            self.redis_url = (
                f"redis://{authentication}{_url_host(self.redis_host)}:"
                f"{self.redis_port}/{self.redis_db}"
            )

        endpoint = self.minio_endpoint.rstrip("/")
        if "://" not in endpoint:
            scheme = "https" if self.minio_secure else "http"
            endpoint = f"{scheme}://{endpoint}"

        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MINIO_ENDPOINT 必须是有效的 HTTP(S) 地址")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("MINIO_ENDPOINT 不能包含路径、查询参数或片段")
        if self.minio_secure != (parsed.scheme == "https"):
            raise ValueError("MINIO_SECURE 必须与 MINIO_ENDPOINT 的协议一致")
        self.minio_endpoint = endpoint
        return self

    @property
    def minio_server(self) -> str:
        """返回 MinIO Python SDK 所需的 host:port。"""

        return urlsplit(self.minio_endpoint).netloc

    @property
    def minio_access_key(self) -> str:
        return self.minio_root_user

    @property
    def minio_secret_key(self) -> str:
        return self.minio_root_password.get_secret_value()

    @property
    def debug(self) -> bool:
        """兼容旧代码；新代码统一使用 app_debug。"""

        return self.app_debug


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程内复用的配置单例。"""

    return Settings()


settings = get_settings()

__all__ = [
    "DEFAULT_ENV_FILE",
    "PROJECT_ROOT",
    "Settings",
    "get_settings",
    "settings",
]
