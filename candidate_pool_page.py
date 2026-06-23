# -*- coding: utf-8 -*-
"""策略选股 / 候选池页面。"""
from __future__ import annotations
import pandas as pd
import streamlit as st
from ui_components import show_df
from market_db import get_universe_from_db, init_db
from strategy_loader import list_strategies
from stock_selector import run_stock_scoring, save_candidate_scores, load_latest_candidate_scores
from watchlist_manager import load_watchlist, add_watch

def _show_df(df: pd.DataFrame, height: int = 420):
    show_df(df, height=height)

def _options_from_universe(df: pd.DataFrame) -> dict[str, str]:
    return {} if df is None or df.empty else {str(r.code).zfill(6): str(r.name) for r in df.itertuples(index=False)}

def _label(code: str, mapping: dict[str, str]) -> str:
    code = str(code).zfill(6)[-6:]
    return f"{code} {mapping.get(code, code)}"

def _parse(label: str) -> str:
    return str(label).split()[0].zfill(6)[-6:]

def page_candidate_pool():
    init_db()
    st.subheader("策略选股 / 候选池")
    tabs = st.tabs(["① 全市场评分", "② 候选池", "③ DIY说明"])
    with tabs[0]: _page_score()
    with tabs[1]: _page_candidates()
    with tabs[2]: _page_help()

def _page_score():
    uni = get_universe_from_db()
    if uni.empty:
        st.warning("数据库中没有股票池。请先到【数据库/回测 → 行情数据库】导入 stock_universe.csv，并构建历史日K。")
        return
    mapping = _options_from_universe(uni)
    labels = [_label(c, mapping) for c in mapping.keys()]
    strategies = list_strategies()
    scoring_keys = {sid: name for sid, name in strategies.items() if "scoring" in sid or "评分" in name or "选股" in name} or {"jzl_stock_scoring_v1": "JZL全市场趋势波段评分策略"}
    trade_keys = {sid: name for sid, name in strategies.items() if "wave" in sid or "执行" in name or "趋势" in name} or {"jzl_wave_core_v1": "JZL趋势波段完整执行策略"}
    c1, c2, c3 = st.columns(3)
    with c1:
        scoring_label_map = {f"{v}｜{k}": k for k, v in scoring_keys.items()}
        scoring_id = scoring_label_map[st.selectbox("选股评分策略", list(scoring_label_map.keys()))]
    with c2:
        trade_label_map = {f"{v}｜{k}": k for k, v in trade_keys.items()}
        trade_id = trade_label_map[st.selectbox("执行策略参考", list(trade_label_map.keys()))]
    with c3:
        start_date = st.date_input("历史数据起点", value=pd.to_datetime("2021-01-01").date(), key="score_start")
    mode = st.radio("评分范围", ["自选收藏", "股票池前N只", "手动多选", "全部股票池"], horizontal=True)
    if mode == "自选收藏":
        w = load_watchlist()
        codes = [str(x).zfill(6) for x in w.get("code", pd.Series(dtype=str)).tolist()] if w is not None and not w.empty else []
        st.write(f"当前自选：{len(codes)} 只")
    elif mode == "股票池前N只":
        n = st.number_input("N", min_value=1, max_value=max(1, len(labels)), value=min(80, len(labels)), step=10)
        codes = list(mapping.keys())[:int(n)]
    elif mode == "手动多选":
        codes = [_parse(x) for x in st.multiselect("选择股票", labels, default=labels[:3])]
    else:
        codes = list(mapping.keys())
    st.write(f"计划评分：{len(codes)} 只")
    if st.button("运行策略评分并生成候选池", type="primary", width="stretch", disabled=len(codes) == 0):
        progress = st.progress(0)
        status = st.empty()
        def cb(i, total, code):
            progress.progress(i / max(1, total))
            status.info(f"{i}/{total} 正在评分 {code}")
        df = run_stock_scoring(codes, scoring_id, trade_id, str(start_date), None, progress_callback=cb)
        sid = save_candidate_scores(df)
        st.session_state["last_candidate_scores"] = df
        st.success(f"候选池已生成，快照ID：{sid}。")
    df = st.session_state.get("last_candidate_scores", pd.DataFrame())
    if df is not None and not df.empty:
        st.markdown("### 本次评分结果")
        _show_df(df, height=520)
        st.download_button("下载候选池CSV", df.to_csv(index=False, encoding="utf-8-sig"), file_name="jzl_candidate_scores.csv", mime="text/csv", width="stretch")
        topn = st.number_input("加入自选Top N", min_value=1, max_value=min(50, len(df)), value=min(10, len(df)), step=1)
        if st.button("把Top N加入收藏自选", width="stretch"):
            added = 0
            for r in df.head(int(topn)).itertuples(index=False):
                if str(getattr(r, 'candidate_level', '')) != 'reject':
                    add_watch(str(r.code).zfill(6), str(r.name), "策略候选", str(getattr(r, 'reason', '')))
                    added += 1
            st.success(f"已加入/更新 {added} 只到收藏自选。")

def _page_candidates():
    df = load_latest_candidate_scores()
    st.markdown("### 最近一次候选池")
    if df is None or df.empty:
        st.info("暂无候选池。请先运行一次全市场评分。")
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("候选总数", len(df))
    with c2: st.metric("核心候选", int((df["candidate_level"] == "core_candidate").sum()))
    with c3: st.metric("观察候选", int((df["candidate_level"] == "watch_candidate").sum()))
    with c4: st.metric("弱观察", int((df["candidate_level"] == "weak_watch").sum()))
    level = st.multiselect("筛选层级", ["core_candidate", "watch_candidate", "weak_watch", "reject"], default=["core_candidate", "watch_candidate", "weak_watch"])
    _show_df(df[df["candidate_level"].isin(level)].copy(), height=560)

def _page_help():
    st.markdown("""
### 策略选股和执行的分工

**选股评分策略**：`strategies/jzl_stock_scoring_v1.yaml`

负责从全市场或股票池中筛候选，不直接买入。可以DIY：
- `score_items`：改评分维度和权重
- `filters.must_pass`：改硬过滤
- `risk_penalty`：改风险扣分
- `candidate_level`：改候选分层阈值

**买卖执行策略**：`strategies/jzl_wave_core_v1.yaml`

负责候选股什么时候买、加、减、清。

**AI执行语言策略**：`strategies/jzl_ai_execution_v1.yaml`

负责AI怎么解释、怎么输出JSON、什么时候降低confidence。

推荐闭环：`全市场评分 → 候选池 → 自选收藏 → AI交易员持续运行 → 虚拟盘记录 → 数据库回测 → AI复盘 → 修改YAML`
""")
