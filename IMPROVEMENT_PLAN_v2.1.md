# fund-advisor-team 改进方案 v2.1

> 目标版本：从 v2.0 → v2.1（**精确性改造版**）
> 部署环境：Claude Desktop + Filesystem MCP，`/Users/jacklee/Documents/01-agents/fund-advisor-team/`
> 适用前提：document-suite 已部署且测试通过（保持不动）；本方案不触碰渲染层，只改"数字怎么来"。
> 核心约束：**跟钱有关的每一个数字，都必须可追溯、可复算、带时效。**

---

## 0. 先定义"精确"——这是整份方案的脊柱

在投资场景里，**"精确"不是小数点后更多位，而是四件事同时成立：**

1. **可追溯（Provenance）**：每个数字要么来自一个**带日期的数据源**，要么来自一个**能复算的公式**。报告里不允许出现"凭经验"的裸数字。
2. **区间+方法，而非伪点估计**：风险/收益用区间或情景给出，并写明算法。`预期回撤 -8%` 这种孤零零的点估计是 v2.0 最大的精确性漏洞——它读起来像承诺，实际没有任何模型支撑。
3. **假设显式（Explicit Assumptions）**：相关性取多少、是否再平衡、用历史均值还是远期估计——全部写出来，让读者能质疑。
4. **时效受控（Freshness Gate）**：每个外部事实带 `as_of` 日期；超期自动告警，禁止陈旧数据进入面向客户的文档。

v2.0 的现状对照：报告里的 `预期年化 5-7%`、`预期最大回撤 -6%~-8%`、`黄金把回撤从 -12% 压到 -8%`、`10年期国债约 1.74%`、`固收+ 2026年93%正收益`——**全部是写死或口述的常量，无一可复算、无一带时效。** v2.1 的全部工作，就是把这些变成"算出来的、带来源的、会过期会告警的"。

---

## 1. P0｜让每个"钱的数字"可复算（核心改造）

新增两个脚本 + 改写报告数字来源。这是整份方案 80% 的价值所在。

### 1.1 新增 `skill/scripts/portfolio_math.py`——组合数学引擎

**为什么必须有它：** 组合的最大回撤**不能**用各基金最大回撤加权平均（它们发生在不同时点，加权是错的）。正确做法是：**用成份基金的累计净值序列，按目标权重合成出"组合净值曲线"，再在这条真实曲线上算回撤、波动、收益、情景表现。** 这样 `-8%` 不再是口述，而是"2021-06 至 2026-06 这条合成曲线峰谷法算出的真实数字"。

核心逻辑（可直接落地，math 部分已校对）：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
portfolio_math.py — 组合风险/收益引擎 v1.0
铁律：所有面向客户的风险/收益数字，必须由本模块基于真实净值序列算出，
      不允许在报告里写死或口述。每个输出都带"计算方法"字符串，便于在报告里标注来源。
输入：{code: weight} + 各基金的累计净值序列 DataFrame(index=日期, 列=该基金累计净值)
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252

def build_portfolio_nav(nav_dict: dict, weights: dict, rebalance: str = "none") -> pd.Series:
    """
    nav_dict: {code: pd.Series(累计净值, index=DatetimeIndex)}
    weights:  {code: 0.30, ...}  权重和应=1.0（函数内部会归一）
    rebalance: "none"=买入持有(权重漂移) / "monthly"=每月再平衡(权重恒定)
    返回：组合净值序列（起点归一为 1.0）
    """
    codes = list(weights.keys())
    w = np.array([weights[c] for c in codes], dtype=float)
    w = w / w.sum()  # 归一，防止权重和≠1引入误差

    # 对齐到所有基金都有数据的交易日（取交集，避免前向填充制造假净值）
    df = pd.concat({c: nav_dict[c] for c in codes}, axis=1).dropna()
    if df.empty or len(df) < 60:
        raise ValueError("有效重叠净值天数不足（<60），无法可靠计算，请检查数据或缩短回看区间")

    norm = df / df.iloc[0]          # 每只基金净值归一到 1.0

    if rebalance == "none":
        # 买入持有：组合价值 = Σ wᵢ · (净值ᵢ,t / 净值ᵢ,0)
        port = (norm * w).sum(axis=1)
    elif rebalance == "monthly":
        # 恒定权重月度再平衡：用日收益按权重加权再累乘
        rets = norm.pct_change().fillna(0.0)
        port_ret = (rets * w).sum(axis=1)
        port = (1.0 + port_ret).cumprod()
        port.iloc[0] = 1.0
    else:
        raise ValueError("rebalance 仅支持 'none' 或 'monthly'")
    return port

