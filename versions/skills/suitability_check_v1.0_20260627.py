#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suitability_check.py — 适当性硬闸门  v1.0  (fund-advisor-team v2.1)
================================================================================
作用：在生成对外报告【之前】强制校验，拦下以下三类问题：
  1. 风险错配：成份基金风险等级 > 客户风险等级上限（如把 R4 股基塞进 R2 组合）
  2. 回撤越线：组合【实测】最大回撤 深于 客户风险等级红线
              （R2 红线取 -10%，对应 EXP-PI-001：R2 行为容忍约 -8%~-10%）
  3. 承诺违规：报告文本出现"保本/稳赚/一定涨"等合规禁语

设计原则：宁可误拦，不可放过。任何一条 FAIL → 不得调用 generate_report.py。

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
          report_text: str = "") -> dict:
    """
    client_risk        : "R1".."R5"
    funds              : [{name, code, type, risk_level?, weight}, ...]
    portfolio_max_dd   : 组合实测最大回撤（负数），来自 portfolio_math.summarize()
    client_tolerance_dd: 客户个体容忍回撤（负数，可选）；若提供则取它与等级红线中更严的一个
    report_text        : 待发报告全文（用于禁语扫描）
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

    # 2) 回撤越线（红线取 等级红线 与 客户个体容忍 中更严者）
    effective_dd_limit = band["max_dd"]
    if client_tolerance_dd is not None:
        effective_dd_limit = max(effective_dd_limit, client_tolerance_dd)  # 更接近0=更严
    if portfolio_max_dd is not None:
        if portfolio_max_dd < effective_dd_limit:  # 实测更深
            fails.append(
                f"回撤越线：组合实测最大回撤 {portfolio_max_dd:.1%} "
                f"深于 {client_risk} 红线 {effective_dd_limit:.0%}"
            )
    else:
        warnings.append("未提供组合实测最大回撤，跳过回撤校验——强烈建议先跑 portfolio_math")

    # 3) 承诺违规
    for w in BANNED_PHRASES:
        if w in (report_text or ""):
            fails.append(f"合规禁语：报告中出现承诺性表述「{w}」，必须删除并改为合规表达")

    return {
        "result": "PASS" if not fails else "FAIL",
        "fails": fails,
        "warnings": warnings,
        "checked": {
            "client_risk": client_risk,
            "max_fund_risk_allowed": band["max_fund_risk"],
            "effective_dd_limit": effective_dd_limit,
            "portfolio_max_dd": portfolio_max_dd,
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
              f"回撤红线{c.get('effective_dd_limit')} / 实测回撤{c.get('portfolio_max_dd')} / "
              f"成份{c.get('n_funds')}只")
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
