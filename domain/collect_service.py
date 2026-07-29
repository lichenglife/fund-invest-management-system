"""采集编排服务(P1-01d，详设§3.1.2 流程 / §3.14 调度 / §3.14.6 锁防重)。

把采集链路(拉取 -> 清洗 -> 幂等 upsert -> 质量日志)封装为可调度作业，
任务执行前获取分布式锁(§3.14.6 防重)，未获锁跳过。

> 纯编排逻辑置于 domain，DB/upsert 在 infra；调度入口在 workers/collect.py(P1-01d-3)。
> 事务边界：单基金 upsert 在事务内(§8.4)；质量日志记录采集结果。
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from domain.collect import clean_fund_list, clean_holdings, clean_nav
from infra.collect_repo import upsert_funds, upsert_holdings, upsert_navs, write_quality_log
from infra.external.coordinator import DataSourceCoordinator
from infra.lock import DistributedLock, get_lock

logger = logging.getLogger(__name__)


class CollectService:
    """采集编排服务(§3.1.2 / §3.14.6)。

    依赖注入(开发规范§1.5)：DB session、数据源协调器、锁均可注入，便于测试。
    """

    def __init__(
        self,
        db: Session,
        *,
        coordinator: DataSourceCoordinator | None = None,
        lock: DistributedLock | None = None,
    ) -> None:
        self.db = db
        self._coordinator = coordinator
        self._lock = lock

    @property
    def coordinator(self) -> DataSourceCoordinator:
        if self._coordinator is None:
            self._coordinator = DataSourceCoordinator()
        return self._coordinator

    @property
    def lock(self) -> DistributedLock:
        if self._lock is None:
            self._lock = get_lock()
        return self._lock

    def collect_fund_list(self) -> int:
        """采集全基金名单(带锁防重，§3.14.6)。返回 upsert 行数。"""
        ok, result = self.lock.with_lock(
            "collect_fund_list",
            self._do_collect_fund_list,
        )
        if not ok:
            logger.info("collect.skip", extra={"action": "collect", "job": "fund_list"})
            return 0
        return result or 0

    def _do_collect_fund_list(self) -> int:
        raw = self.coordinator.fetch("fetch_fund_list")
        cleaned = clean_fund_list(raw)
        count = upsert_funds(self.db, cleaned)
        write_quality_log(
            self.db,
            entity="fund_list",
            missing_count=0,
            anomaly_flag=False,
            source=self.coordinator.primary.source,
            note=f"upsert {count}",
        )
        return count

    def collect_nav(self, code: str, start: str, end: str) -> int:
        """采集单基金净值(带锁防重)。返回 upsert 行数。"""
        ok, result = self.lock.with_lock(
            f"collect_nav:{code}",
            lambda: self._do_collect_nav(code, start, end),
        )
        if not ok:
            return 0
        return result or 0

    def _do_collect_nav(self, code: str, start: str, end: str) -> int:
        raw = self.coordinator.fetch("fetch_nav", code=code, start=start, end=end)
        cleaned = clean_nav(raw, source=self.coordinator.primary.source)
        count = upsert_navs(self.db, cleaned)
        # 质量日志：缺失数 = 期望天数 - 实际(简化：记录实际)
        write_quality_log(
            self.db,
            entity=code,
            missing_count=max(0, len(raw) - count),
            anomaly_flag=False,
            source=self.coordinator.primary.source,
            note=f"nav upsert {count}/{len(raw)}",
        )
        return count

    def collect_holdings(self, code: str, year: str) -> int:
        """采集单基金重仓股(带锁防重)。"""
        ok, result = self.lock.with_lock(
            f"collect_holdings:{code}:{year}",
            lambda: self._do_collect_holdings(code, year),
        )
        if not ok:
            return 0
        return result or 0

    def _do_collect_holdings(self, code: str, year: str) -> int:
        raw = self.coordinator.fetch("fetch_holdings", code=code, year=year)
        cleaned = clean_holdings(raw, source=self.coordinator.primary.source)
        count = upsert_holdings(self.db, cleaned)
        write_quality_log(
            self.db,
            entity=f"{code}:{year}",
            missing_count=0,
            anomaly_flag=False,
            source=self.coordinator.primary.source,
            note=f"holdings {count}",
        )
        return count

    def collect_all(self, codes: list[str], *, start: str, end: str) -> dict[str, int]:
        """批量采集(名单 + 净值 + 重仓)。返回各维度计数。

        用于定时任务入口(§3.14.2 工作日 18:00 增量采集)。
        """
        today_yyyymmdd = date.today().strftime("%Y%m%d")
        result: dict[str, int] = {"funds": 0, "navs": 0, "holdings": 0}
        try:
            result["funds"] = self.collect_fund_list()
        except Exception as exc:  # noqa: BLE001  采集链路容错，不阻断后续(§8.5)
            logger.exception("collect.funds_failed", extra={"action": "collect_all"})
            _ = exc
        for code in codes:
            try:
                result["navs"] += self.collect_nav(code, start=start, end=end)
                result["holdings"] += self.collect_holdings(code, today_yyyymmdd[:4])
            except Exception:  # noqa: BLE001  单基失败不阻断(§8.5 区块级降级)
                logger.exception(
                    "collect.fund_failed", extra={"action": "collect_all", "code": code}
                )
        return result


__all__: list[str] = ["CollectService"]
