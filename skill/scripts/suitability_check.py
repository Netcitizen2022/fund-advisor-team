#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suitability_check.py — 适当性硬闸门  v1.1  (fund-advisor-team v2.2)
================================================================================
作用：在生成对外报告【之前】强制校验，拦下以下五类问题：
  1. 风险错配：成份基金风险等级 > 客户风险等级上限（如把 R4 股基塞进 R2 组合）
  2. 回撤越线：组合【实测】最大回撤 深于 客户风险等级红线
              （R2 红线取 -10%，对应 EXP-PI-001：R2 行为容忍约 -8%~-10%）
  3. 承诺违规：报告文本出现"保本/稳赚/一定涨"等合规禁语
  4.〔v1.1 新增〕集中度越界：单一主题/风格暴露 > 阈值（默认 50%）。
              抓「三只都是 AI」这类伪分散——相关性矩阵看不出、危机里一起崩（FA-PI002 教训）
  5.〔v1.1 新增〕经验收紧：首次权益投资者 / R1-R2 客户，回撤红线自动再收紧 tighten_pp
              （默认 5 个百分点），把 EXP-PI-001 的经验从「文字」变成「代码闸门」

设计原则：宁可误拦，不可放过。任何一条 FAIL → 不得调用 generate_report.py。

v1.1 变更（v2.2 强制执行版）：
  - 新增 concentration_check() + _infer_theme()：主题/风格集中度闸门
  - check() 新增 first_time_equity / experience / concentration_limit / tighten_pp 参数
  - 经验收紧逻辑内嵌进有效回撤红线计算（EXP-PI-001 代码化）
  - 所有新增项均向后兼容：旧调用（不传新参数）行为不变

可独立测试：
  python3 suitability_check.py --selftest
