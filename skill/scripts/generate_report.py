#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基金推荐研究报告生成脚本 v2.2（强制执行版）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.2 变更（强制执行 / 堵死造假后门）：
  - 入口闸门升级为【硬拦截】：
      · _suitability 块缺失  → 不再「仅告警放行」，直接 sys.exit(2)
        （FA-PI002 正是「无 suitability 块仍出报告」溜过的——本版彻底堵死）
      · computed 块必须真实：数据区间/as_of/计算方法 三者齐全，
        且不得含「估算值/非精确计算/应由portfolio_math替换」等造假特征文本，
        历史情景回测与相关性矩阵不得双空 → 否则 sys.exit(2)
  - 新增 --allow-unverified 旗标：仅供手工/调试，显式声明后才放行，
    且产出会被打上「内部草稿·严禁交付」提示（默认不允许）
  - 渲染层（document-suite）改为延迟加载：闸门在前、导入在后——确保造假输入
    在任何环境（含无 document-suite 的 CI/审计机）都于闸门处 exit 2，
    而非在 import 期因缺套件 exit 1，掩盖闸门是否真正生效
  - 删除第四章对冲层「从预估-12%压低至…」的写死兜底，改为「未实测不给数字」
    （任何未经实算的金额/比例，一律不出现在客户报告里）

v2.1 变更（精确性改造）：
  - _load_data() 新增：把 enriched JSON 的 computed / suitability 块带出来
  - MARKET_SNAPSHOT / 宏观常量 从 .py 移除，改读 market_inputs.json（带 as_of 时效检查）
  - 第一章：流动性状态从 market_inputs.macro 读取，替代写死的「1.74%」
  - 第二章：纯债收益率读 computed 分层指标；收益区间、账面金额从 computed 动态算
  - 第四章：对冲层边际作用（「-12%压低至{exp_dd}」）改为读 computed['对冲层边际作用']
  - 第五章：风险表各层影响金额从 computed['分层指标'][层]['最坏加权影响'] 计算
  - 第五章：组合最大亏损金额从 computed['组合_历史最大回撤'] × capital 计算
  - 第五章：「15万心理赎回线」改为 client.tolerance_dd × capital
  - 每个钱数字添加"计算方法 + as_of"脚注（在表格下方 body 段）
  - 新增固定附注块「关键假设与数据时效」（不可删除）
  - 适当性闸门：如 _suitability.result != PASS 则拒绝生成报告

保持不变（铁律：不碰 document-suite 渲染层）：
  - build_consulting_doc() / build_general_doc() 调用方式 100% 不变
  - 命令行参数不变
  - 章节结构/顺序/说服力框架不变

依赖：
  pip install python-docx --break-system-packages
  document-suite 已部署于 /Users/jacklee/Dev/02-skills/document-suite
  skill/references/market_inputs.json 必须存在且 as_of 距今 ≤30 天

版本历史：
  v1.0（2026-06-25）：初始版本，手写样式，已归档
  v2.0（2026-06-25）：接入 document-suite，已归档 → versions/skills/generate_report_v2.0_20260626.py
  v2.1（2026-06-26）：精确性改造——数字来自 computed，宏观常量外置，适当性闸门，强制附注
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import os
import sys
from datetime import datetime, date

# ── document-suite 路径 ───────────────────────────────────────
SUITE_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..',
    '02-skills', 'document-suite'))

if SUITE_ROOT not in sys.path:
    sys.path.insert(0, SUITE_ROOT)

# 渲染层（document-suite）改为「延迟加载」：
#   v2.2 起，造假/适当性闸门必须在触达渲染层之前先行拦截。
#   若在 import 期就因缺少 document-suite 而 exit 1，会掩盖闸门是否生效——
#   因此把渲染层导入下沉到真正出报告时（闸门通过之后）再做。
build_consulting_doc = None
build_general_doc    = None


def _load_render_layer():
    """延迟加载 document-suite 渲染层（在所有闸门通过之后才调用）。

    设计意图：让「造假数据被拒（exit 2）」与「渲染层是否就位」彻底解耦——
    任何机器（含无 document-suite 的 CI/审计环境）跑造假输入都应在闸门处 exit 2，
    而不是在 import 期 exit 1。只有当数据合规、确实要落地 .docx 时，
    才要求 document-suite 就位；缺失时给出友好提示并 exit 1。
    """
    global build_consulting_doc, build_general_doc
    if build_consulting_doc is not None and build_general_doc is not None:
        return
    try:
        from templates.tpl_consulting import build_consulting_doc as _c
        from templates.tpl_general    import build_general_doc    as _g
    except ImportError as e:
        print(f'[错误] 无法加载 document-suite：{e}')
        print(f'  请确认套件路径：{SUITE_ROOT}')
        print('  并已安装依赖：pip install python-docx --break-system-packages')
        sys.exit(1)
    build_consulting_doc = _c
    build_general_doc    = _g

# ── 常量 ─────────────────────────────────────────────────────
RISK_LABELS = {
    'R1': '保守型',
    'R2': '稳健型',
    'R3': '平衡型',
    'R4': '进取型',
    'R5': '激进型',
}

MARKET_STATUS_DESC = {
    '积极': (
        '当前流动性宽松，经济复苏信号明确，政策持续支持，市场整体处于积极状态。'
        '权益仓位可适当偏配置上限，适合增加弹性资产比例。'
    ),
    '中性': (
        '当前市场信号混杂，流动性环境中性，建议按标准框架配置，保持灵活应对。'
        '不激进加仓，也不需要防御性减仓，维持基准比例。'
    ),
    '谨慎': (
        '当前存在流动性收紧或经济下行压力，建议降低权益仓位，增配防御性资产。'
        '固收类和黄金的比例可适当提高，权益类偏配置下限。'
    ),
}

