"""模拟交易服务(P1-07a，详设§3.5 / DC-005 / §8.4 事务原子性)。

虚拟账户闭环：默认 100 万、T 日净值成交、买卖原子事务、持仓/现金一致。
不连通实盘(§3.5.7)；成交 NAV 必须来自 ``navs`` 真实收盘净值(禁止盘中估算)。

> P1-07a：账户/买卖/持仓/现金；P1-07b 分红复权、P1-07c 回本、P1-07d 定投回测随后。
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.models import Fund, Nav, PaperAccount, PaperPosition, PaperTrade
from schemas.errors import BizError, ErrorCode, NotFoundError

logger = logging.getLogger(__name__)

#: 默认初始资金(§3.5.1，100 万)。
DEFAULT_INIT_CAPITAL = Decimal("1000000")

#: 数量精度(4 位小数，§2.20.2 Numeric(18,4))。
SHARES_PRECISION = Decimal("0.0001")


class PaperTradingService:
    """模拟交易服务(§3.5 / DC-005)。

    依赖注入 DB session(§1.5)；买卖在事务边界内(§8.4 原子)。
    """

    #: 默认账户 ID(MVP 单用户)。
    DEFAULT_ACCOUNT_ID = "default"

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ 账户

    def get_or_create_account(self, account_id: str = DEFAULT_ACCOUNT_ID) -> PaperAccount:
        """获取或创建默认账户(§3.5.1，100 万)。"""
        acct = self.db.get(PaperAccount, account_id)
        if acct is None:
            acct = PaperAccount(
                account_id=account_id,
                init_capital=DEFAULT_INIT_CAPITAL,
                cash=DEFAULT_INIT_CAPITAL,
            )
            self.db.add(acct)
            self.db.commit()
        return acct

    # ------------------------------------------------------------------ 净值

    def _get_nav(self, code: str, trade_date: date) -> Decimal:
        """取 T 日收盘净值(§3.5.7：必须来自 navs 真实收盘，禁止盘中估算)。

        若当日无净值(非交易日/停牌)，向前找最近交易日(顺延/回退)。
        Raises:
            NotFoundError: 基金或净值不存在。
        """
        fund = self.db.get(Fund, code)
        if fund is None:
            raise NotFoundError(f"基金不存在: {code}")
        # 取 trade_date 当日或之前最近的净值(收盘价)
        row = self.db.execute(
            select(Nav.nav, Nav.adj_nav)
            .where(Nav.code == code, Nav.trade_date <= trade_date)
            .order_by(Nav.trade_date.desc())
            .limit(1)
        ).first()
        if row is None or row.nav is None:
            raise NotFoundError(f"基金 {code} 在 {trade_date} 前无可用净值")
        return Decimal(str(row.nav))

    # ------------------------------------------------------------------ 买入

    def buy(
        self,
        code: str,
        *,
        account_id: str = DEFAULT_ACCOUNT_ID,
        amount: Decimal | None = None,
        shares: Decimal | None = None,
        trade_date: date | None = None,
    ) -> dict[str, Any]:
        """买入(§3.5.2 / §2.21.2)。

        支持 amount(按金额买)或 shares(按份额买)；二选一。
        原子事务：扣现金 + 增持仓 + 记流水(§8.4)。

        Args:
            code: 基金代码。
            account_id: 账户 ID。
            amount: 买入金额(元)；与 shares 二选一。
            shares: 买入份额；与 amount 二选一。
            trade_date: 交易日期；None 取今日。
        Returns:
            {trade_id, position, cash, trade_date}。
        Raises:
            ParamError: amount/shares 均空或均填。
            NotFoundError: 基金/净值不存在。
            BizError: 现金不足(40003)。
        """
        if (amount is None) == (shares is None):
            raise BizError("amount 与 shares 必须二选一", code=ErrorCode.PARAM_INVALID)

        td = trade_date or date.today()
        nav = self._get_nav(code, td)
        acct = self.get_or_create_account(account_id)

        # 计算实际份额/金额
        if amount is not None:
            actual_shares = (amount / nav).quantize(SHARES_PRECISION, rounding=ROUND_DOWN)
            actual_amount = actual_shares * nav
        else:
            assert shares is not None
            actual_shares = shares
            actual_amount = shares * nav

        # 现金校验
        if actual_amount > acct.cash:
            raise BizError(
                f"现金不足: 需 {actual_amount}，可用 {acct.cash}", code=ErrorCode.BIZ_CONFLICT
            )

        # 原子事务(§8.4)：扣现金 + 增持仓 + 记流水
        acct.cash -= actual_amount
        position = self._upsert_position(account_id, code, actual_shares, nav)
        trade = PaperTrade(
            account_id=account_id,
            code=code,
            side="buy",
            shares=actual_shares,
            nav=nav,
            trade_date=td,
        )
        self.db.add(trade)
        self.db.commit()

        logger.info(
            "paper.buy",
            extra={"action": "buy", "code": code, "shares": str(actual_shares), "nav": str(nav)},
        )
        return {
            "trade_id": trade.trade_id,
            "position": {
                "code": code,
                "shares": float(position.shares),
                "cost": float(position.cost),
            },
            "cash": float(acct.cash),
            "trade_date": td.isoformat(),
        }

    # ------------------------------------------------------------------ 卖出

    def sell(
        self,
        code: str,
        *,
        account_id: str = DEFAULT_ACCOUNT_ID,
        shares: Decimal | None = None,
        amount: Decimal | None = None,
        trade_date: date | None = None,
    ) -> dict[str, Any]:
        """卖出(§3.5.2)。原子事务：减持仓 + 增现金 + 记流水(§8.4)。

        Raises:
            NotFoundError: 持仓不存在。
            BizError: 份额不足(40003)。
        """
        td = trade_date or date.today()
        nav = self._get_nav(code, td)
        acct = self.get_or_create_account(account_id)
        position = self._get_position(account_id, code)
        if position is None:
            raise NotFoundError(f"无持仓: {code}")

        # 计算实际卖出份额
        if shares is not None:
            actual_shares = shares
        elif amount is not None:
            actual_shares = (amount / nav).quantize(SHARES_PRECISION, rounding=ROUND_DOWN)
        else:
            raise BizError("shares 与 amount 必须二选一", code=ErrorCode.PARAM_INVALID)

        # 份额校验
        if actual_shares > position.shares:
            raise BizError(
                f"份额不足: 需 {actual_shares}，持仓 {position.shares}", code=ErrorCode.BIZ_CONFLICT
            )

        actual_amount = actual_shares * nav

        # 赎回费(E3 红线：final_val 扣赎回费，TP-04 REDEEM_FEE_BY_HOLD)
        from domain.paper import final_value

        # 持有时长(从持仓更新日算，简化)
        hold_days = (td - position.updated_at.date()).days if position.updated_at else 0
        final_amount, fee_amount = final_value(actual_amount, hold_days)

        # 原子事务
        position.shares -= actual_shares
        acct.cash += final_amount  # 扣赎回费后入账
        trade = PaperTrade(
            account_id=account_id,
            code=code,
            side="sell",
            shares=actual_shares,
            nav=nav,
            trade_date=td,
        )
        self.db.add(trade)
        # 持仓清零则删除
        if position.shares <= 0:
            self.db.delete(position)
        self.db.commit()

        logger.info(
            "paper.sell",
            extra={"action": "sell", "code": code, "shares": str(actual_shares)},
        )
        return {
            "trade_id": trade.trade_id,
            "position": {
                "code": code,
                "shares": float(position.shares) if position.shares > 0 else 0,
                "cost": float(position.cost),
            },
            "cash": float(acct.cash),
            "trade_date": td.isoformat(),
            "redeem_fee": float(fee_amount),  # 赎回费(E3)
            "settled_amount": float(final_amount),  # 扣费后到账
        }

    # ------------------------------------------------------------------ 持仓

    def get_portfolio(self, account_id: str = DEFAULT_ACCOUNT_ID) -> dict[str, Any]:
        """获取持仓看板(§3.5.3)。"""
        acct = self.get_or_create_account(account_id)
        positions = (
            self.db.execute(select(PaperPosition).where(PaperPosition.account_id == account_id))
            .scalars()
            .all()
        )

        items: list[dict[str, Any]] = []
        total_market_value = Decimal("0")
        for p in positions:
            # 取最新净值
            nav_row = self.db.execute(
                select(Nav.nav).where(Nav.code == p.code).order_by(Nav.trade_date.desc()).limit(1)
            ).first()
            latest_nav = Decimal(str(nav_row.nav)) if nav_row and nav_row.nav else p.cost
            market_value = p.shares * latest_nav
            pnl = market_value - p.shares * p.cost
            total_market_value += market_value
            items.append(
                {
                    "code": p.code,
                    "shares": float(p.shares),
                    "cost": float(p.cost),
                    "latest_nav": float(latest_nav),
                    "market_value": float(market_value),
                    "pnl": float(pnl),
                    "pnl_pct": float(pnl / (p.shares * p.cost)) if p.cost > 0 else 0,
                }
            )

        total_assets = acct.cash + total_market_value
        total_pnl = total_assets - acct.init_capital

        return {
            "account_id": account_id,
            "cash": float(acct.cash),
            "init_capital": float(acct.init_capital),
            "total_market_value": float(total_market_value),
            "total_assets": float(total_assets),
            "total_pnl": float(total_pnl),
            "total_pnl_pct": float(total_pnl / acct.init_capital) if acct.init_capital > 0 else 0,
            "positions": items,
        }

    # ------------------------------------------------------------------ 重置

    def reset(
        self, account_id: str = DEFAULT_ACCOUNT_ID, *, confirm: bool = False
    ) -> dict[str, Any]:
        """重置账户(§3.5.7 需二次确认)。清仓 + 现金回初始。

        Args:
            confirm: 二次确认(必须 True)。
        Raises:
            BizError: 未确认(40003)。
        """
        if not confirm:
            raise BizError("重置需二次确认(confirm=True)", code=ErrorCode.BIZ_CONFLICT)

        acct = self.get_or_create_account(account_id)
        # 清空持仓
        self.db.execute(
            select(PaperPosition).where(PaperPosition.account_id == account_id)
        ).scalars().all()  # 触发加载
        # 删除所有持仓
        positions = (
            self.db.query(PaperPosition).filter(PaperPosition.account_id == account_id).all()
        )
        for p in positions:
            self.db.delete(p)
        # 现金重置
        acct.cash = acct.init_capital
        self.db.commit()

        logger.info("paper.reset", extra={"action": "reset", "account": account_id})
        return {"account_id": account_id, "cash": float(acct.cash), "reset": True}

    # ------------------------------------------------------------------ 分红复权(P1-07b, E3)

    def apply_dividend(
        self,
        code: str,
        div_per_unit: Decimal,
        ex_nav: Decimal,
        *,
        account_id: str = DEFAULT_ACCOUNT_ID,
        mode: str = "reinvest",
    ) -> dict[str, Any]:
        """分红复权调整持仓(§3.5.4 / E3)。

        E3：后复权净值已含分红再投，回测不调用本函数(删 DIVIDEND_MODE)；
        本方法用于单位净值成交场景的分红份额调整(再投/现金)。

        Raises:
            NotFoundError: 持仓不存在。
        """
        from domain.paper import run_dividend

        position = self._get_position(account_id, code)
        if position is None:
            raise NotFoundError(f"无持仓: {code}")
        result = run_dividend(position.shares, div_per_unit, ex_nav, mode=mode)
        if mode == "reinvest":
            position.shares = result["shares_after"]
        else:
            # 现金分红：增加账户现金
            acct = self.get_or_create_account(account_id)
            acct.cash += result["cash_dividend"]
        self.db.commit()
        logger.info(
            "paper.dividend",
            extra={
                "action": "dividend",
                "code": code,
                "mode": mode,
                "new_shares": str(result["new_shares"]),
            },
        )
        return {
            "code": code,
            "mode": mode,
            "shares_after": float(result["shares_after"]),
            "cash_dividend": float(result["cash_dividend"]),
            "new_shares": float(result["new_shares"]),
        }

    # ------------------------------------------------------------------ 内部

    def _upsert_position(
        self, account_id: str, code: str, shares: Decimal, nav: Decimal
    ) -> PaperPosition:
        """更新或创建持仓(加权平均成本)。"""
        pos = self._get_position(account_id, code)
        if pos is None:
            pos = PaperPosition(
                account_id=account_id,
                code=code,
                shares=shares,
                cost=nav,
            )
            self.db.add(pos)
        else:
            # 加权平均成本
            old_value = pos.shares * pos.cost
            new_value = shares * nav
            total_shares = pos.shares + shares
            pos.cost = (old_value + new_value) / total_shares if total_shares > 0 else nav
            pos.shares = total_shares
        return pos

    def _get_position(self, account_id: str, code: str) -> PaperPosition | None:
        """查持仓。"""
        return self.db.execute(
            select(PaperPosition).where(
                PaperPosition.account_id == account_id, PaperPosition.code == code
            )
        ).scalar_one_or_none()


__all__: list[str] = ["PaperTradingService", "DEFAULT_INIT_CAPITAL"]
