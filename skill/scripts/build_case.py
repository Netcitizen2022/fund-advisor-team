#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_case.py — 案例编排器（新前门）  v1.0  (fund-advisor-team v2.1)
================================================================================
把 fetch → math → suitability 串成一条链，产出：
  1) enriched fund_data.json（含 computed 块：每个钱的数字 + 计算方法 + as_of）
  2) 终端"数字体检报告"（人看：所有计算结果 + 来源 + 适当性 PASS/FAIL）
  3) 可选：体检 PASS 后调用既有 generate_report.py 出 docx（--with-report）

设计意图：generate_report.py 里写死的那些数字（-12%、75万亿、各分层影响…），
         今后应改为读取本步产出的 computed 块（见 DEPLOY_AND_INTEGRATE.md 的接线说明）。
         在完成那次改造前，本编排器已能提供：真实计算数字 + 适当性闸门 + 来源报告。

输入 case JSON 格式（references/fund_data_sample_v2.json 即为合规示例）：
{
  "client": {"name":"张女士","risk_level":"R2","capital":"100万元",
             "investment_period":"3年","tolerance_dd":-0.09,
             "rebalance":"none","pain_point":"存款搬家，稳健增值"},
  "funds": [{"name":..,"code":..,"type":..,"manager":..,"risk_level":"R2",
             "weight":"30%","layer":"核心层","highlight":..}, ...]
}

用法：
  在线：  python3 build_case.py --case case.json --out_dir output/FA-.../
  离线：  python3 build_case.py --case case.json --out_dir output/FA-.../ --offline
          （--offline 直接用 references/nav_cache/<code>.csv，不联网；测试/复算用）
  出报告：再加 --with-report （需 document-suite 已部署）
================================================================================
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import portfolio_math as pm           # noqa: E402
import suitability_check as sc        # noqa: E402


def _load_navs(funds: list, offline: bool) -> dict:
    """返回 {code: nav Series}。offline 用缓存 CSV；在线用 fetch_fund_data。"""
    codes = [f["code"] for f in funds]
    if offline:
        import fetch_fund_data as ff
        out = {}
        missing = []
        for c in codes:
            s = ff.load_cached_nav(c)
            if s is None:
                missing.append(c)
            else:
                out[c] = s
        if missing:
            raise SystemExit(f"[离线] 缺少净值缓存：{missing}\n  先在线跑： "
                             f"python3 fetch_fund_data.py --codes {' '.join(codes)}")
        return out
    else:
        import fetch_fund_data as ff
        navs = ff.fetch_and_cache(codes)
        miss = [c for c in codes if c not in navs]
        if miss:
            raise SystemExit(f"[在线] 以下基金无法获取净值且无缓存：{miss}")
        return navs


def run(case_path: str, out_dir: str, offline: bool = False, with_report: bool = False):
    with open(case_path, "r", encoding="utf-8") as f:
        case = json.load(f)
    client = case.get("client", {})
    funds = case.get("funds", [])
    if not funds:
        raise SystemExit("case 文件 funds 为空")

    os.makedirs(out_dir, exist_ok=True)
    rebalance = client.get("rebalance", "none")

    # ① 取净值
    navs = _load_navs(funds, offline)

    # ② 组合数学
    computed = pm.summarize(navs, funds, rebalance=rebalance)

    # 黄金/对冲层边际作用：若组合含对冲层，自动算其对回撤的实测贡献
    hedge = [f for f in funds if "对冲" in f.get("layer", "") or "黄金" in f.get("type", "")]
    if hedge and len(funds) > 1:
        try:
            computed["对冲层边际作用"] = pm.marginal_contribution(navs, funds, hedge[0]["code"], rebalance)
        except Exception as e:
            computed["对冲层边际作用"] = {"_error": str(e)}

    # ③ 适当性闸门（用实测最大回撤）
    suit = sc.check(
        client.get("risk_level", "R5"),
        funds,
        portfolio_max_dd=computed["组合_历史最大回撤"],
        client_tolerance_dd=client.get("tolerance_dd"),
        report_text="",  # 报告正文生成后可再扫一次禁语
    )

    # ④ 写 enriched JSON（report 脚本将从这里读数字）
    enriched = {
        "as_of": str(date.today()),
        "client": client,
        "funds": funds,
        "computed": computed,
        "suitability": suit,
    }
    enriched_path = os.path.join(out_dir, "fund_data_enriched.json")
    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    # ⑤ 数字体检报告（终端）
    _print_health_report(client, funds, computed, suit, enriched_path)

    # ⑥ 可选出报告
    if with_report:
        if suit["result"] != "PASS":
            print("⛔ 适当性未通过，已【阻止】生成对外报告。请先修正组合后重试。")
            sys.exit(2)
        _invoke_generate_report(client, enriched_path, out_dir)

    return enriched


