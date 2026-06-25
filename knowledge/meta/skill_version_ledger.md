# Skill 版本台账 — 基金投资顾问团队

> 维护者：知识归档师
> 所有 skill/ 目录下文件的版本变更历史

---

| 文件 | 当前版本 | 最后更新 | 变更摘要 | 备份位置 |
|------|---------|---------|---------|---------|
| skill/SKILL.md | v1.0 | 2026-06-25 | 初始部署：六角色体系+说服力报告框架 | versions/skills/SKILL_v1.0_20260625.md |
| skill/scripts/generate_report.py | **v2.0** | **2026-06-25** | **接入 document-suite，调用 build_consulting_doc + build_general_doc** | versions/skills/generate_report_v1.0_20260625.py |

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
