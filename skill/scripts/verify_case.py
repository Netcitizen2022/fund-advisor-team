#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_case.py — 案例回访验证  v1.0  (fund-advisor-team v2.1)
================================================================================
作用：让进化闭环真正转起来。给定案例的【推荐日期 + 组合】，自动：
  1) 拉取推荐日至今的真实净值，合成组合净值
  2) 算实际收益 / 实际最大回撤
  3) 与当初预测区间对比 → 判定 已验证 / 部分验证 / 证伪
  4) 打印结论（并可生成可粘贴进 cases_register.md 的回访行）

判定规则（可按需调整）：
  - 已验证 ：实际收益 落在预测年化区间内，且 实际回撤 不深于 预测回撤×1.2
  - 部分验证：收益或回撤之一达标
  - 证伪   ：实际回撤 深于 预测回撤×1.5  或  实际收益 大幅低于预测下限
  - 不可验证：数据不足（持有时间过短等）

用法：
  python3 verify_case.py --case_id FA-20260625-PI001 \
      --rec_date 2026-06-25 \
      --funds 050019:30 007543:40 012643:20 000216:10 \
      --pred_return_low 0.05 --pred_return_high 0.07 --pred_dd -0.08 \
      [--offline]
================================================================================
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import portfolio_math as pm  # noqa: E402


def _parse_funds(items: list) -> list:
    """['050019:30','007543:40'] → [{code,weight,...}]"""
    funds = []
    for it in items:
        code, w = it.split(":")
        funds.append({"code": code.strip(), "weight": f"{float(w)}%",
                      "layer": "未分类", "type": ""})
    return funds


def _load_navs_since(funds, rec_date, offline):
    import fetch_fund_data as ff
    codes = [f["code"] for f in funds]
    navs = {}
    if offline:
        for c in codes:
            s = ff.load_cached_nav(c)
            if s is None:
                raise SystemExit(f"[离线] 缺净值缓存 {c}，先在线缓存： "
                                 f"python3 fetch_fund_data.py --codes {' '.join(codes)}")
            navs[c] = s
    else:
        navs = ff.fetch_and_cache(codes)
    # 截取推荐日至今
    rec = pd.to_datetime(rec_date)
    out = {c: s.loc[s.index >= rec] for c, s in navs.items() if not s.loc[s.index >= rec].empty}
    return out


def verify(case_id, rec_date, funds, pred_low, pred_high, pred_dd, offline=False):
    navs = _load_navs_since(funds, rec_date, offline)
    if len(navs) < len(funds):
        return {"case_id": case_id, "status": "不可验证",
                "reason": f"部分基金推荐日后无数据：{set(f['code'] for f in funds) - set(navs)}"}

    weights = {f["code"]: pm._pct(f.get("weight")) for f in funds}
    try:
        port = pm.build_portfolio_nav(navs, weights, "none")
    except ValueError as e:
        return {"case_id": case_id, "status": "不可验证", "reason": str(e)}

    held_days = (port.index[-1] - port.index[0]).days
    actual_total = pm.total_return(port)
    actual_cagr = pm.cagr(port) if held_days >= 90 else None  # 不足3月不年化
    actual_dd = pm.max_drawdown(port)

    # 判定
    if held_days < 60:
        status, reason = "不可验证", f"持有仅 {held_days} 天，样本过短"
    else:
        ref = actual_cagr if actual_cagr is not None else actual_total
        in_return = (pred_low <= ref <= pred_high) if actual_cagr is not None else (ref >= pred_low * (held_days / 365.25))
        dd_ok = actual_dd >= pred_dd * 1.2          # 实际回撤不深于预测×1.2
        dd_bad = actual_dd < pred_dd * 1.5          # 实际回撤比预测深50%以上
        ret_bad = ref < pred_low * 0.5
        if dd_bad or ret_bad:
            status, reason = "证伪", f"实际回撤{actual_dd:.1%}或收益{ref:.1%}显著背离预测"
        elif in_return and dd_ok:
            status, reason = "已验证", "收益落入预测区间且回撤未越线"
        else:
            status, reason = "部分验证", "收益或回撤之一达标"

    return {
        "case_id": case_id, "rec_date": rec_date, "as_of": str(date.today()),
        "held_days": held_days,
        "actual_total_return": round(actual_total, 4),
        "actual_cagr": round(actual_cagr, 4) if actual_cagr is not None else None,
        "actual_max_dd": round(actual_dd, 4),
        "pred_return_band": [pred_low, pred_high], "pred_dd": pred_dd,
        "status": status, "reason": reason,
    }


def _print(res):
    print("\n" + "=" * 60)
    print(f"  回访验证：{res['case_id']}   →   【{res['status']}】")
    print("=" * 60)
    for k in ["rec_date", "as_of", "held_days", "actual_total_return", "actual_cagr",
              "actual_max_dd", "pred_return_band", "pred_dd", "reason"]:
        if k in res:
            print(f"  {k:<22} {res[k]}")
    if "actual_max_dd" in res:
        print("\n可粘贴进 cases_register.md 回访表的行：")
        print(f"| {res['as_of']} | {res['case_id']} | "
              f"{res.get('actual_cagr') or res.get('actual_total_return')} | "
              f"{res['actual_max_dd']} | {res['status']} | 自动回访 |")
    print()


def _cli():
    p = argparse.ArgumentParser(description="案例回访验证")
    p.add_argument("--case_id", required=True)
    p.add_argument("--rec_date", required=True, help="推荐日 YYYY-MM-DD")
    p.add_argument("--funds", nargs="+", required=True, help="code:weight 形如 050019:30")
    p.add_argument("--pred_return_low", type=float, required=True)
    p.add_argument("--pred_return_high", type=float, required=True)
    p.add_argument("--pred_dd", type=float, required=True, help="预测最大回撤(负数)")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    funds = _parse_funds(args.funds)
    res = verify(args.case_id, args.rec_date, funds,
                 args.pred_return_low, args.pred_return_high, args.pred_dd, args.offline)
    _print(res)


if __name__ == "__main__":
    _cli()
