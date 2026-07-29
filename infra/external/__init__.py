"""infra.external · 外部数据源/LLM 适配器(§2.15 容错 / TP-02 / TP-06)。

约定(§2.15 / §8.5)：任意外部调用须有超时 + fallback；AkShare 失 -> Tushare，
LLM 失 -> 规则摘要(50303)；降级须可观测(degraded=true)。

- ``DataSource``：抽象数据源接口(P1-01a/b 适配器实现)。
- ``AkShareDataSource``：AkShare 主源(P1-01a)。
- ``TushareDataSource``：Tushare 备源 fallback(P1-01b)。
- ``DataSourceCoordinator``：主备 fallback 协调(§2.15)。
- LLM 客户端(P1-06b)待落地。
"""

from infra.external.akshare_source import AkShareDataSource
from infra.external.base import SRC_AKSHARE, SRC_TUSHARE, DataSource
from infra.external.coordinator import DataSourceCoordinator
from infra.external.tushare_source import TushareDataSource

__all__: list[str] = [
    "DataSource",
    "SRC_AKSHARE",
    "SRC_TUSHARE",
    "AkShareDataSource",
    "TushareDataSource",
    "DataSourceCoordinator",
]