================================================================================
"""
from __future__ import annotations
import argparse
import json
import sys

# 客户风险等级 → {允许持有的单基金最高风险, 组合最大回撤红线(负数)}
RISK_BAND = {
    "R1": {"max_fund_risk": "R1", "max_dd": -0.05},
    "R2": {"max_fund_risk": "R3", "max_dd": -0.10},  # R2行为容忍约-8~-10%（EXP-PI-001）
    "R3": {"max_fund_risk": "R4", "max_dd": -0.18},
    "R4": {"max_fund_risk": "R5", "max_dd": -0.30},
    "R5": {"max_fund_risk": "R5", "max_dd": -0.50},
}

_RISK_RANK = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}

# 合规禁语（出现在面向客户文本中即违规）
BANNED_PHRASES = ["保本", "稳赚", "一定涨", "保证收益", "稳赚不赔", "包赚", "零风险", "必涨", "无风险高收益"]

# 基金类型 → 默认风险等级（当 fund 未显式标 risk_level 时的保守推断）
TYPE_DEFAULT_RISK = {
    "货币": "R1", "货基": "R1",
    "纯债": "R2", "一级债基": "R2", "债基": "R2",
    "二级债基": "R3", "固收+": "R3", "偏债混合": "R3", "红利": "R3",
    "平衡混合": "R4", "主动混合": "R4", "指数ETF": "R4", "ETF": "R4", "偏股混合": "R4",
    "主动股基": "R5", "QDII": "R4", "黄金": "R3", "商品": "R4",
}

# ── v1.1：主题/风格集中度 ──────────────────────────────────────────────────────
# 主题标签 → 命中关键词（在 fund 的 name + type + theme 字段里扫描）。
# 设计意图：抓「主动+被动双核但其实是同一个主题」的伪分散。固收/现金/对冲类
# 不计入「权益主题集中度」（它们本就是用来分散权益的，集中持有不构成同向风险）。
THEME_KEYWORDS = {
    "科技AI成长": ["科技", "人工智能", "AI", "智能", "芯片", "半导体", "创新", "信息", "计算机", "软件", "数字", "元宇宙"],
    "新能源车":  ["新能源", "光伏", "电池", "储能", "锂", "汽车", "智能车", "风电"],
    "医药生物":  ["医药", "医疗", "生物", "创新药", "CXO", "器械"],
    "消费":      ["消费", "白酒", "食品饮料", "家电", "免税", "旅游"],
    "红利价值":  ["红利", "价值", "高股息", "央企", "国企改革", "低估值"],
    "周期资源":  ["周期", "有色", "煤炭", "钢铁", "化工", "资源", "石油"],
    "金融地产":  ["金融", "银行", "证券", "保险", "地产", "房"],
    "军工":      ["军工", "国防", "航空", "航天"],
}
# 不计入「权益主题集中度」的资产大类关键词（这些是分散/压舱用途）
NON_EQUITY_THEME_KEYWORDS = ["债", "固收", "货币", "货基", "黄金", "商品", "现金"]


def _infer_theme(fund: dict) -> str | None:
    """
    从 type(权威) + name + 显式 theme 字段推断主题标签。
    固收/现金/商品(黄金)类返回 None（不计权益主题集中度——它们是分散/压舱工具）。
    刻意【不】扫描 highlight 等营销文案，避免「组合保险丝」误命中「保险」之类的假阳性。
    """
    type_blob = str(fund.get("type", ""))
    # 1) 类型层面先判非权益（authoritative）：type 含 债/固收/货币/黄金/商品/现金 → 不计集中度
    if any(kw in type_blob for kw in NON_EQUITY_THEME_KEYWORDS):
        return None
    # 2) 仅在 name + type + 显式 theme 字段里扫主题关键词（不含 highlight）
    blob = " ".join(str(fund.get(k, "")) for k in ("name", "type", "theme"))
    for kw in NON_EQUITY_THEME_KEYWORDS:
        if kw in blob:
            return None
    for theme, kws in THEME_KEYWORDS.items():
        if any(kw in blob for kw in kws):
            return theme
    return "其他权益"


def concentration_check(funds: list, limit: float = 0.50) -> dict:
    """
    主题/风格集中度闸门。返回 {result, exposures, breaches}。
    exposures: {主题: 累计权重}；breaches: 超过 limit 的主题列表。
    口径：只统计权益类主题；固收/现金/对冲（黄金/商品）不计入集中度分母外，
          但也不计为某一主题的暴露——它们是分散工具。
    """
    from_pct = _PCT
    exposures: dict[str, float] = {}
    for f in funds:
        theme = _infer_theme(f)
        if theme is None:
            continue
        exposures[theme] = exposures.get(theme, 0.0) + from_pct(f.get("weight"))
    breaches = [(t, w) for t, w in exposures.items() if w > limit + 1e-9]
    return {
        "result": "FAIL" if breaches else "PASS",
        "limit": limit,
        "exposures": {t: round(w, 4) for t, w in sorted(exposures.items(),
                                                         key=lambda x: x[1], reverse=True)},
        "breaches": [{"theme": t, "exposure": round(w, 4)} for t, w in breaches],
    }


def _PCT(x) -> float:
    """'30%'/'0.3'/30 → 0.30（与 portfolio_math._pct 同口径，避免跨模块依赖）。"""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x) if x <= 1 else float(x) / 100.0
    s = str(x).strip().replace("%", "")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return v / 100.0 if "%" in str(x) or v > 1 else v


def _infer_fund_risk(fund: dict) -> str:
    """优先用 fund['risk_level']；缺失则按类型保守推断；都无法判断则按 R5（最高风险）"""
    rl = fund.get("risk_level")
    if rl in _RISK_RANK:
        return rl
    ftype = fund.get("type", "")
    for k, v in TYPE_DEFAULT_RISK.items():
        if k in ftype:
            return v
    return "R5"


def check(client_risk: str,
          funds: list,
          portfolio_max_dd: float | None = None,
          client_tolerance_dd: float | None = None,
          report_text: str = "",
          first_time_equity: bool = False,
          experience: str = "",
          concentration_limit: float = 0.50,
          tighten_pp: float = 0.05) -> dict:
    """
    client_risk        : "R1".."R5"
    funds              : [{name, code, type, risk_level?, weight, theme?}, ...]
    portfolio_max_dd   : 组合实测最大回撤（负数），来自 portfolio_math.summarize()
    client_tolerance_dd: 客户个体容忍回撤（负数，可选）；若提供则取它与等级红线中更严的一个
    report_text        : 待发报告全文（用于禁语扫描）
    first_time_equity  :〔v1.1〕首次权益投资者 → 触发回撤红线收紧（EXP-PI-001 代码化）
    experience         :〔v1.1〕客户经验描述（含"首次/纯理财/纯存款"等亦触发收紧）
    concentration_limit:〔v1.1〕单一权益主题暴露上限（默认 0.50）
    tighten_pp         :〔v1.1〕首次/低风险客户回撤红线收紧的百分点（默认 0.05）
    返回 {"result": "PASS"/"FAIL", "fails": [...], "warnings": [...], "checked": {...}}
    """
    if client_risk not in RISK_BAND:
        return {"result": "FAIL", "fails": [f"未知客户风险等级：{client_risk}"], "warnings": [], "checked": {}}

    band = RISK_BAND[client_risk]
    fails, warnings = [], []

    # 1) 风险错配
    for f in funds:
        fr = _infer_fund_risk(f)
        if _RISK_RANK[fr] > _RISK_RANK[band["max_fund_risk"]]:
            fails.append(
                f"风险错配：成份基金「{f.get('name', f.get('code', '?'))}」风险{fr} "
                f"超出 {client_risk} 客户允许上限 {band['max_fund_risk']}"
            )
        if not f.get("risk_level"):
            warnings.append(f"基金「{f.get('name', f.get('code','?'))}」未标 risk_level，"
                            f"已按类型保守推断为 {fr}，建议显式标注")

    # 2) 回撤越线（红线取 等级红线 / 客户个体容忍 / 经验收紧 三者中最严者）
    base_dd_limit = band["max_dd"]
    if client_tolerance_dd is not None:
        base_dd_limit = max(base_dd_limit, client_tolerance_dd)  # 更接近0=更严

    # 〔v1.1〕经验收紧（EXP-PI-001 代码化）：首次权益 或 R1/R2 客户，红线再收紧 tighten_pp
    exp_blob = str(experience or "")
    exp_triggers_tighten = first_time_equity or any(
        kw in exp_blob for kw in ("首次", "纯理财", "纯存款", "没买过", "未买过")
    )
    # R1=资本保全本就最严，自动收紧；R2 不一刀切（避免误拦正常稳健组合），
    # 仅当带「首次/纯理财」等明确低经验信号时才收紧（EXP-PI-001 的真实触发条件）。
    risk_triggers_tighten = client_risk == "R1"
    tightening_applied = exp_triggers_tighten or risk_triggers_tighten
    effective_dd_limit = base_dd_limit
    tighten_reason = None
    if tightening_applied:
        effective_dd_limit = base_dd_limit + tighten_pp  # 负数 + 正数 → 更接近0 → 更严
        why = []
        if exp_triggers_tighten:
            why.append("首次权益投资者")
        if risk_triggers_tighten:
            why.append(f"{client_risk}保守客户")
        tighten_reason = (f"经验收紧(EXP-PI-001)：因{'/'.join(why)}，"
                          f"回撤红线由 {base_dd_limit:.0%} 收紧 {tighten_pp:.0%} 至 {effective_dd_limit:.0%}")
        warnings.append(tighten_reason)

    if portfolio_max_dd is not None:
        if portfolio_max_dd < effective_dd_limit:  # 实测更深
            fails.append(
                f"回撤越线：组合实测最大回撤 {portfolio_max_dd:.1%} "
                f"深于 {client_risk} 有效红线 {effective_dd_limit:.1%}"
                + ("（已含经验收紧）" if tightening_applied else "")
            )
    else:
        warnings.append("未提供组合实测最大回撤，跳过回撤校验——强烈建议先跑 portfolio_math")

    # 3) 承诺违规
    for w in BANNED_PHRASES:
        if w in (report_text or ""):
            fails.append(f"合规禁语：报告中出现承诺性表述「{w}」，必须删除并改为合规表达")

    # 4)〔v1.1〕主题/风格集中度
    conc = concentration_check(funds, limit=concentration_limit)
    if conc["result"] == "FAIL":
        for b in conc["breaches"]:
            fails.append(
                f"集中度越界：「{b['theme']}」主题暴露 {b['exposure']:.0%} "
                f"超过上限 {concentration_limit:.0%}——相关性矩阵看不出的伪分散，"
                f"危机期同向风险（FA-PI002 教训）"
            )

    return {
        "result": "PASS" if not fails else "FAIL",
        "fails": fails,
        "warnings": warnings,
        "checked": {
            "client_risk": client_risk,
            "max_fund_risk_allowed": band["max_fund_risk"],
            "base_dd_limit": base_dd_limit,
            "effective_dd_limit": effective_dd_limit,
            "tightening_applied": tightening_applied,
            "tightening_reason": tighten_reason,
            "portfolio_max_dd": portfolio_max_dd,
            "concentration": conc,
            "n_funds": len(funds),
        },
    }


def print_report(res: dict) -> None:
    mark = "✅ PASS" if res["result"] == "PASS" else "❌ FAIL"
    print(f"\n──────── 适当性校验：{mark} ────────")
    if res["fails"]:
        print("【拦截项】")
        for x in res["fails"]:
            print(f"  ✗ {x}")
    if res["warnings"]:
        print("【提示】")
        for x in res["warnings"]:
            print(f"  ! {x}")
    c = res["checked"]
    if c:
        print(f"【口径】客户{c.get('client_risk')} / 单基金上限{c.get('max_fund_risk_allowed')} / "
              f"回撤基线{c.get('base_dd_limit')}→有效{c.get('effective_dd_limit')} / "
              f"实测回撤{c.get('portfolio_max_dd')} / 成份{c.get('n_funds')}只")
        if c.get("tightening_applied"):
            print(f"        ↳ {c.get('tightening_reason')}")
        conc = c.get("concentration", {})
        if conc.get("exposures"):
            exp_str = "，".join(f"{t} {w:.0%}" for t, w in conc["exposures"].items())
            print(f"        ↳ 权益主题暴露：{exp_str}（上限{conc.get('limit', 0.5):.0%}）")
    print("────────────────────────────────\n")


def _selftest():
    print("=== suitability_check 自测 ===")

    # 用例1：R4 股基塞进 R2 → 必须 FAIL（这正是包里回归测试的硬矛盾）
    bad_funds = [
        {"name": "易方达蓝筹精选", "code": "005827", "type": "主动混合", "risk_level": "R4", "weight": "30%"},
        {"name": "沪深300ETF", "code": "510300", "type": "指数ETF", "risk_level": "R4", "weight": "25%"},
    ]
    r1 = check("R2", bad_funds, portfolio_max_dd=-0.28)
    assert r1["result"] == "FAIL", "应拦下R4进R2"
    assert any("风险错配" in x for x in r1["fails"])
    assert any("回撤越线" in x for x in r1["fails"])
    print(f"[OK] R4股基进R2组合 → FAIL（{len(r1['fails'])}项拦截）")

    # 用例2：合规的 R2 组合 → PASS
    good_funds = [
        {"name": "博时稳健回报", "code": "050019", "type": "一级债基", "risk_level": "R2", "weight": "30%"},
        {"name": "博时恒泰债券", "code": "007543", "type": "纯债",     "risk_level": "R2", "weight": "40%"},
        {"name": "中证红利ETF联接", "code": "012643", "type": "红利",  "risk_level": "R3", "weight": "20%"},
        {"name": "华安黄金ETF联接", "code": "000216", "type": "黄金",  "risk_level": "R3", "weight": "10%"},
    ]
    r2 = check("R2", good_funds, portfolio_max_dd=-0.08, report_text="本组合稳健配置，主动揭示风险。")
    assert r2["result"] == "PASS", f"合规组合不应FAIL: {r2['fails']}"
    print(f"[OK] 合规R2组合 → PASS")

    # 用例3：禁语拦截
    r3 = check("R2", good_funds, portfolio_max_dd=-0.08, report_text="本产品保本稳赚，一定涨。")
    assert r3["result"] == "FAIL" and any("禁语" in x for x in r3["fails"])
    print(f"[OK] 承诺禁语 → FAIL（命中{sum('禁语' in x for x in r3['fails'])}处）")

    # 用例4：客户个体容忍更严时以个体为准
    r4 = check("R2", good_funds, portfolio_max_dd=-0.09, client_tolerance_dd=-0.07)
    assert r4["result"] == "FAIL", "个体容忍-7%应拦下-9%组合"
    print(f"[OK] 个体容忍线(-7%)严于等级红线 → 正确拦截-9%组合")

    # 用例5：未标 risk_level 时保守推断 + 提示
    r5 = check("R2", [{"name": "某股基", "code": "999999", "type": "主动股基", "weight": "30%"}],
               portfolio_max_dd=-0.05)
    assert r5["result"] == "FAIL"  # 主动股基→R5→超R2
    assert any("保守推断" in x for x in r5["warnings"])
    print(f"[OK] 缺risk_level → 按类型保守推断为R5并提示")

    # ── v1.1 新增用例 ───────────────────────────────────────────────────────
    # 用例6：PI002 式集中度——R4客户、单基金风险合规、回撤在档内，但 80% 同主题 → FAIL
    pi002_funds = [
        {"name": "富国创新科技A", "code": "016619", "type": "主动权益·科技成长", "risk_level": "R4", "weight": "35%"},
        {"name": "易方达人工智能ETF联接A", "code": "012733", "type": "被动指数·AI主题ETF", "risk_level": "R4", "weight": "25%"},
        {"name": "大成科技创新A", "code": "001654", "type": "主动权益·科技+先进制造", "risk_level": "R4", "weight": "20%"},
        {"name": "中证红利ETF联接A", "code": "012643", "type": "被动指数·高股息红利", "risk_level": "R3", "weight": "10%"},
    ]
    r6 = check("R4", pi002_funds, portfolio_max_dd=-0.20)  # 回撤在R4档(-0.30)内
    assert r6["result"] == "FAIL", "80% 同主题应被集中度闸门拦下"
    assert any("集中度越界" in x for x in r6["fails"])
    conc = r6["checked"]["concentration"]
    assert conc["exposures"].get("科技AI成长", 0) >= 0.79, f"科技暴露应≈80%: {conc['exposures']}"
    print(f"[OK] PI002式 80%科技单主题 → 集中度 FAIL（科技暴露 {conc['exposures'].get('科技AI成长'):.0%}）")

    # 用例7：经验收紧——R4 首次投资者，组合回撤 -28%。不收紧本会PASS(-30档)，收紧5pp→-25%→FAIL
    diversified_r4 = [
        {"name": "某科技基", "code": "A1", "type": "主动权益·科技", "risk_level": "R4", "weight": "30%"},
        {"name": "某医药基", "code": "A2", "type": "主动权益·医药", "risk_level": "R4", "weight": "25%"},
        {"name": "某红利基", "code": "A3", "type": "红利价值", "risk_level": "R3", "weight": "25%"},
        {"name": "某债基",   "code": "A4", "type": "纯债",     "risk_level": "R2", "weight": "20%"},
    ]
    r7_no = check("R4", diversified_r4, portfolio_max_dd=-0.28)  # 非首次
    assert r7_no["result"] == "PASS", f"非首次R4 -28%应在档内PASS: {r7_no['fails']}"
    r7_yes = check("R4", diversified_r4, portfolio_max_dd=-0.28, first_time_equity=True)
    assert r7_yes["result"] == "FAIL", "首次投资者应触发收紧并拦下-28%"
    assert r7_yes["checked"]["tightening_applied"]
    print(f"[OK] 经验收紧：同组合 -28% 非首次PASS / 首次FAIL（红线 "
          f"{r7_no['checked']['effective_dd_limit']:.0%}→{r7_yes['checked']['effective_dd_limit']:.0%}）")

    # 用例8：合规的分散 R4 组合（多主题、非首次、回撤在档）→ PASS（证明不是一律拦截）
    r8 = check("R4", diversified_r4, portfolio_max_dd=-0.22,
               report_text="本组合分散配置，主动揭示风险。")
    assert r8["result"] == "PASS", f"分散合规R4不应FAIL: {r8['fails']}"
    print(f"[OK] 分散多主题R4组合 → PASS（科技暴露 "
          f"{r8['checked']['concentration']['exposures'].get('其他权益', r8['checked']['concentration']['exposures'].get('科技AI成长', 0)):.0%} < 50%）")

    print("=== 全部自测通过 ✓ ===")


def _cli():
    p = argparse.ArgumentParser(description="适当性硬闸门")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--json", help="输入 JSON：{client_risk, funds, portfolio_max_dd, report_text}")
    args = p.parse_args()
    if args.selftest:
        _selftest()
        return
    if args.json:
        with open(args.json, "r", encoding="utf-8") as f:
            d = json.load(f)
        res = check(d.get("client_risk"), d.get("funds", []),
                    d.get("portfolio_max_dd"), d.get("client_tolerance_dd"),
                    d.get("report_text", ""))
        print_report(res)
        sys.exit(0 if res["result"] == "PASS" else 2)  # 非0退出码方便脚本串联
    print("用法： python3 suitability_check.py --selftest   或   --json input.json")


if __name__ == "__main__":
    _cli()
