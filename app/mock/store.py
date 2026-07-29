"""mock.store · 示例数据集(贴合 infra/db/models 字段口径 + 原型取值)。

数据按模块组织，字段名对齐 ORM(Fund/Nav/Holding/Score/PaperAccount/PaperPosition)
与原型 ``fund_invest_prototype.html`` 取值。金融口径红线见 CLAUDE.md §4，算法权威见
对应 TP(TP-01~06)。此处仅提供"指示性"展示数据，真实计算由后端 domain 落地。

> ``source`` 统一 ``mock``、``as_of`` 固定 2025-07-20，保证可复算可测(详设§2.21.1)。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

#: Mock 固定截至日(与 mock.envelope.MOCK_AS_OF 一致)。
AS_OF: date = date(2025, 7, 20)

#: 五因子默认权重(TP-01 §3.1 DEFAULT_WEIGHTS，权重和=1)。
#: 注：CLAUDE.md §4 简写"ret 权重 20"与 TP-01 §3.1(0.30)冲突；按冲突解决条款以 TP 为准。
DEFAULT_WEIGHTS: dict[str, float] = {
    "ret": 0.30,
    "risk": 0.25,
    "perf": 0.20,
    "scale": 0.15,
    "manager": 0.10,
}

#: 五因子中文名与方向(越高越好 / 越接近0越好)，见 TP-01 §3.1。
FACTOR_META: dict[str, dict[str, str]] = {
    "ret": {"name": "收益", "desc": "年化收益(%)", "good": "high"},
    "risk": {"name": "风险", "desc": "最大回撤(负值，越接近0越好)", "good": "low"},
    "perf": {"name": "性价比", "desc": "夏普比率(风险调整后)", "good": "high"},
    "scale": {"name": "规模", "desc": "规模健康度(2~500亿满分)", "good": "high"},
    "manager": {"name": "经理", "desc": "任职超额(标注任期业绩非能力)", "good": "high"},
}


# =====================================================================
# 基金列表(§2.20.2 funds；原型①榜单 / ②数据中心 / ④筛选结果)
# =====================================================================
FUNDS: list[dict[str, Any]] = [
    {
        "code": "110011",
        "name": "易方达中小盘",
        "type": "mix",
        "sub_type": "偏股混合",
        "theme": "消费",
        "style": "中盘成长",
        "scale_yi": 58.0,
        "score": 85,
        "manager": "张坤",
        "tenure_return": 1.20,
        "fee_rate": 0.015,
        "launch_date": date(2007, 4, 11),
        "company": "易方达基金",
    },
    {
        "code": "000961",
        "name": "天弘沪深300ETF",
        "type": "etf",
        "sub_type": "宽基ETF",
        "theme": "宽基",
        "style": "大盘价值",
        "scale_yi": 120.0,
        "score": 83,
        "manager": "陈瑶",
        "tenure_return": 0.45,
        "fee_rate": 0.005,
        "launch_date": date(2015, 1, 20),
        "company": "天弘基金",
    },
    {
        "code": "161725",
        "name": "招商中证白酒",
        "type": "stock",
        "sub_type": "行业股票",
        "theme": "消费",
        "style": "大盘价值",
        "scale_yi": 42.0,
        "score": 80,
        "manager": "侯昊",
        "tenure_return": 0.88,
        "fee_rate": 0.012,
        "launch_date": date(2014, 12, 2),
        "company": "招商基金",
    },
    {
        "code": "100018",
        "name": "富国天利债券",
        "type": "bond",
        "sub_type": "中长期债",
        "theme": "债券",
        "style": "-",
        "scale_yi": 35.0,
        "score": 78,
        "manager": "李羿",
        "tenure_return": 0.32,
        "fee_rate": 0.008,
        "launch_date": date(2003, 12, 2),
        "company": "富国基金",
    },
    {
        "code": "000934",
        "name": "国富大中华QDII",
        "type": "qdii",
        "sub_type": "QDII股票",
        "theme": "海外",
        "style": "中盘成长",
        "scale_yi": 8.5,
        "score": 76,
        "manager": "徐成",
        "tenure_return": 0.65,
        "fee_rate": 0.018,
        "launch_date": date(2014, 12, 24),
        "company": "国海富兰克林",
    },
    {
        "code": "000509",
        "name": "广发货币",
        "type": "money",
        "sub_type": "货币市场",
        "theme": "现金管理",
        "style": "-",
        "scale_yi": 200.0,
        "score": 72,
        "manager": "代宇",
        "tenure_return": 0.08,
        "fee_rate": 0.0,
        "launch_date": date(2013, 1, 18),
        "company": "广发基金",
    },
    {
        "code": "005827",
        "name": "易方达蓝筹精选",
        "type": "mix",
        "sub_type": "偏股混合",
        "theme": "消费",
        "style": "大盘价值",
        "scale_yi": 180.0,
        "score": 74,
        "manager": "张坤",
        "tenure_return": 0.95,
        "fee_rate": 0.015,
        "launch_date": date(2018, 9, 5),
        "company": "易方达基金",
    },
]

#: 类型 -> 中文/Tab 标签(原型① 类型Tab；NL「稳健」排除 index/etf 见 E6)。
TYPE_LABELS: dict[str, str] = {
    "stock": "股票型",
    "mix": "混合型",
    "index": "指数型",
    "etf": "ETF/LOF",
    "bond": "债券型",
    "qdii": "QDII",
    "money": "货币",
    "fof": "FOF",
}

#: 分类树(原型② DC-002 B)。
CATEGORY_TREE: dict[str, list[str]] = {
    "类型": ["股票型", "混合型", "指数型", "ETF/LOF", "债券型", "QDII", "货币", "FOF"],
    "主题": ["红利", "科技AI", "医药", "新能源", "消费", "宽基", "海外"],
    "风格": ["大盘价值", "中盘平衡", "小盘成长"],
}


# =====================================================================
# 净值序列(§2.20.2 navs；adj_nav 后复权净值用于回测/曲线，E3/E14)
# 生成确定性趋势序列供图表使用(禁未来函数：仅历史区间)。
# =====================================================================
def _nav_series(
    code: str, start: float, days: int, drift: float, vol: float
) -> list[dict[str, Any]]:
    """确定性生成净值序列(历史区间，不含未来函数)。

    用 code 字符和为种子，保证可复算；drift>0 上行、vol 波动。
    """
    seed = sum(ord(c) for c in code) + 7
    pts: list[dict[str, Any]] = []
    nav = start
    for i in range(days):
        # 确定性"伪随机"波动(正弦+种子偏移)，非 Math.random
        wave = math.sin(i * 0.18 + seed % 7) * vol
        trend = drift / days
        nav = max(0.01, nav * (1 + trend + wave))
        d = AS_OF - timedelta(days=days - i)
        pts.append(
            {
                "code": code,
                "trade_date": d.isoformat(),
                "nav": round(nav, 4),
                "acc_nav": round(nav * 1.02, 4),
                "adj_nav": round(nav, 4),
                "is_estimate": False,
            }
        )
    return pts


def nav_series(code: str, days: int = 252) -> list[dict[str, Any]]:
    """取基金近 N 个交易日后复权净值(默认 1 年)。"""
    cfg = {
        "110011": (1.20, 0.0012, 0.012),
        "000961": (1.05, 0.0008, 0.008),
        "161725": (1.40, 0.0010, 0.018),
        "005827": (1.30, -0.0004, 0.014),
        "100018": (1.02, 0.0002, 0.002),
        "000934": (1.10, 0.0006, 0.011),
    }
    s, dr, v = cfg.get(code, (1.10, 0.0006, 0.010))
    return _nav_series(code, s, days, dr, v)


#: 盘中估算(原型② DC-002 D，仅供参考以收盘净值为准)。
INTRADAY_ESTIMATE: dict[str, Any] = {
    "code": "110011",
    "estimate_pct": 0.0062,
    "estimate_nav": 1.082,
}


# =====================================================================
# 五因子评分分解(§2.20.2 scores；TP-01 §3.1；原型③)
# sub_score 0~100 子分；contrib = sub_score * weight(贡献分)；composite = Σcontrib
# =====================================================================
SCORES: dict[str, dict[str, Any]] = {
    "110011": {
        "code": "110011",
        "window": "3y",
        "composite": 82,
        "weights": DEFAULT_WEIGHTS,
        # sub_score × weight = contrib，Σcontrib = composite(82)，保证滑杆重算与展示一致(ADR-002)
        "factors": {
            "ret": {"sub_score": 84, "raw": 0.098, "contrib": 25.2},  # +9.8% 年化
            "risk": {"sub_score": 78, "raw": -0.142, "contrib": 19.5},  # 回撤 -14.2%
            "perf": {"sub_score": 86, "raw": 1.32, "contrib": 17.2},  # 夏普 1.32
            "scale": {"sub_score": 74, "raw": 58.0, "contrib": 11.1},  # 58亿
            "manager": {"sub_score": 92, "raw": 1.20, "contrib": 9.2},  # 任职 +120%
        },
    },
    "000961": {
        "code": "000961",
        "window": "3y",
        "composite": 83,
        "weights": DEFAULT_WEIGHTS,
        "factors": {
            "ret": {"sub_score": 70, "raw": 0.072, "contrib": 21.0},
            "risk": {"sub_score": 88, "raw": -0.094, "contrib": 22.0},
            "perf": {"sub_score": 80, "raw": 1.10, "contrib": 16.0},
            "scale": {"sub_score": 95, "raw": 120.0, "contrib": 14.2},
            "manager": {"sub_score": 60, "raw": 0.45, "contrib": 6.0},
        },
    },
    "161725": {
        "code": "161725",
        "window": "3y",
        "composite": 80,
        "weights": DEFAULT_WEIGHTS,
        "factors": {
            "ret": {"sub_score": 88, "raw": 0.155, "contrib": 26.4},
            "risk": {"sub_score": 60, "raw": -0.28, "contrib": 15.0},
            "perf": {"sub_score": 75, "raw": 1.05, "contrib": 15.0},
            "scale": {"sub_score": 70, "raw": 42.0, "contrib": 10.5},
            "manager": {"sub_score": 78, "raw": 0.88, "contrib": 7.8},
        },
    },
}


# =====================================================================
# 核心指标卡(原型③；近3年/沪深300口径)
# =====================================================================
METRICS: dict[str, dict[str, Any]] = {
    "110011": {
        "年化收益": 0.098,
        "年化波动": 0.141,
        "夏普比率": 1.32,
        "索提诺": 1.85,
        "最大回撤": -0.142,
        "卡玛比率": 0.69,
        "window": "3y",
        "benchmark": "沪深300",
        "cv_error": 0.003,  # 交叉验证误差<0.5%(E)
    },
    "000961": {
        "年化收益": 0.072,
        "年化波动": 0.118,
        "夏普比率": 1.10,
        "索提诺": 1.55,
        "最大回撤": -0.094,
        "卡玛比率": 0.76,
        "window": "3y",
        "benchmark": "沪深300",
        "cv_error": 0.002,
    },
}


# =====================================================================
# Brinson 归因(TP-01 §3.5；原型③；仅 mixed/stock，E1/E2)
# allocation=配置 / selection=选股 / interaction=交互；多期几何链接
# =====================================================================
ATTRIBUTION: dict[str, dict[str, Any]] = {
    "110011": {
        "code": "110011",
        "scope": "mixed/stock",
        "multi_period": "geometric_link",
        "allocation": 0.031,
        "selection": 0.054,
        "interaction": 0.008,
        "active_return": 0.093,
        "note": "用披露真实权重+OTHER_CASH残差桶；多期几何链接(Carino/Frongello)",
    },
}
#: 指数/债基替代说明(原型③ Brinson 边界)。
ATTRIBUTION_SUBSTITUTE: dict[str, str] = {
    "index": "指数基金 -> 以跟踪误差/信息比率替代",
    "etf": "ETF -> 以跟踪误差/信息比率替代",
    "bond": "债券基金 -> 不显示归因(边界)",
}


# =====================================================================
# 研究型指标(FR-45 / TP-01 §3.7；原型③；分组卡片+阈值着色)
# PEG/ERP 走 RESEARCH_PROXY_GUARD：未定义口径返 available=False(错误码 40301)
# =====================================================================
RESEARCH: dict[str, dict[str, Any]] = {
    "110011": {
        "items": [
            {"name": "α（选股超额）", "value": 2.1, "level": "good", "desc": "跑赢基准，正向 ✅"},
            {"name": "β（市场暴露）", "value": 0.92, "level": "good", "desc": "略低于市场，防御性"},
            {"name": "跟踪误差", "value": 0.018, "level": "warn", "desc": "主动偏离，需关注"},
            {"name": "折溢价（盘中）", "value": 0.003, "level": "good", "desc": "场内小幅溢价"},
            {
                "name": "PEG",
                "value": 0.9,
                "level": "good",
                "desc": "估值性价比合理 ✅",
                "available": True,
            },
            {
                "name": "ERP（股权风险溢价）",
                "value": 0.042,
                "level": "warn",
                "desc": "中性偏高，权益略优于债",
                "available": True,
                "note": "ERP 拆大/小盘加权 7:3(E10)",
            },
        ],
        "cv_error": 0.003,
    },
}


# =====================================================================
# 重仓股 / 持仓穿透(§2.20.2 holdings；原型②⑨；按占净值比排序)
# 舆情日更 / 持仓季更 / 带来源+时间(BR-11.6)
# =====================================================================
HOLDINGS: dict[str, list[dict[str, Any]]] = {
    "110011": [
        {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "weight": 0.092,
            "sentiment": "正面",
            "source": "新闻聚合",
            "date": "07-20",
        },
        {
            "stock_code": "300750",
            "stock_name": "宁德时代",
            "weight": 0.071,
            "sentiment": "中性",
            "source": "财报/研报",
            "date": "07-19",
        },
        {
            "stock_code": "600036",
            "stock_name": "招商银行",
            "weight": 0.054,
            "sentiment": "负面",
            "source": "新闻聚合",
            "date": "07-20",
        },
        {
            "stock_code": "000858",
            "stock_name": "五粮液",
            "weight": 0.048,
            "sentiment": "正面",
            "source": "新闻聚合",
            "date": "07-20",
        },
        {
            "stock_code": "002714",
            "stock_name": "牧原股份",
            "weight": 0.035,
            "sentiment": "中性",
            "source": "研报",
            "date": "07-18",
        },
    ],
}
#: 重仓股财务四维(原型⑨ BR-11.3；增速/毛利/现金流/杠杆)。
STOCK_FINANCIALS: dict[str, list[dict[str, Any]]] = {
    "600519": [
        {"dim": "增速", "value": "+18%", "level": "good", "desc": "营收净利双增 ✅"},
        {"dim": "毛利率", "value": "91%", "level": "good", "desc": "高毛利护城河"},
        {"dim": "经营现金流", "value": "优", "level": "good", "desc": "现金充裕"},
        {"dim": "杠杆率", "value": "低", "level": "good", "desc": "财务稳健"},
    ],
}
#: 舆情周评(原型⑨ BR-11.4；AI 周报统一出口)。
SENTIMENT_WEEKLY: dict[str, str] = {
    "110011": "整体偏中性；重点风险：招商银行负面集中于息差压力；正面催化：茅台批价企稳。-> 由 AI 周报统一生成「持仓舆情周评」(见模块⑦)。",
}
#: 行业分布(原型②)。
INDUSTRY_DIST: dict[str, list[dict[str, Any]]] = {
    "110011": [
        {"industry": "食品饮料", "weight": 0.42},
        {"industry": "银行", "weight": 0.12},
        {"industry": "新能源", "weight": 0.10},
        {"industry": "医药", "weight": 0.08},
        {"industry": "其他", "weight": 0.28},
    ],
}


# =====================================================================
# 模拟交易(§2.20.2 paper_*；原型⑤；本地 session_state 记账，不连通实盘)
# =====================================================================
PAPER_ACCOUNT: dict[str, Any] = {
    "account_id": "paper-001",
    "init_capital": 1000000.0,
    "cash": 320000.0,  # 初始持仓占用 680000(见 PAPER_POSITIONS)
    "market_value": 680000.0,
    "total_return": 0.086,
}
#: 初始持仓(原型⑤ 持仓看板；005827 亏损联动回本 FR-40)。
PAPER_POSITIONS: list[dict[str, Any]] = [
    {
        "code": "110011",
        "name": "易方达中小盘",
        "cost": 50000.0,
        "market_value": 54300.0,
        "return_pct": 0.086,
        "bench_diff": 0.032,
        "shares": 50277.0,
        "cost_price": 0.994,
    },
    {
        "code": "005827",
        "name": "易方达蓝筹精选",
        "cost": 40000.0,
        "market_value": 33800.0,
        "return_pct": -0.155,
        "bench_diff": -0.041,
        "shares": 30727.0,
        "cost_price": 1.302,
    },
]
#: 定投回测(原型⑤ BR-4.4；区间≥1年真实回放)。
DCA_BACKTEST: dict[str, Any] = {
    "code": "110011",
    "freq": "月定投",
    "amount": 1000.0,
    "period": "2022-01 ~ 2025-07",
    "invested": 42000.0,
    "market_value": 49000.0,
    "return_pct": 0.167,
    "cost_avg": True,
}


# =====================================================================
# 组合诊断(原型⑥；TP-03；红黄绿 status=g/y/r + 可操作建议；E8/E9/E12)
# 股债目标仓位由 risk_type 推导：保守20-40/稳健40-60/进取60-80
# =====================================================================
PORTFOLIO_COMPONENTS: list[dict[str, Any]] = [
    {"name": "沪深300ETF(宽基)", "code": "000961", "weight": 0.50, "role": "核心"},
    {"name": "富国天利(债券)", "code": "100018", "weight": 0.30, "role": "核心"},
    {"name": "招商白酒(行业)", "code": "161725", "weight": 0.20, "role": "卫星"},
]
PORTFOLIO_DIAGNOSIS: list[dict[str, Any]] = [
    {"dim": "股债结构", "status": "现状:固收+货币30%", "level": "g", "advice": "维持"},
    {"dim": "海外覆盖", "status": "QDII 2%", "level": "y", "advice": "提至 ≥5%"},
    {"dim": "行业集中", "status": "科技AI 18%", "level": "y", "advice": "注意波动"},
    {"dim": "风格缺失", "status": "无宽基", "level": "r", "advice": "加入沪深300"},
    {"dim": "个基隐患", "status": "005827 -15%", "level": "r", "advice": "查看回本/减仓"},
]
#: 风险偏好判定(原型⑥ BR-5.11)。
PORTFOLIO_RISK_TYPE: str = "积极型"  # 固收+货币30% -> 进取区间


# =====================================================================
# 宏观市场认知底盘(原型⑦；TP-05；ERP 拆大/小盘加权 7:3(E10)、估值分位近10年(E11))
# =====================================================================
MACRO_CARDS: list[dict[str, Any]] = [
    {"k": "CPI（同比）", "v": "0.3%", "color": "blue"},
    {"k": "PMI", "v": "50.8", "color": "green"},
    {"k": "10Y 国债", "v": "2.25%", "color": "gray"},
    {"k": "北向资金", "v": "-12亿", "color": "red"},
]
MACRO_SENTIMENT: str = "中性偏谨慎"
#: 外围传导(原型⑦ BR-9.3；隔夜美股->次日开盘研判)。
MACRO_SURROUND: dict[str, Any] = {
    "us_nasdaq": 0.008,
    "china_concept": 0.012,
    "a50_future": 0.005,
    "judgment": "次日 A 股高开概率偏强(非交易时段标「暂无」)",
}
#: 高位四维排查(原型⑦⑫ 共享引擎 FR-38；估值/通胀/资金面/政策)。
MACRO_HIGH_SIGNAL: list[dict[str, Any]] = [
    {"dim": "估值", "level": "warn", "signal": "盈利能否消化待观察"},
    {"dim": "通胀", "level": "ok", "signal": "CPI 0.3% 安全"},
    {"dim": "资金面", "level": "warn", "signal": "北向流出"},
    {"dim": "政策", "level": "ok", "signal": "维持宽松"},
]
MACRO_HIGH_VERDICT: str = "中性 -> 维持定投，不追高"
#: 股债中枢(原型⑦ BR-9.5；PE分位->仓位中枢建议)。
MACRO_POSITION: dict[str, Any] = {
    "pe_pct": 0.28,
    "advice": "沪深300 PE 分位 28% -> 股债 60/40（偏股）",
}


# =====================================================================
# 单基实验室(原型⑧；TP-04；FR-40~42)
# 回本公式：回本需涨 = |亏损| / (1 + 亏损) (DC-011/BR-10.1)
# =====================================================================
def breakeven_need(loss_pct: float) -> float:
    """回本需涨 = |亏损| / (1 + 亏损)。亏损为负比率(-0.30)。后端权威，前端演示。"""
    if loss_pct >= 0:
        return 0.0
    return abs(loss_pct) / (1 + loss_pct)


#: 情景推演(原型⑧ BR-10.2；含对持仓影响列)。
LAB_SCENARIOS: list[dict[str, Any]] = [
    {"scenario": "保守", "target": 3000, "expected": -0.05, "impact": "仓位不变"},
    {"scenario": "基准", "target": 3400, "expected": 0.08, "impact": "小步定投"},
    {"scenario": "乐观", "target": 3800, "expected": 0.20, "impact": "可适度加仓"},
]
#: 五策略对照(原型⑧ BR-10.3；适用条件/优劣/适合人群，含回本联动行)。
LAB_STRATEGIES: list[dict[str, Any]] = [
    {
        "strategy": "持有等待",
        "cond": "逻辑未破、长期",
        "pro_con": "省心，需耐性",
        "fit": "长期投资者",
    },
    {"strategy": "定投加仓", "cond": "低估区", "pro_con": "摊低成本，怕阴跌", "fit": "工薪定投族"},
    {"strategy": "波段", "cond": "震荡市", "pro_con": "增厚收益，需纪律", "fit": "有时间盯盘者"},
    {
        "strategy": "调仓/止损",
        "cond": "逻辑破坏",
        "pro_con": "控风险，可能卖飞",
        "fit": "风控优先者",
    },
    {
        "strategy": "回本联动",
        "cond": "已亏损",
        "pro_con": "闭环「亏了怎么办」",
        "fit": "模拟交易者",
    },
]


# =====================================================================
# 学习投教(原型⑩；DC-007；词典/路径/案例沙盒/行为问卷)
# =====================================================================
LEARN_GLOSSARY: list[dict[str, Any]] = [
    {
        "term": "夏普比率",
        "def": "每单位波动带来的超额收益",
        "formula": "(年化收益-无风险)/年化波动",
        "good": "越高越好，>1 合格、>2 优秀",
        "range": ">1",
    },
    {
        "term": "最大回撤",
        "def": "历史最高点到最低点的最大跌幅",
        "formula": "max((峰-谷)/峰)",
        "good": "越接近 0 越好",
        "range": "<15% 稳健",
    },
    {
        "term": "卡玛比率",
        "def": "年化收益/最大回撤",
        "formula": "年化收益/|最大回撤|",
        "good": "越高越好",
        "range": ">1 良好",
    },
    {
        "term": "夏普 vs 索提诺",
        "def": "索提诺只用下行波动",
        "formula": "(年化收益-无风险)/下行波动",
        "good": "对只关心下跌的投资者更直观",
        "range": ">夏普",
    },
]
LEARN_PATH: list[dict[str, str]] = [
    {"stage": "入门", "modules": "仪表盘 / 数据中心"},
    {"stage": "进阶", "modules": "评估详情 / 筛选器"},
    {"stage": "实战", "modules": "模拟交易 / 组合诊断"},
]
LEARN_CASES: list[str] = ["📉 2015 股灾", "😷 2020 新冠暴跌", "📉 2022 下跌"]
LEARN_BIAS_QUESTIONS: list[str] = [
    "我常在上涨时加仓(追涨)",
    "我很少设止损",
    "下跌时我容易恐慌抛售",
    "我倾向持有亏损基等回本(处置效应)",
]


# =====================================================================
# AI 助手(原型⑪；DC-008；RAG对话/周报/拒答降级，FR-29~32)
# 所有输出标注 来源+截至+「仅供参考，不构成投资建议」(FR-46)
# =====================================================================
AI_QUICK_COMMANDS: list[str] = [
    "📄 解读这只基金季报",
    "👤 生成经理画像",
    "📊 生成本周投资周报",
    "🔄 手动重跑周报",
]
AI_DEMO_CHAT: list[dict[str, str]] = [
    {"role": "user", "text": "帮我解读 110011 最新季报"},
    {
        "role": "assistant",
        "text": "本季仓位 78%（Q1 72%），加仓食品饮料，减仓金融；风险点：消费复苏不及预期。",
        "source": "来源：2025-Q1 季报 · 截至 2025-07-20 · 仅供参考，不构成投资建议",
    },
    {"role": "user", "text": "本周我的组合怎么样？"},
    {
        "role": "assistant",
        "text": "本周组合 +1.2%，跑赢沪深300 +0.4%；关注：创业板估值高位建议减仓。",
        "source": "来源：组合诊断+持仓舆情 · 截至 2025-07-20 · 仅供参考",
    },
    {"role": "user", "text": "帮我预测下个月哪只基金会涨？"},
    {
        "role": "assistant",
        "text": "⚠ 无相关依据，无法预测具体涨跌。我可基于持仓/舆情给你「当前状态」，但不做确定性建议。",
        "source": "无依据拒答(§3.11.7)",
        "reject": True,
    },
]
AI_WEEKLY: str = "AI 周报直接引用 FR-43 持仓舆情结果，生成「持仓舆情周评」，避免双套结论。"
AI_DEGRADE: str = "LLM 超时/限频 -> 回退规则摘要(50303)，不阻塞主流程，提示可重试。"


# =====================================================================
# 风险与监控(原型⑫；DC-009；FR-33~36,38)
# 估值定投信号：PE分位->倍数 1.5x/1.0x/0.5x/停投(FR-35)
# 数据质量 Must(FR-36)
# =====================================================================
RISK_TYPES: list[str] = ["稳健型", "均衡型", "积极型"]
RISK_ALERTS: list[dict[str, str]] = [
    {"type": "估值", "text": "创业板指 PE 分位 82% -> 高位提醒"},
    {"type": "回撤", "text": "005827 近月回撤 -15%"},
    {"type": "净值异动", "text": "110011 单日 +2.1%"},
    {"type": "持仓变化", "text": "加仓食品饮料"},
]
#: 估值定投信号映射(原型⑫；PE分位->定投倍数)。
VALUATION_DCA_SIGNAL: list[dict[str, Any]] = [
    {"pe_range": "<30%", "multiple": "1.5x", "action": "多投", "level": "ok"},
    {"pe_range": "30~70%", "multiple": "1.0x", "action": "正常", "level": "ok"},
    {"pe_range": ">70%", "multiple": "0.5x", "action": "少投", "level": "warn"},
    {"pe_range": ">90%", "multiple": "0x", "action": "停投", "level": "bad"},
]
#: 数据质量看板(原型⑫ FR-36 Must；采集成功率/时效/对账误差)。
DATA_QUALITY: list[dict[str, Any]] = [
    {"k": "采集成功率", "v": "99.6%", "level": "good", "d": "近 24h"},
    {"k": "更新时效", "v": "T+1", "level": "good", "d": "达标"},
    {"k": "对账误差", "v": "0.3%", "level": "warn", "d": "阈值 0.5%"},
]


# =====================================================================
# 仪表盘聚合(原型①；FR-D1~D6 / DC-001；状态->榜单->学习 三段式)
# =====================================================================
DASHBOARD_STATUS: list[dict[str, Any]] = [
    {"k": "模拟组合收益", "v": "+12.4%", "color": "green"},
    {"k": "同期沪深300", "v": "+5.1%", "color": "gray"},
    {"k": "待办提醒", "v": "2 条", "color": "red"},
    {"k": "学习进度", "v": "60%", "color": "blue"},
]
DASHBOARD_DYNAMICS: list[str] = [
    "🆕 新发：XX 中证A500ETF 正在募集",
    "⚡ 异动：创业板指估值分位 82%，触发高位信号",
    "💰 分红：110011 每份分红 0.20 元",
    "📈 信号：沪深300 PE 分位 28%，定投倍数 1.5x",
]
DASHBOARD_LEARN_CARD: dict[str, str] = {
    "title": "沪深300ETF",
    "desc": "跟踪沪深300 的场内基金，费用低、透明度高，适合作为组合压舱石。",
}


def fund_by_code(code: str) -> dict[str, Any] | None:
    """按代码取基金(数据中心/评估详情入口)。"""
    for f in FUNDS:
        if f["code"] == code:
            return f
    return None


def dashboard_top10(fund_type: str = "all") -> list[dict[str, Any]]:
    """仪表盘 Top10 综合评分榜(原型① 类型Tab 过滤)。"""
    rows = sorted(FUNDS, key=lambda x: x["score"], reverse=True)
    if fund_type != "all":
        rows = [r for r in rows if r["type"] == fund_type]
    return [
        {
            "rank": i + 1,
            "code": r["code"],
            "name": r["name"],
            "type": TYPE_LABELS.get(r["type"], r["type"]),
            "score": r["score"],
        }
        for i, r in enumerate(rows[:10])
    ]
