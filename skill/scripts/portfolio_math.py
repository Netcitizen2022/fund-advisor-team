#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
portfolio_math.py — 组合风险/收益引擎  v1.0  (fund-advisor-team v2.1)
================================================================================
铁律：所有面向客户的风险/收益数字，必须由本模块基于真实净值序列算出，
      不允许在报告里写死或口述。每个输出都带"计算方法(method)"字符串，
      便于在报告里逐数字标注来源。

核心方法论（为什么这样算）：
  组合的最大回撤 **不能** 用各基金最大回撤加权平均——它们发生在不同时点，
  加权是错的。正确做法：用成份基金的【累计净值】序列、按目标权重，
  合成出一条"组合净值曲线"，再在这条真实曲线上算回撤/波动/收益/情景。
  这样 "-8%" 不再是口述，而是"某区间合成曲线峰谷法算出的真实数字"。

依赖：numpy, pandas
  pip install numpy pandas --break-system-packages

可独立测试（不需要 akshare）：
  python3 portfolio_math.py --selftest
================================================================================
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# 默认历史情景窗口（A股几次典型压力区间）。可在调用时覆盖。
DEFAULT_SCENARIOS = {
    "2015股灾":  ("2015-06-12", "2016-01-31"),
    "2018全年熊": ("2018-01-01", "2018-12-31"),
    "2022回撤":  ("2022-01-01", "2022-12-31"),
    "2024年初":  ("2024-01-01", "2024-02-29"),
}

# ────────────────────────────────────────────────────────────────────────────
# 组合净值合成
# ────────────────────────────────────────────────────────────────────────────
def build_portfolio_nav(nav_dict: dict, weights: dict, rebalance: str = "none",
                        min_days: int = 60) -> pd.Series:
    """
    nav_dict : {code: pd.Series(累计净值, index=DatetimeIndex)}
    weights  : {code: 0.30, ...}  （内部会归一，防止权重和≠1引入误差）
    rebalance: "none"   = 买入持有（权重随行情漂移，更贴近真实持有）
               "monthly"= 月度再平衡（恒定权重）
    min_days : 最少有效重叠交易日（默认60；情景回测等短窗口可放宽至15）
    返回     : 组合净值序列（起点归一为 1.0）

    对齐策略：取所有成份基金都有数据的交易日【交集】，绝不前向填充——
    填充会用昨天的净值冒充今天，制造虚假的低波动。
    """
    codes = list(weights.keys())
    if not codes:
        raise ValueError("weights 为空")
    w = np.array([float(weights[c]) for c in codes], dtype=float)
    if w.sum() <= 0:
        raise ValueError("权重之和必须为正")
    w = w / w.sum()

    missing = [c for c in codes if c not in nav_dict or nav_dict[c] is None or len(nav_dict[c]) == 0]
    if missing:
        raise ValueError(f"缺少净值序列的基金：{missing}")

    df = pd.concat({c: nav_dict[c].astype(float) for c in codes}, axis=1).dropna()
    if len(df) < min_days:
        raise ValueError(f"有效重叠净值天数不足（{len(df)}<{min_days}），无法可靠计算；"
                         f"请缩短回看区间或剔除成立过晚的基金")

    norm = df / df.iloc[0]  # 每只基金净值归一到 1.0

    if rebalance == "none":
        port = (norm * w).sum(axis=1)
    elif rebalance == "monthly":
        rets = norm.pct_change().fillna(0.0)
        port_ret = (rets * w).sum(axis=1)
        port = (1.0 + port_ret).cumprod()
        port.iloc[0] = 1.0
    else:
        raise ValueError("rebalance 仅支持 'none' 或 'monthly'")

    port.name = "portfolio_nav"
    return port


# ────────────────────────────────────────────────────────────────────────────
# 单序列指标
# ────────────────────────────────────────────────────────────────────────────
def max_drawdown(nav: pd.Series) -> float:
    """真实峰谷法最大回撤（负数，如 -0.083 表示 -8.3%）"""
    running_max = nav.cummax()
    dd = nav / running_max - 1.0
    return float(dd.min())


