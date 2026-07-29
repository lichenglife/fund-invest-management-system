"""采集清洗层单测(P1-01c，纯函数，详设§3.1.2 清洗)。

无 DB 依赖：测试 clean_nav/clean_fund_list/clean_holdings 纯函数。
覆盖：nav 缺失丢弃、去重、adj_nav 回退(D6)、字段规整。
"""

from __future__ import annotations

from decimal import Decimal

from domain.collect import clean_fund_list, clean_holdings, clean_nav


class TestCleanNav:
    """§3.1.2 清洗 + D6 adj_nav 回退。"""

    def test_drops_missing_nav(self) -> None:
        """nav 缺失 -> 丢弃(§2.20.2 NOT NULL)。"""
        records = [
            {"code": "000001", "trade_date": "2025-07-28", "nav": 1.308, "acc_nav": 2.678},
            {"code": "000001", "trade_date": "2025-07-29", "nav": None, "acc_nav": None},
            {"code": "000001", "trade_date": "2025-07-30", "nav": "", "acc_nav": None},
        ]
        cleaned = clean_nav(records)
        assert len(cleaned) == 1
        assert cleaned[0]["trade_date"] == "2025-07-28"

    def test_adj_nav_fallback_to_acc_nav(self) -> None:
        """adj_nav 缺失 -> 回退 acc_nav(D6，标 quality_flag)。"""
        records = [
            {
                "code": "000001",
                "trade_date": "2025-07-28",
                "nav": 1.308,
                "acc_nav": 2.678,
                "adj_nav": None,
            },
        ]
        cleaned = clean_nav(records)
        assert cleaned[0]["adj_nav"] == Decimal("2.678")  # 回退 acc_nav
        assert cleaned[0]["quality_flag"] == "adj_nav_proxy"

    def test_adj_nav_present_no_flag(self) -> None:
        """adj_nav 有值 -> 不标 flag。"""
        records = [
            {
                "code": "000001",
                "trade_date": "2025-07-28",
                "nav": 1.308,
                "acc_nav": 2.678,
                "adj_nav": 1.5,
            },
        ]
        cleaned = clean_nav(records)
        assert cleaned[0]["adj_nav"] == Decimal("1.5")
        assert cleaned[0].get("quality_flag") is None

    def test_dedup_by_code_date(self) -> None:
        """(code, trade_date) 重复 -> 去重(§3.14.5 幂等)。"""
        records = [
            {"code": "000001", "trade_date": "2025-07-28", "nav": 1.308, "acc_nav": 2.678},
            {"code": "000001", "trade_date": "2025-07-28", "nav": 1.309, "acc_nav": 2.679},
        ]
        cleaned = clean_nav(records)
        assert len(cleaned) == 1

    def test_decimal_coercion(self) -> None:
        """nav 转 Decimal(避免浮点误差，§6.3)。"""
        records = [{"code": "000001", "trade_date": "2025-07-28", "nav": 1.308, "acc_nav": "2.678"}]
        cleaned = clean_nav(records)
        assert isinstance(cleaned[0]["nav"], Decimal)
        assert cleaned[0]["acc_nav"] == Decimal("2.678")


class TestCleanFundList:
    def test_dedup_by_code(self) -> None:
        records = [
            {"code": "000001", "name": "华夏成长", "type_": "mixed"},
            {"code": "000001", "name": "重复", "type_": "stock"},
            {"code": "000002", "name": "华夏大盘", "type_": "mixed"},
        ]
        cleaned = clean_fund_list(records)
        assert len(cleaned) == 2
        assert cleaned[0]["code"] == "000001"

    def test_empty_type_defaults_mixed(self) -> None:
        records = [{"code": "000001", "name": "x", "type_": ""}]
        cleaned = clean_fund_list(records)
        assert cleaned[0]["type_"] == "mixed"


class TestCleanHoldings:
    def test_dedup_by_composite_pk(self) -> None:
        """复合 PK(code, report_date, stock_code) 去重。"""
        records = [
            {
                "code": "000001",
                "report_date": "2024-03-31",
                "stock_code": "002025",
                "weight": 0.0346,
            },
            {"code": "000001", "report_date": "2024-03-31", "stock_code": "002025", "weight": 0.04},
        ]
        cleaned = clean_holdings(records)
        assert len(cleaned) == 1
        assert cleaned[0]["weight"] == Decimal("0.0346")

    def test_drops_missing_keys(self) -> None:
        records = [
            {"code": "", "report_date": "2024-03-31", "stock_code": "002025"},
            {"code": "000001", "report_date": "2024-03-31", "stock_code": "002025", "weight": 0.03},
        ]
        cleaned = clean_holdings(records)
        assert len(cleaned) == 1
