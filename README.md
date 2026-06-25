# 基金投资顾问团队 (fund-advisor-team)

> 专业基金推荐与研究报告生成 Agent 团队。
> 六角色协作：首席投顾 → 市场研判师 → 基金筛选师 → 组合构建师 → 报告撰写师 → 知识归档师。
> 本地 Agent 团队（Claude Desktop + Filesystem MCP），底座为 `skill/SKILL.md`，
> 外加知识库沉淀、自我进化、版本控制与 GitHub 自动备份。

---

## 核心能力

- **客户画像快速锁定**：五问确定风险等级，输出结构化画像卡片
- **市场研判**：宏观三维扫描，给出明确市场状态标签（积极/中性/谨慎）
- **基金五维评分筛选**：经理能力、历史业绩、回撤控制、规模流动性、费率
- **组合构建**：核心+卫星架构，相关性控制，比例有逻辑
- **说服力报告生成**：六章结构，Word双版本（完整报告+一页纸摘要）
- **进化闭环**：季度回访验证，经验沉淀覆盖层

---

## 快速上手

1. 在 Claude Desktop 新建 Project，把本目录设为 Filesystem MCP 可访问路径
2. 项目指令写：`每次任务先读取 fund-advisor-team/PROJECT_INSTRUCTIONS.md，按团队编排工作。`
3. 直接对话即可

---

## 目录结构

```
fund-advisor-team/
├── PROJECT_INSTRUCTIONS.md     团队编排（每次任务先读）★
├── README.md  CHANGELOG.md  .gitignore
├── skill/
│   ├── SKILL.md                底座技能（六角色体系+说服力报告框架）
│   ├── scripts/
│   │   └── generate_report.py  Word报告生成脚本（Python）
│   └── references/
│       └── fund_data_sample.json   基金数据样例
├── knowledge/
│   ├── meta/
│   │   ├── knowledge_index.md      全局案例索引
│   │   └── skill_version_ledger.md skill版本台账
│   ├── rules/
│   │   ├── experience_overlay_个人投资者.md
│   │   ├── experience_overlay_理财经理渠道.md
│   │   └── experience_overlay_机构客户.md
│   └── cases_register.md       案例台账（关键结论+验证状态）
├── evolution/
│   ├── session-log.md
│   ├── git-commit.log
│   └── AAR/
├── output/                     成果产出（每案一子目录）
├── versions/skills/            skill历史备份
└── scripts/
    ├── git-watcher-daemon.sh
    ├── git-auto-commit.sh
    ├── setup-git-watcher.sh
    └── stage_b_check.sh
```

---

## 首次部署终端命令

```
cd /Users/jacklee/Documents/01-agents/fund-advisor-team
```
```
bash scripts/stage_b_check.sh
```
```
git remote add origin git@github.com:Netcitizen2022/fund-advisor-team.git
```
```
git branch -M main
```
```
git push -u origin main
```

---

## 使用示例

**快速口头推荐**（对话即可）：
> 「我有50万想买基金，稳健一点，投2-3年，以前只买过货基」

**生成完整研究报告**：
> 「帮我生成一份给张女士的基金推荐报告，R3平衡型，市场中性，50万」

**报告生成命令**（总顾问在收集完画像和组合数据后执行）：
```bash
python3 skill/scripts/generate_report.py \
  --client_name 「张女士」 \
  --risk_level R3 \
  --market_status 中性 \
  --funds_json output/FA-20260625-PI001/fund_data.json \
  --output_path output/FA-20260625-PI001/
```

---

> 维护者：Jack Lee　|　GitHub：[Netcitizen2022](https://github.com/Netcitizen2022)