def _fmt_pct(x):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:+.2%}"


def _print_health_report(client, funds, computed, suit, enriched_path):
    print("\n" + "=" * 64)
    print(f"  数字体检报告  |  {client.get('name','(未命名)')}  |  {client.get('risk_level','?')}  "
          f"|  {computed['as_of']}")
    print("=" * 64)
    print(f"数据区间：{computed['数据区间']}  ({computed['有效交易日数']}个交易日, {computed['再平衡方式']})")
    print(f"计算方法：{computed['计算方法']}")
    print("-" * 64)
    print("【组合层面 · 全部为实测/历史模拟，非承诺】")
    print(f"  年化收益(历史)      {_fmt_pct(computed['组合_年化收益_历史'])}")
    print(f"  区间累计收益        {_fmt_pct(computed['组合_区间累计收益'])}")
    print(f"  年化波动率          {_fmt_pct(computed['组合_年化波动率'])}")
    print(f"  历史最大回撤        {_fmt_pct(computed['组合_历史最大回撤'])}   ← 报告'最大可能亏损'用此")
    print(f"  最差滚动1年收益     {_fmt_pct(computed['组合_最差滚动1年收益'])}")
    print(f"  20日95%历史VaR      {_fmt_pct(computed['组合_20日95%历史VaR'])}")
    fwd = computed.get("远期收益估计", {})
    print(f"  远期预期年化(假设)  {_fmt_pct(fwd.get('远期预期年化(假设)'))}   ← 基于显式CMA，与历史分开")

    print("-" * 64)
    print("【分层指标 · 报告各层影响用此（独立回撤≠组合影响，看'最坏加权影响'）】")
    for layer, m in (computed.get("分层指标") or {}).items():
        if not m or "_error" in (m or {}):
            print(f"  {layer:<8} 无法计算（成份缺数据）")
        else:
            print(f"  {layer:<8} 权重{_fmt_pct(m['层权重'])}  独立年化{_fmt_pct(m['层内独立年化'])}  "
                  f"独立回撤{_fmt_pct(m['层内独立最大回撤'])}  最坏加权影响{_fmt_pct(m['最坏加权影响'])}")

    mc = computed.get("对冲层边际作用")
    if mc and "_error" not in mc:
        print("-" * 64)
        print("【对冲层边际作用 · 替代'黄金把回撤从X压到Y'的口述】")
        print(f"  含对冲层最大回撤   {_fmt_pct(mc['最大回撤_含'])}")
        print(f"  剔除后最大回撤     {_fmt_pct(mc['最大回撤_不含'])}")
        print(f"  回撤改善(实测)     {_fmt_pct(mc['最大回撤_改善'])}  (正=回撤变浅)")

    print("-" * 64)
    print("【历史情景回测 · None=该区间有基金尚未成立，不可回测】")
    for label, m in (computed.get("历史情景回测") or {}).items():
        if m is None:
            print(f"  {label:<10} 不可回测")
        else:
            print(f"  {label:<10} 区间收益{_fmt_pct(m['区间收益'])}  最大回撤{_fmt_pct(m['区间最大回撤'])}")

    sc.print_report(suit)
    print(f"📄 enriched 数据已写入：{enriched_path}")
    print("   （generate_report.py 应从此文件的 computed 块读取数字，不再写死）\n")


def _invoke_generate_report(client, enriched_path, out_dir):
    """调用既有 v2.0 报告脚本（需 document-suite）。命令行参数沿用其原接口。"""
    gen = os.path.join(HERE, "generate_report.py")
    if not os.path.exists(gen):
        print(f"[跳过出报告] 未找到 {gen}")
        return
    cmd = [sys.executable, gen,
           "--client_name", client.get("name", "客户"),
           "--risk_level", client.get("risk_level", "R2"),
           "--market_status", client.get("market_status", "谨慎"),
           "--funds_json", enriched_path,
           "--output_path", out_dir]
    print("→ 调用报告生成：", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print("✅ 报告生成完成。")
    else:
        print(f"⚠ 报告脚本返回码 {r.returncode}（多半是 document-suite 未部署或路径问题）。")


def _cli():
    p = argparse.ArgumentParser(description="案例编排器（fetch→math→suitability→report）")
    p.add_argument("--case", required=True, help="案例输入 JSON（client + funds）")
    p.add_argument("--out_dir", required=True, help="输出目录 output/<案例ID>/")
    p.add_argument("--offline", action="store_true", help="用本地净值缓存，不联网（测试/复算）")
    p.add_argument("--with-report", action="store_true", help="体检PASS后调用 generate_report.py")
    args = p.parse_args()
    run(args.case, args.out_dir, offline=args.offline, with_report=args.with_report)


if __name__ == "__main__":
    _cli()
