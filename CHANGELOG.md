# CHANGELOG — 基金投资顾问团队 (fund-advisor-team)

---

## [v2.2] 强制执行版（Enforcement Edition）— 2026-06-27

### 变更背景

第三方成熟度评估（资深基金经理视角）发现：本系统「设计成熟度高、运营成熟度低」——
凡机器强制执行的维度（工程治理）成熟；凡靠人自觉的维度（适当性 / 数据真实性 / 进化闭环）
一到实战就塌方。最尖锐的证据是 **FA-20260627-PI002（李永胜案例）**：

- `output/FA-20260627-PI002/fund_data.json` 的 `computed` 块是**手工编造**的，块内自带
  「以下数字为基于公开历史数据的估算值，非精确计算……应由 portfolio_math.py 联网实算替换」
  的免责声明；`数据区间=None`、`历史情景回测={}`、`成份相关性矩阵={}`。
- 案例**没有 suitability 块**（绕过了 build_case.py 适当性闸门），但台账却记为「适当性 PASS」。
- 组合 80% 集中在三只高相关 AI/科技基金（被包装成「双核分散」），却向 R4 首次权益客户
  承诺「-20% 硬顶 / 极端 -28%」——2022 年同类基金回撤 -40~-50%，该承诺不可信。

根因：generate_report.py 的 `_check_suitability()` 在 suitability 块缺失时**仅告警、继续生成**，
等于给造假留了后门；五维筛选模型与「经验收紧」规则只写在文档里、没有代码强制执行。

### 修复总纲：把「靠人自觉」改成「机器强制」

| 审计发现 | v2.2 修复 | 强制层级 |
|---------|----------|---------|
| 适当性闸门可绕过（空块放行） | generate_report 入口：空 suitability 块**硬退出** | 代码 sys.exit(2) |
| computed 可手编空壳 | 新增 computed 真实性闸门（数据区间/as_of/造假特征文本检测） | 代码 sys.exit(2) |
| 伪分散（三只同主题）查不出 | suitability_check 新增**主题集中度闸门**（单主题>50%→FAIL） | 代码闸门 |
| EXP-PI-001「首次收紧5pp」仅文档 | suitability_check **经验收紧**内嵌进有效回撤红线 | 代码闸门 |
| 五维筛选模型无代码 | 新增 **screen_funds.py**（五维评分+硬排除可执行化） | 新脚本+自测 |
| 写死的「-12% 黄金对冲」兜底 | 删除该兜底，未实测一律不给数字 | 代码 |
| 进化闭环空转（AAR 目录空） | 补写 **AAR-001**（PI002 事故复盘+根因+防线） | 知识沉淀 |

### 文件级变更

**skill/scripts/generate_report.py → v2.2**
- `_check_suitability(client_dict, allow_unverified=False)`：suitability 块缺失从「告警放行」改为
  **硬退出 sys.exit(2)**；result 未知亦默认拦截（FA-PI002 正是空块溜过，本版彻底堵死）
- 新增 `_assert_computed_real()` + `_FAKE_COMPUTED_MARKERS`：computed 缺失 / 数据区间为空 /
  as_of 缺失 / 含「估算值·非精确计算·应由portfolio_math替换」等造假特征文本 / 情景与相关性双空 → 拒绝
- 新增 `--allow-unverified` 旗标：仅供手工调试，显式声明才放行，产出打「内部草稿·严禁交付」标记
- 删除第四章对冲层「从预估-12%压低至…」写死兜底，改为「未实测不给数字」
- 渲染层（document-suite）改为延迟加载：导入下沉到闸门通过之后——造假输入在任何环境
  （含无 document-suite 的 CI/审计机）都确定性 `exit 2`，不再因 import 期缺套件 `exit 1` 掩盖闸门

**skill/scripts/suitability_check.py → v1.1**
- 新增 `_infer_theme()`（按 type/name 权威判定，不扫营销文案，避免「组合保险丝→保险」误判）
- 新增 `concentration_check(funds, limit=0.50)`：权益主题集中度闸门（固收/黄金不计权益集中度）
- `check()` 新增 `first_time_equity / experience / concentration_limit / tighten_pp` 参数（全部向后兼容）
- 经验收紧（EXP-PI-001 代码化）：首次权益 或 R1 客户，回撤红线自动收紧 tighten_pp（默认 5pp）
  - 刻意**不**对所有 R2 一刀切收紧（否则误拦正常稳健组合，PI001 仍 PASS）

**skill/scripts/build_case.py → v1.1**
- 新增 `_derive_first_time_equity()`：从客户经验描述推断首次权益投资者（可由 case JSON 显式覆盖）
- 调 suitability_check 时传入 first_time_equity / experience / concentration_limit，enriched
  suitability 块现含 concentration / tightening 明细

**skill/scripts/screen_funds.py → v1.0（新增）**
- 把 SKILL.md「角色3 基金筛选师」五维模型（经理30/业绩25/回撤20/规模15/费率10）变成可执行评分
- 硬排除项代码化：经理变更<6月 / 规模<2亿 / 成立<1年 / 近1年回撤>-40%
- 子分算法全透明、可复算，`--selftest` 含 5 个合成候选验证打分与排除

