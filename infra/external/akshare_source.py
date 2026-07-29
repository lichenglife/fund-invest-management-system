"""AkShare 数据源适配器(P1-01a，详设§3.1 数据采集 / §2.15 主源 / FR-36,46)。

主源适配器：调用 AkShare 接口，把中文列名映射为标准字段(详设§2.20.2 表口径)，
异常包装为 ExternalError(50301 数据源不可用，§8.5)。失败由调用方走 Tushare fallback(P1-01b)。

接口口径(运行时核实，见 docs/DEFERRED.md D6)：
- 名单：``fund_name_em()`` -> 基金代码/基金简称/基金类型
- 净值：``fund_open_fund_info_em(symbol, indicator="单位净值走势")`` -> 净值日期/单位净值/日增长率
- 重仓：``fund_portfolio_hold_em(symbol, date="2024")`` -> 股票代码/股票名称/占净值比例/季度
- 经理：``fund_manager_em()`` -> 经理信息(字段待 D2)

> AkShare 为延迟导入(运行时才需装；单测用 monkeypatch mock，就绪评估 O1)。
"""

from __future__ import annotations

import logging
from typing import Any

from infra.external.base import SRC_AKSHARE, DataSource
from schemas.errors import ErrorCode, ExternalError

logger = logging.getLogger(__name__)


def _map_fund_type(raw: str) -> str:
    """AkShare 基金类型(中文) -> 标准枚举(详设§2.20.2 type)。

    标准枚举：stock/bond/index/qdii/money/mixed(详设§2.20.2 注释)。
    """
    if not raw:
        return "mixed"
    s = raw.lower()
    if "股票" in raw or "stock" in s:
        return "stock"
    if "债券" in raw or "bond" in s:
        return "bond"
    if "指数" in raw or "index" in s:
        return "index"
    if "qdii" in s or "海外" in raw:
        return "qdii"
    if "货币" in raw or "money" in s:
        return "money"
    if "混合" in raw or "灵活" in raw:
        return "mixed"
    return "mixed"


class AkShareDataSource(DataSource):
    """AkShare 主数据源(§2.15 主源，fallback Tushare，P1-01b)。"""

    source = SRC_AKSHARE

    def fetch_fund_list(self) -> list[dict[str, Any]]:
        """拉取全基金名单(FR-36/DC-002 全类型)。

        AkShare ``fund_name_em()`` 返回 基金代码/基金简称/基金类型。
        """
        df = self._call("fund_name_em")
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            records.append(
                {
                    "code": str(row.get("基金代码", "")).strip(),
                    "name": str(row.get("基金简称", "")).strip(),
                    "type_": _map_fund_type(str(row.get("基金类型", ""))),
                    "raw_type": str(row.get("基金类型", "")).strip(),
                }
            )
        # 过滤空 code
        return [r for r in records if r["code"]]

    def fetch_nav(self, code: str, start: str, end: str) -> list[dict[str, Any]]:
        """拉取基金净值历史(§2.20.2 navs)。

        AkShare ``fund_open_fund_info_em(symbol, indicator="单位净值走势")``。
        ``start``/``end`` 为 YYYYMMDD，按净值日期区间过滤。

        > 口径缺口(D6)：AkShare 单位净值接口无累计净值/后复权净值；
        > ``acc_nav``/``adj_nav`` 暂填 None，由 P1-01c 清洗层补(累计净值接口/复权计算)。
        """
        df = self._call("fund_open_fund_info_em", symbol=code, indicator="单位净值走势")
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            trade_date = str(row.get("净值日期", "")).strip()[:10]
            if not trade_date:
                continue
            # 日期区间过滤(YYYYMMDD 比较)
            ymd = trade_date.replace("-", "")
            if start and ymd < start:
                continue
            if end and ymd > end:
                continue
            nav = row.get("单位净值")
            records.append(
                {
                    "code": code,
                    "trade_date": trade_date,
                    "nav": float(nav) if nav not in (None, "") else None,
                    "acc_nav": None,  # D6 待清洗层补
                    "adj_nav": None,  # D6 待清洗层补
                    "is_estimate": False,
                }
            )
        return records

    def fetch_holdings(self, code: str, year: str) -> list[dict[str, Any]]:
        """拉取基金重仓股(§2.20.2 holdings，季度)。

        AkShare ``fund_portfolio_hold_em(symbol, date=year)`` 返回
        股票代码/股票名称/占净值比例/季度。
        """
        df = self._call("fund_portfolio_hold_em", symbol=code, date=year)
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            stock_code = str(row.get("股票代码", "")).strip()
            if not stock_code:
                continue
            report_date = _parse_report_date(str(row.get("季度", "")))
            weight = row.get("占净值比例")
            records.append(
                {
                    "code": code,
                    "report_date": report_date,
                    "stock_code": stock_code,
                    "stock_name": str(row.get("股票名称", "")).strip(),
                    "weight": float(weight) / 100.0 if weight not in (None, "") else None,
                }
            )
        return records

    def fetch_managers(self) -> list[dict[str, Any]]:
        """拉取基金经理(§2.20.3 managers，字段待 D2 定义)。

        AkShare ``fund_manager_em()``；表结构待 D2，暂返原始列字典。
        """
        df = self._call("fund_manager_em")
        return list(df.to_dict(orient="records"))

    # ------------------------------------------------------------------ 内部

    def _call(self, func_name: str, **kwargs: Any) -> Any:
        """延迟导入 AkShare 并调用；异常包装为 ExternalError(50301，§8.5)。

        单测通过 monkeypatch ``_call`` 或 ``akshare.<func>`` 注入 mock(就绪评估 O1)。
        """
        try:
            import akshare as ak  # 延迟导入(运行时才需装)
        except ImportError as exc:  # pragma: no cover  运行环境依赖
            raise ExternalError(
                "AkShare 未安装，请安装 requirements-extras.txt",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
                cause=exc,
            ) from exc

        func = getattr(ak, func_name, None)
        if func is None:
            raise ExternalError(
                f"AkShare 接口不存在: {func_name}",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
            )
        try:
            return func(**kwargs)
        except Exception as exc:  # noqa: BLE001  第三方异常统一包装(§8.1)
            logger.warning(
                "akshare.fetch_failed",
                extra={"action": "fetch", "func": func_name, "err": str(exc)},
            )
            raise ExternalError(
                f"AkShare 拉取失败({func_name})：{exc}",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
                cause=exc,
            ) from exc


def _parse_report_date(quarter: str) -> str:
    """把 AkShare 季度串(如 '2024年1季度股票投资明细')解析为 report_date(季度末)。

    Returns:
        ``YYYY-MM-DD`` 季度末日期；解析失败返回空串。
    """
    import re

    m = re.search(r"(\d{4})年(\d)季度", quarter)
    if not m:
        return ""
    year, q = int(m.group(1)), int(m.group(2))
    # 季度末日期
    quarter_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{year}-{quarter_end.get(q, '12-31')}"


__all__: list[str] = ["AkShareDataSource", "_map_fund_type"]
