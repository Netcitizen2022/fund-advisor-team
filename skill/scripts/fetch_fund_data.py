#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_fund_data.py — 数据获取层  v1.0  (fund-advisor-team v2.1)
================================================================================
作用：用 akshare 拉取真实基金净值序列、风险指标、宏观利率，给每个数字打 as_of 时效戳，
      并把净值序列缓存到本地 CSV（供 portfolio_math / build_case / verify_case 离线复用）。

⚠ 重要诚实声明：
  akshare 是社区维护、对接第三方网站（天天基金/雪球/东财），接口名与列名【会随版本变化】。
  - 首次部署请 pin 版本：  pip install akshare==<你的版本> --break-system-packages
  - 首次运行务必先核对列名： python3 fetch_fund_data.py --probe 050019
  - 生产使用应：超时重试 + 失败降级到"上次缓存+醒目标注数据可能滞后"。
  本层适合做"决策支撑"，不适合当"实时成交依据"。

依赖：akshare, pandas
================================================================================
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import date

import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "nav_cache")


def _lazy_ak():
    try:
        import akshare as ak
        return ak
    except ImportError:
        print("[错误] 未安装 akshare：pip install akshare pandas --break-system-packages")
        sys.exit(1)


# ────────────────────────────────────────────────────────────────────────────
# 列名核对（首次部署必跑）
# ────────────────────────────────────────────────────────────────────────────
def probe(code: str):
    """打印各接口的真实列名，便于在本环境核对后再写死映射。"""
    ak = _lazy_ak()
    print(f"=== probe {code} ===")
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
        print("[fund_open_fund_info_em 累计净值走势] 列名:", list(df.columns))
        print(df.tail(3).to_string())
    except Exception as e:
        print("  fund_open_fund_info_em 失败:", e)
    try:
        df2 = ak.fund_individual_analysis_xq(symbol=code)
        print("\n[fund_individual_analysis_xq] 列名:", list(df2.columns))
        print(df2.to_string())
    except Exception as e:
        print("  fund_individual_analysis_xq 失败:", e)
    try:
        df3 = ak.bond_zh_us_rate()
        cn10 = [c for c in df3.columns if "中国国债收益率10年" in c]
        print("\n[bond_zh_us_rate] 10年国债列:", cn10, "| 最新:",
              df3.iloc[-1][cn10[0]] if cn10 else "未找到该列，请核对列名")
    except Exception as e:
        print("  bond_zh_us_rate 失败:", e)


# ────────────────────────────────────────────────────────────────────────────
# 净值序列
# ────────────────────────────────────────────────────────────────────────────
def fetch_nav_series(code: str, retries: int = 3, sleep: float = 1.0) -> pd.Series:
    """
    拉取单只【开放式】基金累计净值序列（含分红，用于总回报）。
    返回 pd.Series(index=DatetimeIndex, 累计净值)。
    ⚠ 场内 ETF（如 510300）应改用 ak.fund_etf_hist_sina(symbol='sh510300')，见 fetch_etf_series。
    """
    ak = _lazy_ak()
    last_err = None
    for _ in range(retries):
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
            # ↓ 不同版本列名可能为 ['净值日期','累计净值'] 或 ['x','y']，核对后保留你这版的真实列名
            date_col = "净值日期" if "净值日期" in df.columns else df.columns[0]
            val_col = "累计净值" if "累计净值" in df.columns else df.columns[1]
            s = pd.Series(pd.to_numeric(df[val_col], errors="coerce").values,
                          index=pd.to_datetime(df[date_col]), name=code).dropna().sort_index()
            if s.empty:
                raise ValueError("返回空序列")
            return s
        except Exception as e:
            last_err = e
            time.sleep(sleep)
    raise RuntimeError(f"拉取 {code} 净值失败（已重试{retries}次）：{last_err}")


def fetch_etf_series(em_or_sina_symbol: str) -> pd.Series:
    """
    场内 ETF 历史（新浪源），symbol 形如 'sh510300' / 'sz159915'。
    返回累计收盘价序列（ETF 无累计净值概念，用收盘价近似总回报，分红较小可接受；
    若需严谨可改用复权数据源）。
    """
    ak = _lazy_ak()
    df = ak.fund_etf_hist_sina(symbol=em_or_sina_symbol)
    date_col = "date" if "date" in df.columns else df.columns[0]
    val_col = "close" if "close" in df.columns else df.columns[-2]
    s = pd.Series(pd.to_numeric(df[val_col], errors="coerce").values,
                  index=pd.to_datetime(df[date_col]), name=em_or_sina_symbol).dropna().sort_index()
    return s


