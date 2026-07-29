"""domain 包 · 领域与算法(纯逻辑，不依赖 Web，开发规范§2.1 / ADR-002)。

评分/归因/回测/宏观/筛选/采集清洗等纯函数置于本包；由 api/workers 调用，
不反向依赖 infra/api。算法口径以 TP-01~06 + CLAUDE.md §4 红线为准。
"""

__all__: list[str] = []
