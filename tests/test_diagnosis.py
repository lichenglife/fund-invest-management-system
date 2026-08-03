"""组合诊断单测(P1-08b，详设§3.6.6.1 / TP-03 §4 / E8/E9/E12 红线)。

覆盖：
- E8 股债维：目标仓位由 risk_type 推导(保守20-40/稳健40-60/进取60-80)，偏离即红。
- 海外维：合计>40% 黄。
- E9 个基维：止损红线(相对基准超额<-15% 或 回撤>30%)红；止盈软提示黄。
- E12 个基维：综合费率>2.0% 黄。
- 整体评级合成：任一红->红，任一黄->黄，否则绿。
- 再平衡：偏离目标中点 >5% 触发。
- 无 fund_metrics/无 fund_types 的降级(待指标数据 -> green，不崩溃)。
"""

from __future__ import annotations

from domain.diagnosis import (
    ASSET_TARGET,
    GREEN,
    REBALANCE_DRIFT,
    RED,
    THRESHOLDS,
    YELLOW,
    diagnose,
)


class TestAssetDim:
    """E8：股债目标仓位由 risk_type 推导。"""

    def test_moderate_within_range_is_green(self) -> None:
        """稳健 40-60% 区间内 -> 绿。"""
        weights = {"A": 0.5}
        report = diagnose("p1", weights, fund_types={"A": "stock"}, risk_type="moderate")
        assert report.per_dim["asset"]["status"] == GREEN

    def test_conservative_overweight_is_red(self) -> None:
        """保守型权益 70% 超出 20-40% 上限 -> 红(E8)。"""
        weights = {"A": 0.7, "B": 0.3}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="conservative"
        )
        assert report.per_dim["asset"]["status"] == RED
        assert report.rating == RED  # 任一红 -> 整体红

    def test_aggressive_underweight_is_red(self) -> None:
        """进取型权益 30% 低于 60-80% 下限 -> 红(E8)。"""
        weights = {"A": 0.3, "B": 0.7}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="aggressive"
        )
        assert report.per_dim["asset"]["status"] == RED

    def test_target_ranges_match_spec(self) -> None:
        """E8 口径：保守20-40 / 稳健40-60 / 进取60-80。"""
        assert ASSET_TARGET["conservative"] == (0.2, 0.4)
        assert ASSET_TARGET["moderate"] == (0.4, 0.6)
        assert ASSET_TARGET["aggressive"] == (0.6, 0.8)

    def test_unknown_risk_type_falls_back_to_moderate(self) -> None:
        """未定义 risk_type -> 稳健区间(不崩溃)。"""
        weights = {"A": 0.5}
        report = diagnose("p1", weights, fund_types={"A": "stock"}, risk_type="unknown")
        assert report.per_dim["asset"]["status"] == GREEN


class TestOverseasDim:
    """海外维(§3.2)。"""

    def test_overseas_within_limit_is_green(self) -> None:
        weights = {"A": 0.3, "B": 0.7}
        report = diagnose(
            "p1", weights, fund_types={"A": "qdii", "B": "bond"}, risk_type="moderate"
        )
        assert report.per_dim["overseas"]["status"] == GREEN

    def test_overseas_over_40_is_yellow(self) -> None:
        """海外合计 >40% -> 黄。"""
        weights = {"A": 0.5, "B": 0.5}
        report = diagnose(
            "p1", weights, fund_types={"A": "qdii", "B": "qdii"}, risk_type="moderate"
        )
        assert report.per_dim["overseas"]["status"] == YELLOW


class TestSingleFundDim:
    """E9/E12：个基维。"""

    def test_no_metrics_is_green(self) -> None:
        """无 fund_metrics -> 待指标数据，不崩溃且为绿。"""
        weights = {"A": 1.0}
        report = diagnose("p1", weights, fund_types={"A": "stock"}, risk_type="moderate")
        assert report.per_dim["single"]["status"] == GREEN
        assert report.per_dim["single"]["metrics"]["available"] is False

    def test_e9_excess_loss_triggers_red(self) -> None:
        """E9：相对基准超额<-15% -> 止损红线。"""
        weights = {"A": 1.0}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock"},
            risk_type="moderate",
            fund_metrics={"A": {"excess": -0.20}},  # -20% < -15%
        )
        assert report.per_dim["single"]["status"] == RED
        assert report.per_dim["single"]["metrics"]["red_count"] == 1

    def test_e9_max_drawdown_triggers_red(self) -> None:
        """E9：回撤>30% -> 止损红线。"""
        weights = {"A": 1.0}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock"},
            risk_type="moderate",
            fund_metrics={"A": {"max_drawdown": 0.45}},  # 45% > 30%
        )
        assert report.per_dim["single"]["status"] == RED

    def test_e9_boundary_excess_not_red(self) -> None:
        """E9 边界：超额=-0.15 不触发(严格小于)。"""
        weights = {"A": 1.0}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock"},
            risk_type="moderate",
            fund_metrics={"A": {"excess": -0.15}},  # 等于阈值，不触发红
        )
        assert report.per_dim["single"]["status"] == GREEN

    def test_e12_fee_over_threshold_is_yellow(self) -> None:
        """E12：综合费率>2.0% -> 黄。"""
        weights = {"A": 1.0}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock"},
            risk_type="moderate",
            fund_metrics={"A": {"fee_rate": 0.025}},  # 2.5% > 2.0%
        )
        assert report.per_dim["single"]["status"] == YELLOW

    def test_profit_soft_hint_is_yellow(self) -> None:
        """E9：收益>30% 止盈软提示 -> 黄(不硬止盈)。"""
        weights = {"A": 1.0}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock"},
            risk_type="moderate",
            fund_metrics={"A": {"return": 0.35}},
        )
        assert report.per_dim["single"]["status"] == YELLOW

    def test_scale_bloat_is_yellow(self) -> None:
        """规模>500亿 臃肿 -> 黄。"""
        weights = {"A": 1.0}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock"},
            risk_type="moderate",
            fund_metrics={"A": {"scale": 600.0}},
        )
        assert report.per_dim["single"]["status"] == YELLOW


