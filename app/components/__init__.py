"""components · 可复用 Python 复合控件(开发规范§2.2/§10.2)。

原型线框中的复合展示控件封装于此，供各页面组合复用：
- ``ui``：指标卡/面板/状态药丸/来源页脚等通用件。
- ``score_panel``：五因子评分卡 + 滑杆重算(P1-14a，TP-01 §3.1)。
- ``brinson_chart``：Brinson 三向分解(P1-14b，TP-01 §3.5)。
- ``diagnosis_table``：红黄绿诊断表(P1-17a，TP-03)。
- ``style_box``：九宫格风格箱(BR-2.3/DC-002 F)。
"""

from __future__ import annotations

from app.components import brinson_chart, diagnosis_table, score_panel, style_box, ui  # noqa: F401

__all__: list[str] = [
    "brinson_chart",
    "diagnosis_table",
    "score_panel",
    "style_box",
    "ui",
]
