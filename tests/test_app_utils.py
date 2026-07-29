"""utils 纯函数单测(开发规范§2.2；详设§2.21.1 / DC-011 回本公式)。"""

from __future__ import annotations

import pytest

from app import utils


class TestFormat:
    def test_format_pct(self) -> None:
        assert utils.format_pct(0.1234) == "12.34%"
        assert utils.format_pct(0.0) == "0.00%"
        assert utils.format_pct(None) == "暂无"

    def test_format_pct_digits(self) -> None:
        assert utils.format_pct(0.123456, digits=4) == "12.3456%"

    def test_format_amount(self) -> None:
        assert utils.format_amount(12345) == "1.23万元"
        assert utils.format_amount(1.2e8) == "1.20亿元"
        assert utils.format_amount(None) == "暂无"

    def test_pct_text_sign(self) -> None:
        assert utils.pct_text(0.086) == "+8.60%"
        assert utils.pct_text(-0.155) == "-15.50%"
        assert utils.pct_text(None) == "暂无"


class TestColors:
    def test_pct_color_a_share(self) -> None:
        # A 股惯例：红涨绿跌
        assert utils.pct_color(0.01) == utils.COLOR_RED
        assert utils.pct_color(-0.01) == utils.COLOR_GREEN
        assert utils.pct_color(0) == utils.COLOR_GRAY

    def test_level_color(self) -> None:
        assert utils.level_color("good") == utils.COLOR_GREEN
        assert utils.level_color("warn") == utils.COLOR_AMBER
        assert utils.level_color("bad") == utils.COLOR_RED

    def test_level_emoji(self) -> None:
        assert utils.level_emoji("g") == "🟢"
        assert utils.level_emoji("r") == "🔴"

    def test_color_text_escapes(self) -> None:
        # 受控文本转义尖括号(§9)
        out = utils.color_text("<script>", utils.COLOR_RED)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


class TestBreakeven:
    """回本公式：回本需涨 = |亏损| / (1 + 亏损)（DC-011/BR-10.1）。"""

    @pytest.mark.parametrize(
        "loss,expect",
        [
            (-0.30, 0.42857142857142855),  # -30% -> +42.86%(原型取值)
            (-0.155, 0.18343195266272194),  # -15.5% -> +18.34%(原型⑤)
            (-0.50, 1.0),  # -50% -> +100%
            (0.0, 0.0),  # 未亏损无需回本
            (0.10, 0.0),
        ],
    )
    def test_breakeven_need(self, loss: float, expect: float) -> None:
        assert utils.breakeven_need(loss) == pytest.approx(expect)


class TestWeightedComposite:
    """五因子加权合成(TP-01 §3.1 weighted_sum)。"""

    def test_weighted_sum(self) -> None:
        factors = {
            "ret": {"sub_score": 84},
            "risk": {"sub_score": 78},
            "perf": {"sub_score": 86},
            "scale": {"sub_score": 74},
            "manager": {"sub_score": 92},
        }
        # 0.30*84+0.25*78+0.20*86+0.15*74+0.10*92 = 82.2
        assert (
            utils.weighted_composite(
                factors,
                {
                    "ret": 0.30,
                    "risk": 0.25,
                    "perf": 0.20,
                    "scale": 0.15,
                    "manager": 0.10,
                },
            )
            == 82.2
        )

    def test_weighted_composite_missing_factor(self) -> None:
        # 缺因子不影响(跳过)
        assert (
            utils.weighted_composite({"ret": {"sub_score": 100}}, {"ret": 0.5, "risk": 0.5}) == 50.0
        )
