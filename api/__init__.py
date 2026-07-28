"""api 包 · FastAPI Web 入口(开发规范§2.1)。

仅做路由/校验/依赖注入；算法逻辑置于 domain/，不反向依赖(ADR-002)。
"""

__all__: list[str] = ["main"]
