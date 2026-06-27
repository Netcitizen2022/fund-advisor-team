# CHANGELOG — 基金投资顾问团队 (fund-advisor-team)

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
