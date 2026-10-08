#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screen_funds.py — 基金五维评分筛选引擎  v1.0  (fund-advisor-team v2.2)
================================================================================
背景（为什么新增本脚本）：
  v2.1 之前，「基金筛选师」的五维模型与硬性排除项只存在于 SKILL.md 的文字里，
  没有任何代码实现——这意味着「易方达蓝筹(R4) 塞进 R2 组合」这类问题，靠人记规则，
  记不住就漏。本脚本把 SKILL.md 第二节「角色3 基金筛选师」的方法论变成可执行约束：
    - 硬性排除项 = 不可妥协的布尔闸门（任何一条命中 → 直接出局）
    - 五维评分   = 透明、可复算、带权重的 0~100 打分（每维子分都写明算法）

  本引擎只做「打分与排除」，不替代适当性闸门（suitability_check.py）与组合数学
  （portfolio_math.py）。三者职责分离：
    screen_funds   → 单只基金「够不够格、好不好」
    suitability    → 组合对这个客户「合不合规、越不越线」
    portfolio_math → 组合「真实风险/收益数字」

五维模型（权重沿用 SKILL.md，可在调用时覆盖）：
  | 维度       | 权重 | 子指标                                            |
  |-----------|-----|--------------------------------------------------|
  | 基金经理   | 30% | 任职年限、任职期年化回报、换手率（低换手加分）      |
  | 历史业绩   | 25% | 近3年/5年年化、相对基准超额                         |
  | 回撤控制   | 20% | 最大回撤、卡玛比率、夏普比率                        |
  | 规模流动性 | 15% | 规模（不过小/不过大）                              |
  | 费率结构   | 10% | 管理费+托管费合计（越低越好）                       |

硬性排除项（任一命中即 EXCLUDE）：
  - 基金经理变更/离任 < 6 个月
  - 规模 < 2 亿（流动性风险）
  - 成立不足 1 年（无熊市验证）
  - 近 1 年回撤 > 40%（深于 -40%）且无特殊说明

诚实声明：
  生产使用时，各子指标应由 fetch_fund_data.py 的 fund_individual_analysis_xq（雪球口径）
  与 fund_money_fund_daily_em（成立日/经理）等真实拉取后喂入；缺字段的维度会按「中性 50 分」
  保守处理并提示。打分是「相对优选」工具，不构成对未来表现的承诺。

可独立测试（不依赖外部数据）：
  python3 screen_funds.py --selftest
单文件评分：
  python3 screen_funds.py --json candidates.json
