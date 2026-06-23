# -*- coding: utf-8 -*-
"""UI组件、中文表格和全局CSS。"""
from __future__ import annotations

import html
import pandas as pd
import streamlit as st


COLUMN_LABELS = {
    "id": "记录ID", "datetime": "时间", "date": "日期", "code": "代码", "symbol": "代码", "name": "名称",
    "theme": "主题/板块", "sector": "板块", "close": "收盘价", "open": "开盘价", "high": "最高价", "low": "最低价",
    "pre_close": "昨收", "realtime_price": "实时价", "price": "价格", "pct_chg": "涨跌幅", "pct_change": "涨跌幅",
    "change": "涨跌额", "score": "评分", "suggestion": "建议", "daily_k_trend": "日K趋势", "trend_status": "趋势状态",
    "ma5_relation": "五日线状态", "ma5_deviation_pct": "偏离五日线%", "volume_status": "量能状态", "buy_point": "买点类型",
    "is_breakout": "是否突破", "is_pullback": "是否回踩", "MA5": "五日线", "MA10": "十日线", "MA20": "二十日线", "MA60": "六十日线",
    "support": "支撑位", "pressure": "压力位", "stop_loss": "止损位", "rise_20d": "20日涨幅%", "reason": "触发原因",
    "risk": "风险提示", "amount": "成交金额", "amount_yi": "成交额(亿)", "turnover": "换手率", "volume": "成交量/股数",
    "shares": "股数", "volume_ratio": "量比", "update_time": "更新时间", "up_count": "上涨家数", "down_count": "下跌家数",
    "leader": "领涨股", "leader_pct": "领涨幅", "strength_score": "强度评分", "market_value": "总市值", "side": "方向",
    "action": "动作", "action_type": "操作类型", "position_status": "状态", "note": "交易本子", "rough_return_pct": "粗略收益率%",
    "buy_avg": "买入均价", "sell_avg": "卖出均价", "first_buy_date": "首次买入日", "close_date": "清仓日", "buy_volume": "买入股数",
    "sell_volume": "卖出股数", "title": "标题", "content": "内容", "tags": "标签", "created_at": "创建时间", "updated_at": "更新时间",
    "cash_after": "交易后现金", "position_after": "交易后持仓", "cost_price": "成本价",
    "final_value": "期末资产", "total_return": "总收益率", "annual_return": "年化收益率", "max_drawdown": "最大回撤",
    "win_rate": "胜率", "trade_count": "交易次数", "error": "错误信息", "equity": "资金曲线", "strategy_id": "策略ID",
    "raw_action": "AI原始动作", "final_action": "审计后动作", "audit_status": "审计状态", "rule_signal": "脚本信号",
    "raw_ai_text": "AI原文", "final_decision": "最终决策", "market_state": "行情状态",
    "event": "事件", "message": "信息", "pid": "进程ID", "time": "心跳时间", "status": "状态",
    "selected_codes": "观察代码", "current_code": "当前代码", "results": "本轮结果", "traceback": "错误堆栈",

    "candidate_level": "候选等级", "setup_type": "形态类型", "matched_conditions": "命中条件", "failed_filters": "未通过过滤", "risk_flags": "风险标记",
    "ret20_pct": "20日涨幅%", "ret60_pct": "60日涨幅%", "distance_ma5_pct": "距五日线%", "score_detail": "评分明细",
    "snapshot_id": "快照ID", "source": "来源", "audit_message": "审计说明", "confidence": "信心等级", "execution_plan": "执行计划", "invalid_if": "失效条件", "review_note": "复盘备注",
}

DISPLAY_COLUMN_ORDER = [
    "date", "datetime", "code", "name", "action", "side", "action_type", "price", "shares", "volume", "amount",
    "cash_after", "position_after", "position_status", "reason", "risk", "note", "strategy_id",
    "final_value", "total_return", "annual_return", "max_drawdown", "win_rate", "trade_count",
    "theme", "sector", "close", "realtime_price", "pct_chg", "pct_change", "score", "suggestion", "daily_k_trend",
    "trend_status", "ma5_relation", "MA5", "MA10", "MA20", "MA60", "volume_status", "buy_point", "is_breakout", "is_pullback",
    "support", "pressure", "stop_loss", "rise_20d", "amount_yi", "turnover", "update_time",
]

VALUE_MAP = {
    "BUY": "买入", "SELL": "卖出", "ADD": "加仓", "CLEAR": "清仓",
    "PAPER_BUY": "虚拟买入", "PAPER_ADD": "虚拟加仓", "PAPER_SELL": "虚拟减仓", "PAPER_CLEAR": "虚拟清仓",
    "WATCH": "观察", "NO_ACTION": "不操作",
    "core_candidate": "核心候选", "watch_candidate": "观察候选", "weak_watch": "弱观察", "reject": "剔除",
    "pullback_candidate": "回踩候选", "breakout_candidate": "突破候选", "trend_candidate": "趋势候选", "watch": "观察",
    "low": "低", "medium": "中", "high": "高",
    "cycle_result": "轮询结果", "worker_error": "后台错误", "worker_started": "后台启动", "worker_keyboard_interrupt": "手动中断",
    "running_cycle": "轮询中", "running_code": "处理股票", "cycle_done": "本轮完成", "idle_no_codes": "无观察股票", "stopped": "已停止",
    "code_skip_ai": "规则未触发", "audit_pass": "审计通过", "audit_reject": "审计拒绝",
}

