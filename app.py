# -*- coding: utf-8 -*-
"""JZL证券分析：DeepSeek云端AI虚拟交易员精简版。"""
from __future__ import annotations

import html
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from charts import PLOTLY_2K_CONFIG, make_kline_chart, make_minute_chart
from config import (
    APP_NAME,
    APP_SUBTITLE,
    REPORT_DIR,
    DATA_SOURCE_RULES,
    STREAMLIT_HOST,
    STREAMLIT_PORT,
    MAX_PRECISE_SCAN,
)
from data_fetcher import get_indices_overview, get_stock_universe
from data_tencent import fetch_intraday_minute, fetch_quotes_df
from indicators import add_indicators
from reporting import export_excel, export_pdf
from scanner import cached_all_spot, cached_daily_kline, run_market_scan
from sector_analyzer import analyze_sector_strength
from trade_journal import (
    add_note,
    add_trade_record,
    closed_position_summary,
    export_notebook,
    export_trades,
    filter_records,
    load_notebook,
    load_trade_records,
    save_trade_records,
)
from ui_components import inject_css, metric_card, show_df, format_df_for_display
from watchlist_manager import add_watch, remove_watch, load_watchlist, watchlist_options
from ai_virtual_trader_page import page_ai_virtual_trader
from database_backtest_page import page_database_backtest
from candidate_pool_page import page_candidate_pool

st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide", initial_sidebar_state="collapsed")


def init_state():
    if "scan_df" not in st.session_state:
        st.session_state.scan_df = pd.DataFrame()
    if "core_df" not in st.session_state:
        st.session_state.core_df = pd.DataFrame()
    if "sector_df" not in st.session_state:
        st.session_state.sector_df = pd.DataFrame()
    if "display_mode" not in st.session_state:
        st.session_state.display_mode = "黑夜模式"
    if "selected_watch_code" not in st.session_state:
        st.session_state.selected_watch_code = ""
    if "current_page" not in st.session_state:
        st.session_state.current_page = "市场总览"


def current_mode_key() -> str:
    return "light" if st.session_state.get("display_mode") == "白天模式" else "dark"


def universe_options() -> dict[str, str]:
    try:
        u = get_stock_universe()
        if u:
            return {str(k).zfill(6): v for k, v in u.items()}
    except Exception:
        pass
    return {}


def option_label(code: str, mapping: dict[str, str]) -> str:
    return f"{code} {mapping.get(code, code)}"


def parse_code_from_label(label: str) -> str:
    return str(label).split()[0].zfill(6)[-6:]


def plot_chart(fig, key: str | None = None):
    st.plotly_chart(fig, width="stretch", config=PLOTLY_2K_CONFIG, key=key)


def apply_auto_refresh(enabled: bool, seconds: int):
    if enabled and seconds > 0:
        components.html(
            f"""
            <script>
            setTimeout(function() {{ window.parent.location.reload(); }}, {int(seconds) * 1000});
            </script>
            """,
            height=0,
        )