================================================================================
"""
from __future__ import annotations
import argparse
import json
import sys

# ── 默认五维权重（可在 score_fund(..., weights=) 覆盖）──────────────────────────
DEFAULT_WEIGHTS = {
    "基金经理": 0.30,
    "历史业绩": 0.25,
    "回撤控制": 0.20,
    "规模流动性": 0.15,
    "费率结构": 0.10,
}

# ── 硬性排除阈值（沿用 SKILL.md，可覆盖）────────────────────────────────────────
HARD_FILTERS = {
    "manager_change_months_min": 6,    # 经理变更需 ≥ 6 个月
    "scale_yi_min": 2.0,               # 规模 ≥ 2 亿
    "established_years_min": 1.0,      # 成立 ≥ 1 年
    "recent_1y_dd_floor": -0.40,       # 近 1 年回撤不深于 -40%
}


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ── 各维子评分（全部透明、可复算）──────────────────────────────────────────────
def _score_manager(f: dict) -> tuple[float, str]:
    """基金经理维：任职年限(0~50) + 任职期年化(0~40) + 换手率(0~10，低换手加分)。"""
    tenure = f.get("manager_tenure_years")
    ann = f.get("manager_annual_return")
    turnover = f.get("turnover")  # 年换手倍数，可缺
    parts, score, miss = [], 0.0, []

    # 任职年限：3 年起步合格，≥7 年满分
    if tenure is None:
        score += 25.0; miss.append("任职年限")
    else:
        s = _clamp((tenure - 1.0) / (7.0 - 1.0) * 50.0, 0, 50)
        score += s; parts.append(f"任职{tenure:.1f}年={s:.0f}")

    # 任职期年化回报：0% → 0 分，≥15% → 满分 40
    if ann is None:
        score += 20.0; miss.append("任职期年化")
    else:
        s = _clamp(ann / 0.15 * 40.0, 0, 40)
        score += s; parts.append(f"年化{ann:.1%}={s:.0f}")

    # 换手率：越低越好。<2 倍满分，>8 倍 0 分
    if turnover is None:
        score += 5.0
    else:
        s = _clamp((8.0 - turnover) / (8.0 - 2.0) * 10.0, 0, 10)
        score += s; parts.append(f"换手{turnover:.1f}={s:.0f}")

    note = " / ".join(parts) + (f"（缺:{','.join(miss)}按中性计）" if miss else "")
    return _clamp(score), note


def _score_performance(f: dict) -> tuple[float, str]:
    """历史业绩维：近3年年化(0~50) + 近5年年化(0~25) + 相对基准超额(0~25)。"""
    r3 = f.get("return_3y")
    r5 = f.get("return_5y")
    excess = f.get("excess_vs_benchmark")
    parts, score, miss = [], 0.0, []

    if r3 is None:
        score += 25.0; miss.append("近3年")
    else:
        s = _clamp(r3 / 0.12 * 50.0, 0, 50)  # 12% 年化≈满分
        score += s; parts.append(f"3年{r3:.1%}={s:.0f}")

    if r5 is None:
        score += 12.5; miss.append("近5年")
    else:
        s = _clamp(r5 / 0.12 * 25.0, 0, 25)
        score += s; parts.append(f"5年{r5:.1%}={s:.0f}")

    if excess is None:
        score += 12.5; miss.append("超额")
    else:
        s = _clamp((excess + 0.05) / 0.10 * 25.0, 0, 25)  # -5%→0, +5%→满分
        score += s; parts.append(f"超额{excess:+.1%}={s:.0f}")

    note = " / ".join(parts) + (f"（缺:{','.join(miss)}按中性计）" if miss else "")
    return _clamp(score), note


def _score_drawdown(f: dict) -> tuple[float, str]:
    """回撤控制维：最大回撤(0~40，越浅越好) + 卡玛(0~30) + 夏普(0~30)。"""
    mdd = f.get("max_drawdown")      # 负数
    calmar = f.get("calmar")
    sharpe = f.get("sharpe")
    parts, score, miss = [], 0.0, []

    if mdd is None:
        score += 20.0; miss.append("最大回撤")
    else:
        # 0% 回撤→满分 40；-40% 回撤→0 分
        s = _clamp((1.0 - abs(mdd) / 0.40) * 40.0, 0, 40)
        score += s; parts.append(f"回撤{mdd:.1%}={s:.0f}")

    if calmar is None:
        score += 15.0; miss.append("卡玛")
    else:
        s = _clamp(calmar / 1.5 * 30.0, 0, 30)  # 卡玛≥1.5 满分
        score += s; parts.append(f"卡玛{calmar:.2f}={s:.0f}")

    if sharpe is None:
        score += 15.0; miss.append("夏普")
    else:
        s = _clamp(sharpe / 1.5 * 30.0, 0, 30)  # 夏普≥1.5 满分
        score += s; parts.append(f"夏普{sharpe:.2f}={s:.0f}")

    note = " / ".join(parts) + (f"（缺:{','.join(miss)}按中性计）" if miss else "")
    return _clamp(score), note


def _score_scale(f: dict) -> tuple[float, str]:
    """规模流动性维：不过小不过大。2~50 亿区间评分高，<2 亿(应已被硬排除)/>200 亿降分。"""
    scale = f.get("scale_yi")
    if scale is None:
        return 50.0, "规模缺失按中性计"
    if scale < 2:
        return 10.0, f"规模{scale:.1f}亿偏小(应触发硬排除)"
    if scale <= 50:
        return 100.0, f"规模{scale:.1f}亿（2~50亿理想区间）"
    if scale <= 100:
        return 80.0, f"规模{scale:.1f}亿（偏大，调仓略受限）"
    if scale <= 200:
        return 60.0, f"规模{scale:.1f}亿（大，主动管理难度上升）"
    return 40.0, f"规模{scale:.1f}亿（过大，超额获取难）"


def _score_fee(f: dict) -> tuple[float, str]:
    """费率结构维：管理费+托管费合计，越低越好。≤0.3% 满分，≥1.8% 0 分。"""
    fee = f.get("fee_total_pct")
    if fee is None:
        return 50.0, "费率缺失按中性计"
    s = _clamp((1.8 - fee) / (1.8 - 0.3) * 100.0, 0, 100)
    return s, f"合计费率{fee:.2f}%={s:.0f}"


# ── 硬性排除 ────────────────────────────────────────────────────────────────
def hard_filter(f: dict, thresholds: dict | None = None) -> list:
    """返回命中的硬排除理由列表；为空表示通过硬闸门。"""
    t = {**HARD_FILTERS, **(thresholds or {})}
    reasons = []
    mc = f.get("manager_change_months_ago")
    if mc is not None and mc < t["manager_change_months_min"]:
        reasons.append(f"基金经理变更仅 {mc} 个月 < {t['manager_change_months_min']} 个月红线")
    sc = f.get("scale_yi")
    if sc is not None and sc < t["scale_yi_min"]:
        reasons.append(f"规模 {sc:.2f} 亿 < {t['scale_yi_min']} 亿流动性红线")
    ey = f.get("established_years")
    if ey is not None and ey < t["established_years_min"]:
        reasons.append(f"成立仅 {ey:.1f} 年 < {t['established_years_min']} 年（无熊市验证）")
    dd1y = f.get("recent_1y_drawdown")
    if dd1y is not None and dd1y < t["recent_1y_dd_floor"] and not f.get("dd_exception_note"):
        reasons.append(f"近1年回撤 {dd1y:.1%} 深于 {t['recent_1y_dd_floor']:.0%} 且无特殊说明")
    return reasons


# ── 单只基金综合评分 ───────────────────────────────────────────────────────────
def score_fund(f: dict, weights: dict | None = None, thresholds: dict | None = None) -> dict:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    excl = hard_filter(f, thresholds)

    dims = {
        "基金经理":  _score_manager(f),
        "历史业绩":  _score_performance(f),
        "回撤控制":  _score_drawdown(f),
        "规模流动性": _score_scale(f),
        "费率结构":  _score_fee(f),
    }
    dim_scores = {k: round(v[0], 1) for k, v in dims.items()}
    dim_notes = {k: v[1] for k, v in dims.items()}
    weighted = sum(dim_scores[k] * w[k] for k in w)

    return {
        "code": f.get("code"),
        "name": f.get("name"),
        "passed_hard_filters": len(excl) == 0,
        "exclusions": excl,
        "score": round(weighted, 1) if not excl else 0.0,
        "dimension_scores": dim_scores,
        "dimension_notes": dim_notes,
        "weights_used": w,
        "_口径": "硬排除命中则总分计 0（出局）；五维子分算法见各 dimension_notes，权重见 weights_used",
    }


def screen(candidates: list, weights: dict | None = None,
           thresholds: dict | None = None, top_n: int | None = None) -> dict:
    """对候选池打分排序。返回 {passed:[...降序], excluded:[...], ranked_all:[...]}。"""
    scored = [score_fund(f, weights, thresholds) for f in candidates]
    passed = sorted([s for s in scored if s["passed_hard_filters"]],
                    key=lambda x: x["score"], reverse=True)
    excluded = [s for s in scored if not s["passed_hard_filters"]]
    if top_n:
        passed = passed[:top_n]
    return {"passed": passed, "excluded": excluded, "ranked_all": scored}


def print_screen(res: dict) -> None:
    print("\n" + "=" * 64)
    print("  基金五维评分筛选结果")
    print("=" * 64)
    print("【通过硬闸门 · 按综合得分降序】")
    if not res["passed"]:
        print("  （无通过标的）")
    for i, s in enumerate(res["passed"], 1):
        print(f"  {i}. {s.get('name') or s.get('code'):<22} 综合 {s['score']:.1f}")
        ds = s["dimension_scores"]
        print(f"      经理{ds['基金经理']:.0f} 业绩{ds['历史业绩']:.0f} "
              f"回撤{ds['回撤控制']:.0f} 规模{ds['规模流动性']:.0f} 费率{ds['费率结构']:.0f}")
    if res["excluded"]:
        print("\n【硬性排除 · 不可进入组合】")
        for s in res["excluded"]:
            print(f"  ✗ {s.get('name') or s.get('code')}")
            for r in s["exclusions"]:
                print(f"      - {r}")
    print("=" * 64 + "\n")


# ── 自测（合成候选池，验证打分与排除正确）───────────────────────────────────────
def _selftest():
    print("=== screen_funds 自测 ===")

    candidates = [
        {   # 优质老将：应高分通过
            "code": "050019", "name": "博时稳健回报",
            "manager_tenure_years": 8, "manager_annual_return": 0.09, "turnover": 1.5,
            "return_3y": 0.06, "return_5y": 0.07, "excess_vs_benchmark": 0.02,
            "max_drawdown": -0.08, "calmar": 1.2, "sharpe": 1.1,
            "scale_yi": 30, "fee_total_pct": 0.7,
            "manager_change_months_ago": 96, "established_years": 14, "recent_1y_drawdown": -0.05,
        },
        {   # 新基金：成立<1年 → 硬排除
            "code": "999001", "name": "某新锐成长",
            "manager_tenure_years": 0.5, "return_3y": None,
            "max_drawdown": -0.15, "scale_yi": 5, "fee_total_pct": 1.5,
            "manager_change_months_ago": 6, "established_years": 0.6, "recent_1y_drawdown": -0.10,
        },
        {   # 经理刚换 + 规模过小 → 硬排除（两条）
            "code": "999002", "name": "某迷你换帅基",
            "manager_tenure_years": 0.3, "return_3y": 0.04,
            "max_drawdown": -0.20, "scale_yi": 1.2, "fee_total_pct": 1.6,
            "manager_change_months_ago": 3, "established_years": 5, "recent_1y_drawdown": -0.18,
        },
        {   # 近1年暴跌 > 40% → 硬排除
            "code": "999003", "name": "某踩雷主题基",
            "manager_tenure_years": 4, "return_3y": -0.02,
            "max_drawdown": -0.55, "scale_yi": 10, "fee_total_pct": 1.5,
            "manager_change_months_ago": 50, "established_years": 6, "recent_1y_drawdown": -0.46,
        },
        {   # 合格但平庸：通过但分数低于老将
            "code": "999004", "name": "某平庸债基",
            "manager_tenure_years": 3, "manager_annual_return": 0.04, "turnover": 3,
            "return_3y": 0.035, "return_5y": 0.04, "excess_vs_benchmark": 0.0,
            "max_drawdown": -0.06, "calmar": 0.8, "sharpe": 0.7,
            "scale_yi": 8, "fee_total_pct": 0.9,
            "manager_change_months_ago": 36, "established_years": 7, "recent_1y_drawdown": -0.03,
        },
    ]

    res = screen(candidates)
    print_screen(res)

    # 断言1：三只该被硬排除的都出局了
    excl_codes = {s["code"] for s in res["excluded"]}
    assert excl_codes == {"999001", "999002", "999003"}, f"硬排除集合错误: {excl_codes}"
    print("[OK] 新基金/换帅迷你/踩雷 三只被硬排除")

    # 断言2：换帅迷你基命中两条排除理由
    mini = next(s for s in res["excluded"] if s["code"] == "999002")
    assert len(mini["exclusions"]) >= 2, "换帅+迷你应命中≥2条"
    print(f"[OK] 换帅迷你基命中 {len(mini['exclusions'])} 条硬排除理由")

    # 断言3：老将分数高于平庸债基
    passed = {s["code"]: s["score"] for s in res["passed"]}
    assert passed["050019"] > passed["999004"], "老将应高于平庸"
    print(f"[OK] 综合排序正确：老将 {passed['050019']:.1f} > 平庸 {passed['999004']:.1f}")

    # 断言4：缺字段按中性 50 处理不报错，且分数有界 0~100
    sparse = score_fund({"code": "X", "name": "极简候选"})
    assert 0 <= sparse["score"] <= 100
    print(f"[OK] 全缺字段候选按中性计，得分 {sparse['score']:.1f}（有界）")

    # 断言5：序列化无异常
    json.dumps(res, ensure_ascii=False)
    print("[OK] 结果可序列化")

    print("=== 全部自测通过 ✓ ===")


def _cli():
    p = argparse.ArgumentParser(description="基金五维评分筛选引擎")
    p.add_argument("--selftest", action="store_true", help="运行内置自测（无需外部数据）")
    p.add_argument("--json", help="候选池 JSON（list of fund dicts），打印筛选结果")
    p.add_argument("--top", type=int, default=None, help="只保留得分前 N 名")
    args = p.parse_args()
    if args.selftest:
        _selftest()
        return
    if args.json:
        with open(args.json, "r", encoding="utf-8") as f:
            cands = json.load(f)
        if isinstance(cands, dict):
            cands = cands.get("candidates", cands.get("funds", []))
        res = screen(cands, top_n=args.top)
        print_screen(res)
        return
    print("用法： python3 screen_funds.py --selftest   或   --json candidates.json [--top 5]")


if __name__ == "__main__":
    _cli()
