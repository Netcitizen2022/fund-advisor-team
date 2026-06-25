# DEPLOY_AND_INTEGRATE — fund-advisor-team v2.1 精确性改造

> 把本包的脚本部署进你本地仓库 `/Users/jacklee/Documents/01-agents/fund-advisor-team/`，
> 并把 `generate_report.py` 里写死的钱数字接到"算出来的" computed 块上。
> 全程遵循你 PROJECT_INSTRUCTIONS 第6节既定仪式：**备份→改→台账→CHANGELOG→git**。

---

## 1. 文件清单（放哪里）

直接把本包的 `skill/` 覆盖合并进你仓库的 `skill/`（不覆盖你已有的 `generate_report.py` 与 `SKILL.md`）：

```
skill/scripts/portfolio_math.py      ← 新增·组合数学引擎（已自测通过）
skill/scripts/fetch_fund_data.py     ← 新增·akshare 数据层（首次须 --probe 核对列名）
skill/scripts/suitability_check.py   ← 新增·适当性硬闸门（已自测通过）
skill/scripts/build_case.py          ← 新增·编排器（新前门：fetch→math→闸门→enriched JSON）
skill/scripts/verify_case.py         ← 新增·回访验证（让进化闭环转起来）
skill/references/market_inputs.json      ← 新增·外置宏观常量（带 as_of 时效）
skill/references/fund_data_sample_v2.json ← 替换旧 sample（补 layer + 改为R2合规标的）
```

> 旧的 `fund_data_sample.json` 留作历史或删除；新流程用 `_v2`。
> `references/nav_cache/`（净值缓存 CSV）由 `fetch_fund_data.py` 首次运行时自动创建，**建议加入 `.gitignore`**（数据会变，不必入库）。

---

## 2. 安装与首次核对（一次性）

```bash
cd /Users/jacklee/Documents/01-agents/fund-advisor-team
pip install akshare pandas numpy --break-system-packages
python3 -c "import akshare; print('akshare', akshare.__version__)"   # 记下版本，pin 进 CHANGELOG

# 离线自测（不联网，验证引擎与闸门正确）：
python3 skill/scripts/portfolio_math.py --selftest
python3 skill/scripts/suitability_check.py --selftest

# 首次联网必做：核对 akshare 列名（它会随版本改名）
python3 skill/scripts/fetch_fund_data.py --probe 050019
#   → 看输出的"列名"，若与脚本里写死的 ['净值日期','累计净值'] 不符，按实际改 fetch_nav_series 两行
```

---

## 3. 新工作流：`build_case.py` 是新前门

把它作为每个正式案例的入口。它一步产出：① enriched JSON（含每个钱数字+计算方法+as_of）② 终端"数字体检报告" ③ 适当性 PASS/FAIL。

```bash
# 在线（自动拉净值并缓存）：
python3 skill/scripts/build_case.py \
  --case skill/references/fund_data_sample_v2.json \
  --out_dir output/FA-20260625-PI001/

# 体检 PASS 后顺带出 docx（需 document-suite）：
#   加 --with-report

# 离线复算（用已缓存净值，不联网）：
#   加 --offline
```

产出 `output/<案例ID>/fund_data_enriched.json` 的结构：
```
{ "client": {...}, "funds": [...],
  "computed": {  组合_历史最大回撤 / 组合_年化收益_历史 / 分层指标 / 对冲层边际作用 /
                 历史情景回测 / 远期收益估计 / 计算方法 / as_of ... },
  "suitability": { result: PASS/FAIL, ... } }
```

---

## 4. ★核心：把 `generate_report.py` 的写死数字接到 computed 上

你的 `generate_report.py` 目前把很多案例数字写死在正文字符串里（围绕 PI001 写的）。改造分两步。

### 4a. 让脚本能读到 computed 块（最小改动）

`_load_data()` 目前只返回 `(client, funds)`。改为把 computed 也带出来。最简方式——在 `_load_data` 里把 computed 挂到 client_dict：

```python
def _load_data(funds_json_path):
    with open(funds_json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {}, raw
    client = raw.get('client', {})
    client['_computed'] = raw.get('computed', {})       # ← 新增这一行
    client['_suitability'] = raw.get('suitability', {})  # ← 新增这一行
    return client, raw.get('funds', [])
```

之后在 `_build_sections_full()` 顶部取出：
```python
C = client_dict.get('_computed', {})
capital_num = _to_number(client_dict.get('capital'))  # "100万元"→1000000，自行实现
```

### 4b. 逐处替换写死数字（精确映射表）

