# -*- coding: utf-8 -*-
"""
NL 选基基线解析器（规则兜底 floor，无 LLM）+ 评测脚本。
读取 nl_eval_set.json，对照 gold standard 计算准确率，验证 >=85% SLA 是否可达。

说明：这是「规则兜底层」基线，代表没有 LLM 增强时的最低下限。
生产解析器 = 本规则层 + LLM 语义解析 + 歧义反问（DC-004），预期在自由表述上显著更高。
"""
import json, os, re

# ---------- 词典 ----------
TYPE_KW = {
    "etf": ["ETF", "场内"],
    "index": ["指数", "宽基"],
    "stock": ["股票", "主动股票", "股票型"],
    "mixed": ["混合", "股混", "主动混合", "混合偏股"],
    "bond": ["债券", "债基", "纯债", "二级债", "债券型"],
    "qdii": ["QDII", "海外"],
    "money": ["货币", "货基"],
}
WINDOW_KW = [
    ("ytd", ["今年以来", "年内", "今年"]),
    ("since", ["成立以来", "长期持有", "长期业绩", "长期表现", "长期看"]),
    ("5y", ["近五年", "五年"]),
    ("3y", ["近三年", "三年"]),
    ("1y", ["近一年", "一年"]),
]
# 行业/主题词（长词优先，避免 新能源 误匹配 新能源车）
SECTORS = ["新能源车", "新能源", "美股科技", "半导体", "房地产", "地产", "军工",
           "医药", "白酒", "可转债", "城投", "互联网", "港股通", "原油", "黄金",
           "券商", "保险", "金融"]
NEG_VERBS = ["不要", "别碰", "别买", "不买", "剔除", "避开"]


def _nums(text):
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", text)]


def detect_type(text):
    types = set()
    for t, kws in TYPE_KW.items():
        if any(k in text for k in kws):
            types.add(t)
    if "etf" in types:
        types.discard("index")  # 宽基ETF/指数ETF 只归 etf
    return sorted(types)


def detect_window(text):
    for w, kws in WINDOW_KW:
        if any(k in text for k in kws):
            return w
    return None


def detect_factors(text):
    f = {}
    # 回撤：显式数字 -> max_drawdown_le；否则"小/低/控制好/收敛/抗跌/稳健" -> 默认 0.15
    m = re.search(r"回撤[^，。、]*?(\d+(?:\.\d+)?)\s*%", text)
    if m:
        f["max_drawdown_le"] = float(m.group(1)) / 100.0
    elif re.search(r"回撤(小|低|控制好|收敛)|抗跌|稳健", text):
        f["max_drawdown_le"] = 0.15
    # 收益排名前 X%
    m = re.search(r"收益排名前\s*(\d+)\s*%", text)
    if m:
        f["return_rank_ge"] = int(m.group(1)) / 100.0
    # 年化收益 X% 以上
    m = re.search(r"年化收益\s*(\d+(?:\.\d+)?)\s*%以上", text)
    if m:
        f["annual_return_ge"] = float(m.group(1)) / 100.0
    # 收益稳定 / 走势平稳 / 平稳 / 稳定 -> 波动默认 0.10
    if re.search(r"收益稳定|走势平稳|平稳|稳定", text):
        f["volatility_le"] = 0.10
    # 收益高/好/靠前/不错/累计收益高/长期业绩好（独立于"稳定"分支）
    if re.search(r"收益(高|好|靠前|不错)|累计收益高|长期业绩好|表现不错", text):
        f["return_rank_ge"] = f.get("return_rank_ge", 0.20)
    # 波动小/低/可控
    if re.search(r"波动(小|低|可控)", text):
        f["volatility_le"] = 0.10
    # 规模
    if "规模适中" in text:
        f["scale_min"], f["scale_max"] = 2.0, 50.0
    elif re.search(r"规模(大|百亿以上)|百亿", text):
        f["scale_min"] = 50.0
    elif re.search(r"规模小|迷你|5亿内", text):
        f["scale_max"] = 5.0
    m = re.search(r"规模在?\s*(\d+(?:\.\d+)?)\s*[-到]\s*(\d+(?:\.\d+)?)\s*亿", text)
    if m:
        f["scale_min"], f["scale_max"] = float(m.group(1)), float(m.group(2))
    # 夏普（允许"夏普高（大于1.5）"等间隔）
    m = re.search(r"夏普[^，。、%]*?(\d+(?:\.\d+)?)", text)
    if m:
        f["sharpe_ge"] = float(m.group(1))
    elif "夏普高" in text:
        f["sharpe_ge"] = 1.0
    return f


def detect_exclude(text):
    ex = []
    has_neg = any(v in text for v in NEG_VERBS)
    if not has_neg:
        return ex
    for s in SECTORS:
        if s in text:
            ex.append(s)
    # 长短去重：若某词是另一已匹配词子串（如 新能源⊂新能源车、地产⊂房地产），丢弃短词
    ex = [s for s in ex if not any(s != t and s in t for t in ex)]
    return ex


