# -*- coding: utf-8 -*-
"""
构建 NL 选基评测集（gold standard）：100 条 {问句 -> 期望结构化条件}。
输出：/workspace/nl_eval_set.json
意图分布：
  A 因子+类型+区间   40 条
  B 仅类型           15 条
  C 区间强调         10 条
  D 组合+否定/剔除   20 条
  E 歧义->反问       15 条
结构化条件 schema：
  clarify : bool            # True 表示应触发反问(Clarify)，不返回条件
  type    : list[str]       # stock/mixed/bond/index/etf/qdii/money
  window  : str|None        # 1y/3y/5y/ytd/since
  factors : dict            # max_drawdown_le / return_rank_ge / annual_return_ge /
                            #   volatility_le / scale_min / scale_max / sharpe_ge
  exclude : list[str]       # 剔除行业/主题
"""
import json, os

ITEMS = [
    # ============ A. 因子 + 类型 + 区间 (40) ============
    ("A","近三年混合基金里回撤小于15%、收益排名前20%的", dict(clarify=False,type=["mixed"],window="3y",factors={"max_drawdown_le":0.15,"return_rank_ge":0.20},exclude=[])),
    ("A","近一年股票型基金中收益高、规模适中的", dict(clarify=False,type=["stock"],window="1y",factors={"return_rank_ge":0.20,"scale_min":2,"scale_max":50},exclude=[])),
    ("A","近三年回撤控制在10%以内、年化收益8%以上的混合基", dict(clarify=False,type=["mixed"],window="3y",factors={"max_drawdown_le":0.10,"annual_return_ge":0.08},exclude=[])),
    ("A","成立以来波动小、夏普大于1的宽基指数基金", dict(clarify=False,type=["index"],window="since",factors={"volatility_le":0.10,"sharpe_ge":1.0},exclude=[])),
    ("A","近五年收益靠前、最大回撤不超20%的主动股混", dict(clarify=False,type=["mixed"],window="5y",factors={"return_rank_ge":0.20,"max_drawdown_le":0.20},exclude=[])),
    ("A","近一年规模在10到50亿、收益排名前30%的混合基金", dict(clarify=False,type=["mixed"],window="1y",factors={"scale_min":10,"scale_max":50,"return_rank_ge":0.30},exclude=[])),
    ("A","近三年夏普高、回撤小的债券基金", dict(clarify=False,type=["bond"],window="3y",factors={"sharpe_ge":1.0,"max_drawdown_le":0.15},exclude=[])),
    ("A","今年以来收益好、波动低的股票基金", dict(clarify=False,type=["stock"],window="ytd",factors={"return_rank_ge":0.20,"volatility_le":0.10},exclude=[])),
    ("A","近三年规模适中、回撤低于12%的沪深300指数基金", dict(clarify=False,type=["index"],window="3y",factors={"scale_min":2,"scale_max":50,"max_drawdown_le":0.12},exclude=[])),
    ("A","近一年收益排名前10%、最大回撤15%以内的主动混合", dict(clarify=False,type=["mixed"],window="1y",factors={"return_rank_ge":0.10,"max_drawdown_le":0.15},exclude=[])),
    ("A","成立以来年化收益10%以上、回撤不超25%的混合偏股", dict(clarify=False,type=["mixed"],window="since",factors={"annual_return_ge":0.10,"max_drawdown_le":0.25},exclude=[])),
    ("A","近三年波动平稳、收益靠前的债券型", dict(clarify=False,type=["bond"],window="3y",factors={"volatility_le":0.10,"return_rank_ge":0.20},exclude=[])),
    ("A","近五年规模大、夏普大于1.2的宽基ETF", dict(clarify=False,type=["etf"],window="5y",factors={"scale_min":50,"sharpe_ge":1.2},exclude=[])),
    ("A","近一年回撤小、收益高的QDII基金", dict(clarify=False,type=["qdii"],window="1y",factors={"max_drawdown_le":0.15,"return_rank_ge":0.20},exclude=[])),
    ("A","近三年收益稳定、最大回撤10%以内的混合基金", dict(clarify=False,type=["mixed"],window="3y",factors={"volatility_le":0.10,"max_drawdown_le":0.10},exclude=[])),
    ("A","近一年规模在5到20亿、夏普高、回撤低的股票基", dict(clarify=False,type=["stock"],window="1y",factors={"scale_min":5,"scale_max":20,"sharpe_ge":1.0,"max_drawdown_le":0.15},exclude=[])),
    ("A","近三年收益排名前25%、波动小的指数基金", dict(clarify=False,type=["index"],window="3y",factors={"return_rank_ge":0.25,"volatility_le":0.10},exclude=[])),
    ("A","成立以来回撤控制好的混合基金（不超过15%）", dict(clarify=False,type=["mixed"],window="since",factors={"max_drawdown_le":0.15},exclude=[])),
    ("A","近五年收益高、规模适中、夏普大于1的主动股票", dict(clarify=False,type=["stock"],window="5y",factors={"return_rank_ge":0.20,"scale_min":2,"scale_max":50,"sharpe_ge":1.0},exclude=[])),
    ("A","近一年最大回撤8%以内、年化收益6%以上的债基", dict(clarify=False,type=["bond"],window="1y",factors={"max_drawdown_le":0.08,"annual_return_ge":0.06},exclude=[])),
    ("A","近三年规模百亿以上、收益靠前的宽基指数", dict(clarify=False,type=["index"],window="3y",factors={"scale_min":50,"return_rank_ge":0.20},exclude=[])),
    ("A","今年以来回撤小、收益排名前20%的混合基", dict(clarify=False,type=["mixed"],window="ytd",factors={"max_drawdown_le":0.15,"return_rank_ge":0.20},exclude=[])),
    ("A","近三年夏普高（大于1.5）、回撤低的股票基金", dict(clarify=False,type=["stock"],window="3y",factors={"sharpe_ge":1.5,"max_drawdown_le":0.15},exclude=[])),
    ("A","成立以来波动低、收益稳定的二级债基", dict(clarify=False,type=["bond"],window="since",factors={"volatility_le":0.10},exclude=[])),
    ("A","近一年收益好、规模适中的QDII", dict(clarify=False,type=["qdii"],window="1y",factors={"return_rank_ge":0.20,"scale_min":2,"scale_max":50},exclude=[])),
    ("A","近五年回撤不超20%、夏普大于1.0的混合偏股", dict(clarify=False,type=["mixed"],window="5y",factors={"max_drawdown_le":0.20,"sharpe_ge":1.0},exclude=[])),
    ("A","近三年规模在20到100亿、收益排名前15%的主动混合", dict(clarify=False,type=["mixed"],window="3y",factors={"scale_min":20,"scale_max":100,"return_rank_ge":0.15},exclude=[])),
    ("A","近一年回撤小于10%、波动小的指数ETF", dict(clarify=False,type=["etf"],window="1y",factors={"max_drawdown_le":0.10,"volatility_le":0.10},exclude=[])),
    ("A","近三年收益靠前、最大回撤12%以内、规模适中的债券", dict(clarify=False,type=["bond"],window="3y",factors={"return_rank_ge":0.20,"max_drawdown_le":0.12,"scale_min":2,"scale_max":50},exclude=[])),
    ("A","成立以来年化收益8%以上、夏普高的股票基金", dict(clarify=False,type=["stock"],window="since",factors={"annual_return_ge":0.08,"sharpe_ge":1.0},exclude=[])),
    ("A","近一年规模小（5亿内）、收益排名前30%的混合", dict(clarify=False,type=["mixed"],window="1y",factors={"scale_max":5,"return_rank_ge":0.30},exclude=[])),
    ("A","近三年回撤控制好（不超10%）、收益高的宽基", dict(clarify=False,type=["index"],window="3y",factors={"max_drawdown_le":0.10,"return_rank_ge":0.20},exclude=[])),
    ("A","近五年波动小、回撤低的主动股混", dict(clarify=False,type=["mixed"],window="5y",factors={"volatility_le":0.10,"max_drawdown_le":0.15},exclude=[])),
    ("A","近一年收益排名前20%、夏普大于1.2的QDII", dict(clarify=False,type=["qdii"],window="1y",factors={"return_rank_ge":0.20,"sharpe_ge":1.2},exclude=[])),
    ("A","近三年规模适中、年化收益10%以上、回撤不超15%的混合", dict(clarify=False,type=["mixed"],window="3y",factors={"scale_min":2,"scale_max":50,"annual_return_ge":0.10,"max_drawdown_le":0.15},exclude=[])),
    ("A","今年以来回撤小、波动低的债券基金", dict(clarify=False,type=["bond"],window="ytd",factors={"max_drawdown_le":0.15,"volatility_le":0.10},exclude=[])),
    ("A","近三年收益稳定、夏普高的指数基金", dict(clarify=False,type=["index"],window="3y",factors={"volatility_le":0.10,"sharpe_ge":1.0},exclude=[])),
    ("A","成立以来规模大、收益靠前的沪深300ETF", dict(clarify=False,type=["etf"],window="since",factors={"scale_min":50,"return_rank_ge":0.20},exclude=[])),
    ("A","近一年回撤低、收益好的二级债", dict(clarify=False,type=["bond"],window="1y",factors={"max_drawdown_le":0.15,"return_rank_ge":0.20},exclude=[])),
    ("A","近五年收益排名前10%、回撤不超25%、规模适中的主动混合", dict(clarify=False,type=["mixed"],window="5y",factors={"return_rank_ge":0.10,"max_drawdown_le":0.25,"scale_min":2,"scale_max":50},exclude=[])),

    # ============ B. 仅类型 (15) ============
    ("B","推荐几只主动混合基金", dict(clarify=False,type=["mixed"],window=None,factors={},exclude=[])),
    ("B","有什么好的股票型基金", dict(clarify=False,type=["stock"],window=None,factors={},exclude=[])),
    ("B","想买点债券基金", dict(clarify=False,type=["bond"],window=None,factors={},exclude=[])),
    ("B","宽基指数基金有哪些", dict(clarify=False,type=["index"],window=None,factors={},exclude=[])),
    ("B","场内ETF怎么选", dict(clarify=False,type=["etf"],window=None,factors={},exclude=[])),
    ("B","想配置点QDII", dict(clarify=False,type=["qdii"],window=None,factors={},exclude=[])),
    ("B","货币基金哪只划算", dict(clarify=False,type=["money"],window=None,factors={},exclude=[])),
    ("B","主动股票基金推荐", dict(clarify=False,type=["stock"],window=None,factors={},exclude=[])),
    ("B","中长期纯债基金推荐", dict(clarify=False,type=["bond"],window=None,factors={},exclude=[])),
    ("B","沪深300相关的指数基金", dict(clarify=False,type=["index"],window=None,factors={},exclude=[])),
    ("B","混合偏股基金有哪些", dict(clarify=False,type=["mixed"],window=None,factors={},exclude=[])),
    ("B","二级债基推荐几只", dict(clarify=False,type=["bond"],window=None,factors={},exclude=[])),
    ("B","海外QDII基金", dict(clarify=False,type=["qdii"],window=None,factors={},exclude=[])),
    ("B","宽基ETF有哪些", dict(clarify=False,type=["etf"],window=None,factors={},exclude=[])),
    ("B","纯债基金推荐", dict(clarify=False,type=["bond"],window=None,factors={},exclude=[])),

    # ============ C. 区间强调 (10) ============
    ("C","近一年表现稳健的债券基金", dict(clarify=False,type=["bond"],window="1y",factors={"max_drawdown_le":0.15},exclude=[])),
    ("C","近三年走势平稳的混合基", dict(clarify=False,type=["mixed"],window="3y",factors={"volatility_le":0.10},exclude=[])),
    ("C","今年以来收益不错的股票基金", dict(clarify=False,type=["stock"],window="ytd",factors={"return_rank_ge":0.20},exclude=[])),
    ("C","成立以来长期业绩好的主动混合", dict(clarify=False,type=["mixed"],window="since",factors={"return_rank_ge":0.20},exclude=[])),
    ("C","近五年累计收益高的宽基指数", dict(clarify=False,type=["index"],window="5y",factors={"return_rank_ge":0.20},exclude=[])),
    ("C","近一年波动可控的QDII", dict(clarify=False,type=["qdii"],window="1y",factors={"volatility_le":0.10},exclude=[])),
    ("C","近三年回撤收敛的债券型", dict(clarify=False,type=["bond"],window="3y",factors={"max_drawdown_le":0.15},exclude=[])),
    ("C","今年以来表现抗跌的混合基金", dict(clarify=False,type=["mixed"],window="ytd",factors={"max_drawdown_le":0.15},exclude=[])),
    ("C","近五年稳健增值的二级债", dict(clarify=False,type=["bond"],window="5y",factors={"max_drawdown_le":0.15},exclude=[])),
    ("C","成立以来收益稳定的股票基金", dict(clarify=False,type=["stock"],window="since",factors={"volatility_le":0.10},exclude=[])),

    # ============ D. 组合 + 否定/剔除 (20) ============
    ("D","近三年混合基金，不要新能源、收益排名前20%", dict(clarify=False,type=["mixed"],window="3y",factors={"return_rank_ge":0.20},exclude=["新能源"])),
    ("D","近一年股票基，剔除医药、规模适中", dict(clarify=False,type=["stock"],window="1y",factors={"scale_min":2,"scale_max":50},exclude=["医药"])),
    ("D","想买主动混合，别碰白酒和地产", dict(clarify=False,type=["mixed"],window=None,factors={},exclude=["白酒","地产"])),
    ("D","近三年主动混合，收益好、回撤小，不买军工", dict(clarify=False,type=["mixed"],window="3y",factors={"return_rank_ge":0.20,"max_drawdown_le":0.15},exclude=["军工"])),
    ("D","宽基指数基金，避开白酒", dict(clarify=False,type=["index"],window=None,factors={},exclude=["白酒"])),
    ("D","近一年QDII，不要美股科技", dict(clarify=False,type=["qdii"],window="1y",factors={},exclude=["美股科技"])),
    ("D","混合偏股，剔除半导体和新能源", dict(clarify=False,type=["mixed"],window=None,factors={},exclude=["半导体","新能源"])),
    ("D","近三年债券基金，不要可转债", dict(clarify=False,type=["bond"],window="3y",factors={},exclude=["可转债"])),
    ("D","近一年混合基，收益靠前、规模适中，避开新能源车", dict(clarify=False,type=["mixed"],window="1y",factors={"return_rank_ge":0.20,"scale_min":2,"scale_max":50},exclude=["新能源车"])),
    ("D","主动股票，别买白酒、医药、新能源", dict(clarify=False,type=["stock"],window=None,factors={},exclude=["白酒","医药","新能源"])),
    ("D","近三年混合基，回撤小、收益高，剔除房地产", dict(clarify=False,type=["mixed"],window="3y",factors={"max_drawdown_le":0.15,"return_rank_ge":0.20},exclude=["房地产"])),
    ("D","沪深300ETF，不要金融地产", dict(clarify=False,type=["etf"],window=None,factors={},exclude=["金融","地产"])),
    ("D","近一年混合基，避开券商和保险", dict(clarify=False,type=["mixed"],window="1y",factors={},exclude=["券商","保险"])),
    ("D","近五年主动混合，收益排名前20%、回撤不超20%，不买军工", dict(clarify=False,type=["mixed"],window="5y",factors={"return_rank_ge":0.20,"max_drawdown_le":0.20},exclude=["军工"])),
    ("D","债券基金，剔除可转债和城投", dict(clarify=False,type=["bond"],window=None,factors={},exclude=["可转债","城投"])),
    ("D","近三年主动混合，不要互联网和港股通", dict(clarify=False,type=["mixed"],window="3y",factors={},exclude=["互联网","港股通"])),
    ("D","近一年股票基金，避开新能源、半导体", dict(clarify=False,type=["stock"],window="1y",factors={},exclude=["新能源","半导体"])),
    ("D","宽基指数，剔除白酒和医药", dict(clarify=False,type=["index"],window=None,factors={},exclude=["白酒","医药"])),
    ("D","近三年混合基，收益稳定、规模适中，不买地产", dict(clarify=False,type=["mixed"],window="3y",factors={"volatility_le":0.10,"scale_min":2,"scale_max":50},exclude=["地产"])),
    ("D","QDII，不要原油和黄金", dict(clarify=False,type=["qdii"],window=None,factors={},exclude=["原油","黄金"])),

    # ============ E. 歧义 -> 反问 (15) ============
    ("E","想找个好一点的基金", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","推荐个靠谱的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","有什么值得买的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","稳健一点的就行", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","性价比高的基金", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","帮我选个不错的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","想要个表现好的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","有合适的推荐吗", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","随便来个稳健的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","想买点不错的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","哪个基金比较好", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","给个靠谱的选择", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","想要个省心的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","挑个放心的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("E","有没有好的介绍", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
]

def main():
    out = []
    for i, (cat, q, expect) in enumerate(ITEMS, 1):
        out.append({
            "id": i,
            "category": cat,
            "question": q,
            "expect": expect,
        })
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nl_eval_set.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    # 分布统计
    from collections import Counter
    c = Counter(x["category"] for x in out)
    print(f"已写出 {len(out)} 条 -> {path}")
    print("意图分布:", dict(c))

if __name__ == "__main__":
    main()
