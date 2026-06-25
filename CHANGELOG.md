# CHANGELOG — 基金投资顾问团队 (fund-advisor-team)

---

## [v2.1] — 2026-06-26（精确性改造版）

### skill/scripts/generate_report.py → v2.1

**核心目标：把报告里每一个钱数字，从「写死/口述」改为「算出来的、带来源的、会过期会告警的」。不碰 document-suite 渲染层。**

**新增函数**

- `_load_market_inputs()`：从 `skill/references/market_inputs.json` 加载宏观常量；超过 `stale_after_days`（默认30天）打印时效警告，非阻断模式（留人工判断）
- `_check_suitability()`：适当性硬闸门；`suitability.result == FAIL` → `sys.exit(2)`，禁止生成对外报告；无 suitability 块时提示兼容旧格式
- `_to_number()`：把「100万元」「50万」等字符串转浮点数（元单位），支持万/亿/裸数字
- `_fmt_wan()`：把元数值格式化为「XX.X万元」，用于报告金额展示

**`_load_data()` 改造**

- 新增把 `computed` 块挂到 `client['_computed']`
- 新增把 `suitability` 块挂到 `client['_suitability']`
- v1.0 list 格式、v2.0 dict 格式向后兼容不变

**`_build_sections_full()` 数字来源改造（映射表）**

| 原写死内容 | v2.1 改为读取 |
|-----------|---------------|
| `MARKET_SNAPSHOT` 字典（.py 内写死） | `market_inputs.json → market_snapshot[market_status]` |
| 流动性行「10年期国债约1.74%」 | `market_inputs.macro.cn_10y_yield_pct` |
| 「约75万亿存款搬家」 | `market_inputs.macro.deposit_migration_trillion` |
| 「纯债收益约3%」 | `computed['分层指标']['核心层']['层内独立年化']` |
| 收益区间「5-7%」（第二章） | 分两行：历史 `computed['组合_年化收益_历史']`；远期 `computed['远期收益估计']['远期预期年化(假设)']` |
| 账面金额「约116-122万元」（第二章） | `capital_num × (1 + hist_cagr) ^ 年数`，动态计算 |
| 对冲层「从-12%压低至{exp_dd}」（第四章） | `computed['对冲层边际作用']`：`最大回撤_不含` → `最大回撤_含`，差值标注为两次实测之差 |
| 各层影响金额「2-3.5万/1.6-2.4万/1-1.5万」（第五章） | `computed['分层指标'][层]['最坏加权影响'] × capital_num` |
| 组合最大亏损「8-9万」（第五章） | `computed['组合_历史最大回撤'] × capital_num` |
| 「您15万的心理赎回线」（第五章） | `client.tolerance_dd × capital_num` |
| 利率触发点「升破2%」（第五章） | `market_inputs.macro.cn_10y_yield_pct + 0.3`，动态派生 |

**新增脚注机制**

- 每个包含钱数字的段落后，追加 body 段写明「计算方法 + 数据截止日」
- 四类脚注：`fn_macro`（宏观来源）、`fn_computed`（组合计算方法）、`fn_fwd`（远期估计诚实声明）、`fn_hedge`（对冲测算说明）

**新增不可删附注节**

- 报告末尾新增「附：关键假设与数据时效」节，含：数据截止日、宏观截止日、再平衡方式、CMA方法、相关性取值说明、回撤口径说明、分层影响口径说明、诚实免责声明
- 该节在 `_build_sections_full()` 中硬编码为最后一节，不可通过参数删除

**`generate_full_report()` / `generate_summary_sheet()` 签名变更**

- 新增参数 `market_inputs`（dict），透传给 `_build_sections_*`
- 命令行入口（`main()`）调用顺序：`_load_market_inputs()` → `_load_data()` → `_check_suitability()` → 生成两份文档

**向后兼容**

- 命令行参数完全不变（--client_name / --risk_level / --market_status / --funds_json / --output_path）
- 旧格式 JSON（无 computed 块）：`_computed` 为空 dict，各数字字段降级到 client 字段字符串值（如 `portfolio_expected_return`），保持可读
- 适当性闸门：无 `_suitability` 块时仅打印提示，不阻断（兼容旧流程）
- document-suite 渲染层（`build_consulting_doc` / `build_general_doc`）调用方式 100% 不变

