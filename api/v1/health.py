"""健康检查端点(§6.1 GET /api/v1/health)。

返回统一信封(§2.21)；用于 compose 健康检查与 CI 烟测。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from schemas.envelope import SOURCE_REALTIME, Envelope

router = APIRouter(tags=["meta"])

#: 应用版本(与 pyproject 一致)。
APP_VERSION = "0.1.0"


@router.get("/health", summary="健康检查")
def health() -> Envelope[dict[str, str]]:
    """返回服务状态(信封 code=0)。"""
    # 延迟导入避免 settings 在测试 monkeypatch 前被缓存固化。
    from config.settings import get_settings

    s = get_settings()
    return Envelope.ok(
        data={"status": "ok", "version": APP_VERSION, "env": s.app_env},
        source=SOURCE_REALTIME,
        as_of=date.today(),
    )
