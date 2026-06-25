#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基金推荐研究报告生成脚本 v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
变更：接入 document-suite（/Users/jacklee/Documents/02-skills/document-suite）
      调用 build_consulting_doc() 生成完整版，build_general_doc() 生成一页纸摘要版
      字体/色系/表格规范由 docx_builder.py v1.1 统一管理

依赖：
  pip install python-docx --break-system-packages
  document-suite 已部署于 /Users/jacklee/Documents/02-skills/document-suite

命令行参数（与 v1.0 完全向后兼容）：
  python3 generate_report.py \\
    --client_name  「张先生」 \\
    --risk_level   R2 \\
    --market_status 谨慎 \\
    --funds_json   fund_data.json \\
    --output_path  ../output/FA-20260625-PI001/

fund_data.json 格式（v1.0 list 格式与 v2.0 带 client 字段格式均支持）：
  v1.0 格式：[{fund}, ...]
  v2.0 格式：{"client": {...}, "funds": [{fund}, ...], ...}

铁律：
  - 全部用 Python 生成 Word，不用 JS
  - 文件路径用 os.path.join，不硬编码斜杠
  - document-suite 路径通过 SUITE_ROOT 常量统一管理，方便迁移
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

归档说明：本文件为 v2.0 原版，于 2026-06-26 升级至 v2.1 时备份。
备份位置：versions/skills/generate_report_v2.0_20260626.py
"""

import argparse
import json
import os
import sys
from datetime import datetime

# ── document-suite 路径 ───────────────────────────────────────
# 如需迁移套件位置，只改这一行
SUITE_ROOT = '/Users/jacklee/Documents/02-skills/document-suite'

if SUITE_ROOT not in sys.path:
    sys.path.insert(0, SUITE_ROOT)

try:
    from templates.tpl_consulting import build_consulting_doc
    from templates.tpl_general    import build_general_doc
except ImportError as e:
    print(f'[错误] 无法加载 document-suite：{e}')
    print(f'  请确认套件路径：{SUITE_ROOT}')
    print('  并已安装依赖：pip install python-docx --break-system-packages')
    sys.exit(1)

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

# 当前市场快照（每次案例执行前由首席投顾确认填入）
MARKET_SNAPSHOT = {
    '积极': [
        ['流动性环境', '宽松', '权益仓位可偏上限'],
        ['经济周期',   '复苏', '周期股/成长股受益'],
        ['政策导向',   '积极财政+产业支持', '关注政策受益板块'],
    ],
    '中性': [
        ['流动性环境', '中性', '权益仓位保持基准'],
        ['经济周期',   '平台震荡', '均衡配置'],
        ['政策导向',   '结构性支持', '精选行业机会'],
    ],
    '谨慎': [
        ['流动性环境', '偏紧（10年期国债约1.74%）', '权益仓位偏下限'],
        ['经济周期',   '消费/投资承压', '增配防御性资产'],
        ['政策导向',   '稳增长为主', '关注高股息/固收+'],
    ],
}


# ── 工具函数 ─────────────────────────────────────────────────

def _load_data(funds_json_path):
    """
    加载 fund_data.json，兼容 v1.0（list）与 v2.0（dict with funds key）两种格式。
    返回 (client_dict, funds_list)
    """
    with open(funds_json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if isinstance(raw, list):
        # v1.0 格式：直接是 fund 列表
        return {}, raw
    elif isinstance(raw, dict):
        # v2.0 格式：带 client 字段
        return raw.get('client', {}), raw.get('funds', [])
    else:
        raise ValueError('fund_data.json 格式错误：期望 list 或 dict')


def _fund_table_rows(funds):
    """将 funds 列表转为表格的 headers + rows，供 sections 使用"""
    headers = ['基金名称', '代码', '类型', '近3年年化', '最大回撤', '占比/金额', '核心亮点']
    rows = []
    for f in funds:
        weight  = f.get('weight', '')
        amount  = f.get('amount', '')
        wt_str  = f'{weight} / {amount}' if amount else weight
        rows.append([
            f.get('name',            ''),
            f.get('code',            ''),
            f.get('type',            ''),
            f.get('annual_return_3y',''),
            f.get('max_drawdown',    ''),
            wt_str,
            f.get('highlight',       ''),
        ])
    # 列宽：名称3.2 代码1.5 类型2 年化1.8 回撤1.8 占比2.2 亮点5.0（总≈17.5，A4内容区约14.66cm，按比例缩）
    col_widths = [3.0, 1.5, 1.8, 1.8, 1.8, 2.2, 4.6]
    return headers, rows, col_widths


def _arch_table_rows(funds):
    """三层架构汇总表（层级 / 占比金额 / 基金名称 / 代码 / 逻辑）"""
    # 按 layer 分组
    layers = {}
    for f in funds:
        layer = f.get('layer', '未分类')
        layers.setdefault(layer, []).append(f)

    headers = ['层级', '占比/金额', '基金名称', '代码', '配置逻辑']
    rows = []
    for layer, flist in layers.items():
        names  = ' + '.join(f.get('name', '') for f in flist)
        codes  = ' / '.join(f.get('code', '') for f in flist)
        # 取 layer 对应的第一只基金 highlight 作为逻辑说明
        logic  = flist[0].get('highlight', '') if flist else ''
        # 占比求和
        total_w = 0
        total_a = ''
        for f in flist:
            w = f.get('weight', '0%').replace('%', '')
            try:
                total_w += float(w)
            except ValueError:
                pass
            if f.get('amount'):
                total_a = f.get('amount', '')  # 粗略取最后一个，仅供参考
        rows.append([layer, f'{total_w:.0f}% / {total_a}', names, codes, logic])

    col_widths = [1.8, 2.5, 3.5, 2.0, 5.0]
    return headers, rows, col_widths


def _build_sections_full(client_name, risk_level, market_status,
                          funds, client_dict, report_date):
    """
    构建完整版六章 sections（咨询模板格式）。
    所有内容逻辑集中在此函数，模板负责渲染。
    """
    risk_label   = RISK_LABELS.get(risk_level, risk_level)
    mkt_desc     = MARKET_STATUS_DESC.get(market_status, '')
    mkt_snapshot = MARKET_SNAPSHOT.get(market_status, [])

    # 客户画像信息（从 client_dict 或命令行参数提取）
    capital        = client_dict.get('capital',        '（金额未填）')
    period         = client_dict.get('investment_period', '（期限未填）')
    return_target  = client_dict.get('return_target',  '（目标未填）')
    max_dd_tol     = client_dict.get('max_drawdown_tolerance', '（未填）')
    exp_return     = client_dict.get('portfolio_expected_return', '（未填）')
    exp_dd         = client_dict.get('portfolio_max_drawdown',    '（未填）')
    pain_point     = client_dict.get('pain_point', '存款搬家，稳健增值')
    experience     = client_dict.get('experience', '存款/银行理财/货币基金')

    # 基金表格数据
    fund_headers, fund_rows, fund_col_w = _fund_table_rows(funds)
    arch_headers, arch_rows, arch_col_w = _arch_table_rows(funds)

    # 建仓计划（按基金数量自动生成，3批次）
    batch_rows = []
    for bi, label in enumerate(['第一批（7月）', '第二批（8月）', '第三批（9月）']):
        pct  = ['40%', '40%', '20%'][bi]
        note = ['按推荐比例首次建仓', '确认市场未变化后建仓', '逢市场回调5%-10%加仓'][bi]
        batch_rows.append([label, pct, note])
    batch_headers   = ['建仓批次', '资金比例', '操作要点']
    batch_col_widths = [4.0, 3.0, 8.5]

    sections = [
        # ── 第一章：市场在哪里 ────────────────────────────────
        {
            'h1': '第一章  市场在哪里——我们看到了什么',
            'content': [
                {'type': 'body', 'text': mkt_desc},
                {'type': 'h2',   'text': f'市场状态标签：{market_status}'},
                {'type': 'table',
                 'headers': ['维度', '当前状态', '对组合的影响'],
                 'rows':    mkt_snapshot,
                 'col_widths': [3.0, 4.5, 8.0]},
                {'type': 'body',
                 'text': (
                     '核心判断：在低利率环境下，纯债收益约3%，难以完成6%+目标；'
                     '权益市场6月震荡为主；约75万亿居民存款正在搬家，固收+是最主流承接产品，'
                     '方向正确，时机合理。'
                 ),
                 'highlight': True},
            ],
        },

        # ── 第二章：不行动的代价 ──────────────────────────────
        {
            'h1': '第二章  什么都不做的代价',
            'content': [
                {'type': 'body',
                 'text': (
                     '存款利率已普遍降至1%以下，中长期定存到期后没有好去处。'
                     f'以{capital}为例，若继续存定期（年化约1%），'
                     '扣除通胀（2%假设）后，3年实际购买力将缩水约3%-5%，即损失约3-5万元。'
                 )},
                {'type': 'body',
                 'text': (
                     '反之，本组合预期年化5-7%，3年累计收益约16-22万元。'
                     '「不做决策」本身就是一个代价高昂的决策——'
                     '两种选择之间的差距超过20万元。'
                 ),
                 'highlight': True},
                {'type': 'table',
                 'headers': ['方案', '年化收益', '3年后账面（约）', '说明'],
                 'rows': [
                     ['继续存定期',      '约1%',   f'{capital}（不变）',   '跑不赢通胀，实际缩水'],
                     ['本推荐组合（基准）', exp_return, '约116-122万元', '固收+黄金四基金组合'],
                     ['本推荐组合（乐观）', '7-10%', '约121-133万元', '市场顺风情景'],
                 ],
                 'col_widths': [3.5, 2.5, 4.0, 5.5]},
            ],
        },

        # ── 第三章：基金怎么选 ────────────────────────────────
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

        # ── 第四章：组合怎么搭 ────────────────────────────────
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
                     '低于15%则3年难以完成6%+目标。20%是精确计算后的平衡点。'
                 ), 'indent': True},
                {'type': 'body',
                 'text': (
                     '对冲层10%：黄金与债股相关性极低，加入后可将组合最大回撤'
                     f'从预估-12%压低至{exp_dd}，这10%是「保险丝」，不是为了赚钱。'
                 ), 'indent': True},
            ],
        },

        # ── 第五章：风险在哪里 ────────────────────────────────
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
                 'rows': [
                     ['债市利率超预期上行',
                      '10年期国债升破2%',
                      '核心层回撤-3%至-5%，影响约2-3.5万元',
                      '持有等待修复，债基到期收益为正'],
                     ['权益市场系统性下跌',
                      '沪深300下跌超20%',
                      '卫星层跌8-12%，影响约1.6-2.4万元',
                      '股息收益对冲部分损失，3年维度修复概率高'],
                     ['黄金熊市周期',
                      '黄金下跌超15%',
                      '对冲层影响约1-1.5万元',
                      '对冲工具，整体影响有限'],
                     ['极端不利情景（三者同发）',
                      '概率极低',
                      f'组合最大亏损约8-9万（{exp_dd}）',
                      '仍低于您15万的心理赎回线，坚持持有'],
                 ],
                 'col_widths': [2.8, 3.5, 4.5, 4.7]},
                {'type': 'body',
                 'text': (
                     '触发重新评估的条件：①组合账面亏损超过8万元  '
                     '②任一基金经理离任  '
                     '③您的财务状况或风险偏好发生重大变化  '
                     '④市场研判标签从「中性」转为「谨慎」'
                 ),
                 'highlight': True},
            ],
        },

        # ── 第六章：行动指引 ──────────────────────────────────
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
                 'text': '④ 止稳检查线：账面亏损超8万，不要自行赎回，先联系投顾重新评估',
                 'indent': False},
                {'type': 'body',
                 'text': f'⑤ 下次组合检视时间：3个月后（约{report_date[:7]}之后）',
                 'indent': False,
                 'highlight': True},
            ],
        },
    ]
    return sections


def _build_sections_summary(client_name, risk_level, market_status,
                              funds, client_dict, report_date):
    """
    构建一页纸摘要版 sections（通用模板格式）。
    聚焦：KPI总览 + 基金表 + 三步操作。
    """
    risk_label  = RISK_LABELS.get(risk_level, risk_level)
    exp_return  = client_dict.get('portfolio_expected_return', '5-7%')
    exp_dd      = client_dict.get('portfolio_max_drawdown',    '-6%至-8%')
    capital     = client_dict.get('capital', '（未填）')

    fund_headers, fund_rows, fund_col_w = _fund_table_rows(funds)

    sections = [
        {
            'h1': '',
            'content': [
                {'type': 'table',
                 'headers': ['风险等级', '预期年化', '最大回撤', '权益敞口', '建仓方式'],
                 'rows': [[
                     f'{risk_level} {risk_label}',
                     exp_return,
                     exp_dd,
                     '20%',
                     '分3月分批',
                 ]],
                 'col_widths': [2.5, 2.5, 3.0, 2.5, 5.0]},
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
                 'text': '持有期间只需记住：账面亏损超8万（-8%）→ 先联系投顾，不要自行赎回',
                 'highlight': True},
            ],
        },
    ]
    return sections


# ── 主生成函数 ────────────────────────────────────────────────

def generate_full_report(client_name, risk_level, market_status,
                          funds, client_dict, output_path, report_date):
    """完整版：调用 build_consulting_doc（咨询模板）"""
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
        funds, client_dict, report_date
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
                             funds, client_dict, output_path, report_date):
    """一页纸摘要版：调用 build_general_doc（通用模板，深青+暖橙色系）"""
    risk_label = RISK_LABELS.get(risk_level, risk_level)
    capital    = client_dict.get('capital', '')

    sections = _build_sections_summary(
        client_name, risk_level, market_status,
        funds, client_dict, report_date
    )

    doc = build_general_doc(
        title        = f'基金组合推荐一页纸  ·  {client_name}  ·  {report_date}',
        header       = '基金投资顾问团队',
        footer       = '本摘要配合完整版研究报告使用',
        primary_hex  = '0A4D68',   # 深海蓝（与咨询模板炭灰区分，一眼看出是摘要版）
        accent_hex   = 'F4A261',   # 暖橙
        stripe_hex   = 'EAF4FB',   # 浅蓝条纹
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
        description='基金推荐报告生成器 v2.0（接入 document-suite）'
    )
    parser.add_argument('--client_name',   required=True,  help='客户名称')
    parser.add_argument('--risk_level',    required=True,  help='风险等级：R1-R5')
    parser.add_argument('--market_status', required=True,  help='市场研判：积极/中性/谨慎')
    parser.add_argument('--funds_json',    required=True,  help='基金数据JSON文件路径')
    parser.add_argument('--output_path',   required=True,  help='输出目录')
    args = parser.parse_args()

    if not os.path.exists(args.funds_json):
        print(f'[错误] 基金数据文件不存在：{args.funds_json}')
        sys.exit(1)

    client_dict, funds = _load_data(args.funds_json)

    if not funds:
        print('[错误] 基金列表为空，请检查 fund_data.json')
        sys.exit(1)

    # 命令行参数优先于 json 内的 client 字段（方便覆盖）
    if args.client_name:
        client_dict['name'] = args.client_name
    if args.risk_level:
        client_dict['risk_level'] = args.risk_level

    report_date = datetime.now().strftime('%Y年%m月%d日')

    generate_full_report(
        args.client_name, args.risk_level, args.market_status,
        funds, client_dict, args.output_path, report_date
    )
    generate_summary_sheet(
        args.client_name, args.risk_level, args.market_status,
        funds, client_dict, args.output_path, report_date
    )
    print('[完成] 两份文档均已生成，请检查输出目录。')


if __name__ == '__main__':
    main()