def max_drawdown(nav: pd.Series) -> float:
    """真实峰谷法最大回撤（负数，如 -0.083）"""
    running_max = nav.cummax()
    dd = nav / running_max - 1.0
    return float(dd.min())

def cagr(nav: pd.Series) -> float:
    """年化收益（基于真实区间起止 + 自然日年化）"""
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0:
        return float("nan")
    years = days / 365.25
    return float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1)

def ann_vol(nav: pd.Series) -> float:
    """年化波动率（日收益标准差 × √252）"""
    rets = nav.pct_change().dropna()
    return float(rets.std() * np.sqrt(TRADING_DAYS))

def worst_rolling_return(nav: pd.Series, window_days: int = 252) -> float:
    """最差滚动 N 日收益（默认1年）——比 VaR 更易向零售客户解释的'最惨持有体验'"""
    if len(nav) <= window_days:
        return float("nan")
    roll = nav / nav.shift(window_days) - 1.0
    return float(roll.min())

def hist_var(nav: pd.Series, horizon_days: int = 20, conf: float = 0.95) -> float:
    """历史模拟法 VaR（经验分位数，不假设正态——基金收益有肥尾/偏度，正态会低估尾部风险）"""
    roll = (nav / nav.shift(horizon_days) - 1.0).dropna()
    return float(np.percentile(roll, (1 - conf) * 100))

def correlation_matrix(nav_dict: dict) -> pd.DataFrame:
    """成份基金真实相关性矩阵（替代'<0.7'的口述；注意：危机时相关性会上行）"""
    df = pd.concat({c: nav_dict[c] for c in nav_dict}, axis=1).dropna()
    return df.pct_change().dropna().corr()

def scenario_test(nav_dict: dict, weights: dict, windows: dict, rebalance="none") -> dict:
    """
    历史情景回测：把组合套到指定历史区间，报告它'本会经历的真实回撤'。
    windows = {"2022熊市": ("2022-01-01","2022-12-31"), "2024年初": ("2024-01-01","2024-02-29"), ...}
    """
    out = {}
    for label, (start, end) in windows.items():
        sliced = {c: s.loc[start:end] for c, s in nav_dict.items()
                  if not s.loc[start:end].empty}
        if len(sliced) < len(weights):
            out[label] = None  # 该区间有基金尚未成立 → 诚实标注无法回测
            continue
        try:
            port = build_portfolio_nav(sliced, weights, rebalance)
            out[label] = {"区间收益": cagr(port), "区间最大回撤": max_drawdown(port)}
        except ValueError:
            out[label] = None
    return out

def summarize(nav_dict, weights, rebalance="none", windows=None):
    """一次性产出报告所需的全部风险/收益数字 + 各自的'计算方法'说明"""
    port = build_portfolio_nav(nav_dict, weights, rebalance)
    start, end = port.index[0].date(), port.index[-1].date()
    method = f"基于 {start}~{end} 各成份基金累计净值、按目标权重{'买入持有' if rebalance=='none' else '月度再平衡'}合成的组合净值序列计算"
    res = {
        "数据区间": f"{start} ~ {end}",
        "计算方法": method,
        "年化收益(历史)":  round(cagr(port), 4),
        "年化波动率":      round(ann_vol(port), 4),
        "历史最大回撤":    round(max_drawdown(port), 4),
        "最差滚动1年收益": round(worst_rolling_return(port), 4),
        "20日95%历史VaR":  round(hist_var(port), 4),
        "成份相关性矩阵":  correlation_matrix(nav_dict).round(2).to_dict(),
    }
    if windows:
        res["历史情景回测"] = scenario_test(nav_dict, weights, windows, rebalance)
    return res
