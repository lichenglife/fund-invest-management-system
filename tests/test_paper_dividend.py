"""分红复权与赎回费单测(P1-07b，§3.5.4 / TP-04 / E3 红线)。

纯逻辑：run_dividend 份额调整、redeem_fee 阶梯、final_value 扣费。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.paper import DEF_REDEEM_FEE, REDEEM_FEE_BY_HOLD, final_value, redeem_fee, run_dividend


class TestRedeemFee:
    """TP-04 §3.1 赎回费阶梯。"""

    @pytest.mark.parametrize(
        "hold_days,expected_rate",
        [
            (1, 0.015),  # <7
            (6, 0.015),
            (7, 0.005),  # 7-30
            (29, 0.005),
            (30, 0.0025),  # 30-365
            (364, 0.0025),
            (365, 0.0),  # >365
            (1000, 0.0),
        ],
    )
    def test_fee_ladder(self, hold_days: int, expected_rate: float) -> None:
        assert redeem_fee(hold_days) == expected_rate

    def test_fee_table_constants(self) -> None:
        assert REDEEM_FEE_BY_HOLD == {"d7": 0.015, "d30": 0.005, "d365": 0.0025, "gt365": 0.0}
        assert DEF_REDEEM_FEE == 0.0


class TestFinalValue:
    """E3 final_val 扣赎回费。"""

    def test_final_value_deducts_fee(self) -> None:
        """扣赎回费终值(E3 漏计修复)。"""
        gross = Decimal("10000")
        final, fee = final_value(gross, hold_days=10)  # 7-30 日 0.5%
        assert fee == Decimal("50.0")  # 10000 * 0.005
        assert final == Decimal("9950.0")

    def test_long_hold_no_fee(self) -> None:
        """>365 日免赎回费。"""
        final, fee = final_value(Decimal("10000"), hold_days=400)
        assert fee == Decimal("0")
        assert final == Decimal("10000")


class TestRunDividend:
    """§3.5.4 分红复权调整份额。"""

    def test_reinvest_increases_shares(self) -> None:
        """再投：现金分红按除息净值转份额。"""
        # 1000 份，每份分红 0.1，除息净值 1.0
        # 现金分红 = 1000 * 0.1 = 100；新份额 = 100 / 1.0 = 100
        r = run_dividend(Decimal("1000"), Decimal("0.1"), Decimal("1.0"), mode="reinvest")
        assert r["shares_after"] == Decimal("1100")  # 1000 + 100
        assert r["cash_dividend"] == Decimal("100")
        assert r["new_shares"] == Decimal("100")

    def test_cash_no_share_change(self) -> None:
        """现金分红：份额不变。"""
        r = run_dividend(Decimal("1000"), Decimal("0.1"), Decimal("1.0"), mode="cash")
        assert r["shares_after"] == Decimal("1000")
        assert r["cash_dividend"] == Decimal("100")
        assert r["new_shares"] == Decimal("0")

    def test_zero_ex_nav_no_crash(self) -> None:
        """ex_nav<=0 不崩溃(§4 红线)。"""
        r = run_dividend(Decimal("1000"), Decimal("0.1"), Decimal("0"), mode="reinvest")
        assert r["shares_after"] == Decimal("1000")  # 跳过再投
        assert "note" in r  # 标注跳过

    def test_dividend_calculation(self) -> None:
        """分红金额 = 份额 × 每份分红。"""
        r = run_dividend(Decimal("500"), Decimal("0.05"), Decimal("2.0"), mode="reinvest")
        assert r["cash_dividend"] == Decimal("25.0")  # 500 * 0.05
        assert r["new_shares"] == Decimal("12.5")  # 25 / 2.0
