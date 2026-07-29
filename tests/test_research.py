"""PEG/ERP 代理 + 守卫单测(P1-03d，详设§3.3.7 / TP-01 §3.4 / E7/E10 / §4.2)。

覆盖：守卫关闭返 None、PE≤0 剔除(E7)、growth 越界剔除(E7)、大/小盘 7:3 加权(E10)、
债基返 None、持仓缺失回退基准/available=False、卡片"(代理)"标注与 unavailable 不显示数值。
"""

from __future__ import annotations

import pytest

from domain.research import (
    ERP_LARGE_WEIGHT,
    ERP_SMALL_WEIGHT,
    PEG_GROWTH_MAX,
    PEG_GROWTH_MIN,
    PROXY_NOTE,
    PROXY_SUFFIX,
    RESEARCH_PROXY_GUARD,
    UNAVAILABLE_MSG,
    ERPResult,
    ProxyResult,
    erp_proxy,
    peg_proxy,
    research_metrics_cards,
)


def _holdings() -> list[dict[str, object]]:
    """两只股持仓(大盘 A / 小盘 B)。"""
    return [
        {"stock": "A", "weight": 0.6, "pe": 20, "growth": 10, "ey": 0.05, "style": "large"},
        {"stock": "B", "weight": 0.4, "pe": 15, "growth": 5, "ey": 0.08, "style": "small"},
    ]


class TestPegProxy:
    """§3.3.7 / E7 PEG 代理。"""

    def test_weighted_peg(self) -> None:
        """PEG = Σ(w×PE/growth) = 0.6×2.0 + 0.4×3.0 = 2.4。"""
        p = peg_proxy("mixed", _holdings())
        assert p.available is True
        assert p.value == pytest.approx(2.4)
        assert p.is_proxy is True
        assert p.name_suffix == PROXY_SUFFIX

    def test_exclude_pe_le_zero(self) -> None:
        """E7：PE≤0(亏损)个股剔除，不置0。"""
        hp = _holdings() + [
            {"stock": "C", "weight": 0.3, "pe": -5, "growth": 10, "ey": 0.0, "style": "large"}
        ]
        p = peg_proxy("mixed", hp)
        assert p.value == pytest.approx(2.4)  # 亏损股被剔除，PEG 不变

    def test_exclude_growth_out_of_range(self) -> None:
        """E7：growth 越界(<=0 或 >=100)剔除。"""
        hp = _holdings() + [
            {
                "stock": "C",
                "weight": 0.3,
                "pe": 20,
                "growth": 0,
                "ey": 0.0,
                "style": "large",
            },  # <=0
            {
                "stock": "D",
                "weight": 0.3,
                "pe": 20,
                "growth": 100,
                "ey": 0.0,
                "style": "large",
            },  # >=100
        ]
        p = peg_proxy("mixed", hp)
        assert p.value == pytest.approx(2.4)

    def test_bond_returns_none(self) -> None:
        """债基无 PEG 代理。"""
        p = peg_proxy("bond", _holdings())
        assert p.available is False
        assert p.value is None

    def test_holdings_missing_fallback_benchmark(self) -> None:
        """持仓缺失 -> 回退跟踪基准(§3.3.7)。"""
        bench = _holdings()
        p = peg_proxy("mixed", holdings=None, benchmark_holdings=bench)
        assert p.available is True
        assert p.value == pytest.approx(2.4)
        assert p.source == "benchmark_fallback"

    def test_holdings_missing_all_unavailable(self) -> None:
        """持仓与基准皆缺 -> available=False，绝不硬算(§3.3.7)。"""
        p = peg_proxy("mixed", holdings=None, benchmark_holdings=None)
        assert p.available is False
        assert p.value is None

    def test_all_invalid_pe_unavailable(self) -> None:
        """全部 PE≤0 -> 无可用个股 -> available=False。"""
        hp = [{"stock": "A", "weight": 1.0, "pe": -5, "growth": 10, "ey": 0.0, "style": "large"}]
        p = peg_proxy("mixed", hp)
        assert p.available is False

    def test_growth_bounds(self) -> None:
        """E7 growth 范围常量(0<g<100)。"""
        assert PEG_GROWTH_MIN == 0.0
        assert PEG_GROWTH_MAX == 100.0


