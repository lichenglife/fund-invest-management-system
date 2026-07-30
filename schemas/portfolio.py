"""组合配置请求/响应模型(P1-08a，§3.6.5)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WeightItem(BaseModel):
    """组合权重项。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="基金代码")
    weight: float = Field(description="权重(0-1)")


class PortfolioCreateRequest(BaseModel):
    """POST /api/portfolios 创建组合(§3.6.5)。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="组合名称")
    source: str = Field(default="manual", description="来源(template/manual/import)")
    weights: list[WeightItem] = Field(default_factory=list, description="权重列表")
    account_id: str = Field(default="default", description="账户 ID")


class ImportFromPaperRequest(BaseModel):
    """POST /api/portfolios/import 从模拟持仓导入(§3.6.1)。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="组合名称")
    account_id: str = Field(default="default", description="账户 ID")
