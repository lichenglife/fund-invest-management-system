# -*- coding: utf-8 -*-
"""
构建 NL 选基「对抗样本」评测集（自由表述）：60 条 gold standard。
用于压测规则兜底基线在真实自由表述上的下限，验证 >=85% SLA 是否需 LLM 增强。
输出：/workspace/nl_eval_set_adv.json
类别：
  K 口语化/俚语
  L 省略/跨句指代
  M 错别字/谐音
  N 中英混用
  O 非标准数字表述
  P 组合自由表述
schema 同基线：{clarify, type[], window, factors{...}, exclude[]}
"""
import json, os

ADV = [
    # ===== K 口语化/俚语 (15) =====
    ("K","别让我血本无归，稳点儿的混合基", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),
    ("K","想找个能睡着觉的基金，别太刺激", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("K","不想天天盯盘，躺赢那种股票基", dict(clarify=False,type=["stock"],window=None,factors={"volatility_le":0.10},exclude=[])),
    ("K","有没有涨得多跌得少的，拿久了不心慌的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("K","想要个买了不用操心的混合", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("K","回撤别太狠，收益还过得去的主动混合", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15,"return_rank_ge":0.20},exclude=[])),
    ("K","别坐过山车，稳稳的债基", dict(clarify=False,type=["bond"],window=None,factors={"volatility_le":0.10},exclude=[])),
    ("K","亏也别亏太多，每年能赚个七八个点的混合", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15,"annual_return_ge":0.07},exclude=[])),
    ("K","就想稳稳增值，别大起大落的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("K","找个波动不大的，长期拿着省心的债券", dict(clarify=False,type=["bond"],window=None,factors={"volatility_le":0.10},exclude=[])),
    ("K","收益别太拉胯，回撤控住的股票基", dict(clarify=False,type=["stock"],window=None,factors={"return_rank_ge":0.20,"max_drawdown_le":0.15},exclude=[])),
    ("K","别整那些花里胡哨的，老实债基就行", dict(clarify=False,type=["bond"],window=None,factors={},exclude=[])),
    ("K","想抄个底，跌透了再说的那种", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("K","要个能跑赢通胀的，稳当点的混合", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),
    ("K","别一把亏光，慢慢涨的混合基", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),

    # ===== L 省略/跨句指代 (10) =====
    ("L","就要昨天聊那种，回撤别太大的", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("L","跟上面那个差不多，但别碰白酒", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("L","还是买混合吧，规模别太小", dict(clarify=False,type=["mixed"],window=None,factors={"scale_min":2.0},exclude=[])),
    ("L","换成指数，去掉金融地产", dict(clarify=False,type=["index"],window=None,factors={},exclude=["金融","地产"])),
    ("L","还是股票，回撤压到10%以内", dict(clarify=False,type=["stock"],window=None,factors={"max_drawdown_le":0.10},exclude=[])),
    ("L","那个沪深300的，别要金融", dict(clarify=False,type=["index"],window=None,factors={},exclude=["金融"])),
    ("L","换QDII，别碰原油", dict(clarify=False,type=["qdii"],window=None,factors={},exclude=["原油"])),
    ("L","还是债基，规模大点的", dict(clarify=False,type=["bond"],window=None,factors={"scale_min":50.0},exclude=[])),
    ("L","跟刚才一样，但别买新能源", dict(clarify=True,type=[],window=None,factors={},exclude=[])),
    ("L","就要前面说的主动混合，回撤小点", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),

    # ===== M 错别字/谐音 (10) =====
    ("M","近san年huode高、回撤小的混和基", dict(clarify=False,type=["mixed"],window="3y",factors={"return_rank_ge":0.20,"max_drawdown_le":0.15},exclude=[])),
    ("M","规莫适中的股票鸡", dict(clarify=False,type=["stock"],window=None,factors={"scale_min":2.0,"scale_max":50.0},exclude=[])),
    ("M","近一念收益考前的主动股混", dict(clarify=False,type=["mixed"],window="1y",factors={"return_rank_ge":0.20},exclude=[])),
    ("M","回撤控住在士个点以内的债券", dict(clarify=False,type=["bond"],window=None,factors={"max_drawdown_le":0.10},exclude=[])),
    ("M","想买点主动混和，别碰白九", dict(clarify=False,type=["mixed"],window=None,factors={},exclude=["白酒"])),
    ("M","夏普高一点，回撤别大的股票基", dict(clarify=False,type=["stock"],window=None,factors={"sharpe_ge":1.0,"max_drawdown_le":0.15},exclude=[])),
    ("M","规模再2到50忆的混合", dict(clarify=False,type=["mixed"],window=None,factors={"scale_min":2.0,"scale_max":50.0},exclude=[])),
    ("M","近三年收溢排名前百份之二十的混合", dict(clarify=False,type=["mixed"],window="3y",factors={"return_rank_ge":0.20},exclude=[])),
    ("M","波懂小一点的指数鸡", dict(clarify=False,type=["index"],window=None,factors={"volatility_le":0.10},exclude=[])),
    ("M","年化收溢八个点以上的债基", dict(clarify=False,type=["bond"],window=None,factors={"annual_return_ge":0.08},exclude=[])),

    # ===== N 中英混用 (8) =====
    ("N","要个 low risk 的混合基金", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),
    ("N","sharpe 高一点，回撤小的股票", dict(clarify=False,type=["stock"],window=None,factors={"sharpe_ge":1.0,"max_drawdown_le":0.15},exclude=[])),
    ("N","近一年 high return 的混合", dict(clarify=False,type=["mixed"],window="1y",factors={"return_rank_ge":0.20},exclude=[])),
    ("N","ETF 别太 volatile，规模大些", dict(clarify=False,type=["etf"],window=None,factors={"volatility_le":0.10,"scale_min":50.0},exclude=[])),
    ("N","要 beta 低的宽基", dict(clarify=False,type=["index"],window=None,factors={},exclude=[])),
    ("N","long term 持有，稳点的债基", dict(clarify=False,type=["bond"],window="since",factors={"max_drawdown_le":0.15},exclude=[])),
    ("N","short 回撤的混合基", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),
    ("N","收益 top 20% 的股票基", dict(clarify=False,type=["stock"],window=None,factors={"return_rank_ge":0.20},exclude=[])),

    # ===== O 非标准数字表述 (7) =====
    ("O","回撤十几个点以内的混合", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15},exclude=[])),
    ("O","收益前百分之二十的混合", dict(clarify=False,type=["mixed"],window=None,factors={"return_rank_ge":0.20},exclude=[])),
    ("O","规模两三个亿到五十亿的混合", dict(clarify=False,type=["mixed"],window=None,factors={"scale_min":2.0,"scale_max":50.0},exclude=[])),
    ("O","年化十个点以上的债基", dict(clarify=False,type=["bond"],window=None,factors={"annual_return_ge":0.10},exclude=[])),
    ("O","夏普一点五以上的股票", dict(clarify=False,type=["stock"],window=None,factors={"sharpe_ge":1.5},exclude=[])),
    ("O","回撤不超过两成的混合", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.20},exclude=[])),
    ("O","规模小几亿的混合", dict(clarify=False,type=["mixed"],window=None,factors={"scale_max":5.0},exclude=[])),

    # ===== P 组合自由表述 (10) =====
    ("P","近一年别太刺激、能跑赢余额宝两三倍、别买新能源的混合", dict(clarify=False,type=["mixed"],window="1y",factors={"return_rank_ge":0.20},exclude=["新能源"])),
    ("P","想找个波动小、长期拿着、别碰券商的债券", dict(clarify=False,type=["bond"],window="since",factors={"volatility_le":0.10},exclude=["券商"])),
    ("P","收益高回撤低、规模适中、不要医药的混合", dict(clarify=False,type=["mixed"],window=None,factors={"return_rank_ge":0.20,"max_drawdown_le":0.15,"scale_min":2.0,"scale_max":50.0},exclude=["医药"])),
    ("P","近三年涨得多跌得少、别买军工和半导体的股混", dict(clarify=False,type=["mixed"],window="3y",factors={"return_rank_ge":0.20,"max_drawdown_le":0.15},exclude=["军工","半导体"])),
    ("P","不想亏钱、每年稳稳赚个五个点、别碰地产的混合", dict(clarify=False,type=["mixed"],window=None,factors={"max_drawdown_le":0.15,"annual_return_ge":0.05},exclude=["地产"])),
    ("P","近一年回撤别超十个点、收益排前30%、别买白酒的混合", dict(clarify=False,type=["mixed"],window="1y",factors={"max_drawdown_le":0.10,"return_rank_ge":0.30},exclude=["白酒"])),
    ("P","就要那种稳健、规模别太大的债券", dict(clarify=False,type=["bond"],window=None,factors={"max_drawdown_le":0.15,"scale_min":2.0},exclude=[])),
    ("P","别重仓单一行业、分散点的混合", dict(clarify=False,type=["mixed"],window=None,factors={},exclude=[])),
    ("P","近五年回撤小、夏普高、别碰新能源半导体的主动股票", dict(clarify=False,type=["stock"],window="5y",factors={"max_drawdown_le":0.15,"sharpe_ge":1.0},exclude=["新能源","半导体"])),
    ("P","长期拿着、收益别太差、回撤控住的宽基", dict(clarify=False,type=["index"],window="since",factors={"return_rank_ge":0.20,"max_drawdown_le":0.15},exclude=[])),
]


def main():
    out = []
    for i, (cat, q, expect) in enumerate(ADV, 1):
        out.append({"id": i, "category": cat, "question": q, "expect": expect})
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nl_eval_set_adv.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    from collections import Counter
    c = Counter(x["category"] for x in out)
    print(f"已写出对抗样本 {len(out)} 条 -> {path}")
    print("类别分布:", dict(c))


if __name__ == "__main__":
    main()
