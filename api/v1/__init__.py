"""v1 路由聚合(§6.1 /api/v1)。"""

from __future__ import annotations

from fastapi import APIRouter

from . import admin, evaluation, health, paper, portfolio, screen

router = APIRouter(prefix="/v1")
router.include_router(health.router)
router.include_router(admin.router)
router.include_router(evaluation.router)
router.include_router(screen.router)
router.include_router(paper.router)
router.include_router(portfolio.router)

__all__: list[str] = ["router"]
