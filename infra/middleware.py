"""ASGI 中间件：trace_id 注入(详细设计§5.2 / §6.2)。

从请求头 ``X-Trace-Id`` 取或生成(uuid4 hex 截断)，写入 contextvar 供日志取用，
并回写响应头便于前端/调用方关联。
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .logging import trace_id

#: trace_id 长度(可读性与唯一性折中)。
_TRACE_ID_LEN = 16


def new_trace_id() -> str:
    """生成新 trace_id。"""
    return uuid.uuid4().hex[:_TRACE_ID_LEN]


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求注入 trace_id。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        tid = request.headers.get("x-trace-id") or new_trace_id()
        token = trace_id.set(tid)
        try:
            response = await call_next(request)
        finally:
            trace_id.reset(token)
        response.headers["x-trace-id"] = tid
        return response