def render_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    page = st.session_state.get("current_page", "市场总览")
    c1, c2 = st.columns([6.6, 1.4], vertical_alignment="top")
    with c1:
        st.markdown(
            f"""
            <div class="jzl-app-header">
                <div>
                    <div class="jzl-app-kicker">JZL WORKSTATION</div>
                    <div class="jzl-app-title">{html.escape(APP_NAME)}</div>
                    <div class="jzl-app-subtitle">{html.escape(APP_SUBTITLE)}</div>
                </div>
                <div class="jzl-app-meta">
                    <div class="jzl-app-page">{html.escape(str(page))}</div>
                    <div>{now}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        if st.button("刷新数据", width="stretch"):
            st.cache_data.clear()
            st.success("已刷新。")


def render_pin_panel():
    return


def get_market_summary() -> dict:
    try:
        spot = cached_all_spot()
        up_count = int((spot["pct_chg"] > 0).sum()) if "pct_chg" in spot.columns else 0
        down_count = int((spot["pct_chg"] < 0).sum()) if "pct_chg" in spot.columns else 0
        total_amount = float(spot["amount"].sum()) if "amount" in spot.columns else 0
        return {"上涨家数": up_count, "下跌家数": down_count, "成交额": f"{total_amount / 1e8:.1f} 亿", "扫描样本": len(spot)}
    except Exception:
        return {"上涨家数": 0, "下跌家数": 0, "成交额": "--", "扫描样本": 0}


def page_market_overview():
    st.subheader("市场总览")
    summary = get_market_summary()
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("上涨家数", str(summary["上涨家数"]), "腾讯实时股票池样本")
    with c2: metric_card("下跌家数", str(summary["下跌家数"]), "腾讯实时股票池样本")
    with c3: metric_card("样本成交额", summary["成交额"], "不作为交易结论")
    with c4: metric_card("扫描样本", str(summary["扫描样本"]), "实时接口返回数")
    st.markdown("---")
    st.subheader("指数总览")
    show_df(get_indices_overview(), height=160)
    st.subheader("板块热度")
    sector_df = analyze_sector_strength()
    st.session_state.sector_df = sector_df
    show_df(sector_df.head(20), height=420)


def page_full_scan():
    st.subheader("股票实时扫描信息")
    st.warning("V3扫描范围以 stock_universe.csv 为主；腾讯实时行情用于排序补充，不再单独决定最终扫描数量。")
    c1, c2, c3 = st.columns(3)
    with c1: metric_card("精筛上限", str(MAX_PRECISE_SCAN), "config.py 可调")
    with c2: metric_card("股票池数量", str(len(universe_options())), "stock_universe.csv")
    with c3: metric_card("数据模式", "腾讯快照", "非交易所推送")
    if st.button("🚀 开始股票池扫描", type="primary", width="stretch"):
        progress = st.progress(0)
        status = st.empty()
        df = run_market_scan(progress_bar=progress, status_text=status)
        st.session_state.scan_df = df
        st.session_state.core_df = scan_core_pool()
        st.session_state.sector_df = analyze_sector_strength()
        status.success("扫描完成。")

    df = st.session_state.scan_df
    if df is not None and not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        with c1: metric_card("候选数量", str(len(df)), "通过基础技术评分")
        with c2: metric_card("可加仓", str((df["suggestion"] == "可加仓").sum()), "≥75分")
        with c3: metric_card("可试仓", str((df["suggestion"] == "可试仓").sum()), "55~74分")
        with c4: metric_card("回踩票", str(df["is_pullback"].sum()), "缩量靠近MA10/20")
        show_df(df, height=560)
        st.markdown("### 导出报告")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("导出 Excel", width="stretch"):
                st.success(f"Excel已生成：{export_excel(st.session_state.scan_df, st.session_state.core_df, st.session_state.sector_df)}")
        with col2:
            if st.button("导出 PDF", width="stretch"):
                st.success(f"PDF已生成：{export_pdf(st.session_state.scan_df, st.session_state.core_df, st.session_state.sector_df, get_market_summary())}")
        for p in sorted(REPORT_DIR.glob("*")):
            with open(p, "rb") as f:
                st.download_button(f"下载 {p.name}", f, file_name=p.name, width="stretch")
    else:
        st.info("尚未扫描。点击上方按钮开始。")



def page_professional_chart():
    st.subheader("专业K线 / 分时")
    mapping = universe_options()
    watch_map = watchlist_options(mapping)
    source = st.radio("股票来源", ["自选收藏", "完整股票池"], horizontal=True, index=0)
    source_map = watch_map if source == "自选收藏" and watch_map else mapping
    labels = [option_label(c, source_map) for c in source_map.keys()]
    if not labels:
        st.warning("暂无可选股票，请先到【自选收藏】添加。")
        return
    default_code = "603876" if "603876" in source_map else list(source_map.keys())[0]
    default_idx = labels.index(option_label(default_code, source_map)) if default_code in source_map else 0
    selected_label = st.selectbox("选择单只股票", labels, index=default_idx)
    code = parse_code_from_label(selected_label)
    name = mapping.get(code, source_map.get(code, code))
    fav1, fav2 = st.columns([1, 3])
    with fav1:
        if st.button("⭐ 加入/更新自选", width="stretch"):
            add_watch(code, name, group="自选", note="从K线页添加")
            st.success(f"已加入自选：{code} {name}")

    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.4])
    with c1:
        k_range = st.selectbox("K线显示范围", ["最近120日", "最近180日", "最近260日", "全部历史"], index=1)
    with c2:
        minute_period = st.selectbox("分时周期", ["1", "5", "15", "30", "60"], index=0)
    with c3:
        auto = st.checkbox("自动刷新分时", value=False)
    with c4:
        interval = st.selectbox("刷新间隔", [20, 30, 60], index=0, format_func=lambda x: f"{x}秒")
    apply_auto_refresh(auto, interval)

    k = add_indicators(cached_daily_kline(code))
    if not k.empty and k_range != "全部历史":
        n = int(k_range.replace("最近", "").replace("日", ""))
        k = k.tail(n)
    trades = filter_records(load_trade_records(), code=code)
    plot_chart(make_kline_chart(k, f"{code} {name} 专业日K图", trades=trades, mode=current_mode_key(), height=940), key=f"pro_k_{code}_{k_range}")

    q = fetch_quotes_df([code])
    if q is not None and not q.empty:
        qr = q.iloc[0].to_dict()
        q1, q2, q3, q4, q5 = st.columns(5)
        with q1: metric_card("当前价", str(qr.get("price", "--")), str(qr.get("update_time", "--")))
        with q2: metric_card("涨跌幅", f"{qr.get('pct_change', '--')}%", "腾讯快照")
        with q3: metric_card("最高", str(qr.get("high", "--")), "日内")
        with q4: metric_card("最低", str(qr.get("low", "--")), "日内")
        with q5: metric_card("成交额", f"{qr.get('amount_yi', '--')} 亿", "约值")

    minute = fetch_intraday_minute(code, minute_period)
    plot_chart(make_minute_chart(minute, f"{code} {name} {minute_period}分钟分时图", mode=current_mode_key(), height=600), key=f"pro_m_{code}_{minute_period}")


def page_multi_minute_watch():
    st.subheader("分时拼盘")
    mapping = universe_options()
    labels = [option_label(c, mapping) for c in mapping.keys()]
    watch_map = watchlist_options(mapping)
    default_codes = list(watch_map.keys())[:5] if watch_map else []
    default_labels = [option_label(c, mapping) for c in default_codes]
    selected = st.multiselect("选择最多5只股票，建议先在【收藏自选】添加", labels, default=default_labels)
    if len(selected) > 5:
        st.warning("最多同时查看5只，系统已自动截取前5只。")
        selected = selected[:5]
    c1, c2 = st.columns(2)
    with c1:
        auto = st.checkbox("20秒自动刷新", value=False)
    with c2:
        period = st.selectbox("分钟周期", ["1", "5", "15"], index=0)
    apply_auto_refresh(auto, 20)
    if not selected:
        st.info("请选择股票。")
        return
    codes = [parse_code_from_label(x) for x in selected]
    q = fetch_quotes_df(codes)
    if q is not None and not q.empty:
        show_df(q[["code", "name", "price", "pct_change", "amount_yi", "high", "low", "update_time"]], height=180)
    cols = st.columns(2)
    for idx, code in enumerate(codes):
        name = mapping.get(code, code)
        with cols[idx % 2]:
            minute = fetch_intraday_minute(code, period)
            plot_chart(make_minute_chart(minute, f"{code} {name} {period}分钟分时", mode=current_mode_key(), height=460), key=f"multi_m_{code}_{period}_{idx}")


def page_trade_points():
    st.subheader("买卖点复盘")
    mapping = universe_options()
    labels = [option_label(c, mapping) for c in mapping.keys()]
    left, right = st.columns([0.92, 2.08])

    with left:
        st.markdown("<div class='v3-section-title'>📒 买卖点录入</div>", unsafe_allow_html=True)
        selected_label = st.selectbox("股票", labels, index=0, key="trade_stock")
        code = parse_code_from_label(selected_label)
        name = mapping.get(code, code)
        trade_date = st.date_input("日期", value=datetime.now().date())
        side = st.radio("方向", ["买入", "卖出"], horizontal=True)
        action_type = st.selectbox("操作类型", ["建仓", "加仓", "接回", "减仓", "清仓", "止损", "止盈", "其他"])
        price = st.number_input("成交价", min_value=0.0, value=0.0, step=0.01, format="%.3f")
        volume = st.number_input("数量/股", min_value=0, value=100, step=100)
        status_default = "已清仓" if action_type == "清仓" else "持仓中"
        status = st.selectbox("状态", ["持仓中", "已清仓"], index=1 if status_default == "已清仓" else 0)
        reason = st.text_input("当时理由", placeholder="例如：突破、回踩、压力位止盈、破位降仓")
        note = st.text_area("交易本子", height=120, placeholder="把你和我复盘后的内容、当时盘面、心态、执行情况写在这里。")
        if st.button("保存买卖点", type="primary", width="stretch"):
            if price <= 0 or volume <= 0:
                st.error("价格和数量必须大于0。")
            else:
                add_trade_record(trade_date, code, name, side, action_type, price, volume, reason, note, status)
                st.cache_data.clear()
                st.success("已保存到 trade_records.csv。")
                st.rerun()

    with right:
        st.markdown("<div class='v3-section-title'>📈 日K + B/S点</div>", unsafe_allow_html=True)
        selected_code = parse_code_from_label(st.session_state.get("trade_stock", labels[0])) if labels else "603876"
        selected_name = mapping.get(selected_code, selected_code)
        trades_all = load_trade_records()
        trades = filter_records(trades_all, code=selected_code)
        k = add_indicators(cached_daily_kline(selected_code))
        view_mode = st.radio("显示范围", ["交易日前后60日", "最近120日", "最近260日", "全部历史"], horizontal=True)
        if not k.empty:
            if view_mode == "最近120日":
                k = k.tail(120)
            elif view_mode == "最近260日":
                k = k.tail(260)
            elif view_mode == "交易日前后60日" and trades is not None and not trades.empty:
                start = trades["date"].min() - pd.Timedelta(days=90)
                end = trades["date"].max() + pd.Timedelta(days=90)
                k = k[(k["date"] >= start) & (k["date"] <= end)]
        plot_chart(make_kline_chart(k, f"{selected_code} {selected_name} 买卖点复盘图", trades=trades, mode=current_mode_key(), height=860), key=f"trade_k_{selected_code}_{view_mode}")
        st.caption("图表右上角相机按钮可导出2K高清PNG；已关闭滚轮误缩放，使用工具栏缩放/平移更稳定。")

    st.markdown("---")
    st.markdown("### 交易记录")
    records = load_trade_records()
    if records.empty:
        st.info("暂无买卖点记录。")
    else:
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            q_code = st.text_input("按代码查询", value="")
        with f2:
            q_status = st.selectbox("状态", ["全部", "持仓中", "已清仓"])
        with f3:
            q_start = st.date_input("开始日期", value=(datetime.now() - timedelta(days=365)).date())
        with f4:
            q_end = st.date_input("结束日期", value=datetime.now().date())
        fdf = filter_records(records, code=q_code if q_code else None, start_date=q_start, end_date=q_end, status=q_status)
        show_df(fdf, height=330)
        st.markdown("#### 记录维护")
        if not fdf.empty:
            delete_options = {
                f"{r.get('date').strftime('%Y-%m-%d') if hasattr(r.get('date'), 'strftime') else r.get('date')}｜{r.get('code')}｜{r.get('name')}｜{r.get('side')}｜{r.get('action_type')}｜{r.get('price')}｜{r.get('id')}": r.get('id')
                for _, r in fdf.iterrows()
            }
            del_label = st.selectbox("选择要删除的记录", list(delete_options.keys()))
            if st.button("删除选中记录", width="stretch"):
                del_id = delete_options[del_label]
                new_df = records[records["id"].astype(str) != str(del_id)].copy()
                save_trade_records(new_df)
                st.success("已删除。")
                st.rerun()
        e1, e2 = st.columns(2)
        with e1:
            if st.button("导出买卖点 Excel", width="stretch"):
                path = export_trades(records, fmt="xlsx")
                st.success(f"已生成：{path}")
        with e2:
            if st.button("导出买卖点 CSV", width="stretch"):
                path = export_trades(records, fmt="csv")
                st.success(f"已生成：{path}")
        for p in sorted(Path("output").glob("trade_records_export_*"), reverse=True):
            with open(p, "rb") as f:
                st.download_button(f"下载 {p.name}", f, file_name=p.name, width="stretch")

    st.markdown("### 已清仓股票 / 粗略收益率")
    closed = closed_position_summary(load_trade_records())
    if closed.empty:
        st.info("暂无已清仓记录。清仓收益率只做粗略计算，不含印花税、佣金、滑点。")
    else:
        show_df(closed, height=260)
        st.caption("粗略收益率 = 清仓卖出均价 ÷ 买入均价 - 1；不含印花税、佣金、过户费、分批仓位误差。")


def page_trade_notebook():
    st.subheader("交易本子")
    st.caption("这里不是自动评分区，只用于保存你和我复盘后的文字、交易想法、阶段总结。")
    mapping = universe_options()
    labels = ["无关联股票"] + [option_label(c, mapping) for c in mapping.keys()]
    c1, c2 = st.columns([0.9, 2.1])
    with c1:
        st.markdown("### 新增本子记录")
        note_date = st.date_input("记录日期", value=datetime.now().date(), key="note_date")
        n_label = st.selectbox("关联股票", labels, key="note_stock")
        if n_label == "无关联股票":
            code, name = "", ""
        else:
            code = parse_code_from_label(n_label)
            name = mapping.get(code, code)
        title = st.text_input("标题", placeholder="例如：某只股票清仓复盘")
        tags = st.text_input("标签", placeholder="例如：清仓/卖飞/纪律/回踩")
        content = st.text_area("本子内容", height=260, placeholder="把我们复盘后的结论、你自己的想法、后续规则写在这里。")
        if st.button("保存到交易本子", type="primary", width="stretch"):
            if not content.strip():
                st.error("本子内容不能为空。")
            else:
                add_note(note_date, code, name, title or "交易笔记", content, tags)
                st.success("已保存。")
                st.rerun()
    with c2:
        notes = load_notebook()
        st.markdown("### 查询本子")
        if notes.empty:
            st.info("暂无本子记录。")
            return
        f1, f2, f3 = st.columns(3)
        with f1:
            keyword = st.text_input("关键词", placeholder="标题/内容/标签")
        with f2:
            n_start = st.date_input("起始日期", value=(datetime.now() - timedelta(days=365)).date(), key="n_start")
        with f3:
            n_end = st.date_input("结束日期", value=datetime.now().date(), key="n_end")
        out = notes[(notes["date"] >= pd.to_datetime(n_start)) & (notes["date"] <= pd.to_datetime(n_end))]
        if keyword:
            mask = out[["title", "content", "tags", "code", "name"]].astype(str).apply(lambda s: s.str.contains(keyword, case=False, na=False)).any(axis=1)
            out = out[mask]
        show_df(out, height=520)
        if st.button("导出交易本子 Excel", width="stretch"):
            path = export_notebook(out)
            st.success(f"已生成：{path}")


def page_pools(pool_name: str):
    st.subheader(pool_name)
    df = st.session_state.scan_df
    if df is None or df.empty:
        st.info("请先在【腾讯股票池扫描】页面运行扫描。")
        return
    show_df(classify_pools(df).get(pool_name, pd.DataFrame()), height=560)




def _history_category(path: Path) -> str:
    name = path.name.lower()
    parent = str(path.parent).lower()
    if "ai_auto_worker" in name or "heartbeat" in name or "auto_trader_state" in name:
        return "后台守护"
    if "ai_decision" in name:
        return "AI决策日志"
    if name.startswith("paper_") or "paper_trades" in name or "paper_positions" in name:
        return "虚拟盘记录"
    if "trade_records" in name or "trade_notebook" in name:
        return "复盘记录"
    if "reports" in parent or "report" in name or path.suffix.lower() in {".pdf", ".xlsx"}:
        return "扫描报告"
    if "output" in parent:
        return "导出文件"
    if "logs" in parent or path.suffix.lower() in {".log"}:
        return "系统日志"
    if path.suffix.lower() == ".json":
        return "状态文件"
    return "其他"


def _format_file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _collect_history_files() -> list[dict]:
    roots = [REPORT_DIR, Path("output"), Path("logs"), Path("data")]
    root_files = [
        Path("ai_decision_log.csv"),
        Path("paper_positions.csv"),
        Path("paper_trades.csv"),
        Path("trade_records.csv"),
        Path("trade_notebook.csv"),
    ]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend([p for p in root.glob("*") if p.is_file()])
    paths.extend([p for p in root_files if p.exists() and p.is_file()])

    seen: set[str] = set()
    rows: list[dict] = []
    for p in paths:
        if p.suffix.lower() in {".tmp", ".sqlite", ".db", ".pyc"}:
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            stat = p.stat()
        except OSError:
            continue
        rows.append({
            "path": p,
            "name": p.name,
            "category": _history_category(p),
            "mtime": datetime.fromtimestamp(stat.st_mtime),
            "size": stat.st_size,
        })
    return sorted(rows, key=lambda x: x["mtime"], reverse=True)


def page_history():
    st.subheader("历史记录")
    files = _collect_history_files()
    if not files:
        st.info("暂无历史报告。")
        return

    categories = ["全部", "扫描报告", "AI决策日志", "后台守护", "虚拟盘记录", "复盘记录", "导出文件", "系统日志", "状态文件", "其他"]
    counts = {cat: sum(1 for x in files if cat == "全部" or x["category"] == cat) for cat in categories}
    labels = [f"{cat} · {counts[cat]}" for cat in categories if counts[cat] > 0]
    selected_label = st.radio("历史小目录", labels, horizontal=True, label_visibility="collapsed")
    selected_cat = selected_label.split(" · ")[0]
    view = [x for x in files if selected_cat == "全部" or x["category"] == selected_cat]

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("当前分类", selected_cat, f"{len(view)} 个文件")
    with c2:
        metric_card("最新时间", view[0]["mtime"].strftime("%Y-%m-%d %H:%M:%S"), view[0]["name"])
    with c3:
        metric_card("总文件数", str(len(files)), "报告 / 日志 / 导出")

    for item in view:
        p = item["path"]
        mtime = item["mtime"].strftime("%Y-%m-%d %H:%M:%S")
        row_time, row_info, row_action = st.columns([1.15, 3.3, 1.1], vertical_alignment="center")
        with row_time:
            st.markdown(f"<div class='jzl-history-time'>{html.escape(mtime)}</div>", unsafe_allow_html=True)
        with row_info:
            st.markdown(
                f"<div class='jzl-history-name'>{html.escape(item['name'])}</div>"
                f"<div class='jzl-history-meta'>{html.escape(item['category'])} · {_format_file_size(item['size'])} · {html.escape(str(p))}</div>",
                unsafe_allow_html=True,
            )
        with row_action:
            with open(p, "rb") as f:
                st.download_button("下载", f, file_name=p.name, width="stretch", key=f"hist_{str(p.resolve())}")


def page_settings():
    st.subheader("设置中心")
    st.markdown("### 本地端口")
    st.code(f"http://{STREAMLIT_HOST}:{STREAMLIT_PORT}", language="text")
    st.caption("端口由 .streamlit/config.toml 控制；如8501被占用，可改成8502。")
    st.markdown("### 数据源分工")
    show_df(pd.DataFrame([{"场景": k, "接口分配": v} for k, v in DATA_SOURCE_RULES.items()]), height=220)
    st.markdown("### 腾讯接口连通性测试")
    if st.button("测试自选/样本实时行情", width="stretch"):
        mapping = universe_options()
        watch_map = watchlist_options(mapping)
        sample_codes = list(watch_map.keys())[:5] if watch_map else list(mapping.keys())[:5]
        if not sample_codes:
            st.warning("当前没有自选或股票池样本，请先导入股票池或添加自选。")
        else:
            rt = fetch_quotes_df(sample_codes)
            if rt is not None and not rt.empty:
                st.success("腾讯实时接口可用。")
                show_df(rt[["code", "name", "price", "pct_change", "amount_yi", "update_time"]], height=180)
            else:
                st.error("腾讯实时接口暂不可用。检查网络、代理、交易时段或接口稳定性。")
    st.markdown("### AI接口")
    st.write("默认使用 DeepSeek：读取 DEEPSEEK_API_KEY。OpenAI / ChatGPT API 已预留：读取 OPENAI_API_KEY。")
    st.markdown("### 策略文件位置")
    st.code(r"E:\jzl\证券分析\JZL证券分析\strategies\jzl_wave_core_v1.yaml", language="text")
    st.caption("策略硬规则在 YAML 中修改；AI输出JSON字段在 ai_agent.py 的 build_ai_prompt 中修改。")
    st.warning("JZL证券分析只做纸面模拟，不连接券商，不真实下单；AI动作必须经过代码审计器。")



def render_single_stock_dashboard(code: str, name: str, mapping: dict[str, str]):
    """自选股票单股主页：日K、实时行情、分时直接展示。"""
    if not code:
        return
    st.markdown(f"### {code} {name} 单股主页")
    c1, c2, c3 = st.columns([1.1, 1.1, 1.2])
    with c1:
        k_range = st.selectbox("日K范围", ["最近120日", "最近180日", "最近260日", "全部历史"], index=1, key=f"wl_k_range_{code}")
    with c2:
        minute_period = st.selectbox("分时周期", ["1", "5", "15", "30", "60"], index=0, key=f"wl_minute_{code}")
    with c3:
        auto = st.checkbox("自动刷新分时", value=False, key=f"wl_auto_{code}")
    apply_auto_refresh(auto, 20)

    q = fetch_quotes_df([code])
    if q is not None and not q.empty:
        qr = q.iloc[0].to_dict()
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1: metric_card("当前价", str(qr.get("price", "--")), str(qr.get("update_time", "--")))
        with m2: metric_card("涨跌幅", f"{qr.get('pct_change', '--')}%", "腾讯快照")
        with m3: metric_card("最高", str(qr.get("high", "--")), "日内")
        with m4: metric_card("最低", str(qr.get("low", "--")), "日内")
        with m5: metric_card("成交额", f"{qr.get('amount_yi', '--')} 亿", "约值")

    k = add_indicators(cached_daily_kline(code))
    if not k.empty and k_range != "全部历史":
        n = int(k_range.replace("最近", "").replace("日", ""))
        k = k.tail(n)
    trades = filter_records(load_trade_records(), code=code)
    plot_chart(make_kline_chart(k, f"{code} {name} 日K与B/S点", trades=trades, mode=current_mode_key(), height=760), key=f"wl_k_{code}_{k_range}_{current_mode_key()}")

    minute = fetch_intraday_minute(code, minute_period)
    plot_chart(make_minute_chart(minute, f"{code} {name} {minute_period}分钟分时", mode=current_mode_key(), height=480), key=f"wl_m_{code}_{minute_period}_{current_mode_key()}")



def page_watchlist():
    st.subheader("收藏自选")
    mapping = universe_options()
    left, right = st.columns([0.72, 2.28])
    with left:
        st.markdown("### 添加 / 更新")
        raw_code = st.text_input("股票代码", value="", max_chars=6, placeholder="例如：603876").strip()
        code = raw_code.zfill(6)[-6:] if raw_code else ""
        name = st.text_input("股票名称", value=mapping.get(code, "") if code else "")
        group = st.text_input("分组", value="自选")
        note = st.text_area("备注", height=80, placeholder="例如：回踩观察/有色/AI硬件")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("保存", type="primary", width="stretch"):
                if not code:
                    st.error("请先输入股票代码。")
                else:
                    add_watch(code, name or mapping.get(code, code), group, note)
                    st.session_state.selected_watch_code = code
                    st.success("已保存。")
                    st.rerun()
        with c2:
            if st.button("删除", width="stretch") and code:
                remove_watch(code)
                if st.session_state.get("selected_watch_code") == code:
                    st.session_state.selected_watch_code = ""
                st.warning("已删除。")
                st.rerun()

        st.markdown("### 当前自选")
        wdf = load_watchlist()
        if wdf.empty:
            st.info("暂无自选。")
        else:
            for _, r in wdf.iterrows():
                c = str(r.get("code", "")).zfill(6)[-6:]
                n = str(r.get("name", "")) or mapping.get(c, c)
                if st.button(f"{c}  {n}", key=f"watch_open_{c}", width="stretch"):
                    st.session_state.selected_watch_code = c
                    st.rerun()

    with right:
        selected_code = st.session_state.get("selected_watch_code")
        wmap = watchlist_options(mapping)
        if not selected_code and wmap:
            selected_code = list(wmap.keys())[0]
            st.session_state.selected_watch_code = selected_code
        if selected_code:
            selected_name = mapping.get(selected_code, wmap.get(selected_code, selected_code))
            render_single_stock_dashboard(selected_code, selected_name, mapping)
        else:
            st.info("点击左侧自选股票后，这里会直接显示该股票的日K、B/S点和分时。")


def page_review():
    st.subheader("复盘")
    tab1, tab2 = st.tabs(["买卖点复盘", "交易本子"])
    with tab1:
        page_trade_points()
    with tab2:
        page_trade_notebook()


PAGES = [
    "市场总览",
    "股票实时扫描信息",
    "策略选股",
    "收藏自选",
    "分时拼盘",
    "复盘",
    "AI交易员",
    "数据库/回测",
    "历史记录",
    "设置",
]


def render_left_menu() -> str:
    """内置左侧菜单：不再依赖 Streamlit 官方 st.sidebar。

    官方侧边栏收起状态会被浏览器缓存；部分 Streamlit 版本里展开按钮也可能被主题样式影响。
    因此从 v3.9.9 开始，导航菜单放在主页面左列，刷新/缓存/收起状态都不会导致菜单消失。
    """
    st.markdown("<div class='jzl-left-menu-title'>JZL 工作台</div>", unsafe_allow_html=True)
    st.markdown("<div class='jzl-left-menu-subtitle'>主题</div>", unsafe_allow_html=True)
    st.radio(
        "主题",
        ["黑夜模式", "白天模式"],
        key="display_mode",
        label_visibility="collapsed",
    )
    st.markdown("<div class='jzl-left-menu-subtitle'>模块</div>", unsafe_allow_html=True)
    page = st.radio(
        "功能",
        PAGES,
        key="current_page",
        label_visibility="collapsed",
    )
    return page


def route_page(page: str) -> None:
    if page == "市场总览":
        page_market_overview()
    elif page == "股票实时扫描信息":
        page_full_scan()
    elif page == "策略选股":
        page_candidate_pool()
    elif page == "收藏自选":
        page_watchlist()
    elif page == "分时拼盘":
        page_multi_minute_watch()
    elif page == "复盘":
        page_review()
    elif page == "AI交易员":
        page_ai_virtual_trader(universe_options_func=universe_options, option_label_func=option_label, parse_code_func=parse_code_from_label)
    elif page == "数据库/回测":
        page_database_backtest()
    elif page == "历史记录":
        page_history()
    elif page == "设置":
        page_settings()
    else:
        st.session_state.current_page = "市场总览"
        page_market_overview()


def main():
    init_state()
    inject_css(current_mode_key(), False)

    left_col, content_col = st.columns([0.17, 0.83], gap="medium")
    with left_col:
        page = render_left_menu()
    with content_col:
        render_header()
        route_page(page)


if __name__ == "__main__":
    main()