**文档与知识**
- PROJECT_INSTRUCTIONS.md v1.2 → v1.3：新增铁律10（computed 真实性）、铁律11（集中度上限），
  第8节工作流加入 screen_funds
- skill/SKILL.md v1.1 → v1.2：第6节加 screen_funds 说明，新增集中度原则
- knowledge/rules/experience_overlay_个人投资者.md：EXP-PI-001 标记为「已代码强制」，
  新增 EXP-PI-004（集中度）、EXP-PI-005（computed 真实性），登记 PI002 反例
- knowledge/cases_register.md：PI002 状态更正为「适当性待重算 / 证伪流程中」
- evolution/AAR/AAR-001_PI002_fabricated_computed.md（新增）：首份 AAR
- output/FA-20260627-PI002/fund_data_corrected.json（新增）：剥离造假 computed 的纯输入态案例

### 验收（已在升级包内离线全绿）

```bash
python3 skill/scripts/portfolio_math.py    --selftest   # 不变，回归
python3 skill/scripts/suitability_check.py --selftest   # 8 用例含集中度/经验收紧
python3 skill/scripts/screen_funds.py      --selftest   # 五维评分+硬排除
python3 skill/scripts/build_case.py --case skill/references/fund_data_sample_v2.json \
        --out_dir output/_smoketest/ --offline           # PI001 仍 PASS（回归）
# 关键回归：旧的 PI002 造假 JSON 现在会被报告脚本拒绝（exit 2）
python3 skill/scripts/generate_report.py --client_name 李永胜 --risk_level R4 \
        --market_status 谨慎 --funds_json output/FA-20260627-PI002/fund_data.json \
        --output_path /tmp/should_refuse/   # → [✗] 入口闸门 拒绝，exit 2
```

### 版本台账

| 文件 | 旧版本 | 新版本 | 备份位置 |
|------|-------|-------|---------|
| skill/scripts/generate_report.py | v2.1 | v2.2 | versions/skills/generate_report_v2.1_20260627.py |
| skill/scripts/suitability_check.py | v1.0 | v1.1 | versions/skills/suitability_check_v1.0_20260627.py |
| skill/scripts/build_case.py | v1.0 | v1.1 | versions/skills/build_case_v1.0_20260627.py |
| skill/scripts/screen_funds.py | （新增） | v1.0 | — |
| PROJECT_INSTRUCTIONS.md | v1.2 | v1.3 | versions/skills/PROJECT_INSTRUCTIONS_v1.2_20260627.md |
| skill/SKILL.md | v1.1 | v1.2 | versions/skills/SKILL_v1.1_20260627.md |

---

## [v1.2] PROJECT_INSTRUCTIONS — 2026-06-27（文档渲染规范补丁）

### 变更背景

FA-20260627-PI002（李永胜案例）报告生成过程中，发现两处流程违规：
1. 报告撰写师绕过了 `document-suite` 渲染层，直接使用 Claude 沙箱 Node.js `docx` 库生成 Word，导致字体（Arial vs 微软雅黑）、色系（蓝色系 vs 朱砂红+暗金）、表格风格与 PI001 参考附件不一致
2. 生成的 docx 文件只留在沙箱临时目录 `/mnt/user-data/outputs/`，未写回本地案例目录

### 根本原因

任务开始时跳过了「先读项目规范」步骤，用默认行为替代了明确约定，属于流程遵从性失败。

### 修复内容（PROJECT_INSTRUCTIONS v1.1 → v1.2）

**§4.1 产出形式** 新增：
- 文档渲染强制路由说明：`tpl_finance.py → build_finance_doc() → 本地执行`
- 执行前必读文件列表
- 明确三条禁止行为（❌ Node.js docx / ❌ 其他工具 / ❌ 只留沙箱）
- 案例目录须包含 `gen_report.py` 脚本

**§8 每次任务工作方式** 新增：
- 步骤⑦独立拆出「报告撰写师」子流程（先读模板 → 生成脚本 → 提示本地执行 → 确认归档）
- 文档生成检查清单（6项，每次生成前逐项确认，不可跳过）

### 版本台账

| 文件 | 旧版本 | 新版本 | 备份位置 |
|------|-------|-------|---------|
| PROJECT_INSTRUCTIONS.md | v1.1 | v1.2 | versions/skills/PROJECT_INSTRUCTIONS_v1.1_20260627.md |

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

---

## [v1.0] — 2026-06-25（初始版本）

### 架构决策记录
- 知识库按「客户类型」切分（而非「市场环境」），原因：客户类型决定沟通策略差异更大
- 报告章节顺序为「说服力顺序」而非「分析顺序」，原因：目标是让客户采纳，不是展示分析能力
- 五问客户画像为硬约束，不可绕过，原因：风险匹配是合规底线，也是信任基础

## [2026-06-26] generate_report.py bug fix（测试发现）
- 修复：_build_sections_full 第325行 fwd_return_str 拼接 TypeError
  （fwd_est['采用CMA'] 为 dict，改为 str() 安全转换）
- 修复：assumptions_text 第431行同类问题
- 触发：端到端冒烟测试 --with-report 时发现
- 验证：build_case --offline --with-report 产出两份 docx，全链路通过