CONDITION_LABELS = {
    "price_above_ma5": "价格在五日线上方", "price_above_ma10": "价格在十日线上方", "price_above_ma20": "价格在二十日线上方",
    "price_below_ma10": "跌破十日线", "price_below_ma20": "跌破二十日线", "price_below_ma20_and_trend_broken": "跌破二十日线且趋势破坏",
    "price_near_ma5": "接近五日线", "price_near_ma10": "接近十日线", "price_near_ma20": "接近二十日线",
    "price_near_ma5_or_ma10_or_ma20": "接近关键均线", "price_pullback_to_ma5_or_ma10": "回踩五/十日线附近",
    "ma5_above_ma10": "五日线在十日线上方", "ma10_above_ma20": "十日线在二十日线上方", "ma20_above_ma60": "二十日线在六十日线上方",
    "trend_not_broken": "趋势未破坏", "trend_broken": "趋势破坏",
    "pullback_volume_shrink": "回踩缩量", "volume_healthy": "量能健康", "volume_mild_expand": "温和放量", "volume_big_expand": "明显放量",
    "volume_big_drop": "放量下跌", "volume_up_price_stagnant": "放量滞涨", "volume_not_support": "量能不支持",
    "no_big_bearish_breakdown": "没有放量大阴破位", "high_volume_big_bearish_breakdown": "放量大阴破位", "high_volume_upper_shadow_failed": "放量长上影失败",
    "intraday_recover_vwap": "分时重新站上均价线", "intraday_support_strong": "分时承接较强", "intraday_failed_breakout": "分时突破失败",
    "weak_intraday_rebound": "分时弱反抽", "weak_intraday_rebound_after_rise": "上涨后分时弱反抽",
    "breakout_20d_high": "突破二十日高点", "near_major_resistance_without_breakout": "接近压力位但未突破",
    "pullback_then_recover": "回踩后重新走强", "failed_rebound_after_breakdown": "破位后反抽失败",
    "already_holding": "已有持仓", "not_holding": "当前未持仓", "profit_position": "持仓浮盈", "position_allowed": "仓位允许",
    "max_positions_reached": "持仓数量已满", "add_times_not_exceeded": "加仓次数未超限", "cost_not_too_high": "成本不过高",
    "distance_ma5_too_high": "距离五日线过远", "distance_ma5_too_high_for_add": "加仓时距离五日线过远", "price_far_above_ma5": "价格明显高于五日线",
    "sector_strength_ok": "板块强度尚可", "stock_stronger_than_sector": "个股强于板块", "sector_turns_weak": "板块转弱", "sector_turns_weak_and_stock_breaks_ma10": "板块转弱且个股跌破十日线",
    "insufficient_daily_data": "日线数据不足", "insufficient_intraday_data": "分时数据不足", "insufficient_volume_data": "量能数据不足",
}


def _translate_reason_value(value: object) -> object:
    if pd.isna(value):
        return value
    s = str(value)
    if not s:
        return s
    for sep in [";", "；", ",", "，"]:
        if sep in s:
            parts = [p.strip() for p in s.replace("；", ";").replace("，", ";").replace(",", ";").split(";") if p.strip()]
            return "；".join(CONDITION_LABELS.get(p, VALUE_MAP.get(p, p)) for p in parts)
    return CONDITION_LABELS.get(s, VALUE_MAP.get(s, s))


def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for code_col in ["code", "symbol", "current_code"]:
        if code_col in out.columns:
            out[code_col] = out[code_col].map(_format_stock_code)
    ordered = [col for col in DISPLAY_COLUMN_ORDER if col in out.columns]
    rest = [col for col in out.columns if col not in ordered]
    out = out[ordered + rest]
    for col in out.columns:
        if col in {"action", "raw_action", "final_action", "side", "action_type", "audit_status", "candidate_level", "setup_type", "confidence", "event", "status"}:
            out[col] = out[col].map(lambda x: VALUE_MAP.get(str(x), x) if pd.notna(x) else x)
        if col in {"reason", "risk", "rule_signal", "matched_conditions", "failed_filters", "risk_flags", "execution_plan", "invalid_if"}:
            out[col] = out[col].map(_translate_reason_value)
    out = out.rename(columns={col: COLUMN_LABELS.get(col, col) for col in out.columns})
    return out


def _format_stock_code(value: object) -> object:
    if pd.isna(value):
        return value
    s = str(value).strip()
    if not s:
        return s
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) <= 6 and digits:
        return digits.zfill(6)
    return s