| 报告里现在写死的内容（行附近） | 改为读取 | 备注 |
|---|---|---|
| `MARKET_SNAPSHOT` 字典（L80–97） | `market_inputs.json → market_snapshot[market_status]` | 不再写死在 .py |
| "偏紧（10年期国债约1.74%）"（L92） | `market_inputs.json → macro.cn_10y_yield_pct` | 超 `stale_after_days` 天则告警 |
| "约75万亿存款搬家"、"纯债收益约3%"（L218–221） | `macro.deposit_migration_trillion`；纯债收益用 `C['分层指标']['核心层']['层内独立年化']` | |
| "本组合预期年化5-7%，3年累计约16-22万"（L233–236） | 历史：`C['组合_年化收益_历史']`；远期：`C['远期收益估计']['远期预期年化(假设)']`；金额=`capital_num×收益×年数` | **历史与远期分开写**，标注口径 |
| "约116-122万 / 约121-133万"（L247–249） | `capital_num×(1+区间收益)`，区间用历史/远期两口径 | 动态算，不写死 |
| 第四章 "从预估-12%压低至{exp_dd}"（L307–310） | `C['对冲层边际作用']`：`最大回撤_不含`→`最大回撤_含`，差值=`最大回撤_改善` | **实测两次的差**，不再口述 |
| "20%是精确计算后的平衡点"（L298–301） | 要么指向 computed 佐证，要么删"精确"二字 | 避免无支撑的"精确"措辞 |
| 第五章风险表 各层影响（"-3%~-5%/约2-3.5万"等，L319–345） | 每层影响=`C['分层指标'][层]['最坏加权影响']×capital_num`（取绝对值） | 注意是"最坏加权影响"非"独立回撤" |
| "组合最大亏损约8-9万（{exp_dd}）"（L341） | `C['组合_历史最大回撤']×capital_num` | |
| "您15万的心理赎回线"（L343/L348） | `client.tolerance_dd×capital_num` 或 `C/_suitability` 的 `effective_dd_limit×capital_num` | 与客户实际容忍线一致 |
| "10年期国债升破2%"（L327） | 可保留为情景描述，或由 `macro.cn_10y_yield_pct` 派生触发点 | |

### 4c. 给每个钱数字加来源脚注 + 固定"关键假设"框

- 在 docx 风险/收益表下方写入 `C['计算方法']` 与 `C['as_of']`。
- 报告固定增加一节"**关键假设与数据时效**"（不可删），含：数据截止日、再平衡方式、`C['远期收益估计']['采用CMA']`、`C['诚实声明']`。
- 这一步把"说服力"和"精确"调和：结构照旧有说服力，但每个让客户掏钱的数字都能被复核。

---

## 5. SKILL.md / PROJECT_INSTRUCTIONS 要改的地方

**PROJECT_INSTRUCTIONS 第2节"协作铁律"**，加两条：
> 8. 报告生成前，`build_case.py` 的适当性校验必须 PASS，否则不得出对外报告。
> 9. 报告中任何风险/收益数字必须来自 `computed` 块（portfolio_math 实测），禁止写死或口述。

**PROJECT_INSTRUCTIONS 第8节"每次任务工作方式"**，把第④⑤⑥步替换为：
> ④ 基金筛选师：用 `fetch_fund_data.py` 拉真实数据，五维评分
> ⑤ 组合构建师：定权重与分层 → 写 case JSON
> ⑥ `build_case.py` 跑体检：computed + 适当性闸门 PASS → 再调 generate_report

**SKILL.md 第一节**加一句信条：
> 我们可以很有说服力，但每一个让客户掏钱的数字，都必须经得起客户拿计算器复核。

**SKILL.md 第六节**补充 portfolio_math / fetch_fund_data / suitability_check / build_case / verify_case 的说明（脚本均在 `skill/scripts/`）。

---

## 6. 部署顺序（按 §6 仪式）

```
① 覆盖合并 skill/scripts 与 skill/references（不动 generate_report.py 与 SKILL.md 本体）
② 跑 §2 的两个 --selftest + 一次 --probe，确认环境与列名 OK
③ 备份 generate_report.py → versions/skills/generate_report_v2.0_<日期>.py
④ 按 §4 改 generate_report.py 的 _load_data + 写死数字（先改 _load_data 与第四/五章影响数）
⑤ 用 fund_data_sample_v2.json 跑：
      python3 skill/scripts/build_case.py --case skill/references/fund_data_sample_v2.json \
        --out_dir output/_smoketest/ --with-report
   确认：体检报告数字合理 + 适当性 PASS + 两份 docx 生成 + 数字来自 computed + 附注含 as_of
⑥ 改 PROJECT_INSTRUCTIONS（§2/§8）与 SKILL.md（§1/§6）
⑦ 更新 knowledge/meta/skill_version_ledger.md → 标 v2.1；写 CHANGELOG v2.1
⑧ git add -A && commit（fswatch 守护会自动 push）；删除 output/_smoketest/
⑨ 把 references/nav_cache/ 加进 .gitignore
```

---

## 7. 验收清单（与 IMPROVEMENT_PLAN_v2.1 一致）

- [ ] `portfolio_math --selftest` 与 `suitability_check --selftest` 全绿
- [ ] `fetch_fund_data --probe` 列名已核对，必要处已按本机 akshare 版本修正
- [ ] 报告中**无任何**写死的风险/收益常量，全部来自 computed
- [ ] 每个钱数字旁有"计算方法 + 数据截止日"
- [ ] 组合最大回撤来自**合成净值峰谷法**（非各基金回撤加权）
- [ ] "黄金降回撤"用 `对冲层边际作用` 的两次实测差
- [ ] 各层影响用 `最坏加权影响`（非"独立回撤"，避免把 -42% 这种单层独立数字误当组合影响）
- [ ] 宏观数来自 `market_inputs.json` 且带 as_of，超期告警
- [ ] 适当性闸门能拦下"R4 基金进 R2"与"组合回撤越线"
- [ ] 报告含不可删的"关键假设与数据时效"框
- [ ] `verify_case.py` 能用真实净值自动判定并输出可粘贴的回访行

---

*脚本均已在隔离环境用合成数据跑通全链路（含边界用例）。落地到本机后，唯一需按你 akshare 版本核对的是 `fetch_fund_data.py` 的列名映射——这是社区库版本漂移所致，`--probe` 一步即可确认。*
