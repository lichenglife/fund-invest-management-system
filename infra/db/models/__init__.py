"""infra.db.models · SQLAlchemy 2.x ORM 模型(详设§2.20 数据模型与 DDL)。

按 §2.20.2 核心表 DDL 建模，FK/索引/CHECK 精确对齐。
其余 22 表字段未在详设定义(§3.x.4 仅罗列表名)，见 docs/DEFERRED.md 搁置记录。

模型置于 infra/，由 Alembic 管理迁移(§2.7)。domain/ 算法层用纯 dataclass/TypedDict
做 DTO，不反向依赖 ORM(开发规范§2.1)。
"""

from infra.db.models.fund import Fund, Holding, Nav, ResearchMetric, Score
from infra.db.models.paper import PaperAccount, PaperPosition, PaperTrade
from infra.db.models.portfolio import Portfolio, PortfolioWeight

__all__: list[str] = [
    "Fund",
    "Holding",
    "Nav",
    "ResearchMetric",
    "Score",
    "PaperAccount",
    "PaperPosition",
    "PaperTrade",
    "Portfolio",
    "PortfolioWeight",
]
