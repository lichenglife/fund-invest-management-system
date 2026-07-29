"""Tushare 备数据源适配器(P1-01b，详设§3.1 / §2.15 fallback / FR-36)。

AkShare 主源失败时降级到 Tushare(§2.15 容错)。复用 ``DataSource`` 接口(P1-01a)，
字段映射对齐详设§2.20.2 表口径。

Tushare Pro 用通用入口 ``pro.query(api_name, fields, **kwargs)``；api_name 与字段
按 Tushare 官方文档(运行时未免 token 实跑，见 docs/DEFERRED.md D8)：
- 净值：``fund_nav`` -> ts_code/ann_date/unit_nav/accum_nav
- 名单：``fund_basic`` -> ts_code/name/management/custodian/fund_type
- 持仓：``fund_portfolio`` -> ts_code/ann_date/symbol/name/amount/stk_float_ratio
- 经理：``fund_manager`` -> ts_code/name/ann_date

> token 从 settings.tushare_token 注入(§2.19.1 不入库)；无 token 时不可用(50301)。
> 单测用 sys.modules 注入 fake tushare(就绪评估 O1)。
"""

from __future__ import annotations

import logging
from typing import Any

from infra.external.base import SRC_TUSHARE, DataSource
from schemas.errors import ErrorCode, ExternalError

logger = logging.getLogger(__name__)


def _map_fund_type_pro(raw: str | None) -> str:
    """Tushare fund_type(代码) -> 标准枚举(详设§2.20.2 type)。

    Tushare fund_type 约定：EF/OF/QDII/IDX/MKT(ETF/开放式/QDII/指数/货币)等。
    """
    if not raw:
        return "mixed"
    s = str(raw).upper()
    if s.startswith("EQ") or "股票" in s:
        return "stock"
    if s.startswith("BO") or "债" in s:
        return "bond"
    if s.startswith("ID") or "指" in s:
        return "index"
    if "QDII" in s or "海外" in s:
        return "qdii"
    if s.startswith("MO") or "货" in s or "MM" in s:
        return "money"
    return "mixed"


class TushareDataSource(DataSource):
    """Tushare 备数据源(§2.15 fallback；AkShare 失败时降级)。"""

    source = SRC_TUSHARE

    def __init__(self, token: str | None = None) -> None:
        """Args:
        token: Tushare token；None 取 settings.tushare_token(§2.19.1)。
        """
        if token is None:
            from config.settings import settings

            token = settings.tushare_token
        self._token = token or ""

    def _pro(self) -> Any:
        """初始化 Tushare pro 客户端(延迟；无 token 抛 50301)。

        单测通过 sys.modules['tushare'] 注入 fake 模块。
        """
        if not self._token:
            raise ExternalError(
                "Tushare token 未配置(§2.19.1)，无法 fallback",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
            )
        try:
            import tushare as ts  # 延迟导入
        except ImportError as exc:  # pragma: no cover
            raise ExternalError(
                "tushare 未安装",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
                cause=exc,
            ) from exc
        ts.set_token(self._token)
        return ts.pro_api()

    def fetch_fund_list(self) -> list[dict[str, Any]]:
        """拉取全基金名单(fund_basic)。

        Tushare ``fund_basic`` 返回 ts_code/name/management/custodian/fund_type。
        """
        df = self._query("fund_basic")
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            records.append(
                {
                    "code": str(row.get("ts_code", "")).strip(),
                    "name": str(row.get("name", "")).strip(),
                    "type_": _map_fund_type_pro(row.get("fund_type")),
                    "raw_type": str(row.get("fund_type", "")).strip(),
                }
            )
        return [r for r in records if r["code"]]

    def fetch_nav(self, code: str, start: str, end: str) -> list[dict[str, Any]]:
        """拉取基金净值(fund_nav)。

        Tushare ``fund_nav`` 返回 ts_code/ann_date/unit_nav/accum_nav。
        ``start``/``end`` 为 YYYYMMDD；Tushare 用 trade_date 区间。

        > D6 同缺口：Tushare fund_nav 有 accum_nav(累计净值)，但仍无后复权净值；
        > adj_nav 由 P1-01c 清洗层按分红复权计算。
        """
        ts_code = _to_ts_code(code)
        df = self._query("fund_nav", ts_code=ts_code, start_date=start, end_date=end)
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            ann = str(row.get("ann_date", "")).strip()[:10]
            if not ann:
                continue
            records.append(
                {
                    "code": code,
                    "trade_date": ann,
                    "nav": _to_float(row.get("unit_nav")),
                    "acc_nav": _to_float(row.get("accum_nav")),  # Tushare 有累计净值
                    "adj_nav": None,  # D6 待清洗层补
                    "is_estimate": False,
                }
            )
        return records

    def fetch_holdings(self, code: str, year: str) -> list[dict[str, Any]]:
        """拉取基金重仓(fund_portfolio)。

        Tushare ``fund_portfolio`` 返回 ts_code/ann_date/symbol/name/amount/stk_float_ratio。
        """
        ts_code = _to_ts_code(code)
        df = self._query("fund_portfolio", ts_code=ts_code)
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            stock_code = str(row.get("symbol", "")).strip()
            if not stock_code:
                continue
            ann = str(row.get("ann_date", "")).strip()[:10]
            ratio = row.get("stk_float_ratio")  # 流通股占比
            records.append(
                {
                    "code": code,
                    "report_date": ann,
                    "stock_code": stock_code,
                    "stock_name": str(row.get("name", "")).strip(),
                    "weight": float(ratio) / 100.0 if ratio not in (None, "") else None,
                }
            )
        # 按 year 过滤(ann_date 前4位)
        return [r for r in records if r["report_date"].startswith(year)]

    def fetch_managers(self) -> list[dict[str, Any]]:
        """拉取基金经理(fund_manager)。字段待 D2，暂返原始结构。"""
        df = self._query("fund_manager")
        return list(df.to_dict(orient="records"))

    # ------------------------------------------------------------------ 内部

    def _query(self, api_name: str, **kwargs: Any) -> Any:
        """调用 Tushare pro.query；异常包装 ExternalError(50301，§8.5)。"""
        pro = self._pro()
        try:
            return pro.query(api_name, **kwargs)
        except Exception as exc:  # noqa: BLE001  第三方异常统一包装(§8.1)
            logger.warning(
                "tushare.fetch_failed",
                extra={"action": "fetch", "api": api_name, "err": str(exc)},
            )
            raise ExternalError(
                f"Tushare 拉取失败({api_name})：{exc}",
                code=ErrorCode.DATASOURCE_UNAVAILABLE,
                cause=exc,
            ) from exc


def _to_ts_code(code: str) -> str:
    """AkShare 风格代码 -> Tushare ts_code(开放式基金加 .OF)。

    Tushare 开放式基金 ts_code 形如 ``000001.OF``；若已是 .OF/.SH/.SZ 则原样。
    """
    code = code.strip()
    if "." in code:
        return code
    return f"{code}.OF"


def _to_float(v: Any) -> float | None:
    """安全转 float；空值/None 返回 None。"""
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


__all__: list[str] = ["TushareDataSource", "_map_fund_type_pro"]
