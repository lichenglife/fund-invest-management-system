"""infra 包 · 基础设施(db / redis / external / lock / logging / middleware)。

domain/ 不反向依赖 infra(开发规范§2.1)；infra 提供引擎与连接，由 api/workers 注入。
"""

__all__: list[str] = []
