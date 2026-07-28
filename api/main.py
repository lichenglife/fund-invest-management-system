"""FastAPI 应用装配(开发规范§6/§7/§8)。

职责：
- 注册全局异常 handler -> 统一信封(§8.2)。
- 挂载 TraceId 中间件(§5.2 / §6.2)，并在响应 render 时注入 trace_id。
- 初始化结构化日志(§5)。
- 聚合 v1 路由(§6.1 /api/v1)。

运行：``uvicorn api.main:app --reload``。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from api.v1 import router as v1_router
from config.settings import get_settings
from infra.logging import get_trace_id, setup_logging
from infra.middleware import TraceIdMiddleware
from schemas.envelope import Envelope
from schemas.errors import CODE_TO_HTTP, AppError, ErrorCode

logger = logging.getLogger(__name__)


class EnvelopeResponse(JSONResponse):
    """统一信封响应：render 时从 contextvar 注入 trace_id(§6.2 全站一致)。

    所有走 default_response_class 的成功响应，以及异常 handler 显式构造的失败信封，
    trace_id 均在此统一注入，避免端点/handler 重复手填。
    """

    def render(self, content: Any) -> bytes:
        if isinstance(content, dict) and "code" in content:
            content["trace_id"] = get_trace_id() or None
        return super().render(content)


def _envelope_json(code: int, message: str, *, http_status: int) -> EnvelopeResponse:
    """构造失败信封响应(§7.3：data=null，不泄露内部)；trace_id 由 render 注入。"""
    body = Envelope.fail(code=code, message=message).model_dump()
    return EnvelopeResponse(status_code=http_status, content=body)


def create_app() -> FastAPI:
    """应用工厂(便于测试隔离)。"""
    s = get_settings()
    setup_logging(level=s.log_level, service=s.log_service)

    app = FastAPI(
        title="FundLens API",
        description="基金评估与模拟交易系统内部 API(详设§2.21 契约)",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        default_response_class=EnvelopeResponse,
    )

    # --- 中间件(顺序：后加先执行) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.add_middleware(TraceIdMiddleware)

    # --- 路由 ---
    app.include_router(v1_router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def root() -> Envelope[dict[str, str]]:
        return Envelope.ok(data={"name": "FundLens API", "version": "0.1.0", "docs": "/api/docs"})

    # --- 全局异常 handler(§8.2 -> 信封) ---
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """注册异常 -> 信封映射(§8.2；同一异常只记一次)。"""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> EnvelopeResponse:
        code = int(exc.code.value)
        http_status = CODE_TO_HTTP.get(code, 500)
        logger.warning(
            "app.error",
            extra={"action": "app_error", "err_code": code, "err": exc.message},
        )
        return _envelope_json(code, exc.message, http_status=http_status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> EnvelopeResponse:
        # §7.3：面向用户可读；不直接回堆栈
        return _envelope_json(
            ErrorCode.PARAM_INVALID.value,
            f"参数校验失败: {_format_validation_errors(exc.errors())}",
            http_status=400,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exc(_: Request, exc: StarletteHTTPException) -> EnvelopeResponse:
        # 404 -> 40002；其余按状态归并
        code = (
            ErrorCode.NOT_FOUND.value if exc.status_code == 404 else ErrorCode.PARAM_INVALID.value
        )
        return _envelope_json(code, str(exc.detail) or "请求异常", http_status=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> EnvelopeResponse:
        # §8.2 兜底 50001；记录 ERROR(含 trace_id)，不向用户泄露堆栈(§8.3)
        logger.exception("unhandled.error", extra={"action": "unhandled_error"})
        return _envelope_json(
            ErrorCode.INTERNAL.value, "服务暂时不可用，请稍后重试", http_status=500
        )


def _format_validation_errors(errors: Sequence[dict[str, Any]]) -> str:
    """把 pydantic 校验错误格式化为可读串(§7.3 不泄露内部路径)。"""
    parts: list[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body",))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc or 'field'} {msg}" if loc else msg)
    return "; ".join(parts) if parts else "校验失败"


app: FastAPI = create_app()

__all__: list[str] = ["app", "create_app", "EnvelopeResponse"]