def inject_css(mode: str = "dark", compact: bool = False) -> None:
    is_light = mode == "light"
    if is_light:
        bg = "#f4f7fb"; sidebar = "#ffffff"; card = "#ffffff"; card2 = "#f9fafb"; text = "#111827"; muted = "#475569"; accent = "#2563eb"; border = "rgba(15,23,42,0.12)"; button_bg = "#ffffff"; table_bg = "#ffffff"; table_head = "#eef4ff"; table_text = "#111827"
    else:
        bg = "radial-gradient(circle at top left, #111827 0%, #070b12 44%, #020617 100%)"; sidebar = "linear-gradient(180deg, #0f172a 0%, #020617 100%)"; card = "linear-gradient(145deg, rgba(15, 23, 42, 0.96), rgba(30, 41, 59, 0.78))"; card2 = "#0b1220"; text = "#f8fafc"; muted = "#94a3b8"; accent = "#38bdf8"; border = "rgba(148, 163, 184, 0.18)"; button_bg = "linear-gradient(145deg, rgba(14,165,233,0.18), rgba(37,99,235,0.20))"; table_bg = "#050910"; table_head = "#111827"; table_text = "#e5e7eb"
    st.markdown(f"""
    <style>
    html, body, [class*="css"], .stApp {{ font-family: "Inter", "Microsoft YaHei", "PingFang SC", sans-serif !important; color: {text} !important; }}
    .stApp, div[data-testid="stAppViewContainer"] {{ background: {bg} !important; color: {text} !important; }}
    header[data-testid="stHeader"] {{ background: transparent !important; box-shadow:none !important; }}
    div[data-testid="stToolbar"] {{ background: transparent !important; }}
    section[data-testid="stSidebar"] {{ background: {sidebar} !important; border-right: 1px solid {border}; }}
    section[data-testid="stSidebar"] * {{ color: {text} !important; }}
    .block-container {{ padding-top: 0.65rem !important; padding-bottom: 2rem; max-width: 1720px; }}
    h1,h2,h3,h4,h5,h6,p,label,span,div {{ color: {text}; }}
    .metric-card, .v3-card {{ background: {card}; border:1px solid {border}; border-radius:16px; padding:14px 15px; box-shadow:0 10px 26px rgba(15,23,42,0.08); min-height:88px; }}
    .metric-title {{ color:{muted}; font-size:13px; font-weight:700; margin-bottom:7px; }}
    .metric-value {{ color:{text}; font-size:25px; font-weight:900; line-height:1.15; }}
    .metric-caption {{ color:{accent}; font-size:12px; margin-top:7px; }}
    .stButton > button {{ border-radius:12px; border:1px solid rgba(56,189,248,0.35); background:{button_bg}; color:{text} !important; font-weight:800; min-height:38px; }}
    .stButton > button:hover {{ border-color:{accent}; }}
    input, textarea, [data-baseweb="input"] input, [data-baseweb="textarea"] textarea {{ background: {card2} !important; color:{text} !important; border-color:{border} !important; }}
    div[data-baseweb="select"] > div {{ background:{card2} !important; color:{text} !important; border-color:{border} !important; }}
    div[role="listbox"], ul[role="listbox"] {{ background:{card2} !important; color:{text} !important; border:1px solid {border} !important; }}
    div[role="option"] {{ color:{text} !important; background:{card2} !important; }}
    div[role="option"]:hover {{ background: rgba(56,189,248,0.12) !important; }}
    .stAlert {{ border-radius:12px; }}
    .v3-section-title {{font-size:19px; font-weight:900; margin:10px 0 8px 0; color:{text};}}
    .jzl-table-wrap {{ max-height: 520px; overflow:auto; border:1px solid {border}; border-radius:14px; background:{table_bg}; }}
    table.jzl-table {{ border-collapse: collapse; width:100%; min-width: 920px; font-size:13px; color:{table_text}; }}
    table.jzl-table th {{ position: sticky; top:0; background:{table_head}; color:{table_text}; padding:10px 12px; text-align:left; border-bottom:1px solid {border}; white-space:nowrap; z-index:2; }}
    table.jzl-table td {{ padding:9px 12px; border-bottom:1px solid {border}; white-space:nowrap; color:{table_text}; }}
    table.jzl-table tr:nth-child(even) td {{ background: {('#f8fafc' if is_light else '#060b14')}; }}
    table.jzl-table tr:hover td {{ background: rgba(56,189,248,0.10); }}
    .jzl-note {{ color:{muted}; font-size:13px; }}

    /* V3.9.8：不要再隐藏 Streamlit Header。
       原因：侧边栏收起后的“展开菜单”按钮挂在 header 区域；隐藏 header 会导致菜单无法打开。
       这里只做透明化，不做 display:none / visibility:hidden。 */
    header[data-testid="stHeader"] {{
        background: transparent !important;
        box-shadow: none !important;
        height: 2.4rem !important;
        min-height: 2.4rem !important;
        visibility: visible !important;
        display: block !important;
        pointer-events: auto !important;
    }}
    #MainMenu, footer {{ visibility: hidden !important; height: 0 !important; }}
    div[data-testid="stDecoration"] {{ display:none !important; }}
    .main .block-container {{ padding-top: 0.45rem !important; }}

    /* 白天模式/黑夜模式统一文字对比度，防止部分白字残留 */
    .stMarkdown, .stMarkdown *, .stText, .stText *, .stCaptionContainer, .stCaptionContainer *,
    div[data-testid="stMarkdownContainer"], div[data-testid="stMarkdownContainer"] *,
    div[data-testid="stWidgetLabel"], div[data-testid="stWidgetLabel"] *,
    div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] *,
    div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {{
        color: {text} !important;
    }}

    /* BaseWeb 下拉、输入框、弹窗在白天模式强制白底黑字 */
    div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"], div[role="listbox"] {{
        background: {card2} !important;
        color: {text} !important;
        border: 1px solid {border} !important;
    }}
    div[data-baseweb="popover"] *, div[data-baseweb="menu"] *, ul[role="listbox"] *, div[role="option"] * {{
        color: {text} !important;
    }}
    div[data-baseweb="select"] span, div[data-baseweb="select"] div, div[data-baseweb="input"] input, textarea {{
        color: {text} !important;
    }}
    
    /* 常规表格强制使用中文表格样式，不再调用默认深色DataFrame皮肤 */
    .jzl-table-wrap, .jzl-table-wrap * {{ color: {table_text} !important; }}



    /* V3.9.2 下拉菜单深浅色强制修复：BaseWeb 的弹层会挂在页面外层，必须全局覆盖 */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="menu"],
    div[data-baseweb="menu"] ul,
    ul[role="listbox"],
    div[role="listbox"],
    div[role="presentation"] ul {{
        background: {card2} !important;
        color: {text} !important;
        border: 1px solid {border} !important;
        box-shadow: 0 16px 36px rgba(0,0,0,0.28) !important;
    }}
    li[role="option"],
    div[role="option"],
    div[data-baseweb="menu"] li,
    div[data-baseweb="menu"] div {{
        background: {card2} !important;
        color: {text} !important;
    }}
    li[role="option"] *,
    div[role="option"] *,
    div[data-baseweb="menu"] *,
    div[data-baseweb="popover"] * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}
    li[role="option"]:hover,
    div[role="option"]:hover,
    li[aria-selected="true"],
    div[aria-selected="true"] {{
        background: {('rgba(37,99,235,0.12)' if is_light else 'rgba(56,189,248,0.18)')} !important;
        color: {text} !important;
    }}

    /* V3.9.8：顶部区域透明化，但不能隐藏 header，否则侧边栏收起后无法恢复。 */
    header[data-testid="stHeader"] {{
        background: transparent !important;
        box-shadow: none !important;
        visibility: visible !important;
        display: block !important;
        height: 2.4rem !important;
        min-height: 2.4rem !important;
        pointer-events: auto !important;
    }}
    div[data-testid="stToolbar"] {{
        background: transparent !important;
        visibility: visible !important;
        display: block !important;
        pointer-events: auto !important;
    }}
    div[data-testid="stDecoration"], #MainMenu, footer {{
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        min-height: 0 !important;
        max-height: 0 !important;
    }}
    div[data-testid="stAppViewContainer"] > .main {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}


    /* V3.9.3：修复黑夜模式 AI交易员页面的白色折叠栏、数字输入按钮、空白控件 */
    div[data-testid="stExpander"],
    div[data-testid="stExpander"] details,
    div[data-testid="stExpander"] details summary,
    div[data-testid="stExpander"] > details > summary,
    details summary,
    .streamlit-expanderHeader {{
        background: {card2} !important;
        color: {text} !important;
        border: 1px solid {border} !important;
        border-radius: 12px !important;
        box-shadow: none !important;
    }}
    div[data-testid="stExpander"] details summary *,
    details summary *,
    .streamlit-expanderHeader * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}
    div[data-testid="stExpander"] div[data-testid="stVerticalBlock"],
    div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {{
        background: transparent !important;
        color: {text} !important;
    }}

    /* 数字输入框右侧 +/- 按钮，黑夜模式不能露白 */
    div[data-testid="stNumberInput"] button,
    div[data-testid="stNumberInput"] div[role="button"],
    div[data-testid="stNumberInput"] [data-baseweb="button"] {{
        background: {card2} !important;
        color: {text} !important;
        border-color: {border} !important;
        box-shadow: none !important;
    }}
    div[data-testid="stNumberInput"] button *,
    div[data-testid="stNumberInput"] div[role="button"] *,
    div[data-testid="stNumberInput"] [data-baseweb="button"] * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
        fill: {text} !important;
    }}

    /* 复选框、单选按钮文字和控件颜色统一 */
    div[data-testid="stCheckbox"] *,
    div[data-testid="stRadio"] *,
    label[data-baseweb="checkbox"] *,
    label[data-baseweb="radio"] * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}

    /* 空白的表单容器、展开区域、横向块不应出现白色背景 */
    div[data-testid="stForm"],
    div[data-testid="stForm"] *,
    div[data-testid="stHorizontalBlock"],
    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="column"] {{
        color: {text} !important;
    }}
    div[data-testid="stForm"],
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: transparent !important;
        border-color: {border} !important;
    }}

    /* 任何 BaseWeb 弹层在黑夜模式继续跟随深色背景 */
    [data-baseweb="popover"],
    [data-baseweb="popover"] *,
    [data-baseweb="menu"],
    [data-baseweb="menu"] *,
    [data-baseweb="select-dropdown"],
    [data-baseweb="select-dropdown"] * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [data-baseweb="select-dropdown"] {{
        background: {card2} !important;
        border-color: {border} !important;
    }}


    /* V3.9.4：全局弹层/日期选择器修复。之前黑夜模式仍露白，主要来自 BaseWeb Calendar */
    div[data-testid="stDateInput"],
    div[data-testid="stDateInput"] *,
    div[data-baseweb="datepicker"],
    div[data-baseweb="datepicker"] *,
    div[data-baseweb="calendar"],
    div[data-baseweb="calendar"] *,
    div[data-baseweb="calendar"] table,
    div[data-baseweb="calendar"] thead,
    div[data-baseweb="calendar"] tbody,
    div[data-baseweb="calendar"] tr,
    div[data-baseweb="calendar"] td,
    div[data-baseweb="calendar"] th {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
        border-color: {border} !important;
    }}
    div[data-baseweb="calendar"],
    div[data-baseweb="calendar"] > div,
    div[data-baseweb="calendar"] table,
    div[data-baseweb="calendar"] tbody,
    div[data-baseweb="calendar"] thead,
    div[data-baseweb="calendar"] tr,
    div[data-baseweb="calendar"] td,
    div[data-baseweb="calendar"] th {{
        background: {card2} !important;
    }}
    div[data-baseweb="calendar"] button,
    div[data-baseweb="calendar"] [role="button"],
    div[data-baseweb="calendar"] div[role="gridcell"],
    div[data-baseweb="calendar"] button[role="gridcell"] {{
        background: transparent !important;
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
        border-color: transparent !important;
        box-shadow: none !important;
    }}
    div[data-baseweb="calendar"] button:hover,
    div[data-baseweb="calendar"] [role="button"]:hover,
    div[data-baseweb="calendar"] div[role="gridcell"]:hover,
    div[data-baseweb="calendar"] button[role="gridcell"]:hover {{
        background: {('rgba(37,99,235,0.14)' if is_light else 'rgba(56,189,248,0.18)')} !important;
        color: {text} !important;
    }}
    div[data-baseweb="calendar"] [aria-selected="true"],
    div[data-baseweb="calendar"] button[aria-selected="true"],
    div[data-baseweb="calendar"] div[aria-selected="true"] {{
        background: {accent} !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border-radius: 999px !important;
    }}
    div[data-baseweb="calendar"] [aria-disabled="true"],
    div[data-baseweb="calendar"] [aria-disabled="true"] * {{
        color: {muted} !important;
        -webkit-text-fill-color: {muted} !important;
        opacity: 0.55 !important;
    }}
    div[data-baseweb="calendar"] svg,
    div[data-baseweb="datepicker"] svg,
    div[data-baseweb="popover"] svg {{
        fill: {text} !important;
        color: {text} !important;
    }}
    div[data-baseweb="popover"] > div,
    div[data-baseweb="popover"] > div > div,
    div[data-baseweb="popover"] [data-baseweb="calendar"] {{
        background: {card2} !important;
        border-color: {border} !important;
    }}

    /* V3.9.4：统一所有折叠条、提示条、分页/表单小组件，避免黑夜/白天混色 */
    div[data-testid="stExpander"] details,
    div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] div,
    div[data-testid="stPopover"],
    div[data-testid="stPopover"] *,
    div[data-testid="stTooltipIcon"],
    div[data-testid="stTooltipIcon"] * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}
    div[data-testid="stAlert"] * {{
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}

    /* V3.9.4：浏览器/组件默认白色层兜底，仅对Streamlit内容区生效 */
    div[data-testid="stAppViewContainer"] div[data-baseweb],
    div[data-testid="stAppViewContainer"] div[data-testid="stForm"],
    div[data-testid="stAppViewContainer"] div[data-testid="stHorizontalBlock"] {{
        border-color: {border} !important;
    }}


    /* V3.9.8：侧边栏稳定修复。
       不再隐藏官方收起按钮；保留收起/展开能力。
       重点：无论黑夜/白天模式，展开按钮必须永远可见、可点击。 */
    div[data-testid="stSidebarCollapseButton"],
    button[data-testid="stSidebarCollapseButton"],
    button[title="Close sidebar"],
    button[aria-label="Close sidebar"] {{
        display: flex !important;
        visibility: visible !important;
        opacity: 0.85 !important;
        pointer-events: auto !important;
        color: {text} !important;
        background: transparent !important;
        border: none !important;
        z-index: 999999 !important;
    }}

    div[data-testid="collapsedControl"],
    div[data-testid="stSidebarCollapsedControl"],
    button[title="Open sidebar"],
    button[aria-label="Open sidebar"],
    button[kind="header"] {{
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        z-index: 999999 !important;
        color: {text} !important;
    }}

    div[data-testid="collapsedControl"],
    div[data-testid="stSidebarCollapsedControl"] {{
        display: flex !important;
        position: fixed !important;
        left: 12px !important;
        top: 12px !important;
        width: 44px !important;
        height: 44px !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 12px !important;
        background: {card2} !important;
        border: 1px solid {border} !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.25) !important;
    }}

    div[data-testid="collapsedControl"] *,
    div[data-testid="stSidebarCollapsedControl"] *,
    button[title="Open sidebar"] *,
    button[aria-label="Open sidebar"] *,
    button[title="Close sidebar"] *,
    button[aria-label="Close sidebar"] * {{
        color: {text} !important;
        fill: {text} !important;
        stroke: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}

    section[data-testid="stSidebar"] {{
        min-width: 300px !important;
        max-width: 360px !important;
    }}


    /* V3.9.9：最终侧边栏修复：改为页面内置菜单，完全不依赖官方 st.sidebar。 */
    section[data-testid="stSidebar"] {{
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
    }}
    div[data-testid="collapsedControl"],
    div[data-testid="stSidebarCollapsedControl"],
    button[title="Open sidebar"],
    button[aria-label="Open sidebar"],
    button[title="Close sidebar"],
    button[aria-label="Close sidebar"] {{
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
    }}
    .jzl-left-menu-title {{
        font-size: 28px;
        font-weight: 950;
        margin: 8px 0 26px 0;
        color: {text} !important;
        letter-spacing: -0.4px;
    }}
    .jzl-left-menu-subtitle {{
        font-size: 17px;
        font-weight: 900;
        margin: 12px 0 8px 0;
        color: {text} !important;
    }}
    .jzl-left-menu-note {{
        margin-top: 18px;
        font-size: 12px;
        line-height: 1.6;
        color: {muted} !important;
        opacity: 0.78;
        border-top: 1px solid {border};
        padding-top: 12px;
    }}
    div[role="radiogroup"] label,
    div[role="radiogroup"] label * {{
        font-size: 17px !important;
        font-weight: 780 !important;
        color: {text} !important;
        -webkit-text-fill-color: {text} !important;
    }}
    div[data-testid="stRadio"] {{
        background: transparent !important;
        color: {text} !important;
    }}
    div[data-testid="column"]:first-child {{
        min-width: 250px !important;
    }}

    </style>
    """, unsafe_allow_html=True)

    if is_light:
        app_bg = "#f5f7fb"
        surface = "#ffffff"
        surface_soft = "#f8fafc"
        surface_alt = "#eef2f7"
        text_main = "#101827"
        text_muted = "#64748b"
        accent_main = "#2563eb"
        accent_soft = "rgba(37, 99, 235, 0.10)"
        border_soft = "rgba(15, 23, 42, 0.10)"
        shadow = "0 14px 34px rgba(15, 23, 42, 0.08)"
        table_head_bg = "#eaf1ff"
        table_row_alt = "#f8fafc"
        positive = "#15803d"
        negative = "#dc2626"
        warning = "#b45309"
    else:
        app_bg = "#0f1218"
        surface = "#171b22"
        surface_soft = "#11151c"
        surface_alt = "#202631"
        text_main = "#f4f7fb"
        text_muted = "#9aa4b2"
        accent_main = "#60a5fa"
        accent_soft = "rgba(96, 165, 250, 0.14)"
        border_soft = "rgba(226, 232, 240, 0.12)"
        shadow = "0 16px 42px rgba(0, 0, 0, 0.28)"
        table_head_bg = "#202631"
        table_row_alt = "#141922"
        positive = "#4ade80"
        negative = "#fb7185"
        warning = "#fbbf24"

    st.markdown(f"""
    <style>
    :root {{
        --jzl-bg: {app_bg};
        --jzl-surface: {surface};
        --jzl-surface-soft: {surface_soft};
        --jzl-surface-alt: {surface_alt};
        --jzl-text: {text_main};
        --jzl-muted: {text_muted};
        --jzl-accent: {accent_main};
        --jzl-accent-soft: {accent_soft};
        --jzl-border: {border_soft};
        --jzl-shadow: {shadow};
        --jzl-positive: {positive};
        --jzl-negative: {negative};
        --jzl-warning: {warning};
    }}

    html, body, [class*="css"], .stApp {{
        font-family: "Inter", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif !important;
        letter-spacing: 0 !important;
    }}
    .stApp,
    div[data-testid="stAppViewContainer"] {{
        background: var(--jzl-bg) !important;
        color: var(--jzl-text) !important;
    }}
    .block-container {{
        max-width: 1840px !important;
        padding: 0.75rem 1.15rem 2rem !important;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: var(--jzl-text) !important;
        letter-spacing: 0 !important;
    }}
    div[data-testid="stMarkdownContainer"] h3,
    div[data-testid="stHeading"] h3 {{
        font-size: 20px !important;
        line-height: 1.35 !important;
        margin: 0.95rem 0 0.55rem !important;
        padding-left: 10px !important;
        border-left: 3px solid var(--jzl-accent) !important;
    }}
    p, label, span, div[data-testid="stMarkdownContainer"] {{
        color: var(--jzl-text) !important;
    }}
    div[data-testid="stCaptionContainer"],
    div[data-testid="stCaptionContainer"] * {{
        color: var(--jzl-muted) !important;
    }}

    .jzl-app-header {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        margin: 0 0 14px;
        padding: 14px 16px;
        border: 1px solid var(--jzl-border);
        border-radius: 8px;
        background: var(--jzl-surface);
        box-shadow: var(--jzl-shadow);
    }}
    .jzl-app-kicker {{
        color: var(--jzl-muted) !important;
        font-size: 12px;
        font-weight: 800;
        text-transform: uppercase;
    }}
    .jzl-app-title {{
        color: var(--jzl-text) !important;
        font-size: 27px;
        line-height: 1.2;
        font-weight: 900;
        margin-top: 2px;
    }}
    .jzl-app-subtitle {{
        color: var(--jzl-muted) !important;
        font-size: 13px;
        line-height: 1.6;
        margin-top: 4px;
    }}
    .jzl-app-meta {{
        min-width: 172px;
        color: var(--jzl-muted) !important;
        font-size: 12px;
        line-height: 1.7;
        text-align: right;
        font-weight: 700;
    }}
    .jzl-app-page {{
        color: var(--jzl-accent) !important;
    }}

    div[data-testid="column"]:has(.jzl-left-menu-title) > div[data-testid="stVerticalBlock"] {{
        position: sticky;
        top: 0.75rem;
        padding: 14px;
        border: 1px solid var(--jzl-border);
        border-radius: 8px;
        background: var(--jzl-surface);
        box-shadow: var(--jzl-shadow);
    }}
    .jzl-left-menu-title {{
        font-size: 21px !important;
        font-weight: 900 !important;
        margin: 0 0 14px !important;
        letter-spacing: 0 !important;
        color: var(--jzl-text) !important;
    }}
    .jzl-left-menu-subtitle {{
        font-size: 12px !important;
        font-weight: 900 !important;
        margin: 14px 0 7px !important;
        color: var(--jzl-muted) !important;
        text-transform: uppercase;
    }}
    .jzl-left-menu-note {{
        display: none !important;
    }}
    div[data-testid="stRadio"] {{
        background: transparent !important;
    }}
    div[data-testid="stRadio"] label {{
        min-height: 34px !important;
        border-radius: 8px !important;
        padding: 6px 8px !important;
        border: 1px solid transparent !important;
    }}
    div[data-testid="stRadio"] label:hover {{
        background: var(--jzl-accent-soft) !important;
        border-color: var(--jzl-border) !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) {{
        background: var(--jzl-accent-soft) !important;
        border-color: color-mix(in srgb, var(--jzl-accent) 42%, transparent) !important;
    }}
    div[data-testid="stRadio"] label *,
    div[role="radiogroup"] label * {{
        font-size: 14px !important;
        font-weight: 750 !important;
    }}

    .metric-card,
    .v3-card,
    div[data-testid="stMetric"] {{
        border-radius: 8px !important;
        border: 1px solid var(--jzl-border) !important;
        background: var(--jzl-surface) !important;
        box-shadow: var(--jzl-shadow) !important;
    }}
    .metric-card {{
        position: relative;
        min-height: 82px !important;
        padding: 13px 14px !important;
        overflow: hidden;
    }}
    .metric-card::before {{
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 3px;
        background: var(--jzl-accent);
        opacity: 0.82;
    }}
    .metric-card--positive::before {{ background: var(--jzl-positive); }}
    .metric-card--negative::before {{ background: var(--jzl-negative); }}
    .metric-card--warning::before {{ background: var(--jzl-warning); }}
    .metric-title {{
        color: var(--jzl-muted) !important;
        font-size: 12px !important;
        font-weight: 800 !important;
        margin-bottom: 6px !important;
    }}
    .metric-value {{
        color: var(--jzl-text) !important;
        font-size: 24px !important;
        line-height: 1.16 !important;
        font-weight: 900 !important;
        word-break: break-word;
    }}
    .metric-card--positive .metric-value {{ color: var(--jzl-positive) !important; }}
    .metric-card--negative .metric-value {{ color: var(--jzl-negative) !important; }}
    .metric-card--warning .metric-value {{ color: var(--jzl-warning) !important; }}
    .metric-caption {{
        color: var(--jzl-muted) !important;
        font-size: 12px !important;
        line-height: 1.45 !important;
        margin-top: 6px !important;
    }}
    div[data-testid="stMetric"] {{
        padding: 12px 14px !important;
    }}
    div[data-testid="stMetricLabel"] * {{
        color: var(--jzl-muted) !important;
        font-size: 12px !important;
        font-weight: 800 !important;
    }}
    div[data-testid="stMetricValue"] * {{
        color: var(--jzl-text) !important;
        font-size: 23px !important;
        font-weight: 900 !important;
    }}

    .stButton > button,
    div[data-testid="stDownloadButton"] button {{
        min-height: 38px !important;
        border-radius: 8px !important;
        border: 1px solid var(--jzl-border) !important;
        background: var(--jzl-surface-alt) !important;
        color: var(--jzl-text) !important;
        font-weight: 800 !important;
        box-shadow: none !important;
        transition: border-color 120ms ease, background-color 120ms ease, transform 120ms ease !important;
    }}
    .stButton > button:hover,
    div[data-testid="stDownloadButton"] button:hover {{
        border-color: var(--jzl-accent) !important;
        background: var(--jzl-accent-soft) !important;
        transform: translateY(-1px);
    }}
    .stButton > button[kind="primary"],
    button[kind="primary"] {{
        background: var(--jzl-accent) !important;
        border-color: var(--jzl-accent) !important;
        color: #ffffff !important;
    }}
    .stButton > button[kind="primary"] *,
    button[kind="primary"] * {{
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }}

    input,
    textarea,
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] textarea {{
        border-radius: 8px !important;
        background: var(--jzl-surface-soft) !important;
        border-color: var(--jzl-border) !important;
        color: var(--jzl-text) !important;
        box-shadow: none !important;
    }}
    div[data-testid="stTabs"] button {{
        border-radius: 8px 8px 0 0 !important;
        color: var(--jzl-muted) !important;
        font-weight: 800 !important;
    }}
    div[data-testid="stTabs"] button[aria-selected="true"] {{
        color: var(--jzl-accent) !important;
        background: var(--jzl-accent-soft) !important;
    }}
    div[data-testid="stExpander"] details {{
        border-radius: 8px !important;
        border-color: var(--jzl-border) !important;
        background: var(--jzl-surface) !important;
    }}
    div[data-testid="stAlert"] {{
        border-radius: 8px !important;
        border: 1px solid var(--jzl-border) !important;
    }}

    .jzl-table-wrap {{
        border-radius: 8px !important;
        border: 1px solid var(--jzl-border) !important;
        background: var(--jzl-surface) !important;
        box-shadow: var(--jzl-shadow);
    }}
    table.jzl-table {{
        min-width: 900px !important;
        font-size: 12px !important;
        color: var(--jzl-text) !important;
    }}
    table.jzl-table th {{
        background: {table_head_bg} !important;
        color: var(--jzl-text) !important;
        padding: 9px 10px !important;
        font-weight: 900 !important;
    }}
    table.jzl-table td {{
        padding: 8px 10px !important;
        color: var(--jzl-text) !important;
        border-bottom-color: var(--jzl-border) !important;
    }}
    table.jzl-table tr:nth-child(even) td {{
        background: {table_row_alt} !important;
    }}
    table.jzl-table tr:hover td {{
        background: var(--jzl-accent-soft) !important;
    }}

    .v3-section-title {{
        font-size: 16px !important;
        line-height: 1.35 !important;
        margin: 0 0 10px !important;
        padding-left: 10px !important;
        border-left: 3px solid var(--jzl-accent);
        color: var(--jzl-text) !important;
    }}
    hr {{
        border-color: var(--jzl-border) !important;
        margin: 1rem 0 !important;
    }}
    .element-container {{
        color: var(--jzl-text) !important;
    }}
    div[data-testid="stCodeBlock"],
    div[data-testid="stCodeBlock"] pre,
    div[data-testid="stCodeBlock"] code,
    pre,
    code {{
        background: var(--jzl-surface-soft) !important;
        color: var(--jzl-text) !important;
        border-color: var(--jzl-border) !important;
        border-radius: 8px !important;
        text-shadow: none !important;
    }}
    div[data-testid="stJson"],
    div[data-testid="stJson"] *,
    div[data-testid="stDataFrame"],
    div[data-testid="stDataFrame"] *,
    div[data-testid="stTable"],
    div[data-testid="stTable"] * {{
        background-color: transparent !important;
        color: var(--jzl-text) !important;
        border-color: var(--jzl-border) !important;
    }}
    div[data-testid="stJson"] svg,
    div[data-testid="stDataFrame"] svg {{
        fill: var(--jzl-text) !important;
        color: var(--jzl-text) !important;
    }}
    div[data-baseweb="select"] > div {{
        min-height: 38px !important;
        align-items: center !important;
        overflow: visible !important;
    }}
    div[data-baseweb="select"] div[role="button"],
    div[data-baseweb="tag"] {{
        max-width: 100% !important;
        min-height: 28px !important;
        height: auto !important;
        border-radius: 7px !important;
        background: var(--jzl-accent) !important;
        color: #ffffff !important;
        margin: 3px 4px 3px 0 !important;
        white-space: normal !important;
    }}
    div[data-baseweb="tag"] *,
    div[data-baseweb="select"] div[role="button"] * {{
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        fill: #ffffff !important;
    }}
    .jzl-history-time {{
        display: inline-flex;
        align-items: center;
        min-height: 34px;
        padding: 6px 10px;
        border-radius: 8px;
        background: var(--jzl-accent-soft);
        color: var(--jzl-accent) !important;
        font-size: 13px;
        font-weight: 900;
        border: 1px solid color-mix(in srgb, var(--jzl-accent) 32%, transparent);
        white-space: nowrap;
    }}
    .jzl-history-name {{
        font-weight: 850;
        color: var(--jzl-text) !important;
        line-height: 1.45;
        word-break: break-all;
    }}
    .jzl-history-meta {{
        color: var(--jzl-muted) !important;
        font-size: 12px;
        line-height: 1.5;
        word-break: break-all;
    }}

    @media (max-width: 1100px) {{
        .block-container {{
            padding: 0.7rem 0.85rem 1.5rem !important;
        }}
        div[data-testid="column"]:has(.jzl-left-menu-title) > div[data-testid="stVerticalBlock"] {{
            position: static !important;
            padding: 12px !important;
            margin-bottom: 10px !important;
        }}
        .jzl-app-header {{
            flex-direction: column;
            align-items: stretch;
        }}
        .jzl-app-meta {{
            text-align: left;
            min-width: 0;
        }}
        .jzl-app-title {{
            font-size: 23px;
        }}
        div[data-testid="column"] {{
            min-width: 0 !important;
        }}
        table.jzl-table {{
            min-width: 720px !important;
        }}
    }}
    </style>
    """, unsafe_allow_html=True)


