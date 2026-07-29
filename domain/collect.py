"""采集数据清洗(纯函数)(P1-01c，详设§3.1.2 清洗 / §2.20.2 字段口径)。

把 DataSource 返回的原始记录标准化、去重、补全后复权净值回退，供 upsert 层消费。
纯函数无外部依赖，便于 CI 高频跑与多进程复用(ADR-002)。

口径(D6)：
- ``acc_nav``(累计净值)：由 adapter 合并(累计净值走势)。
- ``adj_nav``(后复权净值)：需按分红复权计算(E3 红线)，当前无分红明细，
  临时回退 ``adj_nav = acc_nav``(累计净值已含分红累积，作为近似后复权)，
  标注 ``quality_flag="adj_nav_proxy"``；待 P1-01c/TP-04 分红复权落地。
- 缺失 ``nav`` 的行丢弃(净值核心字段，§2.20.2 NOT NULL)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict


#: 清洗后的净值记录(DTO，对齐 navs 表)。
class NavRecord(TypedDict, total=False):
    code: str
    trade_date: str
    nav: Decimal
    acc_nav: Decimal | None
    adj_nav: Decimal | None
    is_estimate: bool
    source: str
    quality_flag: str | None


def clean_nav(
    records: list[dict[str, Any]],
    *,
    source: str = "AkShare",
) -> list[NavRecord]:
    """清洗净值记录(§3.1.2 清洗)。

    Args:
        records: adapter fetch_nav 返回的原始记录。
        source: 数据源标识(写入 source 字段，§3.1.7 溯源)。
    Returns:
        清洗后记录：丢弃 nav 缺失行；补 acc_nav；adj_nav 临时回退 acc_nav。
    """
    cleaned: list[NavRecord] = []
    seen: set[tuple[str, str]] = set()  # (code, trade_date) 去重(§3.14.5 幂等)
    for r in records:
        code = str(r.get("code", "")).strip()
        trade_date = str(r.get("trade_date", "")).strip()[:10]
        if not code or not trade_date:
            continue
        nav = _to_decimal(r.get("nav"))
        if nav is None:
            # nav 缺失 -> 丢弃(§2.20.2 NOT NULL)
            continue
        key = (code, trade_date)
        if key in seen:  # 去重
            continue
        seen.add(key)

        acc_nav = _to_decimal(r.get("acc_nav"))
        # adj_nav 回退：无后复权时用 acc_nav 近似(E3 待补，D6)
        adj_raw = r.get("adj_nav")
        adj_nav = _to_decimal(adj_raw) if adj_raw not in (None, "") else acc_nav
        quality_flag = "adj_nav_proxy" if adj_raw in (None, "") else None

        cleaned.append(
            NavRecord(
                code=code,
                trade_date=trade_date,
                nav=nav,
                acc_nav=acc_nav,
                adj_nav=adj_nav,
                is_estimate=bool(r.get("is_estimate", False)),
                source=source,
                quality_flag=quality_flag,
            )
        )
    return cleaned


def clean_fund_list(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗基金名单：去重(按 code)、规整字段。"""
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for r in records:
        code = str(r.get("code", "")).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        cleaned.append(
            {
                "code": code,
                "name": str(r.get("name", "")).strip(),
                "type_": str(r.get("type_", "mixed")).strip() or "mixed",
                "source": str(r.get("source", r.get("raw_type", ""))).strip() or "AkShare",
            }
        )
    return cleaned


def clean_holdings(
    records: list[dict[str, Any]], *, source: str = "AkShare"
) -> list[dict[str, Any]]:
    """清洗重仓股：去重(复合 PK)、weight 规整。"""
    seen: set[tuple[str, str, str]] = set()
    cleaned: list[dict[str, Any]] = []
    for r in records:
        code = str(r.get("code", "")).strip()
        report_date = str(r.get("report_date", "")).strip()[:10]
        stock_code = str(r.get("stock_code", "")).strip()
        if not code or not report_date or not stock_code:
            continue
        key = (code, report_date, stock_code)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            {
                "code": code,
                "report_date": report_date,
                "stock_code": stock_code,
                "stock_name": str(r.get("stock_name", "")).strip(),
                "weight": _to_decimal(r.get("weight")),
                "source": source,
            }
        )
    return cleaned


def _to_decimal(v: Any) -> Decimal | None:
    """安全转 Decimal；空值/非法值返回 None。"""
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None


__all__: list[str] = ["NavRecord", "clean_nav", "clean_fund_list", "clean_holdings"]
