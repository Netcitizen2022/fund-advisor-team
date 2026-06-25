# CHANGELOG — 基金投资顾问团队 (fund-advisor-team)

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
