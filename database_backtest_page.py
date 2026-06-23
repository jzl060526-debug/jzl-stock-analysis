# -*- coding: utf-8 -*-
"""Streamlit页面：行情数据库 / 历史回测。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ai_agent import call_ai_json, build_ai_prompt, check_api_key, PROVIDER_DEEPSEEK, PROVIDER_OPENAI
from backtester import BacktestConfig, run_single_stock_backtest, save_backtest_run
from market_db import (
    DB_PATH,
    UNIVERSE_CSV,
    build_history_for_codes,
    db_stats,
    get_daily_bars,
    get_universe_from_db,
    import_universe_to_db,
    init_db,
    load_stock_universe,
    update_latest_for_codes,
)
from strategy_loader import list_strategies, load_strategy
from watchlist_manager import load_watchlist
from ui_components import show_df


def _show_df(df: pd.DataFrame, height: int = 360):
    show_df(df, height=height)


def _options_from_universe(df: pd.DataFrame) -> dict[str, str]:
    if df is None or df.empty:
        return {}
    return {str(r.code).zfill(6): str(r.name) for r in df.itertuples(index=False)}


def _label(code: str, mapping: dict[str, str]) -> str:
    code = str(code).zfill(6)[-6:]
    return f"{code} {mapping.get(code, code)}"


def _parse(label: str) -> str:
    return str(label).split()[0].zfill(6)[-6:]


def page_database_backtest():
    st.subheader("行情数据库 / 策略回测")

    tabs = st.tabs(["① 行情数据库", "② 策略回测", "③ AI回测复盘", "④ 使用说明"])
    with tabs[0]:
        _page_database()
    with tabs[1]:
        _page_backtest()
    with tabs[2]:
        _page_ai_review()
    with tabs[3]:
        _page_help()


def _page_database():
    init_db()
    st.markdown("### 本地行情数据库")
    stats = db_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("股票池", stats.get("stock_count", 0))
    with c2: st.metric("已覆盖股票", stats.get("covered_stocks", 0))
    with c3: st.metric("日K记录", stats.get("bar_count", 0))
    with c4: st.metric("最早日期", stats.get("min_date") or "--")
    with c5: st.metric("最新日期", stats.get("max_date") or "--")
    st.code(str(DB_PATH), language="text")

    st.markdown("### 股票池导入")
    st.caption("默认读取项目根目录 stock_universe.csv。你刚给的表格已放入这个文件，共约536只股票。")
    local_uni = load_stock_universe(UNIVERSE_CSV)
    st.write(f"当前 stock_universe.csv 股票数：{len(local_uni)}")
    if st.button("导入 / 更新股票池到数据库", type="primary", width="stretch"):
        n = import_universe_to_db(UNIVERSE_CSV)
        st.success(f"已导入/更新 {n} 只股票到数据库。")
        st.rerun()
    with st.expander("预览股票池", expanded=False):
        _show_df(local_uni.head(100), height=320)

    st.markdown("---")
    st.markdown("### 扫描历史行情并生成数据库")
    st.warning("批量抓 2021年至今 的历史日K会访问腾讯免费接口。536只股票可能需要几分钟，运行期间不要关闭窗口。")
    uni_db = get_universe_from_db()
    if uni_db.empty:
        st.info("请先导入股票池到数据库。")
        return
    mapping = _options_from_universe(uni_db)
    labels = [_label(c, mapping) for c in mapping.keys()]

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("起始日期", value=pd.to_datetime("2021-01-01").date(), key="db_start")
    with col2:
        end_date = st.date_input("结束日期", value=datetime.now().date(), key="db_end")
    with col3:
        sleep_s = st.number_input("接口间隔/秒", min_value=0.0, max_value=2.0, value=0.12, step=0.02)

    mode = st.radio("更新范围", ["自选收藏", "手动选择", "股票池前N只", "全部股票池"], horizontal=True)
    codes: list[str] = []
    if mode == "自选收藏":
        w = load_watchlist()
        codes = [str(x).zfill(6) for x in w.get("code", pd.Series(dtype=str)).tolist()] if w is not None and not w.empty else []
        st.write(f"当前自选收藏：{len(codes)} 只")
    elif mode == "手动选择":
        selected = st.multiselect("选择要更新的股票", labels, default=labels[:3])
        codes = [_parse(x) for x in selected]
    elif mode == "股票池前N只":
        n = st.number_input("N", min_value=1, max_value=max(1, len(labels)), value=min(30, len(labels)), step=1)
        codes = list(mapping.keys())[:int(n)]
    else:
        codes = list(mapping.keys())

    st.write(f"本次计划更新：{len(codes)} 只")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("开始构建历史数据库", type="primary", width="stretch", disabled=len(codes) == 0):
            progress = st.progress(0)
            status = st.empty()
            def cb(i, total, code, bars):
                progress.progress(i / max(1, total))
                status.info(f"{i}/{total} 正在处理 {code}，累计写入/覆盖 {bars} 条日K")
            res = build_history_for_codes(codes, str(start_date), str(end_date), sleep_seconds=float(sleep_s), progress_callback=cb)
            st.success(f"完成：成功{res['ok']}，失败{res['fail']}，写入/覆盖日K {res['bars']} 条。")
            if res.get("errors"):
                st.warning("部分错误预览：")
                st.write(res["errors"])
            st.rerun()
    with b2:
        if st.button("增量更新最新行情", width="stretch", disabled=len(codes) == 0):
            progress = st.progress(0)
            status = st.empty()
            def cb(i, total, code, bars):
                progress.progress(i / max(1, total))
                status.info(f"{i}/{total} 正在增量更新 {code}，累计写入/覆盖 {bars} 条日K")
            res = update_latest_for_codes(codes, sleep_seconds=float(sleep_s), progress_callback=cb)
            st.success(f"完成：成功{res['ok']}，失败{res['fail']}，写入/覆盖日K {res['bars']} 条。")
            if res.get("errors"):
                st.warning("部分错误预览：")
                st.write(res["errors"])
            st.rerun()

    st.markdown("### 单股数据库检查")
    if labels:
        label = st.selectbox("查看某只股票日K", labels, index=0)
        code = _parse(label)
        df = get_daily_bars(code).tail(260)
        _show_df(df, height=300)


def _page_backtest():
    init_db()
    st.markdown("### 策略历史回测")
    uni = get_universe_from_db()
    if uni.empty:
        st.warning("数据库中没有股票池。请先到【行情数据库】导入股票池并构建历史日K。")
        return
    mapping = _options_from_universe(uni)
    labels = [_label(c, mapping) for c in mapping.keys()]
    strategies = list_strategies()
    if not strategies:
        st.error("未找到策略文件。")
        return

    # 回测只允许选择买卖执行策略；选股评分/AI语言策略不参与逐日交易。
    if isinstance(strategies, dict):
        strategies = {sid: name for sid, name in strategies.items() if ("wave" in sid or "core" in sid or "执行" in name or "趋势波段" in name)}
        strategy_label_map = {f"{name}｜{sid}": sid for sid, name in strategies.items()}
    else:
        strategy_label_map = {
            f"{x.get('strategy_name', x.get('strategy_id'))}｜{x.get('strategy_id')}": x.get("strategy_id")
            for x in strategies
            if isinstance(x, dict) and ("wave" in str(x.get("strategy_id")) or "core" in str(x.get("strategy_id")) or "执行" in str(x.get("strategy_name")) or "趋势波段" in str(x.get("strategy_name")))
        }

    c1, c2, c3 = st.columns(3)
    with c1:
        strategy_label = st.selectbox("选择策略", list(strategy_label_map.keys()))
        strategy_id = strategy_label_map[strategy_label]
    with c2:
        start_date = st.date_input("开始日期", value=pd.to_datetime("2021-01-01").date(), key="bt_start")
    with c3:
        end_date = st.date_input("结束日期", value=datetime.now().date(), key="bt_end")

    c4, c5, c6, c7 = st.columns(4)
    with c4:
        initial_cash = st.number_input("初始资金", min_value=1000.0, value=100000.0, step=10000.0)
    with c5:
        fee_rate = st.number_input("手续费率", min_value=0.0, max_value=0.01, value=0.0003, step=0.0001, format="%.4f")
    with c6:
        slippage = st.number_input("滑点比例", min_value=0.0, max_value=0.02, value=0.0, step=0.0005, format="%.4f")
    with c7:
        max_add_times = st.number_input("最多加仓次数", min_value=0, max_value=10, value=2, step=1)

    mode = st.radio("回测范围", ["单只股票", "自选收藏批量", "手动多选"], horizontal=True)
    selected_codes: list[str] = []
    if mode == "单只股票":
        selected_label = st.selectbox("股票", labels, index=0)
        selected_codes = [_parse(selected_label)]
    elif mode == "自选收藏批量":
        w = load_watchlist()
        selected_codes = [str(x).zfill(6) for x in w.get("code", pd.Series(dtype=str)).tolist()] if w is not None and not w.empty else []
        st.write(f"自选股票：{len(selected_codes)} 只")
    else:
        selected = st.multiselect("选择股票", labels, default=labels[:3])
        selected_codes = [_parse(x) for x in selected]

    if st.button("运行脚本历史回测", type="primary", width="stretch", disabled=len(selected_codes) == 0):
        strategy = load_strategy(strategy_id)
        cfg = BacktestConfig(
            initial_cash=float(initial_cash),
            start_date=str(start_date),
            end_date=str(end_date),
            fee_rate=float(fee_rate),
            slippage_pct=float(slippage),
            max_add_times=int(max_add_times),
        )
        all_metrics = []
        all_trades = []
        last_equity = pd.DataFrame()
        progress = st.progress(0)
        status = st.empty()
        for i, code in enumerate(selected_codes, start=1):
            progress.progress(i / max(1, len(selected_codes)))
            status.info(f"{i}/{len(selected_codes)} 回测 {code} {mapping.get(code, code)}")
            res = run_single_stock_backtest(code, mapping.get(code, code), strategy, cfg)
            if res.get("error"):
                all_metrics.append({"code": code, "name": mapping.get(code, code), "error": res["error"]})
                continue
            met = res["metrics"].copy()
            met.update({"code": code, "name": mapping.get(code, code)})
            all_metrics.append(met)
            tr = res["trades"]
            if tr is not None and not tr.empty:
                all_trades.append(tr)
            last_equity = res["equity"]
            # 只保存单股回测 run；批量结果另导出CSV
            try:
                save_backtest_run(strategy_id, [code], cfg, res)
            except Exception:
                pass
        metrics_df = pd.DataFrame(all_metrics)
        trades_df = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
        st.session_state["last_backtest_metrics"] = metrics_df
        st.session_state["last_backtest_trades"] = trades_df
        st.session_state["last_backtest_equity"] = last_equity
        st.session_state["last_backtest_strategy_id"] = strategy_id
        status.success("回测完成。")

    metrics_df = st.session_state.get("last_backtest_metrics", pd.DataFrame())
    trades_df = st.session_state.get("last_backtest_trades", pd.DataFrame())
    equity_df = st.session_state.get("last_backtest_equity", pd.DataFrame())

    if metrics_df is not None and not metrics_df.empty:
        st.markdown("### 回测指标")
        _show_df(metrics_df, height=320)
        csv = metrics_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("下载回测指标CSV", csv, file_name="jzl_backtest_metrics.csv", mime="text/csv", width="stretch")
    if trades_df is not None and not trades_df.empty:
        st.markdown("### 交易明细")
        _show_df(trades_df, height=360)
        csv = trades_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("下载交易明细CSV", csv, file_name="jzl_backtest_trades.csv", mime="text/csv", width="stretch")
    if equity_df is not None and not equity_df.empty:
        st.markdown("### 单股资金曲线预览")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=equity_df["date"], y=equity_df["equity"], mode="lines", name="资金曲线", line=dict(width=2.4, shape="spline", smoothing=0.45)))
        is_light = st.session_state.get("display_mode") == "白天模式"
        fig.update_layout(
            template="plotly_white" if is_light else "plotly_dark",
            height=420, margin=dict(l=20, r=20, t=40, b=20), xaxis_rangeslider_visible=False,
            paper_bgcolor="#ffffff" if is_light else "#05070b",
            plot_bgcolor="#ffffff" if is_light else "#05070b",
            font=dict(color="#111827" if is_light else "#e5e7eb"),
        )
        st.plotly_chart(fig, width="stretch", config={"scrollZoom": False, "displaylogo": False})


def _page_ai_review():
    st.markdown("### AI 回测复盘")
    st.caption("这里不是让AI逐日回测，而是让AI读取脚本回测结果，做策略质量分析、亏损原因、参数修改建议。")
    metrics_df = st.session_state.get("last_backtest_metrics", pd.DataFrame())
    trades_df = st.session_state.get("last_backtest_trades", pd.DataFrame())
    if metrics_df is None or metrics_df.empty:
        st.info("请先在【策略回测】运行一次回测。")
        return
    provider = st.selectbox("AI来源", [PROVIDER_DEEPSEEK, PROVIDER_OPENAI], format_func=lambda x: "DeepSeek" if x == PROVIDER_DEEPSEEK else "OpenAI/ChatGPT API")
    model = st.text_input("模型", value="deepseek-v4-pro" if provider == PROVIDER_DEEPSEEK else "gpt-5.4-mini")
    if provider == PROVIDER_DEEPSEEK:
        ok, _msg = check_api_key(PROVIDER_DEEPSEEK)
        if not ok:
            st.warning("未检测到 DEEPSEEK_API_KEY。")
    if provider == PROVIDER_OPENAI:
        ok, _msg = check_api_key(PROVIDER_OPENAI)
        if not ok:
            st.warning("未检测到 OPENAI_API_KEY。")
    sample_trades = trades_df.tail(30).to_dict(orient="records") if trades_df is not None and not trades_df.empty else []
    prompt = f"""
