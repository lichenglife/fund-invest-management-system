"""AkShare 适配器单测(P1-01a，详设§3.1 / §2.15 / §8.5 降级)。

全 mock：注入 sys.modules['akshare'] fake 模块，不依赖网络(就绪评估 O1)。
覆盖：字段映射(中文列->标准字段)、日期区间过滤、异常包装(50301)。
"""

from __future__ import annotations

import sys

import pandas as pd
import pytest

from infra.external.akshare_source import AkShareDataSource, _map_fund_type
from infra.external.base import SRC_AKSHARE
from schemas.errors import ErrorCode, ExternalError

# --- AkShare 假数据(模拟真实列名) ---


def _fake_name_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "基金代码": ["000001", "000002", "510300"],
            "拼音缩写": ["A", "B", "C"],
            "基金简称": ["华夏成长混合", "华夏成长混合后", "沪深300ETF"],
            "基金类型": ["混合型-灵活", "混合型-灵活", "指数型-ETF"],
            "拼音全称": ["A", "B", "C"],
        }
    )


def _fake_nav_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "净值日期": ["2025-07-01", "2025-07-02", "2025-07-28"],
            "单位净值": [1.012, 1.015, 1.308],
            "日增长率": [0.1, 0.3, -6.44],
        }
    )


def _fake_holdings_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "序号": [1, 2],
            "股票代码": ["002025", "600862"],
            "股票名称": ["航天电器", "中航高科"],
            "占净值比例": [3.46, 3.24],
            "持股数": [209.92, 380.43],
            "持仓市值": [7947.67, 7441.67],
            "季度": ["2024年1季度股票投资明细", "2024年1季度股票投资明细"],
        }
    )


class _FakeAkshare:
    """注入 sys.modules 的 mock akshare 模块。"""

    __version__ = "1.18.80-test"

    @staticmethod
    def fund_name_em() -> pd.DataFrame:
        return _fake_name_df()

    @staticmethod
    def fund_open_fund_info_em(symbol: str, indicator: str) -> pd.DataFrame:
        return _fake_nav_df()

    @staticmethod
    def fund_portfolio_hold_em(symbol: str, date: str) -> pd.DataFrame:
        return _fake_holdings_df()

    @staticmethod
    def fund_manager_em() -> pd.DataFrame:
        return pd.DataFrame({"姓名": ["张三"], "任职基金数": [5]})


@pytest.fixture()
def fake_ak(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入 fake akshare 到 sys.modules(_call 内 `import akshare` 命中)。"""
    monkeypatch.setitem(sys.modules, "akshare", _FakeAkshare)  # type: ignore[arg-type]


@pytest.fixture()
def source(fake_ak: None) -> AkShareDataSource:
    return AkShareDataSource()


class TestFundTypeMapping:
    """§2.20.2 type 枚举映射。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("股票型", "stock"),
            ("混合型-灵活", "mixed"),
            ("债券型", "bond"),
            ("指数型-ETF", "index"),
            ("QDII", "qdii"),
            ("货币市场型", "money"),
            ("", "mixed"),
        ],
    )
    def test_map_type(self, raw: str, expected: str) -> None:
        assert _map_fund_type(raw) == expected


class TestAkShareSource:
    """P1-01a 拉取与字段映射。"""

    def test_source_tag(self, source: AkShareDataSource) -> None:
        assert source.source == SRC_AKSHARE == "AkShare"

    def test_fetch_fund_list_mapping(self, source: AkShareDataSource) -> None:
        """名单：中文列 -> 标准字段(code/name/type_)。"""
        records = source.fetch_fund_list()
        assert len(records) == 3
        assert records[0]["code"] == "000001"
        assert records[0]["name"] == "华夏成长混合"
        assert records[0]["type_"] == "mixed"
        assert records[2]["type_"] == "index"  # 指数型-ETF

    def test_fetch_nav_date_filter(self, source: AkShareDataSource) -> None:
        """净值：日期区间过滤(YYYYMMDD 比较)。"""
        all_nav = source.fetch_nav("000001", "20250101", "20251231")
        assert len(all_nav) == 3
        assert all_nav[0]["code"] == "000001"
        assert all_nav[2]["trade_date"] == "2025-07-28"
        assert all_nav[2]["nav"] == 1.308
        # 缩小区间：只取 20250702 之后
        sub = source.fetch_nav("000001", "20250702", "20251231")
        assert len(sub) == 2
        # acc_nav/adj_nav 暂为 None(D6 口径缺口)
        assert all(n["acc_nav"] is None for n in all_nav)

    def test_fetch_holdings_mapping(self, source: AkShareDataSource) -> None:
        """重仓：占净值比例(%) -> 权重(小数)；季度串 -> report_date。"""
        records = source.fetch_holdings("000001", "2024")
        assert len(records) == 2
        assert records[0]["stock_code"] == "002025"
        assert records[0]["stock_name"] == "航天电器"
        assert records[0]["report_date"] == "2024-03-31"  # 1季度末
        assert records[0]["weight"] == pytest.approx(0.0346)  # 3.46% -> 0.0346

    def test_fetch_managers(self, source: AkShareDataSource) -> None:
        """经理：返回原始列(managers 表字段待 D2)。"""
        records = source.fetch_managers()
        assert len(records) == 1
        assert records[0]["姓名"] == "张三"


class TestAkShareErrorWrapping:
    """§8.5：第三方异常包装为 ExternalError(50301)。"""

    def test_call_failure_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AkShare 函数抛异常 -> ExternalError(50301)。"""

        class _BrokenAkshare:
            @staticmethod
            def fund_name_em() -> pd.DataFrame:
                raise ConnectionError("network down")

        monkeypatch.setitem(sys.modules, "akshare", _BrokenAkshare)  # type: ignore[arg-type]
        source = AkShareDataSource()
        with pytest.raises(ExternalError) as exc_info:
            source.fetch_fund_list()
        assert exc_info.value.code == ErrorCode.DATASOURCE_UNAVAILABLE

    def test_missing_func_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """接口不存在 -> ExternalError(50301)。"""

        class _EmptyAkshare:
            pass

        monkeypatch.setitem(sys.modules, "akshare", _EmptyAkshare)  # type: ignore[arg-type]
        source = AkShareDataSource()
        with pytest.raises(ExternalError) as exc_info:
            source.fetch_fund_list()
        assert exc_info.value.code == ErrorCode.DATASOURCE_UNAVAILABLE
