"""数据源抽象接口(§2.15 容错 / P1-01a AkShare 主 + P1-01b Tushare 备)。

定义统一拉取契约：fetch 返回标准化 DataFrame(dict 行)，由 P1-01c 清洗+upsert 层消费。
各适配器把第三方列名映射为标准字段(详设 §2.20.2 表字段口径)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

#: 数据源标识(写入 source 字段，§2.19.7 溯源)。
SRC_AKSHARE = "AkShare"
SRC_TUSHARE = "Tushare"


class DataSource(ABC):
    """基金数据源抽象基类(§2.15 / §3.1.2 流程)。

    子类实现具体拉取逻辑；统一返回标准化结构，异常包装为 ExternalError(§8.1)。
    """

    #: 数据源标识(写入 source 字段)。
    source: str = "unknown"

    @abstractmethod
    def fetch_fund_list(self) -> list[dict[str, Any]]:
        """拉取全基金名单(基础信息，FR-36/DC-002 全类型)。

        Returns:
            标准化基金记录列表：{code, name, type_, ...}。
        """

    @abstractmethod
    def fetch_nav(self, code: str, start: str, end: str) -> list[dict[str, Any]]:
        """拉取基金净值历史(§2.20.2 navs)。

        Args:
            code: 基金代码(如 000001)。
            start: 起始日期 YYYYMMDD。
            end: 结束日期 YYYYMMDD。
        Returns:
            标准化净值记录列表：{code, trade_date, nav, acc_nav, adj_nav, ...}。
        """

    @abstractmethod
    def fetch_holdings(self, code: str, year: str) -> list[dict[str, Any]]:
        """拉取基金重仓股(§2.20.2 holdings，季度)。

        Args:
            code: 基金代码。
            year: 年份(如 2024)。
        Returns:
            标准化重仓记录列表：{code, report_date, stock_code, stock_name, weight, ...}。
        """

    @abstractmethod
    def fetch_managers(self) -> list[dict[str, Any]]:
        """拉取基金经理(§2.20.3 managers，字段待 D2 定义，暂返原始结构)。"""


__all__: list[str] = ["DataSource", "SRC_AKSHARE", "SRC_TUSHARE"]