def fetch_risk_metrics_xq(code: str) -> dict:
    """雪球口径 近1/3/5年 年化波动率/夏普/最大回撤——用于与 portfolio_math 自算结果交叉校验。"""
    ak = _lazy_ak()
    try:
        df = ak.fund_individual_analysis_xq(symbol=code)
        key = "周期" if "周期" in df.columns else df.columns[0]
        return df.set_index(key).to_dict("index")
    except Exception as e:
        return {"_error": str(e)}


def fetch_cn_10y_yield() -> dict:
    """中国10年期国债收益率（替换写死的 1.74%）。"""
    ak = _lazy_ak()
    try:
        df = ak.bond_zh_us_rate()
        col = [c for c in df.columns if "中国国债收益率10年" in c]
        date_col = df.columns[0]
        val = float(df.sort_values(date_col).iloc[-1][col[0]]) if col else None
        return {"中国10年期国债收益率": val, "as_of": str(date.today()),
                "data_source": "akshare bond_zh_us_rate"}
    except Exception as e:
        return {"中国10年期国债收益率": None, "as_of": str(date.today()), "_error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# 缓存
# ────────────────────────────────────────────────────────────────────────────
def cache_nav(code: str, s: pd.Series):
    os.makedirs(CACHE_DIR, exist_ok=True)
    s.to_frame("累计净值").to_csv(os.path.join(CACHE_DIR, f"{code}.csv"),
                                  encoding="utf-8-sig", index_label="date")


def load_cached_nav(code: str) -> pd.Series | None:
    path = os.path.join(CACHE_DIR, f"{code}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    return df.iloc[:, 0].rename(code)


def fetch_and_cache(codes: list, use_cache_on_fail: bool = True) -> dict:
    """批量拉取并缓存净值序列。失败时可降级到上次缓存（并标注）。返回 {code: Series}。"""
    out, notes = {}, []
    for code in codes:
        try:
            s = fetch_nav_series(code)
            cache_nav(code, s)
            out[code] = s
        except Exception as e:
            if use_cache_on_fail:
                cached = load_cached_nav(code)
                if cached is not None:
                    out[code] = cached
                    notes.append(f"{code}: 在线拉取失败，已降级使用本地缓存（数据可能滞后）：{e}")
                    continue
            notes.append(f"{code}: 拉取失败且无缓存：{e}")
    if notes:
        print("\n".join("[降级] " + n for n in notes))
    return out


# ────────────────────────────────────────────────────────────────────────────
# 写出 enriched 元数据（净值序列单独缓存为 CSV，JSON 只存摘要+来源）
# ────────────────────────────────────────────────────────────────────────────
def build_enriched_meta(codes_weights: dict, out_json: str) -> dict:
    today = str(date.today())
    nav = fetch_and_cache(list(codes_weights.keys()))
    funds_meta = []
    for code, w in codes_weights.items():
        s = nav.get(code)
        funds_meta.append({
            "code": code,
            "weight": f"{float(w) * 100:.0f}%" if float(w) <= 1 else f"{float(w):.0f}%",
            "nav_last": float(s.iloc[-1]) if s is not None else None,
            "nav_last_date": str(s.index[-1].date()) if s is not None else None,
            "nav_start_date": str(s.index[0].date()) if s is not None else None,
            "risk_metrics_xq": fetch_risk_metrics_xq(code),
            "data_source": "akshare fund_open_fund_info_em / fund_individual_analysis_xq",
            "as_of": today,
        })
    payload = {"as_of": today, "macro": fetch_cn_10y_yield(), "funds": funds_meta,
               "note": "净值时间序列见 references/nav_cache/<code>.csv"}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[完成] 元数据写入 {out_json}；净值缓存于 {CACHE_DIR}")
    return payload


def _cli():
    p = argparse.ArgumentParser(description="akshare 数据获取层")
    p.add_argument("--probe", metavar="CODE", help="核对接口列名（首次部署必跑）")
    p.add_argument("--codes", nargs="+", help="批量拉取并缓存净值的基金代码")
    p.add_argument("--out", default="fund_data_enriched.json", help="元数据输出 JSON 路径")
    args = p.parse_args()
    if args.probe:
        probe(args.probe)
    elif args.codes:
        cw = {c: 1.0 / len(args.codes) for c in args.codes}  # 仅缓存用，权重占位
        build_enriched_meta(cw, args.out)
    else:
        print("用法：\n  核对列名： python3 fetch_fund_data.py --probe 050019\n"
              "  批量缓存： python3 fetch_fund_data.py --codes 050019 007543 012643 000216")


if __name__ == "__main__":
    _cli()
