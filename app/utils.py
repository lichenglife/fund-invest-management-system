"""utils · 纯函数(格式化/计算，开发规范§2.2 utils.py)。

无 Streamlit 依赖，便于单测与复用。
"""

from __future__ import annotations

from typing import SupportsFloat


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
    """状态徽章文本(红绿，A股红涨绿跌惯例用于涨跌；这里状态用绿=正常/红=异常)。"""
    return "🟢 正常" if ok else "🔴 异常"
