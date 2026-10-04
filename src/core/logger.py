"""项目日志配置，统一应用与 Uvicorn 的控制台输出。"""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

from src.core.config import settings


TEXT_LOG_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIG_LOCK = Lock()
_configured_signature: tuple[str, str] | None = None


class JsonFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON，便于日志平台采集。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    *,
    level: str | None = None,
    log_format: Literal["text", "json"] | None = None,
    force: bool = False,
) -> None:
    """配置根日志器及 Uvicorn 日志器；重复调用不会重复添加处理器。"""

    global _configured_signature

    resolved_level = (level or settings.log_level).upper()
    resolved_format = log_format or settings.log_format
    if resolved_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"不支持的日志级别：{resolved_level}")
    if resolved_format not in {"text", "json"}:
        raise ValueError(f"不支持的日志格式：{resolved_format}")

    signature = (resolved_level, resolved_format)
    with _CONFIG_LOCK:
        if not force and _configured_signature == signature:
            return

        formatter: dict[str, object]
        if resolved_format == "json":
            formatter = {"()": JsonFormatter}
        else:
            formatter = {"format": TEXT_LOG_FORMAT, "datefmt": DATE_FORMAT}

        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {"default": formatter},
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "default",
                        "level": resolved_level,
                        "stream": "ext://sys.stdout",
                    }
                },
                "root": {"handlers": ["console"], "level": resolved_level},
                "loggers": {
                    "uvicorn": {
                        "handlers": ["console"],
                        "level": resolved_level,
                        "propagate": False,
                    },
                    "uvicorn.error": {
                        "handlers": ["console"],
                        "level": resolved_level,
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": ["console"],
                        "level": resolved_level,
                        "propagate": False,
                    },
                },
            }
        )
        _configured_signature = signature


def get_logger(name: str) -> logging.Logger:
    """获取项目日志器，并确保日志系统已初始化。"""

    configure_logging()
    return logging.getLogger(name)


logger = get_logger("cj_agent")

__all__ = ["JsonFormatter", "configure_logging", "get_logger", "logger"]
