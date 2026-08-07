"""风格箱(九宫格 size × value_growth)(P1-03b，详设§3.3.1 / TP-01 §3.5 / 闭合 E13 / DC-003)。

九宫格 = 持仓市值分布定 ``size`` + 估值/成长因子定 ``value_growth``，
并用历史收益对价值/成长因子做回归交叉验证(回归载荷与持仓法不一致 -> ``cv_flag=True``)。

口径(详设§3.3.1 / TP-01 §3.5)：
- ``size`` ∈ {大盘, 中盘, 小盘}，由持仓加权市值判定。
- ``value_growth`` ∈ {价值, 平衡, 成长}，由持仓加权盈利增速(成长倾斜)判定，
  PE 作为价值佐证因子一并披露(低 PE 偏价值)。
- 回归交叉验证固定窗口 = 3y(与因子同窗口)，披露 ``reg_window``；窗口外不外推。
- **E13(闭合)**：仅权益类(``stock``/``mixed``/``index``/``etf``)适用；
  债/货/QDII/另类不显示风格箱。载荷不显著(``|load|<0.3`` 且 ``p>0.1``)时 ``cv_flag=True``。

数据依赖与回退(同 PEG/ERP 代理范式，§3.3.7)：
持仓法需个股 ``market_cap``/``pe``/``growth``；缺失时按回退链降级，绝不硬算：

1. **持仓法**(主)：holdings 含 ``market_cap``/``pe``/``growth`` -> 计算两轴(method=``holdings``)。
2. **基金披露风格**(回退)：``fund_style`` 形如"大盘价值" -> 解析两轴(method=``fund_declared``,
   ``is_proxy=True``，披露口径非持仓计算)。前向兼容 P1-02 采集填充 ``fund.style``。
3. **持仓缺基本面**(回退)：holdings 在但无 market_cap/pe/growth -> ``available=False``。
4. **无持仓**(回退)：holdings 缺失 -> ``available=False``。

阈值(初值，待 ``SENSITIVITY_TEST`` 校准后写正式版，同 ERP 大/小盘权重初值口径)：
- 市值分界(亿)：大盘 ≥ 1000，中盘 300–1000，小盘 < 300。
- 成长倾斜分界(%)：成长 ≥ 25，价值 ≤ 10，平衡其间。

> 守卫开关 ``STYLEBOX_GUARD``：口径未定义前一律 None，杜绝 naive 计算(对齐 §3.3.7 守卫语义)。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

#: 守卫开关(§3.3.7 语义)。开启后口径未定义前一律 None，防 naive。
STYLEBOX_GUARD: bool = True

#: 权益类适用类型(E13：仅权益类；债/货/QDII/另类不显示)。
#: index/etf 跟踪权益指数视为权益口径(与 diagnosis EQUITY_TYPES 一致)；QDII 即便含权益亦按 E13 不显示。
STYLEBOX_SCOPE: list[str] = ["stock", "mixed", "index", "etf"]

#: 回归交叉验证固定窗口(与因子同窗口，E13，默认 3y)。
REG_WINDOW = "3y"

#: 载荷显著性阈值(E13：|load|<0.3 且 p>0.1 -> 不显著 -> cv_flag=True)。
LOAD_SIGNIFICANCE = 0.3
#: p>0.1 近似为 |t|<1.645(双侧，大样本；statsmodels 未安装，用 t 近似)。
T_P010 = 1.645

#: 市值分界(亿，初值，待 SENSITIVITY_TEST 校准)。
LARGE_CAP_MIN = 1000.0
MID_CAP_MIN = 300.0

#: 成长倾斜分界(%，初值，待 SENSITIVITY_TEST 校准)。
GROWTH_HIGH = 25.0
GROWTH_LOW = 10.0

#: PEG/成长越界判定(对齐 E7 / research.PEG_GROWTH，剔除异常增长)。
GROWTH_MIN = 0.0
GROWTH_MAX = 100.0

#: 中文 token(对齐 managers.style_box_size/vg 存储 + components.style_box 渲染)。
SIZE_LARGE, SIZE_MID, SIZE_SMALL = "大盘", "中盘", "小盘"
VG_VALUE, VG_BALANCED, VG_GROWTH = "价值", "平衡", "成长"

#: 数据不足/代理值待定文案(对齐 research.UNAVAILABLE_MSG)。
UNAVAILABLE_MSG = "数据不足/风格箱待定"

#: size -> value_growth 中文 token 映射(基金披露风格解析用)。
_SIZE_TOKENS = {SIZE_LARGE, SIZE_MID, SIZE_SMALL}
_VG_TOKENS = {VG_VALUE, VG_BALANCED, VG_GROWTH}


@dataclass(frozen=True)
class StyleBoxResult:
    """风格箱结果(§3.3.1 / TP-01 §3.5 / E13)。

    Attributes:
        size: 市值风格(大盘/中盘/小盘)；None 表示不可得。
        value_growth: 价值/成长风格(价值/平衡/成长)；None 表示不可得。
        available: 两轴均判定为 True；False 时禁止展示九宫格定位。
        cv_flag: 回归交叉验证标志。True=持仓法与回归不一致或载荷不显著(前端提示)；
            False=一致；None=未做回归(因子收益缺失)。
        method: 判定方法(holdings/fund_declared/holdings_fundamentals_missing/...)。
        reg_window: 回归窗口(固定 3y，E13 披露)。
        is_proxy: True=披露口径代理(基金披露风格)，非持仓计算。
        as_of: 数据截至。
        source: 数据来源。
        metrics: 透明披露的中间量(weighted_market_cap/weighted_pe/weighted_growth/reg_loadings)。
    """

    size: str | None = None
    value_growth: str | None = None
    available: bool = False
    cv_flag: bool | None = None
    method: str = "uninitialized"
    reg_window: str = REG_WINDOW
    is_proxy: bool = False
    as_of: str | None = None
    source: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "value_growth": self.value_growth,
            "available": self.available,
            "cv_flag": self.cv_flag,
            "method": self.method,
            "reg_window": self.reg_window,
            "is_proxy": self.is_proxy,
            "as_of": self.as_of,
            "source": self.source,
            "metrics": self.metrics,
        }


def style_box(
    fund_type: str,
    holdings: list[dict[str, Any]] | None,
    *,
    fund_style: str | None = None,
    benchmark_holdings: list[dict[str, Any]] | None = None,
    factor_returns: dict[str, list[float]] | None = None,
    fund_returns: list[float] | None = None,
    as_of: str | None = None,
    guard: bool = STYLEBOX_GUARD,
) -> StyleBoxResult:
    """风格箱九宫格判定(§3.3.1 / TP-01 §3.5 / E13)。

    Args:
        fund_type: 基金类型(非权益类 -> available=False，E13)。
        holdings: 持仓快照 ``[{"stock","weight","market_cap","pe","growth"}]``，
            market_cap(亿)/pe/growth 可缺。
        fund_style: 基金披露风格(如"大盘价值")；持仓法缺基本面时回退解析。
        benchmark_holdings: 跟踪基准持仓(持仓缺失回退用，对齐 PEG/ERP)。
        factor_returns: 价值/成长因子收益序列 ``{"value":[...],"growth":[...]}``(回归 CV 用)。
        fund_returns: 基金历史收益序列(与 factor_returns 同长，回归 CV 用)。
        as_of: 数据截至。
        guard: 守卫开关；True 且口径未定义时一律 None。
    Returns:
        StyleBoxResult；按回退链降级，绝不硬算。
    """
    # 守卫：口径未定义前一律 None(§3.3.7 语义，防 naive)
    if guard and not _guard_passed():
        return StyleBoxResult(method="guard_blocked", as_of=as_of)

    # E13：非权益类不显示风格箱
    if fund_type not in STYLEBOX_SCOPE:
        return StyleBoxResult(method="type_not_applicable", as_of=as_of)

    # 持仓缺失 -> 回退跟踪基准(对齐 PEG/ERP)
    source = "holdings"
    hp = holdings
    if not hp:
        hp = benchmark_holdings
        source = "benchmark_fallback"

    # ---- 主：持仓法 ----
    size, vg, metrics = _holdings_method(hp) if hp else (None, None, {})
    if size is not None and vg is not None:
        result = StyleBoxResult(
            size=size,
            value_growth=vg,
            available=True,
            method="holdings",
            as_of=as_of,
            source=source,
            metrics=metrics,
        )
        return _apply_regression(result, factor_returns, fund_returns)

    # ---- 回退 1：基金披露风格 ----
    if fund_style:
        decl_size, decl_vg = _parse_declared_style(fund_style)
        if decl_size is not None and decl_vg is not None:
            return StyleBoxResult(
                size=decl_size,
                value_growth=decl_vg,
                available=True,
                cv_flag=None,
                method="fund_declared",
                is_proxy=True,
                as_of=as_of,
                source="fund_declared_style",
                metrics={**metrics, "declared_style": fund_style},
            )

    # ---- 回退 2/3：基本面缺失 / 无持仓 ----
    if hp:
        method = "holdings_fundamentals_missing"
        metrics = {**metrics, "available": False}
    else:
        method = "holdings_missing"
        metrics = {}
    return StyleBoxResult(
        size=None,
        value_growth=None,
        available=False,
        method=method,
        as_of=as_of,
        source=source,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# 持仓法(主)：市值分布定 size + 估值/成长因子定 value_growth
# ---------------------------------------------------------------------------


def _holdings_method(
    holdings: list[dict[str, Any]]
) -> tuple[str | None, str | None, dict[str, Any]]:
    """持仓法判定两轴(TP-01 §3.5)。

    Args:
        holdings: 持仓项，含 weight/market_cap(亿)/pe/growth(%)。
    Returns:
        (size, value_growth, metrics)；任一轴数据不足时对应项为 None。
    """
    size = _classify_size(holdings)
    vg, pe, growth = _classify_value_growth(holdings)
    metrics: dict[str, Any] = {}
    if size is not None:
        wmc = _weighted_field(holdings, "market_cap")
        metrics["weighted_market_cap"] = wmc
    if pe is not None:
        metrics["weighted_pe"] = pe
    if growth is not None:
        metrics["weighted_growth"] = growth
    return size, vg, metrics


def _classify_size(holdings: list[dict[str, Any]]) -> str | None:
    """持仓加权市值 -> 大/中/小盘(§3.5 持仓市值分布)。

    market_cap 缺失个股跳过；全缺 -> None(不可得，不硬算)。
    """
    wmc = _weighted_field(holdings, "market_cap")
    if wmc is None:
        return None
    if wmc >= LARGE_CAP_MIN:
        return SIZE_LARGE
    if wmc >= MID_CAP_MIN:
        return SIZE_MID
    return SIZE_SMALL


def _classify_value_growth(
    holdings: list[dict[str, Any]],
) -> tuple[str | None, float | None, float | None]:
    """持仓加权成长倾斜 -> 价值/平衡/成长(§3.5 估值/成长因子)。

    成长倾斜 = 持仓加权盈利增速(剔除越界/缺失，对齐 E7)；PE 作为价值佐证因子披露。
    growth 全缺 -> (None, pe, None) 不可得，不硬算。
    Returns:
        (value_growth, weighted_pe, weighted_growth)。
    """
    w_growth = _weighted_field(holdings, "growth", coerce=_valid_growth)
    w_pe = _weighted_field(holdings, "pe", coerce=_valid_pe)
    if w_growth is None:
        return None, w_pe, None
    if w_growth >= GROWTH_HIGH:
        vg = VG_GROWTH
    elif w_growth <= GROWTH_LOW:
        vg = VG_VALUE
    else:
        vg = VG_BALANCED
    return vg, w_pe, w_growth


# ---------------------------------------------------------------------------
# 回归交叉验证(收益回归法，§3.5 / E13)
# ---------------------------------------------------------------------------


def _apply_regression(
    result: StyleBoxResult,
    factor_returns: dict[str, list[float]] | None,
    fund_returns: list[float] | None,
) -> StyleBoxResult:
    """对持仓法结果叠加回归交叉验证(§3.5)。

    fund_returns 与 factor_returns(value/growth)同长 -> OLS 回归得载荷；
    载荷不显著(|load|<0.3 且 p>0.1，E13)或与持仓法结论不一致 -> cv_flag=True；
    因子收益缺失 -> cv_flag=None(未做回归，披露 reg_window)。
    """
    if factor_returns is None or fund_returns is None:
        # 未做回归：cv_flag=None，仅披露 reg_window(已在 result)
        return result

    loads = _regression_loadings(fund_returns, factor_returns)
    if loads is None:
        # 样本不足 -> 不可回归
        metrics = {**result.metrics, "regression": "insufficient_sample"}
        return StyleBoxResult(**{**result.to_dict(), "cv_flag": None, "metrics": metrics})

    loadings, growth_significant = loads
    beta_v, beta_g = loadings["value"], loadings["growth"]
    reg_implied = _regression_style(beta_v, beta_g)
    cv_flag = _decide_cv(result.value_growth, reg_implied, beta_g, growth_significant)
    metrics = {**result.metrics, "reg_loadings": loadings, "reg_implied": reg_implied}
    return StyleBoxResult(**{**result.to_dict(), "cv_flag": cv_flag, "metrics": metrics})


def _regression_loadings(
    fund_returns: list[float],
    factor_returns: dict[str, list[float]],
) -> tuple[dict[str, float], bool] | None:
    """OLS 回归 fund_ret = α + β_value·value + β_growth·growth + ε。

    Returns:
        ({"value":β_v,"growth":β_g,"alpha":α}, growth_significant)；
        样本不足(≤3 或长度不齐)返 None。
        growth_significant = |β_growth|≥0.3 且 |t|≥1.645(p≤0.1 近似，E13)。
    """
    vf = factor_returns.get("value")
    gf = factor_returns.get("growth")
    if vf is None or gf is None:
        return None
    n = len(fund_returns)
    if n <= 3 or len(vf) != n or len(gf) != n:
        return None

    # 设计矩阵 [1, value, growth]
    x = np.column_stack([np.ones(n), np.array(vf, dtype=float), np.array(gf, dtype=float)])
    y = np.array(fund_returns, dtype=float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    alpha, beta_v, beta_g = float(beta[0]), float(beta[1]), float(beta[2])

    # t 统计量(双侧 p>0.1 近似 |t|<1.645，大样本)
    resid = y - x @ beta
    dof = n - 3
    sigma2 = float(resid @ resid) / dof if dof > 0 else 0.0
    if sigma2 <= 0.0:
        # 完美拟合(残差 0)：载荷可靠，显著性由载荷量级判定(避免 0/0)
        growth_significant = abs(beta_g) >= LOAD_SIGNIFICANCE
    else:
        try:
            xtx_inv = np.linalg.inv(x.T @ x)
        except np.linalg.LinAlgError:
            xtx_inv = np.zeros((3, 3))
        se = np.sqrt(np.diag(sigma2 * xtx_inv))
        t_g = beta_g / se[2] if se[2] > 0 else 0.0
        growth_significant = abs(beta_g) >= LOAD_SIGNIFICANCE and abs(t_g) >= T_P010

    return {"value": beta_v, "growth": beta_g, "alpha": alpha}, growth_significant


def _regression_style(beta_value: float, beta_growth: float) -> str:
    """回归载荷 -> 隐含风格(成长倾斜 dominant -> 成长，反之价值，等 -> 平衡)。"""
    if beta_growth > beta_value:
        return VG_GROWTH
    if beta_value > beta_growth:
        return VG_VALUE
    return VG_BALANCED


def _decide_cv(
    holding_vg: str | None,
    reg_implied: str,
    beta_growth: float,
    growth_significant: bool,
) -> bool:
    """交叉验证判定(E13)。

    - 载荷不显著(|β_g|<0.3 或 p>0.1) -> cv_flag=True(E13 提示)。
    - 持仓法与回归结论不一致 -> cv_flag=True(§3.5)。
    - 一致 -> False。
    """
    if not growth_significant:
        return True
    if holding_vg is None:
        return True
    return holding_vg != reg_implied


# ---------------------------------------------------------------------------
# 基金披露风格解析(回退 1)
# ---------------------------------------------------------------------------


def _parse_declared_style(fund_style: str) -> tuple[str | None, str | None]:
    """解析基金披露风格串 -> (size, value_growth)。

    兼容"大盘价值"/"中盘 平衡"(带空格)/"小盘-成长"等写法；
    命中 _SIZE_TOKENS 与 _VG_TOKENS 子串。
    """
    size = next((t for t in (SIZE_LARGE, SIZE_MID, SIZE_SMALL) if t in fund_style), None)
    vg = next((t for t in (VG_VALUE, VG_BALANCED, VG_GROWTH) if t in fund_style), None)
    return size, vg


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _guard_passed() -> bool:
    """守卫通过判定(§3.3.7 语义)。

    口径已定义(持仓法+回归+披露回退在 TP-01 §3.5 落地)，守卫通过。
    口径真正未定义时应返 False(返回 None)。
    """
    return True  # 口径已定义(P1-03b)


def _weighted_field(
    holdings: list[dict[str, Any]],
    field: str,
    *,
    coerce: Callable[[Any], float | None] | None = None,
) -> float | None:
    """持仓加权某字段(权重为 0 回退算术平均)；全缺返 None。

    Args:
        holdings: 持仓项。
        field: 字段名(market_cap/pe/growth)。
        coerce: 可选校验/转换函数，返 None 表示该项跳过(如剔除 PE≤0)。
    """
    values: list[float] = []
    weights: list[float] = []
    for h in holdings:
        raw = h.get(field)
        if raw is None:
            continue
        val = coerce(raw) if coerce is not None else float(raw)
        if val is None:  # coerce 剔除
            continue
        values.append(val)
        weights.append(float(h.get("weight", 0.0)))
    if not values:
        return None
    total_w = sum(weights)
    if total_w == 0:
        return sum(values) / len(values)
    return sum(v * w for v, w in zip(values, weights, strict=False)) / total_w


def _valid_pe(raw: Any) -> float | None:
    """PE 校验：剔除 PE≤0(亏损，对齐 PEG E7)。"""
    try:
        pe = float(raw)
    except (TypeError, ValueError):
        return None
    return pe if pe > 0 else None


def _valid_growth(raw: Any) -> float | None:
    """成长增速校验：剔除越界/非数(对齐 PEG E7：0<g<100)。"""
    try:
        g = float(raw)
    except (TypeError, ValueError):
        return None
    return g if GROWTH_MIN < g < GROWTH_MAX else None


__all__: list[str] = [
    "STYLEBOX_GUARD",
    "STYLEBOX_SCOPE",
    "REG_WINDOW",
    "LOAD_SIGNIFICANCE",
    "T_P010",
    "LARGE_CAP_MIN",
    "MID_CAP_MIN",
    "GROWTH_HIGH",
    "GROWTH_LOW",
    "SIZE_LARGE",
    "SIZE_MID",
    "SIZE_SMALL",
    "VG_VALUE",
    "VG_BALANCED",
    "VG_GROWTH",
    "UNAVAILABLE_MSG",
    "StyleBoxResult",
    "style_box",
]
