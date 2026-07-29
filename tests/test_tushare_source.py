"""Tushare 备源适配器 + fallback 协调器单测(P1-01b，§2.15 / §8.5 降级)。

全 mock：sys.modules 注入 fake tushare(就绪评估 O1)，无网络/无 token 依赖。
覆盖：字段映射、fallback 降级(degraded 标注)、皆失 50301、无 token 50301。
"""

from __future__ import annotations

import sys
from typing import Any

import pandas as pd
import pytest

from infra.external.akshare_source import AkShareDataSource
from infra.external.base import SRC_AKSHARE, SRC_TUSHARE, DataSource
from infra.external.coordinator import DataSourceCoordinator
from infra.external.tushare_source import TushareDataSource, _map_fund_type_pro, _to_ts_code
from schemas.errors import ErrorCode, ExternalError

# --- Tushare 假数据(模拟 fund_basic/fund_nav/fund_portfolio 返回) ---


def _fake_basic_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.OF", "510300.SH"],
            "name": ["华夏成长混合", "沪深300ETF"],
            "management": ["华夏基金", "华泰柏瑞"],
            "custodian": ["建行", "工行"],
            "fund_type": ["混合型", "指数型"],
        }
    )


def _fake_nav_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.OF", "000001.OF"],
            "ann_date": ["20250701", "20250728"],
            "unit_nav": [1.012, 1.308],
            "accum_nav": [2.345, 2.678],
        }
    )


def _fake_portfolio_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.OF", "000001.OF"],
            "ann_date": ["20240331", "20240331"],
            "symbol": ["002025", "600862"],
            "name": ["航天电器", "中航高科"],
            "amount": [100, 200],
            "stk_float_ratio": [3.46, 3.24],
        }
    )


class _FakeProApi:
    """fake tushare pro_api 实例(pro.query 入口)。"""

    def query(self, api_name: str, **kwargs: Any) -> pd.DataFrame:
        mapping = {
            "fund_basic": _fake_basic_df(),
            "fund_nav": _fake_nav_df(),
            "fund_portfolio": _fake_portfolio_df(),
            "fund_manager": pd.DataFrame({"ts_code": ["000001.OF"], "name": ["张三"]}),
        }
        if api_name not in mapping:
            raise ValueError(f"未知 api_name: {api_name}")
        return mapping[api_name]


class _FakeTushareModule:
    """注入 sys.modules 的 fake tushare 模块。"""

    @staticmethod
    def set_token(token: str) -> None:
        _FakeTushareModule._token = token  # type: ignore[attr-defined]

    @staticmethod
    def pro_api() -> _FakeProApi:
        return _FakeProApi()

    __version__ = "1.4.16-test"


@pytest.fixture()
def fake_tushare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "tushare", _FakeTushareModule)  # type: ignore[arg-type]


@pytest.fixture()
def tushare_src(fake_tushare: None) -> TushareDataSource:
    return TushareDataSource(token="fake-token")


class TestFundTypeMapping:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("EQ股票", "stock"),
            ("BO债券", "bond"),
            ("IDX指数", "index"),
            ("QDII", "qdii"),
            ("MO货币", "money"),
            (None, "mixed"),
        ],
    )
    def test_map_type(self, raw: str | None, expected: str) -> None:
        assert _map_fund_type_pro(raw) == expected

    def test_to_ts_code(self) -> None:
        assert _to_ts_code("000001") == "000001.OF"
        assert _to_ts_code("510300.SH") == "510300.SH"  # 已有后缀原样


class TestTushareSource:
    """P1-01b Tushare 拉取与字段映射。"""

    def test_source_tag(self, tushare_src: TushareDataSource) -> None:
        assert tushare_src.source == SRC_TUSHARE

    def test_fetch_fund_list(self, tushare_src: TushareDataSource) -> None:
        records = tushare_src.fetch_fund_list()
        assert len(records) == 2
        assert records[0]["code"] == "000001.OF"
        assert records[0]["name"] == "华夏成长混合"
        assert records[0]["type_"] == "mixed"  # "混合型" -> mixed

    def test_fetch_nav_has_accum_nav(self, tushare_src: TushareDataSource) -> None:
        """Tushare fund_nav 含 accum_nav(累计净值)；adj_nav 仍 None(D6)。"""
        records = tushare_src.fetch_nav("000001", "20250101", "20251231")
        assert len(records) == 2
        assert records[1]["nav"] == 1.308
        assert records[1]["acc_nav"] == 2.678  # Tushare 有累计净值
        assert records[1]["adj_nav"] is None  # D6 待清洗层补

    def test_fetch_holdings_year_filter(self, tushare_src: TushareDataSource) -> None:
        """重仓：stk_float_ratio(%) -> 权重(小数)；ann_date 按 year 过滤。"""
        records = tushare_src.fetch_holdings("000001", "2024")
        assert len(records) == 2
        assert records[0]["stock_code"] == "002025"
        assert records[0]["weight"] == pytest.approx(0.0346)
        # year 过滤：2023 应无数据
        empty = tushare_src.fetch_holdings("000001", "2023")
        assert empty == []