**备份**

- v2.0 备份位置：`versions/skills/generate_report_v2.0_20260626.py`

---

### skill/SKILL.md → v1.1

- **第一节**新增精确性信条：「我们可以很有说服力，但每一个让客户掏钱的数字，都必须经得起客户拿计算器复核。」
- **第六节**从「v2.0 单脚本调用说明」全面改写为「v2.1 六脚本完整说明」
  - 新增跨脚本工作流图（`build_case.py` 为前门）
  - 新增六脚本职责表（`portfolio_math` / `fetch_fund_data` / `suitability_check` / `build_case` / `verify_case` / `generate_report`）
  - 新增首次部署命令（含 --selftest / --probe 步骤）
  - 新增正式案例入口（Step1 体检 → Step2 生报告）
  - 新增 enriched JSON 格式示例（含 computed + suitability 结构）
  - 版本历史补充 v2.1 条目

---

### PROJECT_INSTRUCTIONS.md → v1.1

- **第2节「协作铁律」**新增两条：
  - 铁律8：适当性校验 PASS 前置——生成对外报告前 `build_case.py` 必须输出 PASS，FAIL 则禁止调用 `generate_report.py`
  - 铁律9：数字来源强制——报告中任何风险/收益数字必须来自 `computed` 块或带 `as_of` 的 `market_inputs.json`，禁止写死或口述
- **第8节「每次任务工作方式」** ④⑤⑥步改写：
  - ④ 基金筛选师：调用 `fetch_fund_data.py` 拉真实净值，五维评分
  - ⑤ 组合构建师：定权重与分层 → 写 case JSON（含 `layer` 字段与 `tolerance_dd`）
  - ⑥ `build_case.py` 跑体检：produced computed + 适当性 PASS 后，再调 `generate_report.py`

---

### knowledge/meta/skill_version_ledger.md → 更新

- `generate_report.py` 条目更新为 v2.1，备份指向 `generate_report_v2.0_20260626.py`
- `SKILL.md` 条目更新为 v1.1
- `PROJECT_INSTRUCTIONS.md` 条目新增 v1.1
- 新增「v2.1 变更说明」完整段落

---

### 验收清单

- [x] v2.0 备份至 `versions/skills/generate_report_v2.0_20260626.py`
- [x] generate_report.py 无任何写死的风险/收益常量，全部来自 computed 或 market_inputs
- [x] 每个钱数字段落后有计算方法 + 数据截止日脚注
- [x] 宏观常量（10年国债等）来自 market_inputs.json 且带 as_of，超期告警
- [x] 对冲层边际作用用两次实测差，不再口述
- [x] 各层影响用「最坏加权影响」口径，非独立回撤
- [x] 心理赎回线从 client.tolerance_dd × capital 动态算，不写死「15万」
- [x] 适当性闸门能拦下 FAIL 案例，阻止生成对外报告
- [x] 报告含不可删「关键假设与数据时效」附注节
- [x] SKILL.md 含精确性信条 + 六脚本完整说明
- [x] PROJECT_INSTRUCTIONS 含铁律8+9 + 新前门流程步骤
- [ ] `portfolio_math --selftest` 全绿（**待用户终端验证**）
- [ ] `suitability_check --selftest` 全绿（**待用户终端验证**）
- [ ] `fetch_fund_data --probe 050019` 列名已核对（**待用户终端验证**）
- [ ] 冒烟测试：`build_case + fund_data_sample_v2.json` 两份 docx 正常生成（**待用户终端验证**）

---

## [v2.0] — 2026-06-25

### skill/scripts/generate_report.py → v2.0（重大重构）

**核心变更：接入 document-suite，统一文档规范**

- 渲染引擎从手写 python-docx 样式替换为 `document-suite` 模板库
  - 完整版：`build_consulting_doc()`（咨询模板，炭灰 #2C3E50 + 橙金 #E67E22）
  - 一页纸：`build_general_doc()`（通用模板，深海蓝 #0A4D68 + 暖橙 #F4A261）
