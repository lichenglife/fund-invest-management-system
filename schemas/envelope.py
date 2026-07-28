"""统一响应信封（详细设计§2.21.1 字段级契约，闭环评审 S4；§5.2 通用契约）。

权威字段集（7 字段）：
    {code, data, source, as_of, disclaimer, message, trace_id}

> 注：CLAUDE.md §6 / 开发规范§6.2 的简写示例漏列 ``disclaimer``；以本文件（§2.21.1
> 字段级契约 + §5.2 通用契约）为权威，统一为 7 字段。

字段口径：
- ``code``     : 0 成功；非 0 失败(§4.2 错误码)。
- ``data``     : 成功载荷；失败时 null。
- ``source``   : 数据来源(batch/realtime/cache 或 AkShare/Tushare)，溯源与降级标识。
- ``as_of``    : 数据截至日期(``YYYY-MM-DD``，金融数据强时效，必须带)。
- ``disclaimer``: 免责声明(默认"仅供参考，不构成投资建议"，§5.2)。
- ``message``  : 面向用户可读信息；不泄露内部实现(§7.3)。
- ``trace_id`` : 与日志(§5.2)、错误(§7.3)同源，端到端排查。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

#: §5.2 默认免责声明。
DISCLAIMER_DEFAULT: str = "仅供参考，不构成投资建议"

#: 数据来源枚举(非穷举，见§2.21.1 ``source`` 字段说明)。
SOURCE_BATCH = "batch"
SOURCE_REALTIME = "realtime"
SOURCE_CACHE = "cache"


class Envelope(BaseModel, Generic[T]):
    """统一响应信封(§2.21.1 / §5.2)。

    用法::

        Envelope.ok(data={"score": 82.3}, source=SOURCE_BATCH)
        Envelope.fail(40001, "参数校验失败: code 必填")
    """

    model_config = ConfigDict(extra="forbid")

    code: int = 0
    data: T | None = None
    source: str | None = None
    as_of: date | None = None
    disclaimer: str | None = DISCLAIMER_DEFAULT
    message: str = "ok"
    trace_id: str | None = None

    # ------------------------------------------------------------------ 构造助手
    @classmethod
    def ok(
        cls,
        data: Any = None,
        *,
        source: str | None = None,
        as_of: date | None = None,
        message: str = "ok",
        trace_id: str | None = None,
        disclaimer: str | None = DISCLAIMER_DEFAULT,
    ) -> Envelope[Any]:
        """构造成功信封(code=0)。"""
        return cls(
            code=0,
            data=data,
            source=source,
            as_of=as_of,
            disclaimer=disclaimer,
            message=message,
            trace_id=trace_id,
        )

    @classmethod
    def fail(
        cls,
        code: int,
        message: str,
        *,
        trace_id: str | None = None,
        source: str | None = None,
        as_of: date | None = None,
    ) -> Envelope[Any]:
        """构造失败信封(code≠0, data=null, §7.3)。"""
        return cls(
            code=code,
            data=None,
            source=source,
            as_of=as_of,
            disclaimer=None,
            message=message,
            trace_id=trace_id,
        )


class Page(BaseModel, Generic[T]):
    """分页响应载荷(§2.21.1 分页约定 / §6.3)。

    Attributes:
        items: 当前页数据。
        total: 总记录数。
        page: 当前页码(从 1 起)。
        page_size: 每页大小。
    """

    model_config = ConfigDict(extra="forbid")

    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
