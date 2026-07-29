"""五因子评分单测(P1-03b，详设§3.3.8.1 / TP-01 / DC-003 / §4 红线)。

覆盖：横截面百分位归一化、composite 合成公式、缺失因子剔除、scale_health 非线性(E4)、
货基排除(E5)、因子分解、滑杆调权重重算(ADR-002)。
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.scoring import (
    FACTOR_ORDER,
    SCORE_WEIGHTS,
    compute_composite,
    factor_decomposition,
    manager_excess,
    multi_factor_score,
    percentile_subscore,
    recompute_with_weights,
    scale_health,
)


class TestScaleHealth:
    """§3.3.8.1 scale_health 非线性(E4)。"""

    @pytest.mark.parametrize(
        "aum,expected",
        [
            (100.0, 100.0),  # [2,500] -> 100
            (2.0, 100.0),  # 边界下限
            (500.0, 100.0),  # 边界上限
            (1.0, 50.0),  # <2亿 清盘缓降(1/2*100)
            (0.5, 25.0),  # 更小
            (600.0, 96.0),  # >500 钝化(100-(100/500)*20=96)
            (1000.0, 80.0),  # 下限80
            (None, None),  # 缺失
        ],
    )
    def test_scale_thresholds(self, aum: float | None, expected: float | None) -> None:
        assert scale_health(aum) == expected


class TestManagerExcess:
    def test_excess(self) -> None:
        """§3.3.8.1 manager_excess=任期收益−基准收益(非能力归因)。"""
        assert manager_excess(0.15, 0.08) == pytest.approx(0.07)

    def test_none_on_missing(self) -> None:
        assert manager_excess(None, 0.08) is None
        assert manager_excess(0.15, None) is None


class TestPercentileSubscore:
    """§3.3.8.1 横截面百分位(E5，按 asset_class 分组)。"""

    def test_max_value_gets_100(self) -> None:
        """同类中最大值 -> 子分 100。"""
        uni = pd.Series([0.05, 0.10, 0.15, 0.20])
        assert percentile_subscore(uni, 0.20) == 100.0

    def test_min_value_gets_low(self) -> None:
        uni = pd.Series([0.05, 0.10, 0.15, 0.20])
        # 最小值 0.05：(valid<=0.05)=1，1/4*100=25
        assert percentile_subscore(uni, 0.05) == 25.0

    def test_none_value_returns_none(self) -> None:
        """缺失值 -> None(剔除)。"""
        uni = pd.Series([0.05, 0.10])
        assert percentile_subscore(uni, None) is None

    def test_insufficient_universe(self) -> None:
        """universe<2 -> None。"""
        assert percentile_subscore(pd.Series([0.1]), 0.1) is None


class TestComputeComposite:
    """§3.3.8.1 composite = Σ(w·s)/Σw(缺失因子剔除)。"""

    def test_all_factors_present(self) -> None:
        from domain.scoring import FactorScore

        factors = {
            "ret": FactorScore("ret", 80.0, 20, contrib=1600.0),
            "risk": FactorScore("risk", 70.0, 25, contrib=1750.0),
        }
        # (1600+1750)/(20+25) = 3350/45 = 74.44
        assert compute_composite(factors) == pytest.approx(74.44, abs=0.01)

    def test_missing_factor_excluded(self) -> None:
        """缺失因子 sub_score=None -> 剔除，分母缩小。"""
        from domain.scoring import FactorScore

        factors = {
            "ret": FactorScore("ret", 80.0, 20, contrib=1600.0),
            "risk": FactorScore("risk", None, 25, contrib=None),  # 缺失
        }
        # 仅 ret: 1600/20 = 80
        assert compute_composite(factors) == 80.0

    def test_all_missing_returns_none(self) -> None:
        from domain.scoring import FactorScore

        factors = {
            "ret": FactorScore("ret", None, 20, contrib=None),
            "risk": FactorScore("risk", None, 25, contrib=None),
        }
        assert compute_composite(factors) is None


def _universe() -> dict[str, pd.Series]:
    """构造横截面 universe(同类 4 基金)。"""
    return {
        "ret": pd.Series([0.05, 0.08, 0.12, 0.15]),
        "risk": pd.Series([-0.10, -0.08, -0.05, -0.03]),
        "perf": pd.Series([0.4, 0.6, 0.8, 1.0]),
        "manager": pd.Series([0.01, 0.02, 0.04, 0.06]),
    }


class TestMultiFactorScore:
    """§3.3.8.1 五因子合成 + 货基排除(E5)。"""

    def test_returns_factors_and_composite(self) -> None:
        """返回五因子 + 综合分(0-100)。"""
        nav = pd.Series([1.0 * (1.10 ** (i / 250)) for i in range(252)])
        s = multi_factor_score(
            "000001", nav=nav, aum=100.0, asset_class="equity", universe=_universe()
        )
        assert set(s.factors.keys()) == set(FACTOR_ORDER)
        assert s.composite is not None
        assert 0 <= s.composite <= 100

    def test_money_excluded(self) -> None:
        """E5：货基 composite=None，excluded='money'。"""
        nav = pd.Series([1.0 * (1.02 ** (i / 250)) for i in range(252)])
        s = multi_factor_score("M001", nav=nav, asset_class="money")
        assert s.composite is None
        assert s.excluded == "money"

    def test_weights_default(self) -> None:
        s = multi_factor_score("000001", asset_class="equity")
        assert s.weights == SCORE_WEIGHTS
        assert SCORE_WEIGHTS["ret"] == 20  # E4 降共线权重

    def test_missing_factor_excluded_in_composite(self) -> None:
        """nav 缺失 -> ret/risk/perf 子分 None；仅 scale 有效 -> composite=scale 子分。"""
        s = multi_factor_score("000001", aum=100.0, asset_class="equity", universe=_universe())
        # nav=None：ret/risk/perf 原始值 None -> 子分 None；scale=100
        assert s.factors["ret"]["sub_score"] is None
        assert s.factors["scale"]["sub_score"] == 100.0
        # 仅 scale 有效：(15*100)/15 = 100
        assert s.composite == 100.0


class TestFactorDecomposition:
    def test_returns_contrib(self) -> None:
        nav = pd.Series([1.0 * (1.10 ** (i / 250)) for i in range(252)])
        s = multi_factor_score(
            "000001", nav=nav, aum=100.0, asset_class="equity", universe=_universe()
        )
        decomp = factor_decomposition(s)
        assert "ret" in decomp
        assert all(k in decomp for k in FACTOR_ORDER)


class TestRecomputeWithWeights:
    """ADR-002：滑杆调权后即时重算(分位表不变)。"""

    def test_recompute_changes_composite(self) -> None:
        nav = pd.Series([1.0 * (1.10 ** (i / 250)) for i in range(252)])
        s = multi_factor_score(
            "000001", nav=nav, aum=100.0, asset_class="equity", universe=_universe()
        )
        # 加大 ret 权重
        new_w = dict(SCORE_WEIGHTS)
        new_w["ret"] = 50
        new_composite = recompute_with_weights(s, new_w)
        assert new_composite is not None
        # sub_score 不变，仅权重变 -> composite 应改变
        assert new_composite != s.composite or s.composite is None