def nl_parse(question):
    """返回 dict: {clarify, type, window, factors, exclude}"""
    typ = detect_type(question)
    win = detect_window(question)
    fac = detect_factors(question)
    has_num = bool(_nums(question))  # 任何数字（规模/回撤/收益/夏普）
    # 反问规则：无类型 + 无区间 + 无数字阈值 -> 触发 Clarify
    clarify = (not typ) and (win is None) and (not has_num)
    if clarify:
        return {"clarify": True, "type": [], "window": None, "factors": {}, "exclude": []}
    return {"clarify": False, "type": typ, "window": win,
            "factors": fac, "exclude": detect_exclude(question)}


# ---------- 评估 ----------
FACTOR_TOL = {"ratio": 0.02, "scale": 1.0}


def factors_match(got, exp):
    gk, ek = set(got), set(exp)
    if gk != ek:
        return False, "key_diff"
    for k in gk:
        gv, ev = got[k], exp[k]
        tol = FACTOR_TOL["scale"] if "scale" in k else FACTOR_TOL["ratio"]
        if abs(gv - ev) > tol:
            return False, f"{k}:{gv}!={ev}"
    return True, ""


def evaluate(items):
    total = len(items)
    correct = exact = clarify_ok = 0
    lenient = 0  # type+window+exclude 对，因子容差
    by_cat = {}
    fails = []
    for it in items:
        cat = it["category"]
        exp = it["expect"]
        got = nl_parse(it["question"])
        by_cat.setdefault(cat, {"n": 0, "ok": 0, "exact": 0})
        by_cat[cat]["n"] += 1
        # clarify 一致性
        if exp["clarify"] and got["clarify"]:
            correct += 1; exact += 1; clarify_ok += 1
            by_cat[cat]["ok"] += 1; by_cat[cat]["exact"] += 1
            continue
        if exp["clarify"] != got["clarify"]:
            fails.append((it["id"], it["question"], "clarify", exp, got))
            continue
        # 结构化比较
        type_ok = sorted(exp["type"]) == sorted(got["type"])
        win_ok = exp["window"] == got["window"]
        excl_ok = sorted(exp["exclude"]) == sorted(got["exclude"])
        fac_ok, reason = factors_match(got["factors"], exp["factors"])
        if type_ok and win_ok and excl_ok and fac_ok:
            correct += 1; exact += 1
            by_cat[cat]["ok"] += 1; by_cat[cat]["exact"] += 1
        elif type_ok and win_ok and excl_ok:
            lenient += 1
            fails.append((it["id"], it["question"], "factor:" + reason, exp, got))
        else:
            fails.append((it["id"], it["question"],
                          f"type={type_ok},win={win_ok},excl={excl_ok},fac={fac_ok}", exp, got))
    return total, correct, exact, lenient, clarify_ok, by_cat, fails


def main():
    import sys
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nl_eval_set.json")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    label = sys.argv[2] if len(sys.argv) > 2 else "基线(结构化)"
    items = json.load(open(path, encoding="utf-8"))
    total, correct, exact, lenient, clarify_ok, by_cat, fails = evaluate(items)
    acc = correct / total
    print("=" * 60)
    print(f"NL 选基评测 [{label}]（规则兜底层，无 LLM）")
    print(f"样本数: {total}  |  目标 SLA: >= 85% (NL_ACCURACY_TARGET)")
    print("-" * 60)
    print(f"总体准确率(严格):       {acc*100:.1f}%   ({correct}/{total})")
    print(f"  其中 反问识别正确:     {clarify_ok}/{sum(1 for x in items if x['expect']['clarify'])}")
    print(f"  结构化完全匹配:       {exact}/{total-clarify_ok}")
    print(f"  结构化因子容差匹配+:  {lenient}  (type/window/exclude 对, 仅因子阈值差)")
    print(f"  宽松准确率(因子容差): {(correct+lenient)/total*100:.1f}%")
    print("-" * 60)
    print("分意图准确率:")
    for c in sorted(by_cat):
        d = by_cat[c]
        print(f"  {c}: {d['ok']}/{d['n']}  ({d['ok']/d['n']*100:.0f}%)")
    print("-" * 60)
    print(f"SLA 结论: {'✅ 可达 (>=85%)' if acc>=0.85 else '⚠️ 未达 (规则层地板即此，需 LLM 增强)'}")
    print("=" * 60)
    if fails:
        print(f"\n失败/容差样例 ({len(fails)} 条):")
        for fid, q, why, exp, got in fails[:12]:
            print(f"  #{fid} [{why}] {q}")
            print(f"     expect: {exp}")
            print(f"     got   : {got}")
    # 落盘报告（按输入文件名派生，避免互相覆盖）
    rep = {
        "total": total, "correct": correct, "exact": exact, "lenient": lenient,
        "clarify_ok": clarify_ok, "accuracy_strict": round(acc, 4),
        "accuracy_lenient": round((correct + lenient) / total, 4),
        "by_category": {c: by_cat[c]["ok"] / by_cat[c]["n"] for c in by_cat},
        "fails": [{"id": f[0], "q": f[1], "why": f[2], "expect": f[3], "got": f[4]} for f in fails],
    }
    stem = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{stem}_report.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n报告已写出: {out}")


if __name__ == "__main__":
    main()
