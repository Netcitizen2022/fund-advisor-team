# Skill 版本台账 — 基金投资顾问团队

> 维护者：知识归档师
> 所有 skill/ 目录下文件的版本变更历史

---

| 文件 | 当前版本 | 最后更新 | 变更摘要 | 备份位置 |
|------|---------|---------|---------|---------|
| skill/SKILL.md | v1.0 | 2026-06-25 | 初始部署：六角色体系+说服力报告框架 | versions/skills/SKILL_v1.0_20260625.md |
| skill/scripts/generate_report.py | v1.0 | 2026-06-25 | 初始部署：完整报告+一页纸摘要生成 | versions/skills/generate_report_v1.0_20260625.py |

---

## 更新规则

- `v1.x`：小迭代（新增字段、文字调整、bug修复）
- `v2.0`：大重构（角色体系变化、报告框架重设计、筛选逻辑重写）
- 每次更新：先备份旧版到 `versions/skills/`，再更新本表，再写 CHANGELOG
- 脚本更新后必须回归测试：`python3 skill/scripts/generate_report.py --funds_json skill/references/fund_data_sample.json ...`
