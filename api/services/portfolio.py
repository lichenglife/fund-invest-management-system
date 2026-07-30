"""组合配置服务(P1-08a，详设§3.6 / DC-006 / FR-20,21,37)。

组合 CRUD + 从模拟持仓导入 + 权重管理。
诊断(P1-08b)/回测(P1-08c)/再平衡(P1-08d)随后。
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.models import PaperPosition, Portfolio, PortfolioWeight
from schemas.errors import NotFoundError, ParamError

logger = logging.getLogger(__name__)

#: 核心-卫星模板默认权重(§3.6.1)。
CORE_SATELLITE_TEMPLATE = {
    "core": 0.7,  # 核心仓位(宽基)
    "satellite": 0.3,  # 卫星仓位(行业/主题)
}


class PortfolioService:
    """组合配置服务(§3.6 / DC-006)。

    依赖注入 DB session(§1.5)。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        account_id: str = "default",
        name: str | None = None,
        source: str = "manual",
        weights: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """创建组合(§3.6.2)。

        Args:
            account_id: 账户 ID。
            name: 组合名称。
            source: 来源(template/manual/import)。
            weights: 权重列表 [{code, weight}]。
        Returns:
            组合信息。
        Raises:
            ParamError: source 非法(40001)。
        """
        if source not in ("template", "manual", "import"):
            raise ParamError(f"非法来源: {source}")

        portfolio_id = f"pf_{uuid.uuid4().hex[:12]}"
        portfolio = Portfolio(
            portfolio_id=portfolio_id,
            account_id=account_id,
            name=name,
            source=source,
        )
        self.db.add(portfolio)

        # 保存权重
        if weights:
            for w in weights:
                pw = PortfolioWeight(
                    portfolio_id=portfolio_id,
                    code=w["code"],
                    weight=Decimal(str(w["weight"])),
                )
                self.db.add(pw)

        self.db.commit()
        logger.info(
            "portfolio.create",
            extra={"action": "create", "id": portfolio_id, "source": source},
        )
        return self.get(portfolio_id)

    def create_from_paper(
        self,
        *,
        account_id: str = "default",
        name: str | None = None,
    ) -> dict[str, Any]:
        """从模拟持仓导入组合(§3.6.1 从模拟持仓一键导入)。

        读取 paper_positions，按市值占比作为组合权重。
        Raises:
            NotFoundError: 无模拟持仓(40002)。
        """
        positions = (
            self.db.execute(select(PaperPosition).where(PaperPosition.account_id == account_id))
            .scalars()
            .all()
        )
        if not positions:
            raise NotFoundError("无模拟持仓可导入")

        # 按持仓市值算权重(用 cost 近似)
        total_value = sum(p.shares * p.cost for p in positions)
        if total_value <= 0:
            raise NotFoundError("模拟持仓市值为零")

        weights = [
            {"code": p.code, "weight": float(p.shares * p.cost) / float(total_value)}
            for p in positions
        ]
        return self.create(
            account_id=account_id,
            name=name or "模拟持仓导入",
            source="import",
            weights=weights,
        )

    def get(self, portfolio_id: str) -> dict[str, Any]:
        """查组合详情(§3.6.5 GET /api/portfolio/{id})。

        Raises:
            NotFoundError: 组合不存在(40002)。
        """
        portfolio = self.db.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise NotFoundError(f"组合不存在: {portfolio_id}")
        weights = (
            self.db.execute(
                select(PortfolioWeight).where(PortfolioWeight.portfolio_id == portfolio_id)
            )
            .scalars()
            .all()
        )
        return {
            "portfolio_id": portfolio.portfolio_id,
            "account_id": portfolio.account_id,
            "name": portfolio.name,
            "source": portfolio.source,
            "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
            "weights": [{"code": w.code, "weight": float(w.weight)} for w in weights],
        }

    def list_portfolios(self, account_id: str = "default") -> list[dict[str, Any]]:
        """列出账户下所有组合。"""
        portfolios = (
            self.db.execute(select(Portfolio).where(Portfolio.account_id == account_id))
            .scalars()
            .all()
        )
        return [
            {
                "portfolio_id": p.portfolio_id,
                "name": p.name,
                "source": p.source,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in portfolios
        ]

    def delete(self, portfolio_id: str) -> dict[str, Any]:
        """删除组合(级联删权重)。

        Raises:
            NotFoundError: 组合不存在(40002)。
        """
        portfolio = self.db.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise NotFoundError(f"组合不存在: {portfolio_id}")
        self.db.delete(portfolio)  # ON DELETE CASCADE 级联删权重
        self.db.commit()
        logger.info("portfolio.delete", extra={"action": "delete", "id": portfolio_id})
        return {"portfolio_id": portfolio_id, "deleted": True}


__all__: list[str] = ["PortfolioService", "CORE_SATELLITE_TEMPLATE"]