def cagr(nav: pd.Series) -> float:
    """年化收益（基于真实区间起止 + 自然日年化）"""
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0:
        return float("nan")
    years = days / 365.25
    return float((nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0)


def total_return(nav: pd.Series) -> float:
    """区间累计收益"""
    return float(nav.iloc[-1] / nav.iloc[0] - 1.0)


def ann_vol(nav: pd.Series) -> float:
    """年化波动率（日收益标准差 × √252）"""
    rets = nav.pct_change().dropna()
    if len(rets) < 2:
        return float("nan")
    return float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sharpe(nav: pd.Series, rf_annual: float = 0.0) -> float:
    """年化夏普（默认无风险利率0；如需更准可传入当前1年定存或国债短端利率）"""
    rets = nav.pct_change().dropna()
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return float("nan")
    excess = rets.mean() * TRADING_DAYS - rf_annual
    return float(excess / (rets.std(ddof=1) * np.sqrt(TRADING_DAYS)))


def worst_rolling_return(nav: pd.Series, window_days: int = TRADING_DAYS) -> float:
    """最差滚动 N 个交易日收益（默认~1年）——比 VaR 更易向零售客户解释的'最惨持有体验'"""
    if len(nav) <= window_days:
        return float("nan")
    roll = nav / nav.shift(window_days) - 1.0
    return float(roll.min())


def hist_var(nav: pd.Series, horizon_days: int = 20, conf: float = 0.95) -> float:
    """
    历史模拟法 VaR（经验分位数，不假设正态分布）。
    基金收益有肥尾/偏度，正态法会系统性低估尾部风险——这里用真实分布的分位数。
    返回负数：horizon_days 内、conf 置信度下的最大可能损失（历史口径）。
    """
    roll = (nav / nav.shift(horizon_days) - 1.0).dropna()
    if roll.empty:
        return float("nan")
    return float(np.percentile(roll, (1.0 - conf) * 100.0))


def correlation_matrix(nav_dict: dict) -> pd.DataFrame:
    """成份基金真实相关性矩阵（替代'<0.7'的口述）。注意：危机期相关性会上行。"""
    df = pd.concat({c: nav_dict[c].astype(float) for c in nav_dict}, axis=1).dropna()
    return df.pct_change().dropna().corr()


# ────────────────────────────────────────────────────────────────────────────
# 分层 / 情景 / 边际贡献
# ────────────────────────────────────────────────────────────────────────────
def layer_metrics(nav_dict: dict, funds: list, rebalance: str = "none") -> dict:
    """
    按 fund['layer'] 分组，为每一层合成子组合并计算指标。
    用于报告第五章"核心层/卫星层/对冲层各自的回撤影响"——让每个分层数字也可复算。
    funds: [{code, weight, layer, ...}, ...]
    """
    layers: dict[str, dict] = {}
    for f in funds:
        layers.setdefault(f.get("layer", "未分类"), {})[f["code"]] = _pct(f.get("weight"))
    out = {}
    for layer, w in layers.items():
        sub = {c: nav_dict[c] for c in w if c in nav_dict}
        if len(sub) != len(w):
            out[layer] = None
            continue
        try:
            nav = build_portfolio_nav(sub, w, rebalance)
            layer_weight = sum(w.values())
            sleeve_dd = max_drawdown(nav)
            out[layer] = {
                "层权重": round(layer_weight, 4),                      # 该层占总组合比例
                "层内独立收益": round(total_return(nav), 4),           # 该层若100%持有的表现
                "层内独立年化": round(cagr(nav), 4),
                "层内独立最大回撤": round(sleeve_dd, 4),               # 该层独立回撤(非组合影响)
                "层内年化波动率": round(ann_vol(nav), 4),
                "最坏加权影响": round(sleeve_dd * layer_weight, 4),    # ≈该层暴雷时对总组合的拖累(粗估)
                "_口径": "独立指标=该层若单独100%持有；最坏加权影响=独立回撤×层权重，"
                         "用于报告'该层影响约X元'(capital×|最坏加权影响|)，为粗略上界",
            }
        except ValueError as e:
            out[layer] = {"_error": str(e)}
    return out


def scenario_test(nav_dict: dict, weights: dict, windows: dict, rebalance: str = "none") -> dict:
    """
    历史情景回测：把组合套到指定历史区间，报告它'本会经历的真实收益与回撤'。
    某区间若有基金尚未成立 → 诚实标注 None（不可回测），绝不编造。
    """
    out = {}
    for label, (start, end) in windows.items():
        sliced = {c: s.loc[start:end] for c, s in nav_dict.items()
                  if c in weights and not s.loc[start:end].empty}
        if len(sliced) < len(weights):
            out[label] = None
            continue
        try:
            port = build_portfolio_nav(sliced, weights, rebalance, min_days=15)
            out[label] = {
                "区间收益": round(total_return(port), 4),
                "区间最大回撤": round(max_drawdown(port), 4),
            }
        except ValueError:
            out[label] = None
    return out


def marginal_contribution(nav_dict: dict, funds: list, target_code: str,
                          rebalance: str = "none") -> dict:
    """
    某只基金的"边际作用"：对比【含该基金】与【剔除该基金后其余权重归一】两个组合，
    报告最大回撤与年化波动率的实测差值。
    用途：把"黄金把回撤从-12%压到-8%"这类口述，变成两次实测的差。
    """
    weights_all = {f["code"]: _pct(f.get("weight")) for f in funds}
    if target_code not in weights_all:
        raise ValueError(f"{target_code} 不在组合内")

    nav_with = build_portfolio_nav({c: nav_dict[c] for c in weights_all}, weights_all, rebalance)

    weights_wo = {c: w for c, w in weights_all.items() if c != target_code}
    if not weights_wo:
        raise ValueError("剔除后组合为空")
    nav_wo = build_portfolio_nav({c: nav_dict[c] for c in weights_wo}, weights_wo, rebalance)

    return {
        "对比对象": target_code,
        "口径": "含该基金 vs 剔除该基金后其余权重归一，同区间同再平衡方式",
        "最大回撤_含": round(max_drawdown(nav_with), 4),
        "最大回撤_不含": round(max_drawdown(nav_wo), 4),
        "最大回撤_改善": round(max_drawdown(nav_with) - max_drawdown(nav_wo), 4),  # 正=回撤变浅
        "年化波动_含": round(ann_vol(nav_with), 4),
        "年化波动_不含": round(ann_vol(nav_wo), 4),
    }


# ────────────────────────────────────────────────────────────────────────────
# 远期收益估计（诚实处理：历史≠未来）
# ────────────────────────────────────────────────────────────────────────────
# 资本市场假设（CMA）——这是【假设】，必须定期复核并在报告中显示。
# 仅作默认占位，使用者应按当前利率/估值环境调整。
DEFAULT_CMA = {
    "固收类": 0.025,   # 债券：用当前到期收益率(YTM)作远期代理优于历史滚动
    "权益类": 0.060,   # 权益：无风险利率 + 风险溢价的粗略中性估计
    "商品/海外": 0.020,
    "现金类": 0.012,
}

# 基金类型 → 资产大类 的归并
ASSET_CLASS_MAP = {
    "一级债基": "固收类", "二级债基": "固收类", "债基": "固收类", "纯债": "固收类",
    "货币": "现金类", "货基": "现金类",
    "主动股基": "权益类", "指数ETF": "权益类", "ETF": "权益类", "主动混合": "权益类",
    "混合": "权益类", "红利": "权益类", "QDII": "商品/海外", "黄金": "商品/海外",
    "商品": "商品/海外",
}


def forward_return_estimate(funds: list, cma: dict | None = None) -> dict:
    """
    远期组合收益的【显式假设】估计：Σ wᵢ · CMA(资产大类ᵢ)。
    与历史CAGR分开报告，并写明用了哪套CMA。绝不把历史当未来。
    """
    cma = cma or DEFAULT_CMA
    total = 0.0
    breakdown = []
    for f in funds:
        w = _pct(f.get("weight"))
        ac = _asset_class(f.get("type", ""))
        r = cma.get(ac, 0.0)
        total += w * r
        breakdown.append({"code": f.get("code"), "type": f.get("type"),
                          "资产大类": ac, "权重": round(w, 4), "假设年化": r})
    return {
        "远期预期年化(假设)": round(total, 4),
        "口径": "Σ 权重×资产大类CMA；CMA为假设值，需按当前利率/估值定期复核",
        "采用CMA": cma,
        "分解": breakdown,
    }


# ────────────────────────────────────────────────────────────────────────────
# 汇总：一次产出报告所需的全部数字 + 各自的计算方法
# ────────────────────────────────────────────────────────────────────────────
def summarize(nav_dict: dict, funds: list, rebalance: str = "none",
              windows: dict | None = None, cma: dict | None = None) -> dict:
    """
    funds: [{code, weight, layer, type, ...}, ...]
    返回：可直接序列化进 enriched fund_data.json 的 computed 块。
    """
    weights = {f["code"]: _pct(f.get("weight")) for f in funds}
    port = build_portfolio_nav(nav_dict, weights, rebalance)
    start, end = port.index[0].date(), port.index[-1].date()
    rb = "买入持有" if rebalance == "none" else "月度再平衡"
    method = (f"基于 {start}~{end} 各成份基金累计净值、按目标权重{rb}"
              f"合成的组合净值序列计算（峰谷法/历史模拟，非正态假设）")

    res = {
        "as_of": str(date.today()),
        "数据区间": f"{start} ~ {end}",
        "有效交易日数": int(len(port)),
        "再平衡方式": rb,
        "计算方法": method,
        "组合_年化收益_历史": round(cagr(port), 4),
        "组合_区间累计收益": round(total_return(port), 4),
        "组合_年化波动率": round(ann_vol(port), 4),
        "组合_历史最大回撤": round(max_drawdown(port), 4),
        "组合_最差滚动1年收益": round(worst_rolling_return(port), 4),
        "组合_20日95%历史VaR": round(hist_var(port, 20, 0.95), 4),
        "组合_20日99%历史VaR": round(hist_var(port, 20, 0.99), 4),
        "分层指标": layer_metrics(nav_dict, funds, rebalance),
        "成份相关性矩阵": correlation_matrix(nav_dict).round(2).to_dict(),
        "历史情景回测": scenario_test(nav_dict, weights, windows or DEFAULT_SCENARIOS, rebalance),
        "远期收益估计": forward_return_estimate(funds, cma),
        "诚实声明": "历史表现不代表未来；相关性在危机期会上行；远期估计基于显式CMA假设。",
    }
    return res


# ────────────────────────────────────────────────────────────────────────────
# 小工具
# ────────────────────────────────────────────────────────────────────────────
def _pct(x) -> float:
    """'30%' / '0.3' / 30 → 0.30"""
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


def _asset_class(fund_type: str) -> str:
    for k, v in ASSET_CLASS_MAP.items():
        if k in (fund_type or ""):
            return v
    return "权益类"  # 未知类型保守归权益（更高风险假设）


# ────────────────────────────────────────────────────────────────────────────
# 自测（合成已知序列，验证算法正确，不依赖外部数据）
# ────────────────────────────────────────────────────────────────────────────
def _selftest():
    print("=== portfolio_math 自测 ===")
    idx = pd.date_range("2020-01-01", periods=4, freq="D")

    # 用例1：净值 1.0→1.2→0.9→1.1，最大回撤应为 0.9/1.2-1 = -25%
    s = pd.Series([1.0, 1.2, 0.9, 1.1], index=idx)
    dd = max_drawdown(s)
    assert abs(dd - (0.9 / 1.2 - 1.0)) < 1e-9, f"max_drawdown 错误: {dd}"
    print(f"[OK] max_drawdown(1.0,1.2,0.9,1.1) = {dd:.4f} (期望 -0.2500)")

    # 用例2：买入持有，两只各50%，一只翻倍一只不变 → 组合应 = 1.5
    idx2 = pd.date_range("2020-01-01", periods=300, freq="D")
    a = pd.Series(np.linspace(1.0, 2.0, 300), index=idx2)   # 线性翻倍
    b = pd.Series(np.ones(300), index=idx2)                  # 不变
    port = build_portfolio_nav({"A": a, "B": b}, {"A": 0.5, "B": 0.5}, "none")
    assert abs(port.iloc[-1] - 1.5) < 1e-9, f"组合终值错误: {port.iloc[-1]}"
    print(f"[OK] 50/50 买入持有终值 = {port.iloc[-1]:.4f} (期望 1.5000)")

    # 用例3：权重不归一应被自动归一（30/30 → 50/50）
    port2 = build_portfolio_nav({"A": a, "B": b}, {"A": 0.3, "B": 0.3}, "none")
    assert abs(port2.iloc[-1] - 1.5) < 1e-9, "权重归一失败"
    print(f"[OK] 权重自动归一 终值 = {port2.iloc[-1]:.4f} (期望 1.5000)")

    # 用例4：CAGR 一年翻倍应≈100%
    idx3 = pd.date_range("2020-01-01", "2021-01-01", freq="D")
    c = pd.Series(np.linspace(1.0, 2.0, len(idx3)), index=idx3)
    g = cagr(c)
    assert 0.95 < g < 1.05, f"CAGR 异常: {g}"
    print(f"[OK] 一年翻倍 CAGR = {g:.4f} (期望≈1.0)")

    # 用例5：边际贡献——加一个稳定资产应降低波动
    idx4 = pd.date_range("2020-01-01", periods=300, freq="D")
    rng = np.random.default_rng(42)
    vol_series = pd.Series(np.cumprod(1 + rng.normal(0.0003, 0.02, 300)), index=idx4)
    stable = pd.Series(np.cumprod(1 + rng.normal(0.0001, 0.001, 300)), index=idx4)
    funds = [{"code": "VOL", "weight": "70%", "layer": "卫星", "type": "主动股基"},
             {"code": "STB", "weight": "30%", "layer": "核心", "type": "债基"}]
    mc = marginal_contribution({"VOL": vol_series, "STB": stable}, funds, "STB", "none")
    assert mc["年化波动_含"] < mc["年化波动_不含"], "加入稳定资产未降低波动"
    print(f"[OK] 加入稳定资产: 波动 {mc['年化波动_不含']:.3f} → {mc['年化波动_含']:.3f}")

    # 用例6：summarize 全链路可序列化
    res = summarize({"VOL": vol_series, "STB": stable}, funds, "none",
                    windows={"自测窗口": ("2020-02-01", "2020-08-01")})
    json.dumps(res, ensure_ascii=False)  # 应无异常
    print(f"[OK] summarize 全链路通过，组合年化波动 = {res['组合_年化波动率']:.4f}")

    print("=== 全部自测通过 ✓ ===")


def _cli():
    p = argparse.ArgumentParser(description="组合风险/收益引擎")
    p.add_argument("--selftest", action="store_true", help="运行内置自测（无需外部数据）")
    args = p.parse_args()
    if args.selftest:
        _selftest()
    else:
        print("本模块通常被 build_case.py 调用。独立验证请运行： python3 portfolio_math.py --selftest")


if __name__ == "__main__":
    _cli()