class TestErpProxy:
    """§3.3.7 / E10 ERP 代理(拆大/小盘 7:3)。"""

    def test_split_large_small(self) -> None:
        """ERP 大/小盘分别 = EY − rf。"""
        e = erp_proxy("mixed", _holdings(), rf_rate=0.025)
        assert e.ey_large == pytest.approx(0.05)
        assert e.ey_small == pytest.approx(0.08)
        assert e.large == pytest.approx(0.05 - 0.025)  # 0.025
        assert e.small == pytest.approx(0.08 - 0.025)  # 0.055

    def test_weighted_7_3(self) -> None:
        """E10：大/小盘加权 7:3。"""
        e = erp_proxy("mixed", _holdings(), rf_rate=0.025)
        expected = 0.025 * ERP_LARGE_WEIGHT + 0.055 * ERP_SMALL_WEIGHT
        assert e.weighted == pytest.approx(expected)
        assert ERP_LARGE_WEIGHT == 0.7
        assert ERP_SMALL_WEIGHT == 0.3

    def test_bond_returns_none(self) -> None:
        e = erp_proxy("bond", _holdings(), rf_rate=0.025)
        assert e.available is False

    def test_holdings_missing_unavailable(self) -> None:
        e = erp_proxy("mixed", None, rf_rate=0.025, benchmark_holdings=None)
        assert e.available is False

    def test_only_large_available(self) -> None:
        """仅大盘可得 -> weighted=大盘值。"""
        hp = [{"stock": "A", "weight": 1.0, "ey": 0.06, "style": "large"}]
        e = erp_proxy("mixed", hp, rf_rate=0.025)
        assert e.large is not None
        assert e.small is None
        assert e.weighted == pytest.approx(0.06 - 0.025)


class TestGuard:
    """§3.3.7 RESEARCH_PROXY_GUARD 守卫。"""

    def test_guard_blocked_returns_none(self) -> None:
        """守卫开启且口径未定义(模拟) -> peg/erp 一律 None(防 naive)。"""
        # guard=True 但模拟口径未定义：通过 monkeypatch _guard_passed=False
        import domain.research as rmod

        original = rmod._guard_passed
        rmod._guard_passed = lambda: False  # type: ignore[assignment]
        try:
            p = peg_proxy("mixed", _holdings(), guard=True)
            assert p.value is None
            assert p.available is False
            assert p.method == "guard_blocked"
            e = erp_proxy("mixed", _holdings(), rf_rate=0.025, guard=True)
            assert e.available is False
            assert e.method == "guard_blocked"
        finally:
            rmod._guard_passed = original  # type: ignore[assignment]

    def test_guard_flag_default_true(self) -> None:
        """§3.3.7 守卫默认开启。"""
        assert RESEARCH_PROXY_GUARD is True


class TestMetricCards:
    """§3.3.7 研究指标卡片(代理标注 + unavailable 不显示数值)。"""

    def test_peg_card_has_proxy_suffix(self) -> None:
        """PEG 卡 name 带"(代理)"。"""
        p = peg_proxy("mixed", _holdings())
        e = erp_proxy("mixed", _holdings(), rf_rate=0.025)
        cards = research_metrics_cards(p, e)
        peg_card = next(c for c in cards if "PEG" in c.name)
        assert PROXY_SUFFIX in peg_card.name
        assert PROXY_NOTE in peg_card.interpretation

    def test_erp_card_proxy_note(self) -> None:
        p = peg_proxy("mixed", _holdings())
        e = erp_proxy("mixed", _holdings(), rf_rate=0.025)
        cards = research_metrics_cards(p, e)
        erp_card = next(c for c in cards if "ERP" in c.name)
        assert PROXY_SUFFIX in erp_card.name
        assert "7:3" in erp_card.interpretation

    def test_unavailable_shows_no_value(self) -> None:
        """available=False -> 卡片 value=None + 显示"数据不足/代理值待定"(硬性约束)。"""
        p = ProxyResult(value=None, method="holdings_missing", available=False)
        e = ERPResult(available=False, method="holdings_missing")
        cards = research_metrics_cards(p, e)
        for card in cards[:2]:  # PEG/ERP 卡
            assert card.value is None
            assert card.available is False
            assert UNAVAILABLE_MSG in card.interpretation

    def test_threshold_coloring(self) -> None:
        """阈值着色(DC-003)：PEG<=1 偏低(ok)，>1 偏高。

        注：ERP 阈值与值单位需一致(技术规格 erp=3.0 为相对高低提示线)。
        """
        p = ProxyResult(value=0.8, method="holdings_weighted", available=True)  # PEG 低
        # ERP 用与阈值同量级的值(4.0>=3.0 -> ok)
        e = ERPResult(weighted=4.0, available=True, large=4.0, small=4.0)
        cards = research_metrics_cards(p, e)
        peg_card = next(c for c in cards if "PEG" in c.name)
        assert peg_card.threshold_ok is True  # PEG 0.8<=1.0
        erp_card = next(c for c in cards if "ERP" in c.name)
        assert erp_card.threshold_ok is True  # 4.0>=3.0