- 字体规范统一：标题 黑体/方正小标宋，正文 仿宋_GB2312，由 `docx_builder.py v1.1` 管理
- 表格规范统一：tblGrid + tcW 双重列宽锁定 + 固定布局 + 单元格内边距，防 Word/WPS 列宽失效
- 新增 `SUITE_ROOT` 常量：路径迁移只改一行

**新增功能**

- `_load_data()`：自动识别 v1.0 list 格式与 v2.0 dict 格式，向后兼容
- `_fund_table_rows()`：自动合并 weight + amount 列，生成「占比/金额」
- `_arch_table_rows()`：按 fund.layer 字段自动生成三层架构汇总表
- `_build_sections_full()`：六章内容完整组装，市场快照表、风险量化表均动态生成
- `_build_sections_summary()`：一页纸三节：KPI总览 + 基金表 + 三步操作
- `MARKET_SNAPSHOT` 字典：三种市场状态对应的三维快照数据，随状态标签自动切换

**向后兼容**

- 命令行参数完全不变（--client_name / --risk_level / --market_status / --funds_json / --output_path）
- fund_data.json v1.0 list 格式仍可直接使用，client 字段为可选增强
- 输出文件名规则不变

**已归档**

- v1.0 备份位置：`versions/skills/generate_report_v1.0_20260625.py`

---

### skill/SKILL.md → 第六节更新

- 第六节「Python报告生成脚本」全面更新为 v2.0 说明
- 新增渲染引擎对照表、fund_data.json v2.0 推荐格式示例、路径迁移说明
- 新增版本历史记录

---

### knowledge/meta/skill_version_ledger.md → 更新

- generate_report.py 条目更新为 v2.0
- 新增 v2.0 变更说明、向后兼容说明、回归测试命令

---

### 回归测试命令

```bash
cd /Users/jacklee/Documents/01-agents/fund-advisor-team

python3 skill/scripts/generate_report.py \
  --client_name  客户 \
  --risk_level   R2 \
  --market_status 谨慎 \
  --funds_json   output/FA-20260625-PI001/fund_data.json \
  --output_path  output/FA-20260625-PI001/

# 期望：两份 docx 成功生成，无报错
# 完整版：咨询模板，炭灰+橙金，黑体/仿宋字体
# 一页纸：通用模板，深海蓝+暖橙
```

---

## [v1.0] — 2026-06-25

### 初始部署
- 建立团队六层骨架：`skill/ · knowledge/ · evolution/ · output/ · versions/ · scripts/`
- 底座 skill/SKILL.md v1.0：六角色体系（首席投顾/市场研判师/基金筛选师/组合构建师/报告撰写师/知识归档师）
- 五维基金筛选模型：基金经理能力(30%) / 历史业绩(25%) / 回撤控制(20%) / 规模流动性(15%) / 费率(10%)
- 说服力六章报告框架：市场锚定→不行动代价→筛选透明化→组合结构→主动风险揭示→行动指引
- Python报告生成脚本 v1.0：完整研究报告 + 一页纸摘要双版本（skill/scripts/generate_report.py）
- 知识库：三客户类型经验覆盖层（个人投资者/理财经理渠道/机构客户），冷启动含3条LOW置信先验
- 运维层：git自动化三件套（BASE自动探测）、.gitignore、stage_b_check.sh（含python-docx依赖检查）

### 待办（用户终端执行）
- `bash scripts/stage_b_check.sh` 完整运行
- 在 GitHub 建空仓库 `fund-advisor-team`，连接 remote，首次 push
- Claude Desktop 新建 Project，设路径 + 项目指令

### 架构决策记录
- 知识库按「客户类型」切分（而非「市场环境」），原因：客户类型决定沟通策略差异更大
- 报告章节顺序为「说服力顺序」而非「分析顺序」，原因：目标是让客户采纳，不是展示分析能力
- 五问客户画像为硬约束，不可绕过，原因：风险匹配是合规底线，也是信任基础
