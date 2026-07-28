"""v1 路由聚合(§6.1 /api/v1)。"""

from __future__ import annotations

from fastapi import APIRouter

from . import health

router = APIRouter(prefix="/v1")
router.include_router(health.router)

__all__: list[str] = ["router"]