```

**这一步直接修复的伪精确：**
- `黄金把回撤从 -12% 压到 -8%` → 跑两次 `summarize`（含黄金 vs 剔除黄金后归一），报告**实测**的回撤差，并附"计算方法"。
- `预期最大回撤 -6%~-8%` → 用 `历史最大回撤` + `历史情景回测`（2022/2018/2015 区间的真实回撤）给区间，并写明这是历史实测、非未来保证。
- `相关系数 < 0.7` → 直接贴真实相关性矩阵的数字，并加一句"危机期相关性会上行"的诚实限定。

> **远期收益的诚实处理（重要）**：历史年化是**最弱**的未来收益估计。债券端应优先用**当前到期收益率(YTM)**作远期代理，而非滚动历史收益；权益端用"无风险利率 + 风险溢价"比滚动历史更稳健。建议 `portfolio_math.py` 另设 `forward_return_estimate(method=...)`，强制在报告里写明用了哪种方法。"历史 5-7%" 和 "远期中性估计 4-6%" 是两个不同的数字，不能混用。

### 1.2 新增 `skill/scripts/fetch_fund_data.py`——数据获取层（akshare）

**为什么必须有它：** v2.0 所有基金指标靠手敲 JSON，且无任何机制校验数字真假与时效——一个抄错的回撤会直通客户报告。接入 akshare 后，"基金筛选师/市场研判师"从"纯框架"升级为"有数据支撑"。

已核实可用的 akshare 接口（v1.18.x；**首次运行务必核对列名**，akshare 会改列名）：

| 用途 | 接口 | 关键返回 |
|------|------|---------|
| 单只基金历史净值序列 | `ak.fund_open_fund_info_em(symbol="050019", indicator="累计净值走势")` | 净值时间序列（喂给 portfolio_math 的核心输入，用**累计净值**算含分红总回报） |
| 单只基金风险指标 | `ak.fund_individual_analysis_xq(symbol="050019")` | 近1/3/5年的 年化波动率 / 夏普 / 最大回撤（与自算结果交叉校验） |
| 持有盈利概率 | `ak.fund_individual_profit_probability_xq(symbol="050019")` | 持有满6月/1/2/3年盈利概率+平均收益（用于报告"盈利概率"叙事，有据可查） |
| 全市场最新净值/类型 | `ak.fund_open_fund_daily_em()` / `ak.fund_name_em()` | 代码、简称、类型、最新单位/累计净值 |
| 场内 ETF 历史 | `ak.fund_etf_hist_sina(symbol="sh510300")` | ETF 日线（场内标的用这个，非场外接口） |
| 货基/经理/成立日 | `ak.fund_money_fund_daily_em()` | 含 成立日期、基金经理（用于硬性排除项"经理任职<6月""成立<1年"的自动判定） |
| 宏观·10年国债 | `ak.bond_zh_us_rate()` | 中国10年期国债收益率（**替换写死的 1.74%**，首次运行核对列名） |

参考实现骨架（防御式，含 as_of 戳与单基金缓存）：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_fund_data.py — 数据获取层 v1.0
说明：akshare 接口名/列名可能随版本变化。请 pin 版本：pip install akshare==<你的版本> --break-system-packages
      并在首次运行用 --probe 模式打印一次列名核对。
产出：带 as_of 戳的 enriched fund_data.json，每个数字附 data_source。
"""
import akshare as ak
import pandas as pd
from datetime import date

def fetch_nav_series(code: str, indicator: str = "累计净值走势") -> pd.Series:
    df = ak.fund_open_fund_info_em(symbol=code, indicator=indicator)
    # ↓首次运行请核对真实列名后再写死；不同版本可能是 ['净值日期','累计净值'] 或 ['x','y']
    date_col = "净值日期" if "净值日期" in df.columns else df.columns[0]
    val_col  = "累计净值" if "累计净值" in df.columns else df.columns[1]
    s = pd.Series(df[val_col].astype(float).values,
                  index=pd.to_datetime(df[date_col]), name=code).sort_index()
    return s

def fetch_risk_metrics(code: str) -> dict:
    """雪球口径风险指标，用于交叉校验自算结果"""
    try:
        df = ak.fund_individual_analysis_xq(symbol=code)
        return df.set_index("周期").to_dict("index")  # {"近3年": {"最大回撤":..,"年化夏普比率":..}}
    except Exception as e:
        return {"_error": str(e)}

def fetch_cn_10y_yield() -> dict:
    df = ak.bond_zh_us_rate()
    col = [c for c in df.columns if "中国国债收益率10年" in c]
    val = float(df.sort_values(df.columns[0]).iloc[-1][col[0]]) if col else None
    return {"中国10年期国债收益率": val, "as_of": str(date.today()), "data_source": "akshare bond_zh_us_rate"}

def build_enriched_json(codes_weights: dict, out_path: str):
    today = str(date.today())
    funds = []
    for code, w in codes_weights.items():
        nav = fetch_nav_series(code)
        funds.append({
            "code": code, "weight": f"{w*100:.0f}%",
            "nav_last": float(nav.iloc[-1]), "nav_last_date": str(nav.index[-1].date()),
            "risk_metrics_xq": fetch_risk_metrics(code),
            "data_source": "akshare fund_open_fund_info_em / fund_individual_analysis_xq",
            "as_of": today,
        })
    payload = {"as_of": today, "macro": fetch_cn_10y_yield(), "funds": funds}
    pd.Series(payload).to_json(out_path, force_ascii=False, indent=2)
    return payload
```