class TestOverallRating:
    """整体评级合成(TP-03 §4)。"""

    def test_any_red_makes_red(self) -> None:
        """任一维红 -> 整体红。"""
        weights = {"A": 0.7, "B": 0.3}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="conservative"
        )
        assert report.rating == RED

    def test_any_yellow_makes_yellow(self) -> None:
        """仅黄无红 -> 整体黄(权益在区间内，海外超限)。"""
        # moderate 40-60%：A=stock 50% 在区间 -> 资产绿；B=qdii 50% 海外 -> 黄
        weights = {"A": 0.5, "B": 0.5}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock", "B": "qdii"},
            risk_type="moderate",
        )
        assert report.per_dim["asset"]["status"] == GREEN
        assert report.per_dim["overseas"]["status"] == YELLOW
        assert report.rating == YELLOW

    def test_all_green(self) -> None:
        """均衡组合 -> 整体绿。"""
        weights = {"A": 0.5, "B": 0.5}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="moderate"
        )
        assert report.rating == GREEN

    def test_red_dominates_yellow(self) -> None:
        """红+黄同时存在 -> 红(红优先)。"""
        # conservative 20-40%：A=stock 50% 越上限 -> 红；B=qdii 50% 海外 -> 黄
        weights = {"A": 0.5, "B": 0.5}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock", "B": "qdii"},
            risk_type="conservative",
        )
        assert report.per_dim["asset"]["status"] == RED
        assert report.per_dim["overseas"]["status"] == YELLOW
        assert report.rating == RED


class TestRebalance:
    """再平衡提醒(§5：偏离>5% 触发)。"""

    def test_drift_triggers_rebalance(self) -> None:
        """偏离目标中点>5% -> 触发再平衡。"""
        # 稳健中点 50%，权益 30% -> 偏离 20% > 5%
        weights = {"A": 0.3, "B": 0.7}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="moderate"
        )
        assert len(report.rebalance) >= 1
        assert report.rebalance[0]["dim"] == "asset"

    def test_no_drift_no_rebalance(self) -> None:
        """权益恰在目标中点 -> 不触发。"""
        # 稳健中点 50%，权益 50%
        weights = {"A": 0.5, "B": 0.5}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="moderate"
        )
        assert report.rebalance == []

    def test_rebalance_drift_threshold(self) -> None:
        """阈值 = 5%(REBALANCE_DRIFT)。"""
        assert REBALANCE_DRIFT == 0.05


class TestSmoke:
    """冒烟：均衡/失衡组合。"""

    def test_balanced_portfolio_green(self) -> None:
        """均衡稳健组合 -> 绿(冒烟)。"""
        weights = {"A": 0.3, "B": 0.3, "C": 0.4}
        report = diagnose(
            "p1",
            weights,
            fund_types={"A": "stock", "B": "stock", "C": "bond"},
            risk_type="moderate",
        )
        assert report.rating == GREEN
        # 报告可序列化
        d = report.to_dict()
        assert d["portfolio_id"] == "p1"
        assert set(d["per_dim"]) == {"asset", "overseas", "industry", "style", "single"}

    def test_equity_heavy_conservative_red(self) -> None:
        """偏股保守型 -> 红(冒烟)。"""
        weights = {"A": 0.8, "B": 0.2}
        report = diagnose(
            "p1", weights, fund_types={"A": "stock", "B": "bond"}, risk_type="conservative"
        )
        assert report.rating == RED


class TestThresholds:
    """E9/E12 阈值口径对齐(§4 红线)。"""

    def test_e9_excess_threshold(self) -> None:
        assert THRESHOLDS["single_excess_loss"] == -0.15

    def test_e9_drawdown_threshold(self) -> None:
        assert THRESHOLDS["single_max_drawdown"] == 0.30

    def test_e12_fee_threshold(self) -> None:
        assert THRESHOLDS["single_fee_max"] == 0.02
