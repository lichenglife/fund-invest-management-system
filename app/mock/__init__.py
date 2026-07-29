"""mock · 前端契约优先的示例数据层(开发计划§3.2 前后端并行；详设§2.21 信封)。

后端 12 模块接口未就绪期间，前端通过本层拿到符合 §2.21.1 七字段信封的示例数据，
保证页面可运行、可演示。``source`` 标 ``mock`` 以区分真实数据；后端就绪后翻转
``MOCK_MODE`` 即切真实接口，页面代码零改动(§8.5 降级不阻断)。

> 数据形状贴合 ``infra/db/models``(Fund/Nav/Holding/Score/PaperAccount/PaperPosition)
> 字段口径，降低切换到真实接口的成本。金融口径红线见 CLAUDE.md §4。
"""

from __future__ import annotations

from app.mock import envelope, store

__all__: list[str] = ["envelope", "store"]
