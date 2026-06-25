# CHANGELOG — 基金投资顾问团队 (fund-advisor-team)

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