> **诚实声明**：akshare 是社区维护、对接第三方网站，**接口偶尔会失效或改字段**。生产用法须加：版本 pin、列名核对、超时重试、失败降级到"上次缓存+醒目标注数据可能滞后"。它适合做"决策支撑"，不适合做"实时成交依据"。

### 1.3 改写 `generate_report.py` 的数字来源（不动渲染层）

只改"数字从哪来"，`build_consulting_doc()` / `build_general_doc()` 调用方式不变：

- **删除/外置**所有写死的风险收益常量。第 309 行 `'从预估-12%压低至{exp_dd}'`、风险量化表、预期收益区间，全部改为读取 `portfolio_math.summarize()` 的输出。
- **每个钱的数字加来源脚注**：在 docx 对应单元格下方或附注区，自动写入该数字的"计算方法"字符串 + `数据截止日`。例：
  > 历史最大回撤 −8.3%（基于 2021-06-25~2026-06-25 四只成份基金累计净值按目标权重买入持有合成的组合净值序列，峰谷法计算；历史表现不代表未来）。
- 报告新增固定附注块"**关键假设与数据时效**"：列出 as_of 日期、再平衡假设、相关性取值方式、远期收益估计方法。

### 1.4 时效闸门：外置宏观常量

把 `MARKET_SNAPSHOT`、`1.74%`、`75万亿存款搬家`、`固收+ 93%正收益` 从 .py 和知识库里抽出来，集中到 `skill/references/market_inputs.json`：

```json
{
  "as_of": "2026-06-25",
  "cn_10y_yield": 1.74,
  "deposit_migration_trillion": 75,
  "fixed_income_plus_positive_ratio_2026": 0.93,
  "notes": "每次正式案例前由首席投顾用 fetch_fund_data.py 刷新，或人工核对填入"
}
```

`generate_report.py` 启动时检查 `as_of`：**超过 30 天 → 打印醒目告警并要求确认**，避免把过期的"1.74%"打进三个月后的客户报告（那是事实性错误，不是估计误差）。

---

## 2. P1｜把"适当性"做成硬闸门（合规即护钱）