def _metric_tone(value: object) -> str:
    s = str(value).strip()
    if not s or s == "--":
        return "neutral"
    if s.startswith("-") or "跌" in s or "亏" in s:
        return "negative"
    if s.startswith("+") or "涨" in s or "盈" in s:
        return "positive"
    return "neutral"


def metric_card(title: str, value: str, caption: str = "", tone: str | None = None) -> None:
    card_tone = tone or _metric_tone(value)
    if card_tone not in {"neutral", "positive", "negative", "warning"}:
        card_tone = "neutral"
    st.markdown(f"""
    <div class="metric-card metric-card--{card_tone}">
        <div class="metric-title">{html.escape(str(title))}</div>
        <div class="metric-value">{html.escape(str(value))}</div>
        <div class="metric-caption">{html.escape(str(caption))}</div>
    </div>
    """, unsafe_allow_html=True)


def show_df(df: pd.DataFrame, height: int = 400) -> None:
    if df is None or df.empty:
        st.info("暂无数据。")
        return
    out = format_df_for_display(df)
    max_rows = 500
    if len(out) > max_rows:
        st.caption(f"数据较多，仅显示前 {max_rows} 行；完整数据请用导出按钮。")
        out = out.head(max_rows)
    html_table = out.to_html(index=True, escape=True, border=0, classes="jzl-table")
    st.markdown(f"<div class='jzl-table-wrap' style='max-height:{max(160, min(int(height), 620))}px'>{html_table}</div>", unsafe_allow_html=True)
