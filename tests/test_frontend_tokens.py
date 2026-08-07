"""前端令牌一致性(CR-20260806-01 · 红涨绿跌语义锁)。

锁定全局唯一的涨跌配色语义，并防止令牌/常量漂移回到「翠绿=正」矛盾：
- utils.COLOR_GAIN == 红，COLOR_LOSS == 绿
- pct_color(>0)=红、pct_color(<0)=绿
- style.css 定义 --color-gain / --color-loss 且值与常量对齐(单一权威源)
- 页面/组件内联硬色码全部收敛为 var(--token) 引用(除 utils.py 合法令牌源)
- 分数/等级走状态色(LEVEL_COLOR)，与红涨绿跌涨跌语义区分
- style.css 补齐 warn-border / brand-border / surface-2 / neutral-bg 令牌
"""

from __future__ import annotations

import re
from pathlib import Path

from app import utils

CSS_PATH = Path(__file__).resolve().parents[1] / "app" / "static" / "style.css"
APP_DIR = Path(__file__).resolve().parents[1] / "app"
HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,6}\b")


def test_gain_loss_semantics_red_up_green_down() -> None:
    """红涨绿跌：涨/正=红，跌/负=绿(对齐原型§5)。"""
    assert utils.COLOR_GAIN == utils.COLOR_RED
    assert utils.COLOR_LOSS == utils.COLOR_GREEN
    assert utils.COLOR_GAIN.upper() == "#E23B3B"
    assert utils.COLOR_LOSS.upper() == "#16A34A"


def test_pct_color_alignment() -> None:
    """pct_color 全局唯一遵循红涨绿跌。"""
    assert utils.pct_color(0.1) == utils.COLOR_GAIN
    assert utils.pct_color(-0.1) == utils.COLOR_LOSS
    assert utils.pct_color(0) == utils.COLOR_GRAY
    assert utils.pct_color(None) == utils.COLOR_GRAY


def test_css_tokens_define_gain_loss() -> None:
    """style.css 为唯一权威源，定义涨跌语义令牌且与常量值对齐。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "--color-gain:" in css
    assert "--color-loss:" in css
    assert "#E23B3B" in css  # 涨=红
    assert "#16A34A" in css  # 跌=绿


def test_css_tokens_define_new_surfaces() -> None:
    """style.css 补齐收敛所需的表面/边框令牌。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    for tok in ("--warn-border", "--brand-border", "--surface-2", "--neutral-bg"):
        assert f"{tok}:" in css, f"style.css 缺少令牌 {tok}"


def test_level_color_status_semantics() -> None:
    """分数/等级走状态色(LEVEL_COLOR)，与红涨绿跌涨跌语义区分。

    good/ok=品牌绿、warn=琥珀、bad=红；good 不等于涨(红)，证明评分语义与
    价格涨跌语义已绝缘(score_panel 据此着色，避免绿=跌误读)。
    """
    assert utils.LEVEL_COLOR["good"] == utils.COLOR_GREEN
    assert utils.LEVEL_COLOR["ok"] == utils.COLOR_GREEN
    assert utils.LEVEL_COLOR["warn"] == utils.COLOR_AMBER
    assert utils.LEVEL_COLOR["bad"] == utils.COLOR_RED
    # 关键隔离：状态绿(good) 不是 涨红
    assert utils.LEVEL_COLOR["good"] != utils.COLOR_GAIN


def test_no_inline_hex_outside_utils() -> None:
    """页面/组件内联硬色码必须收敛为 var(--token) 引用(仅 utils.py 为合法令牌源)。"""
    offenders: dict[str, list[str]] = {}
    for p in sorted(APP_DIR.rglob("*.py")):
        if p.name == "utils.py":
            continue
        text = p.read_text(encoding="utf-8")
        hits = HEX_RE.findall(text)
        if hits:
            offenders[str(p.relative_to(APP_DIR))] = hits
    assert not offenders, f"仍存在游离硬色码: {offenders}"


def test_a11y_skip_link_and_focus_ring() -> None:
    """A11y 基线：跳转链接 / 焦点可见 / 减弱动效适配存在(CSS · AA)。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert ".fl-skip-link" in css, "缺少跳转链接样式"
    assert ":focus-visible" in css, "缺少焦点可见样式(AA)"
    assert "prefers-reduced-motion" in css, "缺少减弱动效适配"


def test_responsive_grid_and_viewport_bridge() -> None:
    """响应式：auto-fit 网格 + 视口桥断点规则存在(CSS)。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert ".fl-grid" in css, "缺少响应式网格容器"
    assert "repeat(auto-fit" in css, "fl-grid 未使用 auto-fit 回流"
    assert '[data-fl-view="sm"]' in css, "缺少手机端视口桥规则"
    assert "#main-content:focus" in css, "缺少跳转目标焦点清理"


def test_ui_responsive_infra_present() -> None:
    """ui 提供视口桥与响应式网格，且表头注入跳转链接+地标(Python 侧 · 免 import)。"""
    ui_src = (APP_DIR / "components" / "ui.py").read_text(encoding="utf-8")
    assert "inject_responsive_bridge" in ui_src, "ui 缺少视口桥函数"
    assert "kpi_grid" in ui_src, "ui 缺少响应式网格函数"
    assert "data-fl-view" in ui_src, "inject_responsive_bridge 未写入视口属性"
    assert "fl-skip-link" in ui_src, "page_header 未注入跳转链接"
    assert 'id="main-content"' in ui_src, "page_header 未注入无障碍地标"


def test_kpi_card_html_exported() -> None:
    """kpi_card_html 已抽离为可拼接的 HTML 字符串(供 kpi_grid 使用)。"""
    src = (APP_DIR / "components" / "kpi_card.py").read_text(encoding="utf-8")
    assert "def kpi_card_html" in src, "kpi_card 未抽离 HTML 生成"
    assert '"kpi_card_html"' in src, "__all__ 未导出 kpi_card_html"
    assert "fl-kpi-card" in src, "kpi_card_html 未产出 fl-kpi-card 容器"