class TestTushareErrors:
    """§8.5：无 token / 拉取失败 -> 50301。"""

    def test_no_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 token -> ExternalError(50301)。"""
        # 清空 token
        monkeypatch.setenv("TUSHARE_TOKEN", "")
        from config.settings import Settings

        src = TushareDataSource(token=Settings().tushare_token)
        with pytest.raises(ExternalError) as exc_info:
            src.fetch_fund_list()
        assert exc_info.value.code == ErrorCode.DATASOURCE_UNAVAILABLE

    def test_query_failure_wrapped(self, fake_tushare: None) -> None:
        """pro.query 抛异常 -> ExternalError(50301)。"""

        class _BrokenProApi:
            def query(self, api_name: str, **kwargs: Any) -> pd.DataFrame:
                raise RuntimeError("tushare 500")

        class _BrokenTushare:
            @staticmethod
            def set_token(token: str) -> None: ...

            @staticmethod
            def pro_api() -> _BrokenProApi:
                return _BrokenProApi()

        import sys as _sys

        _sys.modules["tushare"] = _BrokenTushare  # type: ignore[assignment]
        src = TushareDataSource(token="fake-token")
        with pytest.raises(ExternalError) as exc_info:
            src.fetch_fund_list()
        assert exc_info.value.code == ErrorCode.DATASOURCE_UNAVAILABLE


class TestCoordinator:
    """§2.15 fallback 协调器：主源成功 / 主源失败 fallback / 皆失。"""

    def test_primary_success_no_degraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """主源成功：返回数据，不标 degraded。"""
        _inject_fake_akshare(monkeypatch)
        coord = DataSourceCoordinator(
            primary=AkShareDataSource(), fallback=_StubSource(SRC_TUSHARE)
        )

        records = coord.fetch("fetch_fund_list")
        assert len(records) == 1
        assert records[0].get("degraded") is None  # 主源成功不标降级

    def test_primary_fail_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """主源失败 -> fallback 成功；数据标 degraded=True(§8.5 可观测)。"""
        broken = _BrokenSource(SRC_AKSHARE)  # 主源总是失败
        good_fb = _StubSource(SRC_TUSHARE)
        coord = DataSourceCoordinator(primary=broken, fallback=good_fb)

        records = coord.fetch("fetch_fund_list")
        assert len(records) == 1
        assert records[0]["degraded"] is True
        assert records[0]["source"] == SRC_TUSHARE

    def test_all_fail_raises_50301(self) -> None:
        """主源与备源皆失 -> ExternalError(50301)。"""
        coord = DataSourceCoordinator(
            primary=_BrokenSource(SRC_AKSHARE), fallback=_BrokenSource(SRC_TUSHARE)
        )
        with pytest.raises(ExternalError) as exc_info:
            coord.fetch("fetch_fund_list")
        assert exc_info.value.code == ErrorCode.DATASOURCE_UNAVAILABLE


# --- stubs for coordinator tests ---


class _StubSource(DataSource):
    """返回单条固定数据的存根源。"""

    source = "stub"

    def __init__(self, tag: str = "stub") -> None:
        self.source = tag

    def fetch_fund_list(self) -> list[dict[str, Any]]:
        return [{"code": "000001", "name": "stub", "type_": "mixed"}]

    def fetch_nav(self, code: str, start: str, end: str) -> list[dict[str, Any]]:
        return [{"code": code, "trade_date": "2025-07-28", "nav": 1.0}]

    def fetch_holdings(self, code: str, year: str) -> list[dict[str, Any]]:
        return [{"code": code, "stock_code": "002025"}]

    def fetch_managers(self) -> list[dict[str, Any]]:
        return [{"name": "stub"}]


class _BrokenSource(DataSource):
    """总是抛 ExternalError 的损坏源。"""

    def __init__(self, tag: str = "broken") -> None:
        self.source = tag

    def _fail(self, **kwargs: Any) -> list[dict[str, Any]]:
        raise ExternalError("source down", code=ErrorCode.DATASOURCE_UNAVAILABLE)

    fetch_fund_list = _fail  # type: ignore[assignment]
    fetch_nav = _fail  # type: ignore[assignment]
    fetch_holdings = _fail  # type: ignore[assignment]
    fetch_managers = _fail  # type: ignore[assignment]


def _inject_fake_akshare(monkeypatch: pytest.MonkeyPatch) -> None:
    """为 coordinator 主源成功用例注入 fake akshare(通过 monkeypatch 自动清理)。"""

    class _AK:
        @staticmethod
        def fund_name_em() -> pd.DataFrame:
            return pd.DataFrame(
                {"基金代码": ["000001"], "基金简称": ["华夏成长"], "基金类型": ["混合型"]}
            )

        @staticmethod
        def fund_open_fund_info_em(symbol: str, indicator: str) -> pd.DataFrame:
            return pd.DataFrame()

        @staticmethod
        def fund_portfolio_hold_em(symbol: str, date: str) -> pd.DataFrame:
            return pd.DataFrame()

        @staticmethod
        def fund_manager_em() -> pd.DataFrame:
            return pd.DataFrame()

    monkeypatch.setitem(sys.modules, "akshare", _AK)  # type: ignore[arg-type]