### 2.1 新增 `skill/scripts/suitability_check.py`——出报告前强制闸门

我审包时发现的硬矛盾：CHANGELOG 的回归测试用 `--risk_level R2` 跑了易方达蓝筹(-34%)/沪深300ETF(-27%)/兴全合宜(-30%)这类 R4 股基——**直接违反系统自己的"不得向R2推荐R4产品"红线**，也违反它自估的"R2行为容忍线约-8%~-10%"。这类错误必须由机器在出文档前拦下：

```python
RISK_BAND = {  # 客户风险等级允许持有的单基金最高风险 + 组合回撤红线
    "R1": {"max_fund_risk": "R1", "max_dd": -0.05},
    "R2": {"max_fund_risk": "R3", "max_dd": -0.10},  # R2行为容忍约-8~-10%(见EXP-PI-001)
    "R3": {"max_fund_risk": "R4", "max_dd": -0.18},
    "R4": {"max_fund_risk": "R5", "max_dd": -0.30},
    "R5": {"max_fund_risk": "R5", "max_dd": -0.50},
}
BANNED = ["保本", "稳赚", "一定涨", "保证收益", "稳赚不赔"]

def check(client_risk, funds, portfolio_max_dd, report_text=""):
    fails = []
    band = RISK_BAND[client_risk]
    for f in funds:
        if _risk_rank(f.get("risk_level","R5")) > _risk_rank(band["max_fund_risk"]):
            fails.append(f"成份基金 {f['name']} 风险({f.get('risk_level')}) 超出 {client_risk} 上限")
    if portfolio_max_dd < band["max_dd"]:   # 实测回撤比红线更深
        fails.append(f"组合历史最大回撤 {portfolio_max_dd:.1%} 超出 {client_risk} 红线 {band['max_dd']:.0%}")
    for w in BANNED:
        if w in report_text:
            fails.append(f"出现承诺性违规表述：'{w}'")
    return ("PASS", []) if not fails else ("FAIL", fails)
```

**PROJECT_INSTRUCTIONS 第 2 节"协作铁律"加一条：** "报告生成前，suitability_check 必须 PASS，否则不得调用 generate_report.py。"

### 2.2 修正示范数据 `fund_data_sample.json`

补 `layer` 字段（否则 v2.0 的三层架构表全是"未分类"），并把标的换成与 R2 真正匹配的组合（照搬 cases_register 里那个干净的 PI001：博时稳健回报 + 博时恒泰债 + 红利ETF + 黄金）。**别让随包的示范本身违反自己的红线。**

### 2.3 调和"说服力 vs 精确"——这是这套系统的关键张力

SKILL.md 明文"说服力优先于数据完整性""每章≤3个数据""把'不构成投资建议'移出正文""结尾必须行动号召"——这套行为设计在证据薄弱时，会**工程化地制造"信念跑赢证据"**。修法不是删掉说服力（它是这个团队真正的长板），而是加一道**不可删除的诚实底线**：

- 保留六章说服结构，但**强制保留一个"关键假设与数据时效"框**（含 as_of、计算方法、"数字为历史/估算、非承诺"）。
- "制造紧迫感"章节里量化"不行动成本"时，同样走 1.1 的计算 + 来源标注，不能口述。
- 一句话原则写进 SKILL.md 第一节：**"我们可以很有说服力，但每一个让客户掏钱的数字，都必须经得起客户拿计算器复核。"**

---

## 3. P2｜让进化闭环真正闭合（目前 n=0、且回访也是手动）

### 3.1 新增 `skill/scripts/verify_case.py`——自动回访验证

现状：进化机制设计完整，但 1 个案例、0 验证，且"季度回访"靠人工。接入数据层后可自动化：

```
输入：案例ID + 推荐日期 + 组合{code:weight}
动作：用 fetch_nav_series 拉推荐日至今的真实净值 → portfolio_math 合成 → 算实际收益/回撤
对比：实际 vs 当初预测区间 → 判定 已验证/部分验证/证伪
写回：自动更新 cases_register.md 的验证状态 + 实际收益/回撤列
```

