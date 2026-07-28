"""结构化日志(JSON)+ trace_id(详细设计§5.2 / 开发规范§5)。

JSON 结构必含字段(§5.2)::

    {"ts","level","service","trace_id","action","msg", ...extra}

``trace_id`` 由 ``TraceIdMiddleware``(HTTP)或调用方(worker)注入 contextvar，
全链路贯穿(请求->计算->DB)，与响应信封 ``trace_id`` 同源(§6.2)。
敏感信息脱敏见§5.3(本模块不记录密码/token/PII 原文)。
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

#: 全链路 trace_id(与信封 trace_id / 错误 trace_id 同源)。
trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """获取当前上下文 trace_id(可能为空串)。"""
    return trace_id.get()


def set_trace_id(value: str) -> None:
    """设置 trace_id(通常由中间件/worker 入口调用)。"""
    trace_id.set(value)


class JsonFormatter(logging.Formatter):
    """JSON 行格式化器(§5.2)。"""

    # 优先输出的字段顺序；其余 record 属性作为 extra 追加。
    _STANDARD_KEYS = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
        }
    )

    def __init__(self, service: str = "fundlens") -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        # 先格式化 message(支持 % 占位)
        message = record.getMessage()
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "trace_id": get_trace_id(),
            "logger": record.name,
            "msg": message,
        }
        # 追加业务 extra(如 action / cost_ms / user_id)
        for key, value in record.__dict__.items():
            if key not in self._STANDARD_KEYS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", service: str = "fundlens") -> None:
    """配置根日志器：JSON 输出到 stdout(容器采集，§5.4)。

    幂等：多次调用仅配置一次行为(避免重复 handler)。
    """
    root = logging.getLogger()
    # 清理既有 handler(避免 uvicorn/streamlit 各自追加导致重复)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(service=service))
    root.addHandler(handler)
    root.setLevel(level.upper())
    # 第三方库降噪
    for noisy in ("uvicorn.access", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
