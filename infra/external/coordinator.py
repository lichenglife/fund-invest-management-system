"""数据源 fallback 协调器(详设§2.15 容错 / §3.1.2 流程 C 分支)。

AkShare 主源 -> 失败 fallback Tushare；两者皆失则抛 ExternalError(50301)，
上层(§8.5)降级展示"数据暂不可用"。降级须可观测(degraded=True，§8.5)。
"""

from __future__ import annotations

import logging
from typing import Any

from infra.external.akshare_source import AkShareDataSource
from infra.external.base import DataSource
from schemas.errors import ErrorCode, ExternalError

logger = logging.getLogger(__name__)


class DataSourceCoordinator:
    """主源(AkShare) + 备源(Tushare) fallback 协调(§2.15)。

    Usage::

        coord = DataSourceCoordinator()
        records = coord.fetch("fetch_nav", code="000001", start="20250101", end="20251231")
    """

    def __init__(
        self,
        primary: DataSource | None = None,
        fallback: DataSource | None = None,
    ) -> None:
        """Args:
        primary: 主源；None 用 AkShareDataSource。
        fallback: 备源；None 用 TushareDataSource(token 从 settings)。
        """
        # 延迟导入避免循环
        self.primary: DataSource = primary or AkShareDataSource()
        self._fallback: DataSource | None = fallback

    def fetch(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        """按方法名拉取；主源失败 -> fallback；皆失抛 50301(§2.15)。

        Args:
            method: DataSource 方法名(fetch_nav/fetch_fund_list/...)。
            **kwargs: 传给方法的参数。
        Returns:
            标准化记录列表；fallback 成功时记录标 degraded=True(§8.5 可观测)。
        Raises:
            ExternalError(50301): 主源与备源皆失败。
        """
        primary_fn = getattr(self.primary, method, None)
        if primary_fn is None:
            raise ExternalError(f"数据源无方法 {method}", code=ErrorCode.INTERNAL)

        # 主源
        try:
            records: list[dict[str, Any]] = list(primary_fn(**kwargs))
            return records
        except ExternalError as exc:
            logger.warning(
                "datasource.primary_failed",
                extra={"action": "fetch", "method": method, "err": str(exc)},
            )

        # fallback(惰性初始化，无 token 仍报 50301)
        fb = self._fallback or self._make_fallback()
        fb_fn = getattr(fb, method, None)
        if fb_fn is None:
            raise ExternalError(f"备源无方法 {method}", code=ErrorCode.INTERNAL)
        try:
            records = list(fb_fn(**kwargs))
        except ExternalError as exc:
            logger.error(
                "datasource.all_failed",
                extra={"action": "fetch", "method": method, "err": str(exc)},
            )
            raise ExternalError(
                "数据源不可用(AkShare + Tushare 皆失)",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
                cause=exc,
            ) from exc

        # 标注降级(§8.5 可观测)
        for r in records:
            if isinstance(r, dict):
                r["degraded"] = True
                r["source"] = fb.source
        logger.info(
            "datasource.fallback_ok",
            extra={"action": "fetch", "method": method, "fallback": fb.source},
        )
        return records

    def _make_fallback(self) -> DataSource:
        """惰性构造 Tushare fallback(避免无 token 时 import 失败)。"""
        from infra.external.tushare_source import TushareDataSource

        fb = TushareDataSource()
        self._fallback = fb
        return fb


__all__: list[str] = ["DataSourceCoordinator"]