这样 PROJECT_INSTRUCTIONS 第 5 节的"≥3 案例已验证 → 升 HIGH 置信"才真正可执行，经验层才会从"全是 LOW 先验"逐步沉淀出真东西。

### 3.2 经验升级以**真实验证结果**为唯一依据

`experience_overlay_*.md` 的置信升级，必须由 `verify_case.py` 产出的"已验证"案例计数驱动，不允许人工拍脑袋升级。

---

## 4. 部署顺序（Claude Desktop + Filesystem MCP）

每一步都走 PROJECT_INSTRUCTIONS 第 6 节既定仪式：**备份旧版 → 改文件 → 更新 skill_version_ledger → 写 CHANGELOG → git commit**（fswatch 守护会自动 push）。

```
① 装依赖（终端）：
   pip install akshare pandas numpy --break-system-packages
   python3 -c "import akshare; print(akshare.__version__)"   # 记下版本号，pin 进 CHANGELOG

② 建 portfolio_math.py（1.1）→ 用 PI001 的真实代码跑通 summarize，肉眼核对回撤合理
   （这一步不依赖 akshare 也能测：手动喂两段净值序列验证 max_drawdown/cagr 正确）

③ 建 fetch_fund_data.py（1.2）→ 先 --probe 打印列名核对 → 跑通单只基金净值拉取

④ 建 suitability_check.py（2.1）→ 用 R2 + 那批 R4 股基测试，确认它正确 FAIL

⑤ 改 generate_report.py 数字来源（1.3）→ 备份 v2.0 到 versions/skills/
   → 用 PI001 完整跑一遍：两份 docx 生成 + 风险数字来自引擎 + 附注含 as_of/方法

⑥ 外置 market_inputs.json（1.4）+ 修 fund_data_sample.json（2.2）

⑦ 建 verify_case.py（3.1）→ 用 PI001 试跑（推荐日至今）

⑧ 更新 SKILL.md（第一/五/六/八节）+ PROJECT_INSTRUCTIONS（第2/8节加闸门）
   → skill_version_ledger 标 v2.1 → CHANGELOG 写 v2.1 → git commit
```

---

## 5. 验收清单（v2.1 完成的判定标准）

- [ ] 报告里**没有任何**写死的风险/收益常量，全部来自 `portfolio_math` 输出
- [ ] 每个钱的数字旁都有"计算方法 + 数据截止日"脚注
- [ ] 组合最大回撤是**合成净值峰谷法**算出（非各基金回撤加权）
- [ ] "黄金降回撤"类对比有**两次实测**支撑，不再口述
- [ ] 宏观数（10年国债等）来自 `market_inputs.json` 且带 as_of，超期会告警
- [ ] `suitability_check` 能拦下"R4 基金进 R2 组合"和"组合回撤超容忍线"
- [ ] 报告强制含"关键假设与数据时效"框，说服力结构保留
- [ ] `fund_data_sample.json` 合规且含 layer 字段
- [ ] `verify_case.py` 能用真实净值自动更新 cases_register 验证状态
- [ ] 回归测试：PI001 两份 docx 正常生成，无报错

---

## 附：本次未纳入、但建议后续考虑

- **因子/风格暴露**：相关性矩阵之外，加风格箱（大小盘×价值成长）检查，防"两只低相关基金实为同一久期/成长押注，regime 切换一起崩"。
- **债券久期/信用风险显式化**："固收+"论点高度依赖利率路径；建议对债券成份标注久期，并在 10年国债破 2% 等触发点上做敏感性提示（PI001 已把"国债破2%"列为止损触发，方向正确，可系统化）。
- **机构/渠道经验层落地**：目前两类客户经验层仍是空壳 LOW 先验，待真实案例积累。

---

*本方案只改"数字怎么来"，不改 document-suite 渲染层与团队六角色编排。落地后，团队的"说服力"长板保留，而"判断的可信度"从'读起来确定'升级为'经得起复核'。*
