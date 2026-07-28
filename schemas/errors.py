"""错误码枚举与分层异常(详细设计§4.2 + 开发规范§8.1 / §8.2)。

错误码体系(§4.2，新增错误码须在此区间内扩段，禁止随意数字)：
    0       成功
    400xx   参数/业务     40001 参数校验失败 / 40002 资源不存在 / 40003 业务规则冲突
    401xx   认证/权限     40101 未认证 / 40103 无权限
    403xx   守卫拦截      40301 RESEARCH_PROXY_GUARD 口径未定义
    429xx   限流          42901 外部限频
    500xx   内部异常      50001 内部计算异常(已降级)
    503xx   依赖不可用    50301 数据源 / 50302 DB / 50303 LLM 超时降级

异常分层(§8.1)：业务代码抛具体项目异常，禁裸 ``Exception``；底层(infra)捕获第三方
异常并包装为项目异常，保留 cause(``raise InternalError(...) from e``)。
"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    """错误码枚举(§4.2)。"""

    SUCCESS = 0

    # --- 参数/业务 400xx ---
    PARAM_INVALID = 40001  # 缺字段 / 类型错 / 越界
    NOT_FOUND = 40002  # 基金代码 / 组合不存在
    BIZ_CONFLICT = 40003  # 业务规则冲突(重置未二次确认 / 非交易时段顺延)

    # --- 认证/权限 401xx ---
    UNAUTHENTICATED = 40101  # admin 端点未登录
    FORBIDDEN = 40103  # 非管理员访问 admin

    # --- 守卫 403xx ---
    GUARD_BLOCKED = 40301  # RESEARCH_PROXY_GUARD 口径未定义

    # --- 限流 429xx ---
    RATE_LIMITED = 42901  # Tushare / LLM 返回 429

    # --- 内部 500xx ---
    INTERNAL = 50001  # 内部计算异常(已降级)

    # --- 依赖不可用 503xx ---
    DATASOURCE_UNAVAILABLE = 50301  # AkShare + Tushare 皆失
    DB_UNAVAILABLE = 50302  # 数据库连接失败
    LLM_DEGRADED = 50303  # LLM 超时/限频，回退规则摘要


class AppError(Exception):
    """项目异常基类(开发规范§8.1)。

    继承 ``Exception`` 而非 ``BaseException``：FastAPI/Starlette 的
    ``ExceptionMiddleware`` 仅捕获 ``Exception``，继承 Exception 方可被全局
    handler 捕获并映射为§7 信封(§8.2)。(§8.1 图中 ``AppError(BaseException)``
    为示意「基类」，实现以可被 handler 捕获为准。)

    Attributes:
        code: 错误码(§4.2)。
        message: 面向用户可读信息(§7.3，不泄露内部)。
        cause: 原始异常(外部依赖场景，§8.1 ExternalError)。
    """

    code: ErrorCode = ErrorCode.INTERNAL

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.cause = cause

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ParamError(AppError):
    """参数校验失败(40001，§8.1)。"""

    code = ErrorCode.PARAM_INVALID


class NotFoundError(AppError):
    """资源不存在(40002，§8.1)。"""

    code = ErrorCode.NOT_FOUND


class BizError(AppError):
    """业务规则冲突(40003，§8.1)。"""

    code = ErrorCode.BIZ_CONFLICT


class AuthError(AppError):
    """认证/权限错误(40101/40103，§8.1)。

    默认 40101 未认证；权限不足用 ``AuthError(code=ErrorCode.FORBIDDEN)``。
    """

    code = ErrorCode.UNAUTHENTICATED


class GuardError(AppError):
    """守卫拦截(40301，RESEARCH_PROXY_GUARD，§8.1)。"""

    code = ErrorCode.GUARD_BLOCKED


class ExternalError(AppError):
    """外部依赖错误(42901/503xx，§8.1，含 cause)。

    用于数据源/LLM/DB 不可用场景，底层捕获第三方异常后包装：
    ``raise ExternalError("数据源不可用", code=DATASOURCE_UNAVAILABLE) from e``
    """

    code = ErrorCode.DATASOURCE_UNAVAILABLE


class InternalError(AppError):
    """内部计算异常(50001，已降级，§8.1)。"""

    code = ErrorCode.INTERNAL


#: 错误码 -> HTTP 状态码映射(§6.1/§7.2)。
CODE_TO_HTTP: dict[int, int] = {
    ErrorCode.PARAM_INVALID.value: 400,
    ErrorCode.NOT_FOUND.value: 404,
    ErrorCode.BIZ_CONFLICT.value: 409,
    ErrorCode.UNAUTHENTICATED.value: 401,
    ErrorCode.FORBIDDEN.value: 403,
    ErrorCode.GUARD_BLOCKED.value: 403,
    ErrorCode.RATE_LIMITED.value: 429,
    ErrorCode.INTERNAL.value: 500,
    ErrorCode.DATASOURCE_UNAVAILABLE.value: 503,
    ErrorCode.DB_UNAVAILABLE.value: 503,
    ErrorCode.LLM_DEGRADED.value: 503,
}
