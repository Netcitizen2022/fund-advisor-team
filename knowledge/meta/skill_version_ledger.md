# Skill 版本台账 — 基金投资顾问团队

> 维护者：知识归档师
> 所有 skill/ 目录下文件的版本变更历史

---

| 文件 | 当前版本 | 最后更新 | 变更摘要 | 备份位置 |
|------|---------|---------|---------|---------| 
| skill/SKILL.md | v1.1 | 2026-06-26 | v2.1 同步：第1节加精确性信条；第6节改为五脚本说明+新前门工作流 | versions/skills/SKILL_v1.0_20260625.md |
| skill/scripts/generate_report.py | **v2.1** | **2026-06-26** | **精确性改造：数字来自 computed，宏观外置，适当性闸门，强制附注块** | versions/skills/generate_report_v2.0_20260626.py |
| PROJECT_INSTRUCTIONS.md | v1.1 | 2026-06-26 | 铁律8+9（适当性前置/数字来源）；第8节④⑤⑥步改为新前门流程 | （文档类，无需独立备份）|

---

## v2.0 变更说明（generate_report.py）

### 核心变更
- **接入 document-suite**：通过 `SUITE_ROOT` 常量引入 `/Users/jacklee/Documents/02-skills/document-suite`
- **完整版**：由 `build_consulting_doc()` 生成，色系炭灰+橙金，字体黑体/仿宋，橙金左竖线章节标题
- **一页纸摘要版**：由 `build_general_doc()` 生成，深海蓝+暖橙色系，与完整版一眼区分
- **字体规范**：标题黑体/方正小标宋，正文仿宋_GB2312，由 docx_builder.py v1.1 统一管理
- **表格规范**：tblGrid + tcW 双重列宽锁定，固定布局，单元格内边距，防列宽失效

### 向后兼容
- 命令行参数完全不变（--client_name / --risk_level / --market_status / --funds_json / --output_path）
- fund_data.json 两种格式均支持：v1.0 list 格式 / v2.0 dict with client+funds 格式
- 输出文件名规则不变

### 新增功能
- `_load_data()`：自动识别 json 格式，提取 client 字段（资金额、期限、预期收益、最大回撤等）用于报告内容
- `_fund_table_rows()`：自动合并 weight + amount 为「占比/金额」列
- `_arch_table_rows()`：按 layer 字段自动生成三层架构汇总表
- `_build_sections_full()`：六章内容完整组装，市场快照表、风险量化表均自动生成
- `_build_sections_summary()`：一页纸三节：KPI总览 + 基金表 + 三步操作

### 路径迁移
如果 document-suite 移动位置，只需修改脚本顶部的 `SUITE_ROOT` 常量，其余代码不动。

### 回归测试命令
```bash
cd /Users/jacklee/Documents/01-agents/fund-advisor-team
python3 skill/scripts/generate_report.py \
  --client_name  客户 \
  --risk_level   R2 \
  --market_status 谨慎 \
  --funds_json   output/FA-20260625-PI001/fund_data.json \
  --output_path  output/FA-20260625-PI001/
```
期望输出：
- `output/FA-20260625-PI001/基金推荐报告_客户_YYYYMMDD.docx`（咨询模板，炭灰+橙金）
- `output/FA-20260625-PI001/基金组合一页纸_客户_YYYYMMDD.docx`（通用模板，深海蓝+暖橙）

---

## 更新规则

- `v1.x`：小迭代（新增字段、文字调整、bug修复）
- `v2.0`：大重构（接入外部库、渲染引擎替换、接口兼容性升级）
- 每次更新：先备份旧版到 `versions/skills/`，再更新本表，再写 CHANGELOG
- 脚本更新后必须回归测试（见上方命令），确认两份 docx 均能正确生成

---

## v2.1 变更说明（generate_report.py + SKILL.md + PROJECT_INSTRUCTIONS）

### generate_report.py v2.1 核心变更

**精确性改造（不碰 document-suite 渲染层）**

- `_load_data()`：新增把 `computed` 块挂到 `client['_computed']`，`suitability` 挂到 `client['_suitability']`，供各章节读取
- `_load_market_inputs()`：新增函数，从 `skill/references/market_inputs.json` 加载宏观常量，超过 `stale_after_days`（默认30天）打印告警
- `_check_suitability()`：新增适当性闸门，`suitability.result == FAIL` 则 `sys.exit(2)`，不得生成对外报告
- `_to_number()` / `_fmt_wan()`：新增工具函数，把「100万元」转浮点数、把元值格式化为「XX万元」
- 第一章：流动性行从 `market_inputs.macro.cn_10y_yield_pct` 读取，替代写死的「1.74%」；存款搬家规模从 `deposit_migration_trillion` 读取
- 第二章：收益展示分「历史年化」与「远期估计」两个口径，各自标注来源；账面金额从 `capital_num × hist_cagr × 年数` 动态算
- 第四章：对冲层边际作用从 `computed['对冲层边际作用']` 读实测两次之差，不再口述「-12%→exp_dd」
- 第五章：各层影响金额从 `computed['分层指标'][层]['最坏加权影响'] × capital_num` 算；组合最大亏损从 `computed['组合_历史最大回撤'] × capital_num` 算；心理赎回线从 `client.tolerance_dd × capital_num` 算
- 每个钱数字段落后附「计算方法 + 数据截止日」脚注 body 段
- 新增报告第七节「关键假设与数据时效」（不可删除），含数据截止日、再平衡方式、CMA方法、诚实声明

### SKILL.md v1.1 变更
- 第一节新增精确性信条：「我们可以很有说服力，但每一个让客户掏钱的数字，都必须经得起客户拿计算器复核。」
- 第六节从「v2.0 单脚本」改为「v2.1 六脚本完整说明」，含跨脚本工作流图、首次部署命令、enriched JSON 格式示例

### PROJECT_INSTRUCTIONS.md v1.1 变更
- 第2节新增铁律8：适当性校验 PASS 前置，否则禁止调用 generate_report.py
- 第2节新增铁律9：风险/收益数字必须来自 computed 块或带 as_of 的 market_inputs，禁止写死或口述
- 第8节 ④⑤⑥ 步改为：fetch_fund_data拉数据 → 写case JSON → build_case体检（PASS后）→ generate_report

### 向后兼容
- 命令行参数不变
- 旧格式 JSON（无 computed 块）：跳过适当性闸门（仅提示），数字降级到 client 字段的字符串值
- document-suite 渲染层（build_consulting_doc / build_general_doc）调用方式 100% 不变

### 验收命令（需在用户终端执行）
```bash
cd /Users/jacklee/Documents/01-agents/fund-advisor-team

# 离线自测
python3 skill/scripts/portfolio_math.py --selftest
python3 skill/scripts/suitability_check.py --selftest

# 联网列名核对（首次必做）
python3 skill/scripts/fetch_fund_data.py --probe 050019

# 冒烟测试
python3 skill/scripts/build_case.py \
  --case skill/references/fund_data_sample_v2.json \
  --out_dir output/_smoketest/ --with-report
```
