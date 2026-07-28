"""统一信封与错误码单元测试(详细设计§2.21.1 / §4.2；开发规范§6.2/§7.2/§8.1)。"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from schemas.envelope import DISCLAIMER_DEFAULT, SOURCE_BATCH, Envelope, Page
from schemas.errors import (
    CODE_TO_HTTP,
    AppError,
    AuthError,
    BizError,
    ErrorCode,
    ExternalError,
    GuardError,
    InternalError,
    NotFoundError,
    ParamError,
)


class TestEnvelopeFields:
    """§2.21.1 七字段契约。"""

    EXPECTED_FIELDS = {"code", "data", "source", "as_of", "disclaimer", "message", "trace_id"}

    def test_ok_has_seven_fields(self) -> None:
        env = Envelope.ok(data={"x": 1}, source=SOURCE_BATCH, as_of=date(2025, 7, 28))
        dumped = env.model_dump()
        assert set(dumped.keys()) == self.EXPECTED_FIELDS

    def test_ok_defaults(self) -> None:
        env = Envelope.ok()
        assert env.code == 0
        assert env.message == "ok"
        assert env.disclaimer == DISCLAIMER_DEFAULT == "仅供参考，不构成投资建议"
        assert env.data is None

    def test_fail_data_null_disclaimer_none(self) -> None:
        env = Envelope.fail(40001, "参数校验失败: code 必填")
        assert env.code == 40001
        assert env.data is None
        assert env.disclaimer is None  # §7.3 失败体
        assert env.message == "参数校验失败: code 必填"

    def test_extra_forbidden(self) -> None:
        # extra 字段应被拒(extra="forbid")
        with pytest.raises(ValidationError):
            Envelope.model_validate({"code": 0, "message": "ok", "unexpected": 1})


class TestPage:
    def test_page_defaults(self) -> None:
        p: Page[int] = Page()
        assert p.items == []
        assert p.total == 0
        assert p.page == 1
        assert p.page_size == 20


class TestErrorCode:
    """§4.2 错误码枚举精确值。"""

    def test_success_zero(self) -> None:
        assert ErrorCode.SUCCESS.value == 0

    @pytest.mark.parametrize(
        "name,value",
        [
            ("PARAM_INVALID", 40001),
            ("NOT_FOUND", 40002),
            ("BIZ_CONFLICT", 40003),
            ("UNAUTHENTICATED", 40101),
            ("FORBIDDEN", 40103),
            ("GUARD_BLOCKED", 40301),
            ("RATE_LIMITED", 42901),
            ("INTERNAL", 50001),
            ("DATASOURCE_UNAVAILABLE", 50301),
            ("DB_UNAVAILABLE", 50302),
            ("LLM_DEGRADED", 50303),
        ],
    )
    def test_code_values(self, name: str, value: int) -> None:
        assert ErrorCode[name].value == value


class TestAppErrorHierarchy:
    """§8.1 分层异常默认错误码。"""

    @pytest.mark.parametrize(
        "exc_cls,code",
        [
            (ParamError, ErrorCode.PARAM_INVALID),
            (NotFoundError, ErrorCode.NOT_FOUND),
            (BizError, ErrorCode.BIZ_CONFLICT),
            (AuthError, ErrorCode.UNAUTHENTICATED),
            (GuardError, ErrorCode.GUARD_BLOCKED),
            (ExternalError, ErrorCode.DATASOURCE_UNAVAILABLE),
            (InternalError, ErrorCode.INTERNAL),
        ],
    )
    def test_default_code(self, exc_cls: type[AppError], code: ErrorCode) -> None:
        exc = exc_cls("msg")
        assert exc.code == code
        assert isinstance(exc, Exception)  # 可被全局 handler 捕获(§8.2)

    def test_external_error_carries_cause(self) -> None:
        root = RuntimeError("conn refused")
        exc = ExternalError("db down", cause=root)
        assert exc.cause is root

    def test_str_format(self) -> None:
        exc = ParamError("bad input")
        assert str(exc) == "[40001] bad input"


class TestCodeToHttp:
    """§6.1/§7.2 错误码 -> HTTP 映射。"""

    def test_mappings(self) -> None:
        assert CODE_TO_HTTP[40001] == 400
        assert CODE_TO_HTTP[40002] == 404
        assert CODE_TO_HTTP[40003] == 409
        assert CODE_TO_HTTP[40101] == 401
        assert CODE_TO_HTTP[40301] == 403
        assert CODE_TO_HTTP[42901] == 429
        assert CODE_TO_HTTP[50001] == 500
        assert CODE_TO_HTTP[50303] == 503