你是JZL证券分析的策略回测复盘助手。
请基于脚本回测结果做结构化复盘，重点输出：
1. 策略是否可继续优化
2. 买入过早/追高/清仓过慢/减仓过敏等问题
3. 参数修改建议
4. 下一轮回测建议
5. 不能给实盘保证，只能做研究建议

回测指标：
{metrics_df.to_json(force_ascii=False, orient='records')[:18000]}

交易样本：
{json.dumps(sample_trades, ensure_ascii=False)[:12000]}
"""
    if st.button("调用AI生成回测复盘", type="primary", width="stretch"):
        try:
            raw, data = call_ai_json(prompt, provider=provider, model=model)
            st.session_state["last_ai_backtest_review"] = raw
            st.success("AI复盘完成。")
        except Exception as e:
            st.error(f"AI复盘失败：{e}")
    raw = st.session_state.get("last_ai_backtest_review")
    if raw:
        st.markdown("### AI复盘结果")
        st.code(raw, language="json" if str(raw).strip().startswith("{") else "text")


def _page_help():
    st.markdown("""
### 这个模块怎么用

**第一步：导入股票池**

- 使用项目根目录 `stock_universe.csv`
- 点击“导入 / 更新股票池到数据库”

**第二步：构建历史数据库**

- 起始日期选 `2021-01-01`
- 更新范围先选“自选收藏”或“股票池前N只”测试
- 确认没问题后再选“全部股票池”

**第三步：增量更新**

- 每天或每周点击“增量更新最新行情”
- 系统会从数据库里已有的最新日期往前回看一段，并覆盖写入，避免漏数据

**第四步：策略回测**

- 使用 `strategies/jzl_wave_core_v1.yaml`
- 回测按“当日收盘产生信号、下一交易日开盘执行”处理，尽量避免未来函数
- 当前是研究级回测，不含涨停买不到、跌停卖不出、停牌等完整交易约束

**第五步：AI回测复盘**

- 脚本负责可复现回测
- AI只负责读回测结果，分析问题和建议调参

### 为什么不让AI逐日历史回测？

逐日调用AI会：

- 成本高
- 速度慢
- 不可复现
- 容易产生理解波动

所以正确流程是：

`脚本回测 → 得到交易明细和收益曲线 → AI复盘策略质量`
""")
