"""mock.envelope · 示例数据信封包装(详设§2.21.1 七字段权威契约)。

权威字段集(7 字段)：``{code, data, source, as_of, disclaimer, message, trace_id}``。
> CLAUDE.md §6 / 开发规范§6.2 的简写示例漏列 ``disclaimer``；以详设§2.21.1 为权威。

复用 ``schemas.envelope.Envelope`` 保证与真实后端完全一致(extra="forbid")，
Mock 统一标注 ``source="mock"``、固定 ``as_of``、默认免责声明(§5.2)。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from schemas.envelope import DISCLAIMER_DEFAULT, Envelope

#: Mock 数据来源标识(与真实 batch/realtime/cache/AkShare/Tushare 区分)。
MOCK_SOURCE = "mock"

#: Mock 数据固定截至日(金融数据强时效，§2.21.1 ``as_of`` 必须带)。
#: 用固定日期保证可复算、可测；真实接口由后端按 T+1 给出。
MOCK_AS_OF: date = date(2025, 7, 20)


def ok(data: Any, *, as_of: date | None = None, message: str = "ok") -> dict[str, Any]:
    """构造 Mock 成功信封(七字段，source=mock)。

    返回 dict 而非 Envelope 实例：前端 api_client 期望 JSON 体；
    与真实后端响应结构一致(经 ``model_dump`` 后的形状)。
    """
    env = Envelope.ok(
        data=data,
        source=MOCK_SOURCE,
        as_of=as_of or MOCK_AS_OF,
        message=message,
        disclaimer=DISCLAIMER_DEFAULT,
    )
    return env.model_dump(mode="json")


def fail(code: int, message: str) -> dict[str, Any]:
    """构造 Mock 失败信封(code≠0, data=null, §7.3)。"""
    env = Envelope.fail(code=code, message=message, source=MOCK_SOURCE, as_of=MOCK_AS_OF)
    return env.model_dump(mode="json")
