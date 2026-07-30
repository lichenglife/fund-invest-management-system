"""utils · 纯函数(格式化/计算/颜色，开发规范§2.2 utils.py)。

无 Streamlit 依赖，便于单测与复用。颜色遵循 A 股惯例：红涨绿跌；状态用
绿=正常/红=异常；阈值着色 good/warn/bad -> 绿/琥珀/红(原型设计令牌§5)。
"""

from __future__ import annotations

from typing import Any, SupportsFloat

#: 设计令牌色(原型§5 金融翠绿专业风；与 app/static/style.css 权威源对齐)。
#: 主色墨绿/翠绿仅用于品牌、收益、选中态；红仅用于亏损/风险数值，禁用于 active。
COLOR_GREEN_D = "#0A6B4A"  # 墨绿：品牌主色(对齐 style.css --brand-deep)
COLOR_GREEN = "#16A34A"  # 翠绿：收益正/选中态高亮(对齐 style.css --brand)
COLOR_BLUE = "#1D4ED8"  # 信息蓝
COLOR_RED = "#E23B3B"  # 红：仅亏损/风险数值
COLOR_AMBER = "#B45309"  # 琥珀：警告
COLOR_GRAY = "#6B7280"  # 次要文字

#: level -> hex(原型 .rcard good/warn/bad 着色)。
LEVEL_COLOR: dict[str, str] = {
    "good": COLOR_GREEN,
    "ok": COLOR_GREEN,
    "g": COLOR_GREEN,
    "warn": COLOR_AMBER,
    "y": COLOR_AMBER,
    "bad": COLOR_RED,
    "r": COLOR_RED,
}


def format_pct(value: SupportsFloat | None, digits: int = 2) -> str:
    """比率 -> 百分比字符串(0.1234 -> 12.34%)；None -> 暂无。"""
    if value is None:
        return "暂无"
    return f"{float(value) * 100:.{digits}f}%"


def format_amount(value: SupportsFloat | None, unit: str = "元") -> str:
    """金额格式化(万元/亿元自适应)。"""
    if value is None:
        return "暂无"
    v = float(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿{unit}"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万{unit}"
    return f"{v:,.2f}{unit}"


def status_badge(ok: bool) -> str:
    """状态徽章文本(绿=正常/红=异常)。"""
    return "🟢 正常" if ok else "🔴 异常"


def pct_color(value: SupportsFloat | None) -> str:
    """涨跌着色：A 股惯例 红涨(>0)/绿跌(<0)/灰(0或None)。"""
    if value is None:
        return COLOR_GRAY
    v = float(value)
    if v > 0:
        return COLOR_RED
    if v < 0:
        return COLOR_GREEN
    return COLOR_GRAY


def pct_text(value: SupportsFloat | None, digits: int = 2) -> str:
    """涨跌文本：带 +/- 符号百分比(0.086 -> +8.60%)。"""
    if value is None:
        return "暂无"
    v = float(value)
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.{digits}f}%"


def level_color(level: str) -> str:
    """诊断等级(g/y/r 或 good/warn/bad) -> 颜色 hex。"""
    return LEVEL_COLOR.get(level, COLOR_GRAY)


def level_emoji(level: str) -> str:
    """诊断等级 -> emoji(原型⑥ 红黄绿状态列)。"""
    return {
        "g": "🟢",
        "y": "🟡",
        "r": "🔴",
        "good": "🟢",
        "ok": "🟢",
        "warn": "🟡",
        "bad": "🔴",
    }.get(level, "⚪")


def level_row(level: str) -> str:
    """诊断状态列文本(原型⑥ diag-r/y/g)：emoji + 中文标签。"""
    label = {
        "good": "正面",
        "ok": "安全",
        "warn": "中性",
        "bad": "负面",
        "g": "均衡",
        "y": "偏低",
        "r": "风险",
    }.get(level, "")
    return f"{level_emoji(level)} {label}"


def color_text(text: str, color: str) -> str:
    """生成带颜色的 markdown span(用于 st.markdown)。

    注意：内容为受控文本(非外部输入)，无需 bleach 净化(§9)。外部内容须先净化。
    """
    safe = text.replace("<", "&lt;").replace(">", "&gt;")
    return f'<span style="color:{color};font-weight:600">{safe}</span>'


def breakeven_need(loss_pct: float) -> float:
    """回本需涨 = |亏损| / (1 + 亏损)(DC-011/BR-10.1；TP-04)。

    亏损为负比率(-0.30 -> +0.4286)。后端权威，前端演示与之一致。
    """
    if loss_pct >= 0:
        return 0.0
    return abs(loss_pct) / (1 + loss_pct)


def weighted_composite(factors: dict[str, Any], weights: dict[str, float]) -> float:
    """五因子加权合成(TP-01 §3.1 weighted_sum)。

    composite = Σ(sub_score_i × weight_i)。权重可调(滑杆)，分位表不变(ADR-002)。
    """
    total = 0.0
    for k, w in weights.items():
        f = factors.get(k)
        if f and "sub_score" in f:
            total += float(f["sub_score"]) * float(w)
    return round(total, 1)


def tooltip(title: str, text: str) -> str:
    """生成 hover tooltip 的 markdown(原型② 字段解释；原生 title 替代)。

    受控文本，转义尖括号。优先用 st 组件 ``help=`` 参数，本函数仅用于表格内联。
    """
    safe_t = title.replace("<", "&lt;")
    safe_x = text.replace("<", "&lt;").replace(">", "&gt;")
    return f'{safe_t}<span title="{safe_x}" style="cursor:help"> ℹ️</span>'


def mock_badge() -> str:
    """示例数据角标文本(后端未就绪时页面顶部提示)。"""
    return "示例数据 · 接口待实现"