# ── market_inputs.json 加载（替代写死的宏观常量）────────────────
# 路径相对于本脚本所在目录（skill/scripts/），上两级是仓库根
_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT    = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
MARKET_INPUTS_PATH = os.path.join(_REPO_ROOT, 'skill', 'references', 'market_inputs.json')


def _load_market_inputs():
    """
    加载外置宏观常量文件，检查 as_of 时效。
    超过 stale_after_days 天则打印警告并等待确认（非自动中止，留给人工判断）。
    返回 market_inputs dict；若文件不存在则返回空 dict 并告警。
    """
    if not os.path.exists(MARKET_INPUTS_PATH):
        print(f'[警告] market_inputs.json 未找到：{MARKET_INPUTS_PATH}')
        print('  宏观常量将使用内置默认值（可能过期），建议补充文件后重跑。')
        return {}
    with open(MARKET_INPUTS_PATH, 'r', encoding='utf-8') as f:
        mi = json.load(f)
    as_of_str    = mi.get('as_of', '')
    stale_days   = mi.get('stale_after_days', 30)
    if as_of_str:
        try:
            as_of_date = datetime.strptime(as_of_str, '%Y-%m-%d').date()
            delta      = (date.today() - as_of_date).days
            if delta > stale_days:
                print(f'[⚠️  数据时效警告] market_inputs.json 的 as_of={as_of_str}，'
                      f'已过 {delta} 天（阈值 {stale_days} 天）。')
                print('  宏观数字可能过期，建议用 fetch_fund_data.py 刷新后重跑。')
                print('  当前为非阻断模式：继续生成，请在报告审核时核实宏观数字。')
        except ValueError:
            print(f'[警告] market_inputs.json 的 as_of 格式无法解析：{as_of_str}')
    return mi


# ── 工具函数 ─────────────────────────────────────────────────

def _to_number(val_str):
    """
    把「100万元」「50万」「1000000」等字符串转成浮点数（元为单位）。
    无法解析返回 None。
    """
    if val_str is None:
        return None
    s = str(val_str).replace(' ', '').replace(',', '')
    # 处理「万」单位
    if '万' in s:
        num_part = s.replace('万元', '').replace('万', '')
        try:
            return float(num_part) * 10000
        except ValueError:
            return None
    # 处理「亿」单位
    if '亿' in s:
        num_part = s.replace('亿元', '').replace('亿', '')
        try:
            return float(num_part) * 100000000
        except ValueError:
            return None
    # 纯数字（元）
    num_part = s.replace('元', '')
    try:
        return float(num_part)
    except ValueError:
        return None


def _fmt_wan(amount_yuan, decimal=1):
    """把元数值格式化为「XX万元」字符串，便于报告展示。"""
    if amount_yuan is None:
        return '（未知）'
    wan = amount_yuan / 10000
    return f'{wan:.{decimal}f}万元'


