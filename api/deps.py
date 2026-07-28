"""FastAPI 依赖注入(§2.1 / §6.4 鉴权在依赖层)。

复用 infra 提供的引擎/连接，由路由声明 ``Depends(get_db)`` 注入。
后续鉴权(P0-05)、限流(§6.5)、Redis 依赖在此扩展。
"""

from __future__ import annotations

from infra.db.session import get_db

__all__: list[str] = ["get_db"]