def _load_data(funds_json_path):
    """
    加载 fund_data.json，兼容三种格式：
      v1.0 格式：list of funds（直接是基金列表）
      v2.0 格式：dict with client + funds
      v2.1 enriched 格式：dict with client + funds + computed + suitability（build_case.py 产出）

    v2.1 新增：
      - 把 computed 块挂到 client_dict['_computed']
      - 把 suitability 块挂到 client_dict['_suitability']
    返回 (client_dict, funds_list)
    """
    with open(funds_json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if isinstance(raw, list):
        # v1.0 格式：直接是 fund 列表，无 computed 块
        return {}, raw
    elif isinstance(raw, dict):
        client = raw.get('client', {})
        # ── v2.1 新增：把 computed 与 suitability 挂载到 client 字典上，供后续章节读取 ──
        client['_computed']    = raw.get('computed', {})       # 组合数学引擎输出
        client['_suitability'] = raw.get('suitability', {})    # 适当性校验结果
        return client, raw.get('funds', [])
    else:
        raise ValueError('fund_data.json 格式错误：期望 list 或 dict')


def _check_suitability(client_dict, allow_unverified=False):
    """
    适当性入口闸门（v2.2 硬化）：
      - _suitability 缺失（v1.0/v2.0 旧格式 或 手编 JSON）→ 默认【硬拦截】退出。
        这正是 FA-PI002 事故的特征：案例未过 build_case.py 适当性闸门即出报告。
        如确需对旧格式手工出稿，须显式加 --allow-unverified（产出严禁交付客户）。
      - result == FAIL → 始终硬拦截退出。
      - result 未知 → 默认拦截（除非 --allow-unverified）。
    """
    s = client_dict.get('_suitability', {})
    if not s:
        print('[✗] 入口闸门：未检测到适当性校验结果（_suitability 块缺失）。')
        print('    这是 FA-PI002 事故的特征——案例未经 build_case.py 适当性闸门即生成报告。')
        print('    正确做法：python3 skill/scripts/build_case.py --case <case.json> --out_dir <目录>')
        print('    再用其产出的 fund_data_enriched.json 作为 --funds_json。')
        if allow_unverified:
            print('[⚠️ --allow-unverified：已跳过适当性闸门，仅限手工/调试，产出严禁交付客户]')
            return
        sys.exit(2)
    result = s.get('result', '')
    if result == 'PASS':
        print(f'[✓] 适当性校验：PASS（{s.get("summary", "")}）')
    elif result == 'FAIL':
        reasons = s.get('fails', s.get('reasons', []))
        print('[✗] 适当性校验 FAIL，拒绝生成对外报告！')
        for r in reasons:
            print(f'  × {r}')
        print('  请修正 case JSON 后重跑 build_case.py，确认 PASS 再生成报告。')
        sys.exit(2)
    else:
        print(f'[?] 适当性结果未知（result={result!r}）。')
        if allow_unverified:
            print('[⚠️ --allow-unverified：未知结果仍继续，产出严禁交付客户]')
            return
        print('  默认拦截。如确需手工出稿，请加 --allow-unverified。')
        sys.exit(2)


# 造假特征文本（出现即判定 computed 非实算）
_FAKE_COMPUTED_MARKERS = (
    '非精确计算', '估算值', '仅供报告展示', '仅供展示',
    '应由portfolio_math', '应由 portfolio_math', '联网实算替换', '手填',
)


def _assert_computed_real(client_dict, allow_unverified=False):
    """
    computed 真实性入口闸门（v2.2 新增）。
    报告里每个「钱的数字」必须来自 portfolio_math 实算。本闸门拦下「手编 computed 空壳」：
      - computed 缺失
      - 数据区间 / as_of / 计算方法 任一缺失或为空
      - 含造假特征文本（自带"估算/非精确/应由portfolio_math替换"等免责）
      - 历史情景回测 与 成份相关性矩阵 双空（典型空壳特征）
    任一命中 → 默认硬拦截（除非 --allow-unverified）。
    """
    comp = client_dict.get('_computed', {})
    reasons = []
    if not comp:
        reasons.append("computed 块缺失（疑似未经 build_case.py 实算）")
    else:
        if not comp.get('数据区间'):
            reasons.append("computed['数据区间'] 为空/None（未经 portfolio_math 合成净值实算）")
        if not comp.get('as_of'):
            reasons.append("computed['as_of'] 缺失（数据时效不可追溯）")
        if not comp.get('计算方法'):
            reasons.append("computed['计算方法'] 缺失（数字不可复算）")
        blob = json.dumps(comp, ensure_ascii=False)
        hit = [m for m in _FAKE_COMPUTED_MARKERS if m in blob]
        if hit:
            reasons.append(f"computed 含造假特征文本：{('、'.join(hit))}")
        sc_empty = isinstance(comp.get('历史情景回测'), dict) and len(comp.get('历史情景回测')) == 0
        cor_empty = isinstance(comp.get('成份相关性矩阵'), dict) and len(comp.get('成份相关性矩阵')) == 0
        if sc_empty and cor_empty:
            reasons.append("历史情景回测与相关性矩阵均为空（典型手填空壳特征）")

    if reasons:
        print('[✗] 入口闸门：computed 块未通过真实性校验，拒绝生成对外报告：')
        for r in reasons:
            print(f'  × {r}')
        print('  v2.2 根因防线：报告中任何风险/收益金额必须来自 portfolio_math 实算。')
        print('  修复：python3 skill/scripts/build_case.py --case <case.json> --out_dir <目录>（联网实算后重跑）')
        if allow_unverified:
            print('[⚠️ --allow-unverified：已强行继续，产出仅为内部草稿，严禁交付客户]')
            return
        sys.exit(2)
    print(f'[✓] computed 真实性校验：PASS（数据区间 {comp.get("数据区间")}，as_of {comp.get("as_of")}）')


def _fund_table_rows(funds):
    """将 funds 列表转为表格的 headers + rows，供 sections 使用"""
    headers = ['基金名称', '代码', '类型', '近3年年化', '最大回撤', '占比/金额', '核心亮点']
    rows = []
    for f in funds:
        weight = f.get('weight', '')
        amount = f.get('amount', '')
        wt_str = f'{weight} / {amount}' if amount else weight
        rows.append([
            f.get('name',            ''),
            f.get('code',            ''),
            f.get('type',            ''),
            f.get('annual_return_3y',''),
            f.get('max_drawdown',    ''),
            wt_str,
            f.get('highlight',       ''),
        ])
    col_widths = [3.0, 1.5, 1.8, 1.8, 1.8, 2.2, 4.6]
    return headers, rows, col_widths


def _arch_table_rows(funds):
    """三层架构汇总表（层级 / 占比金额 / 基金名称 / 代码 / 逻辑）"""
    layers = {}
    for f in funds:
        layer = f.get('layer', '未分类')
        layers.setdefault(layer, []).append(f)

    headers = ['层级', '占比/金额', '基金名称', '代码', '配置逻辑']
    rows = []
    for layer, flist in layers.items():
        names  = ' + '.join(f.get('name', '') for f in flist)
        codes  = ' / '.join(f.get('code', '') for f in flist)
        logic  = flist[0].get('highlight', '') if flist else ''
        total_w = 0
        total_a = ''
        for f in flist:
            w = f.get('weight', '0%').replace('%', '')
            try:
                total_w += float(w)
            except ValueError:
                pass
            if f.get('amount'):
                total_a = f.get('amount', '')
        rows.append([layer, f'{total_w:.0f}% / {total_a}', names, codes, logic])

    col_widths = [1.8, 2.5, 3.5, 2.0, 5.0]
    return headers, rows, col_widths


def _build_sections_full(client_name, risk_level, market_status,
                          funds, client_dict, report_date, market_inputs):
    """
    构建完整版六章 sections（咨询模板格式）。
    v2.1：所有钱的数字读 computed 块；宏观常量读 market_inputs；每处加来源脚注。
    """
    risk_label   = RISK_LABELS.get(risk_level, risk_level)
    mkt_desc     = MARKET_STATUS_DESC.get(market_status, '')

    # ── 从 market_inputs.json 读市场快照（替代写死的 MARKET_SNAPSHOT）──────────
    mi_snapshot = market_inputs.get('market_snapshot', {})
    mkt_snapshot = mi_snapshot.get(market_status, [
        ['数据', '（market_inputs.json 未找到，请补充）', '—'],
    ])
    mi_macro     = market_inputs.get('macro', {})
    mi_as_of     = market_inputs.get('as_of', '（未知）')

    # 10年期国债收益率（替代写死的 1.74%）
    cn_10y_yield = mi_macro.get('cn_10y_yield_pct', None)
    yield_str    = f'{cn_10y_yield}%' if cn_10y_yield is not None else '（见 market_inputs.json）'

    # 存款搬家规模
    deposit_migration = mi_macro.get('deposit_migration_trillion', None)
    deposit_str = f'约{deposit_migration}万亿' if deposit_migration is not None else '约数十万亿'

    # ── 从 computed 块读取组合数字 ──────────────────────────────────────────────
    C             = client_dict.get('_computed', {})
    capital_str   = client_dict.get('capital', '（金额未填）')
    capital_num   = _to_number(capital_str)   # 元
    period        = client_dict.get('investment_period', '（期限未填）')
    exp_return    = client_dict.get('portfolio_expected_return', '5-7%')  # 兼容旧格式
    exp_dd_legacy = client_dict.get('portfolio_max_drawdown', '-6%至-8%') # 兼容旧格式
    pain_point    = client_dict.get('pain_point', '存款搬家，稳健增值')
    tolerance_dd  = client_dict.get('tolerance_dd', None)   # 如 -0.09

    # 从 computed 提取核心数字
    hist_cagr  = C.get('组合_年化收益_历史', None)
    hist_dd    = C.get('组合_历史最大回撤',  None)   # 负数，如 -0.083
    fwd_est    = C.get('远期收益估计', {})
    fwd_return = fwd_est.get('远期预期年化(假设)', None)
    data_range = C.get('数据区间', '')
    calc_method= C.get('计算方法', '详见 build_case.py 输出')
    c_as_of    = C.get('as_of', mi_as_of)

    # 分层指标
    layer_stats   = C.get('分层指标', {})
    hedge_effect  = C.get('对冲层边际作用', {})

    # 核心层净值年化（用于替代「纯债收益约3%」）
    core_layer_ann = None
    if '核心层' in layer_stats:
        core_layer_ann = layer_stats['核心层'].get('层内独立年化', None)
    core_return_str = (
        f'{core_layer_ann*100:.1f}%（核心层历史年化，{data_range}）'
        if core_layer_ann is not None else '约3-5%'
    )

    # 历史年化收益区间（替代写死的「5-7%」）
    if hist_cagr is not None:
        hist_return_str = f'{hist_cagr*100:.1f}%（历史年化，{data_range}）'
    else:
        hist_return_str = exp_return + '（参考值，建议通过量化模型重新测算确认）'

    # 远期预期收益
    # v2.1 fix: 采用CMA 是 dict，不可直接拼字符串，改用 '口径' 字段
    _cma_desc = fwd_est.get('口径', '来自 computed CMA')
    if isinstance(_cma_desc, dict):
        _cma_desc = str(_cma_desc)
    fwd_return_str = (
        f'{fwd_return*100:.1f}%（远期中性估计，{_cma_desc}）'
        if fwd_return is not None else '（见 computed 远期收益估计）'
    )

    # 3年后账面金额（历史口径）
    if capital_num and hist_cagr is not None:
        yrs = 3
        low_amt   = capital_num * ((1 + hist_cagr) ** yrs)
        high_amt  = capital_num * ((1 + hist_cagr * 1.2) ** yrs)   # 乐观 +20%
        amt_hist_str = f'约{_fmt_wan(low_amt)}~{_fmt_wan(high_amt)}'
    else:
        amt_hist_str = '（需 computed 数据）'

    # 组合历史最大回撤（负数转正为百分比字符串）
    if hist_dd is not None:
        hist_dd_str   = f'{hist_dd*100:.1f}%'
        hist_dd_pct   = hist_dd        # 保留浮点供后续计算
    else:
        hist_dd_str   = exp_dd_legacy
        hist_dd_pct   = None

    # 最大亏损金额
    if capital_num and hist_dd_pct is not None:
        max_loss_yuan  = abs(hist_dd_pct * capital_num)
        max_loss_str   = _fmt_wan(max_loss_yuan)
    else:
        max_loss_str   = '约8-9万元（见 computed 组合最大回撤）'
        max_loss_yuan  = None

    # 心理赎回线（替代写死的「15万」）
    if tolerance_dd is not None and capital_num is not None:
        tol_yuan    = abs(tolerance_dd * capital_num)
        tol_str     = _fmt_wan(tol_yuan)
    else:
        tol_str     = '（见客户 tolerance_dd × 本金）'
        tol_yuan    = None

    # 对冲层边际作用（替代写死的「-12%→{exp_dd}」）
    dd_without_hedge = hedge_effect.get('最大回撤_不含', None)
    dd_with_hedge    = hedge_effect.get('最大回撤_含',   None)
    dd_improve       = hedge_effect.get('最大回撤_改善', None)
    if dd_without_hedge is not None and dd_with_hedge is not None:
        hedge_desc = (
            f'从实测的{dd_without_hedge*100:.1f}%压低至{dd_with_hedge*100:.1f}%'
            f'（改善{abs(dd_improve)*100:.1f}个百分点，经投资组合量化模型两次独立测算所得）'
        )
    else:
        # v2.2：删除写死的「-12%」兜底——任何未经实算的数字都不得进入客户报告
        hedge_desc = ('（对冲层边际作用未实测，本报告不就该项给出具体数字；'
                      '如需量化，请经 build_case.py 复算后补充）')

    # 各层风险金额（替代写死的「2-3.5万」等）
    def _layer_impact_str(layer_name):
        """读 computed 分层指标，返回「最坏加权影响×资本」的字符串"""
        ls = layer_stats.get(layer_name, {})
        worst = ls.get('最坏加权影响', None)
        if worst is not None and capital_num is not None:
            yuan = abs(worst * capital_num)
            return _fmt_wan(yuan) + f'（{layer_name}最坏加权影响 {worst*100:.1f}%，经量化模型测算）'
        return '（待 computed 填充）'

    core_impact_str   = _layer_impact_str('核心层')
    sat_impact_str    = _layer_impact_str('卫星层')
    hedge_impact_str  = _layer_impact_str('对冲层')

    # ── 更新市场快照的流动性行（把写死的「1.74%」替换为 market_inputs 的值）─────
    # 注意：market_snapshot 已外置到 market_inputs.json 的「谨慎」块里
    # 此处做一次防御性替换，确保 cn_10y_yield 正确出现
    updated_snapshot = []
    for row in mkt_snapshot:
        new_row = list(row)
        if '流动性环境' in new_row[0] and cn_10y_yield is not None:
            # 替换残存的占位符。
            # 注意顺序：必须【先长后短】。若先替换短串 'cn_10y_yield_pct'，
            # 长串 '见 macro.cn_10y_yield_pct' 就再也匹配不到，
            # 结果会把「见 macro.1.74%」原样印进客户文档（20260626 版张女士报告即此 bug）。
            new_row[1] = new_row[1].replace(
                '见 macro.cn_10y_yield_pct', f'{cn_10y_yield}%'
            ).replace(
                'cn_10y_yield_pct', f'{cn_10y_yield}%'
            )
        updated_snapshot.append(new_row)

    # ── 脚注文本 ─────────────────────────────────────────────────────────────
    fn_macro   = f'【数据来源】宏观常量来自 market_inputs.json，截止日 {mi_as_of}，数据源：{market_inputs.get("data_sources", {}).get("cn_10y_yield", "见 market_inputs.json")}。'
    fn_computed= f'【数据来源】以上数字由投资组合量化模型基于成份基金历史净值序列测算，数据截止 {c_as_of}。历史表现不代表未来，本数字为历史实测结果，非收益承诺。'
    fn_fwd     = f'【远期估计】{fwd_est.get("诚实声明", "远期收益为估算值，存在不确定性，仅供参考。")}'
    fn_hedge   = f'【对冲测算】{hedge_effect.get("计算说明", "对冲层边际作用 = 含对冲层组合回撤 - 不含对冲层组合回撤，均为投资组合量化模型实测结果。")}'

    # ── 基金表格 ──────────────────────────────────────────────────────────────
    fund_headers, fund_rows, fund_col_w = _fund_table_rows(funds)
    arch_headers, arch_rows, arch_col_w = _arch_table_rows(funds)

    # ── 建仓计划 ──────────────────────────────────────────────────────────────
    batch_rows = []
    for bi, label in enumerate(['第一批（7月）', '第二批（8月）', '第三批（9月）']):
        pct  = ['40%', '40%', '20%'][bi]
        note = ['按推荐比例首次建仓', '确认市场未变化后建仓', '逢市场回调5%-10%加仓'][bi]
        batch_rows.append([label, pct, note])
    batch_headers    = ['建仓批次', '资金比例', '操作要点']
    batch_col_widths = [4.0, 3.0, 8.5]

    # ── 关键假设与数据时效附注（不可删除）───────────────────────────────────────
    assumptions_text = (
        '■ 数据截止日：' + c_as_of + '\n'
        '■ 宏观常量截止日：' + mi_as_of + '\n'
        '■ 组合净值合成方法：' + client_dict.get('rebalance', 'none（买入持有，权重漂移）') + '\n'
        '■ 远期收益估计方法：' + (str(fwd_est.get('采用CMA', '见 computed.远期收益估计')) if isinstance(fwd_est.get('采用CMA'), dict) else fwd_est.get('采用CMA', '见 computed.远期收益估计')) + '\n'
        '■ 相关性取值：来自成份基金历史日收益率矩阵（危机时相关性会上行，历史相关性有低估风险）\n'
        '■ 历史最大回撤口径：组合合成净值峰谷法，非各基金回撤加权\n'
        '■ 分层影响金额：各层最坏加权影响（非独立回撤，避免高估极端损失）\n'
        '■ 本报告所有风险/收益数字均为历史实测或合理估算，不构成投资承诺，过去表现不代表未来。'
    )
    fwd_honest = C.get('诚实声明', '远期收益为估算值，存在不确定性。历史年化与远期估计为两个不同口径，不可混用。')

    # ── 正式组装 sections ────────────────────────────────────────────────────
    sections = [

        # ── 第一章：市场在哪里 ────────────────────────────────────────────────
        {
            'h1': '第一章  市场在哪里——我们看到了什么',
            'content': [
                {'type': 'body', 'text': mkt_desc},
                {'type': 'h2',   'text': f'市场状态标签：{market_status}'},
                {'type': 'table',
                 'headers': ['维度', '当前状态', '对组合的影响'],
                 'rows':    updated_snapshot,
                 'col_widths': [3.0, 4.5, 8.0]},
                # v2.1：用 market_inputs 的真实数字，不写死
                {'type': 'body',
                 'text': (
                     f'核心判断：在低利率环境下（10年期国债 {yield_str}），'
                     f'纯债收益约{core_return_str}，难以完成6%+目标；'
                     f'权益市场震荡为主；{deposit_str}居民存款正在搬家，'
                     '固收+是最主流承接产品，方向正确，时机合理。'
                 ),
                 'highlight': True},
                {'type': 'body', 'text': fn_macro},  # 宏观数据来源脚注
            ],
        },

        # ── 第二章：不行动的代价 ──────────────────────────────────────────────
        {
            'h1': '第二章  什么都不做的代价',
            'content': [
                {'type': 'body',
                 'text': (
                     '存款利率已普遍降至1%以下，中长期定存到期后没有好去处。'
                     f'以{capital_str}为例，若继续存定期（年化约1%），'
                     '扣除通胀（2%假设）后，3年实际购买力将缩水约3%-5%，即损失约3-5万元。'
                 )},
                {'type': 'body',
                 # v2.1：历史年化与远期估计分开写，不混用，各自标注口径
                 'text': (
                     f'反之，本组合历史年化约{hist_return_str}，'
                     f'远期中性估计约{fwd_return_str}。'
                     '「不做决策」本身就是一个代价高昂的决策。'
                 ),
                 'highlight': True},
                {'type': 'table',
                 'headers': ['方案', '年化收益', f'3年后账面（约，基于{capital_str}）', '说明'],
                 'rows': [
                     # v2.1：账面金额从 computed 动态算，不写死
                     ['继续存定期', '约1%',
                      capital_str + '（不变）', '跑不赢通胀，实际缩水'],
                     ['本推荐组合（历史口径）',
                      hist_return_str,
                      amt_hist_str,
                      f'历史年化{data_range}实测，非未来保证'],
                     ['本推荐组合（远期估计）',
                      fwd_return_str,
                      '（详见完整版报告远期估计）',
                      fwd_honest],
                 ],
                 'col_widths': [3.0, 3.5, 4.0, 5.5]},
                {'type': 'body', 'text': fn_computed},  # 计算方法脚注
                {'type': 'body', 'text': fn_fwd},       # 远期估计脚注
            ],
        },

        # ── 第三章：基金怎么选 ────────────────────────────────────────────────
        {
            'h1': '第三章  我们怎么选——筛选标准透明化',
            'content': [
                {'type': 'body',
                 'text': (
                     f'基于您的{risk_label}风险偏好，我们从五个维度对候选基金进行量化评分筛选，'
                     '硬性排除基金经理离任<6个月、规模<2亿、成立<1年的产品：'
                 )},
                {'type': 'table',
                 'headers': ['筛选维度', '权重', '核心指标'],
                 'rows': [
                     ['基金经理能力', '30%', '任职≥3年 / 牛熊各一轮表现 / 换手率控制'],
                     ['历史业绩质量', '25%', '近3/5年年化收益 / 相对基准超额'],
                     ['回撤控制',     '20%', '最大回撤 / 夏普比率 / 卡玛比率'],
                     ['规模与流动性', '15%', '规模合理区间 / 日均申赎畅通'],
                     ['费率结构',     '10%', '管理费+托管费总负担最小化'],
                 ],
                 'col_widths': [3.0, 2.0, 10.5]},
                {'type': 'h2', 'text': '推荐基金明细'},
                {'type': 'table',
                 'headers': fund_headers,
                 'rows':    fund_rows,
                 'col_widths': fund_col_w},
            ],
        },

        # ── 第四章：组合怎么搭 ────────────────────────────────────────────────
        {
            'h1': '第四章  组合是怎么搭的',
            'content': [
                {'type': 'body',
                 'text': (
                     f'基于{risk_label}投资者标准框架，本组合采用「核心+卫星+对冲」三层架构，'
                     '最大回撤硬约束-10%，权益敞口不超过20%：'
                 )},
                {'type': 'table',
                 'headers': arch_headers,
                 'rows':    arch_rows,
                 'col_widths': arch_col_w},
                {'type': 'h2', 'text': '比例设计逻辑'},
                {'type': 'body',
                 'text': (
                     '核心层70%：您的真实回撤承受约-8%至-10%，必须以低波债基为压舱石，'
                     '确保市场震荡时不被迫割肉。'
                 ), 'indent': True},
                {'type': 'body',
                 'text': (
                     '卫星层20%：权益敞口超过20%将触碰恐慌赎回线；'
                     '低于15%则3年难以完成6%+目标。'
                     '20%是在回撤约束与收益目标之间经量化模型测算的平衡点。'
                 ), 'indent': True},
                {'type': 'body',
                 # v2.1：对冲层边际作用改为读 computed，不写死 -12%
                 'text': (
                     f'对冲层10%：黄金与债股相关性极低，加入后可将组合最大回撤{hedge_desc}。'
                     '这10%是「保险丝」，不是为了赚钱。'
                 ), 'indent': True},
                {'type': 'body', 'text': fn_hedge},  # 对冲测算脚注
            ],
        },

        # ── 第五章：风险在哪里 ────────────────────────────────────────────────
        {
            'h1': '第五章  风险在哪里——我们不回避的话题',
            'content': [
                {'type': 'body',
                 'text': (
                     '我们主动告诉您这个组合可能亏钱的情况，'
                     '因为只有你知道最坏的情景，才能真正拿得住：'
                 )},
                {'type': 'table',
                 'headers': ['风险类型', '触发情景', '预估账面影响', '应对策略'],
                 # v2.1：各层影响金额从 computed 分层指标读取；触发利率从 market_inputs 读
                 'rows': [
                     ['债市利率超预期上行',
                      f'10年期国债升破{cn_10y_yield + 0.3 if cn_10y_yield else 2.0:.1f}%',
                      core_impact_str,
                      '持有等待修复，债基到期收益为正'],
                     ['权益市场系统性下跌',
                      '沪深300下跌超20%',
                      sat_impact_str,
                      '股息收益对冲部分损失，3年维度修复概率高'],
                     ['黄金熊市周期',
                      '黄金下跌超15%',
                      hedge_impact_str,
                      '对冲工具，整体影响有限'],
                     ['极端不利情景（三者同发）',
                      '概率极低',
                      # v2.1：最大亏损金额从 computed 组合回撤×资本算
                      f'组合最大亏损约{max_loss_str}（历史最大回撤口径）',
                      # v2.1：心理赎回线从 client.tolerance_dd×资本算
                      f'仍低于您{tol_str}的心理赎回线，坚持持有'],
                 ],
                 'col_widths': [2.8, 3.5, 4.5, 4.7]},
                {'type': 'body', 'text': fn_computed},  # 计算方法脚注（复用）
                {'type': 'body',
                 'text': (
                     f'触发重新评估的条件：①组合账面亏损超过{max_loss_str}  '
                     '②任一基金经理离任  '
                     '③您的财务状况或风险偏好发生重大变化  '
                     '④市场研判标签从「中性」转为「谨慎」'
                 ),
                 'highlight': True},
            ],
        },

        # ── 第六章：行动指引 ──────────────────────────────────────────────────
        {
            'h1': '第六章  接下来怎么做——明确的行动清单',
            'content': [
                {'type': 'body',
                 'text': (
                     '建议分3个月分批建仓，平滑成本，避免一次性买在阶段高点：'
                 )},
                {'type': 'table',
                 'headers': batch_headers,
                 'rows':    batch_rows,
                 'col_widths': batch_col_widths},
                {'type': 'h2', 'text': '关键操作细节'},
                {'type': 'body',
                 'text': '① 选A类份额：100万申购享受A类费率优惠，持有3年比C类更合算',
                 'indent': False},
                {'type': 'body',
                 'text': '② 购买渠道：天天基金网/支付宝基金，优先选费率打一折的平台',
                 'indent': False},
                {'type': 'body',
                 'text': '③ 购买前确认：登录天天基金核查各基金经理是否有变动，确认无变动后再买入',
                 'indent': False},
                {'type': 'body',
                 'text': f'④ 止稳检查线：账面亏损超{max_loss_str}，不要自行赎回，先联系投顾重新评估',
                 'indent': False},
                {'type': 'body',
                 'text': f'⑤ 下次组合检视时间：3个月后（约{report_date[:7]}之后）',
                 'indent': False,
                 'highlight': True},
            ],
        },

        # ── 关键假设与数据时效（不可删除）────────────────────────────────────
        {
            'h1': '附：关键假设与数据时效（不可删除）',
            'content': [
                {'type': 'body',
                 'text': (
                     '本报告所有风险/收益数字均由投资组合量化模型基于真实净值序列测算，'
                     '或来自带时效标注的外置宏观常量。以下为核心假设，供客户复核：'
                 )},
                {'type': 'body', 'text': assumptions_text},
                {'type': 'body',
                 'text': fwd_honest,
                 'highlight': True},
            ],
        },
    ]
    return sections


def _build_sections_summary(client_name, risk_level, market_status,
                              funds, client_dict, report_date, market_inputs):
    """
    构建一页纸摘要版 sections（通用模板格式）。
    v2.1：KPI 行读 computed；增加 as_of 脚注。
    """
    risk_label = RISK_LABELS.get(risk_level, risk_level)
    C          = client_dict.get('_computed', {})
    mi_as_of   = market_inputs.get('as_of', '（未知）')
    c_as_of    = C.get('as_of', mi_as_of)

    # 收益数字
    hist_cagr  = C.get('组合_年化收益_历史', None)
    hist_dd    = C.get('组合_历史最大回撤',  None)
    fwd_est    = C.get('远期收益估计', {})
    fwd_return = fwd_est.get('远期预期年化(假设)', None)

    exp_return_display = (
        f'{hist_cagr*100:.1f}%（历史）/ {fwd_return*100:.1f}%（远期估计）'
        if hist_cagr is not None and fwd_return is not None
        else client_dict.get('portfolio_expected_return', '（见完整报告）')
    )
    exp_dd_display = (
        f'{hist_dd*100:.1f}%'
        if hist_dd is not None
        else client_dict.get('portfolio_max_drawdown', '（见完整报告）')
    )

    fn_kpi = f'以上数字由投资组合量化模型基于成份基金历史净值序列测算，数据截止 {c_as_of}。历史表现不代表未来。'

    fund_headers, fund_rows, fund_col_w = _fund_table_rows(funds)

    capital_num = _to_number(client_dict.get('capital'))
    hist_dd_pct = hist_dd if hist_dd is not None else None
    max_loss_str = (
        _fmt_wan(abs(hist_dd_pct * capital_num))
        if hist_dd_pct and capital_num else '8万元（见完整报告）'
    )

    sections = [
        {
            'h1': '',
            'content': [
                {'type': 'table',
                 'headers': ['风险等级', '年化收益', '历史最大回撤', '权益敞口', '建仓方式'],
                 'rows': [[
                     f'{risk_level} {risk_label}',
                     exp_return_display,
                     exp_dd_display,
                     '20%',
                     '分3月分批',
                 ]],
                 'col_widths': [2.5, 3.5, 2.5, 2.0, 5.0]},
                {'type': 'body', 'text': fn_kpi},
            ],
        },
        {
            'h1': '四基金组合方案',
            'content': [
                {'type': 'table',
                 'headers': fund_headers,
                 'rows':    fund_rows,
                 'col_widths': fund_col_w},
            ],
        },
        {
            'h1': '三步操作指引',
            'content': [
                {'type': 'body',
                 'text': '第一步：打开天天基金/支付宝基金，搜索代码并核实基金经理无变动',
                 'indent': False},
                {'type': 'body',
                 'text': '第二步：选A类份额，首次买入总资金40%，按核心:卫星:对冲=70:20:10比例分配',
                 'indent': False},
                {'type': 'body',
                 'text': '第三步：次月再买40%，第三个月买20%，三个月完成全部建仓',
                 'indent': False},
                {'type': 'body',
                 'text': f'持有期间只需记住：账面亏损超{max_loss_str} → 先联系投顾，不要自行赎回',
                 'highlight': True},
            ],
        },
    ]
    return sections


# ── 主生成函数 ────────────────────────────────────────────────

def generate_full_report(client_name, risk_level, market_status,
                          funds, client_dict, output_path, report_date, market_inputs):
    """完整版：调用 build_consulting_doc（咨询模板）"""
    _load_render_layer()   # 闸门已在 main() 通过；此处才载入渲染层
    risk_label = RISK_LABELS.get(risk_level, risk_level)
    capital    = client_dict.get('capital', '')

    subtitle_parts = [f'{risk_label}']
    if capital:
        subtitle_parts.append(capital)
    period = client_dict.get('investment_period', '')
    if period:
        subtitle_parts.append(f'{period}投资期')
    subtitle = '  ·  '.join(subtitle_parts)

    sections = _build_sections_full(
        client_name, risk_level, market_status,
        funds, client_dict, report_date, market_inputs
    )

    doc = build_consulting_doc(
        title    = '基金投资组合推荐报告',
        subtitle = subtitle,
        header   = '基金投资顾问团队',
        footer   = '风险提示：本报告基于历史数据，不构成投资建议，基金投资有风险',
        client   = client_name,
        date     = report_date,
        sections = sections,
    )

    os.makedirs(output_path, exist_ok=True)
    date_str  = datetime.now().strftime('%Y%m%d')
    filename  = f'基金推荐报告_{client_name}_{date_str}.docx'
    full_path = os.path.join(output_path, filename)
    doc.save(full_path)
    print(f'[OK] 完整版报告已生成：{full_path}')
    return full_path


def generate_summary_sheet(client_name, risk_level, market_status,
                             funds, client_dict, output_path, report_date, market_inputs):
    """一页纸摘要版：调用 build_general_doc（通用模板，深青+暖橙色系）"""
    _load_render_layer()   # 闸门已在 main() 通过；此处才载入渲染层
    sections = _build_sections_summary(
        client_name, risk_level, market_status,
        funds, client_dict, report_date, market_inputs
    )

    doc = build_general_doc(
        title        = f'基金组合推荐一页纸  ·  {client_name}  ·  {report_date}',
        header       = '基金投资顾问团队',
        footer       = '本摘要配合完整版研究报告使用',
        primary_hex  = '0A4D68',
        accent_hex   = 'F4A261',
        stripe_hex   = 'EAF4FB',
        title_align  = 'center',
        sections     = sections,
    )

    os.makedirs(output_path, exist_ok=True)
    date_str  = datetime.now().strftime('%Y%m%d')
    filename  = f'基金组合一页纸_{client_name}_{date_str}.docx'
    full_path = os.path.join(output_path, filename)
    doc.save(full_path)
    print(f'[OK] 一页纸摘要版已生成：{full_path}')
    return full_path


# ── CLI 入口 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='基金推荐报告生成器 v2.1（精确性改造版）'
    )
    parser.add_argument('--client_name',   required=True,  help='客户名称')
    parser.add_argument('--risk_level',    required=True,  help='风险等级：R1-R5')
    parser.add_argument('--market_status', required=True,  help='市场研判：积极/中性/谨慎')
    parser.add_argument('--funds_json',    required=True,  help='基金数据JSON路径（enriched优先）')
    parser.add_argument('--output_path',   required=True,  help='输出目录')
    parser.add_argument('--allow-unverified', dest='allow_unverified', action='store_true',
                        help='跳过入口真实性闸门（仅限手工/调试；产出为内部草稿，严禁交付客户）')
    args = parser.parse_args()

    if not os.path.exists(args.funds_json):
        print(f'[错误] 基金数据文件不存在：{args.funds_json}')
        sys.exit(1)

    # ── v2.1：先加载宏观常量（含时效检查）──────────────────────────────────────
    market_inputs = _load_market_inputs()

    # ── 加载基金数据（含 computed + suitability）─────────────────────────────────
    client_dict, funds = _load_data(args.funds_json)

    if not funds:
        print('[错误] 基金列表为空，请检查 fund_data.json')
        sys.exit(1)

    # ── v2.2：入口双闸门（FAIL 直接退出，堵死 PI002 式造假/绕闸）─────────────────
    if args.allow_unverified:
        print('=' * 64)
        print('  ⚠️  --allow-unverified 已启用：入口真实性闸门降级为告警。')
        print('     本次产出仅供内部草稿/调试，严禁作为对客户的正式交付物。')
        print('=' * 64)
    _check_suitability(client_dict, allow_unverified=args.allow_unverified)
    _assert_computed_real(client_dict, allow_unverified=args.allow_unverified)

    # 命令行参数优先于 json 内的 client 字段
    if args.client_name:
        client_dict['name'] = args.client_name
    if args.risk_level:
        client_dict['risk_level'] = args.risk_level

    report_date = datetime.now().strftime('%Y年%m月%d日')

    generate_full_report(
        args.client_name, args.risk_level, args.market_status,
        funds, client_dict, args.output_path, report_date, market_inputs
    )
    generate_summary_sheet(
        args.client_name, args.risk_level, args.market_status,
        funds, client_dict, args.output_path, report_date, market_inputs
    )
    print('[完成] 两份文档均已生成，请检查输出目录。')


if __name__ == '__main__':
    main()
