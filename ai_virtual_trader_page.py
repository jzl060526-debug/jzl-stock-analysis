# -*- coding: utf-8 -*-
"""Streamlit 页面：AI虚拟交易员，默认 DeepSeek，预留 OpenAI。

V3.5 关键逻辑：
1. 行情/策略粗筛可以每10秒持续运行。
2. 脚本规则引擎先判断是否触发策略条件；没有触发则不调用AI，节省API费用。
3. 触发后才调用 DeepSeek / OpenAI，输出结构化JSON交易语言。
4. AI动作必须经过审计器；审计通过后才写入虚拟盘和K线B/S标注。
5. 自动模式带交易冷却，防止同一只股票在同一个信号附近反复买卖。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import subprocess
import sys
import time

import pandas as pd
import streamlit as st

from ai_agent import (
    DEEPSEEK_MODEL_DEFAULT,
    OPENAI_MODEL_DEFAULT,
    PROVIDER_DEEPSEEK,
    PROVIDER_OPENAI,
    build_ai_prompt,
    call_ai_json,
    check_api_key,
    provider_label,
)
from ai_decision_audit import audit_ai_decision
from market_state_builder import build_market_state
from paper_trader import (
    execute_paper_order,
    export_paper_data,
    load_ai_logs,
    load_paper_trades,
    load_positions,
    save_ai_decision_log,
)
from strategy_engine import evaluate_strategy
from strategy_loader import list_strategies, load_strategy
from watchlist_manager import load_watchlist
from ui_components import show_df, metric_card


AUTO_RUNNING_KEY = "jzl_ai_trader_auto_running"
AUTO_LAST_RUN_KEY = "jzl_ai_trader_auto_last_run"
AUTO_LAST_SUMMARY_KEY = "jzl_ai_trader_auto_last_summary"

# 自动运行状态持久化文件。
# 说明：Streamlit 页面刷新后 session_state 可能重建，
# 因此不能只把“持续运行中”存在内存里；否则 10 秒刷新一次页面后会自动停止。
# 这里把运行状态和参数写入本地 JSON，页面刷新后再恢复。
AUTO_STATE_PATH = Path("data") / "ai_auto_trader_state.json"
WORKER_HEARTBEAT_PATH = Path("data") / "ai_auto_worker_heartbeat.json"
WORKER_LOG_PATH = Path("data") / "ai_auto_worker_log.csv"

TRADE_ACTIONS = {"PAPER_BUY", "PAPER_ADD", "PAPER_SELL", "PAPER_CLEAR"}


def _load_auto_state_file() -> dict:
    """读取自动运行状态。读不到时返回空字典。"""
    try:
        if AUTO_STATE_PATH.exists():
            return json.loads(AUTO_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_auto_state_file(state: dict) -> None:
    """保存自动运行状态。用于防止页面自动刷新后持续运行丢失。"""
    try:
        AUTO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        state = dict(state or {})
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        AUTO_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # 自动运行状态保存失败不应导致交易页面崩溃。
        pass


def _set_auto_running(running: bool, config: dict | None = None) -> None:
    """同时写入 session_state 和本地 JSON 文件。"""
    old = _load_auto_state_file()
    if config:
        old.update(config)
    old["running"] = bool(running)
    _save_auto_state_file(old)
    st.session_state[AUTO_RUNNING_KEY] = bool(running)


def _restore_auto_running_from_file() -> dict:
    """页面加载时从本地文件恢复持续运行状态。"""
    state = _load_auto_state_file()
    if state.get("running") and AUTO_RUNNING_KEY not in st.session_state:
        st.session_state[AUTO_RUNNING_KEY] = True
    return state




def _load_worker_heartbeat() -> dict:
    """读取后台守护进程心跳；读不到说明后台暂未启动或尚未写入。"""
    try:
        if WORKER_HEARTBEAT_PATH.exists():
            return json.loads(WORKER_HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _worker_recently_alive(max_age_seconds: int = 45) -> tuple[bool, dict]:
    """判断后台守护进程最近是否有心跳。"""
    hb = _load_worker_heartbeat()
    t = _parse_dt(hb.get("time")) if hb else None
    if not t:
        return False, hb
    age = (datetime.now() - t).total_seconds()
    return age <= max_age_seconds, hb


def _start_background_worker() -> tuple[bool, str]:
    """尝试从页面启动独立后台守护进程。

    注意：后台真正执行轮询，页面只负责写状态和显示心跳。
    这样浏览器页面刷新不会导致持续运行丢失，也避免页面刷新重复执行交易。
    """
    alive, hb = _worker_recently_alive(max_age_seconds=45)
    if alive:
        return True, f"后台已在运行，最近心跳：{hb.get('time')}，状态：{hb.get('status')}"

    bat = Path("AI交易员后台持续运行.bat").resolve()
    py = Path("ai_auto_worker.py").resolve()
    try:
        if os.name == "nt" and bat.exists():
            # Windows 下启动独立命令行窗口，不依赖当前网页会话。
            subprocess.Popen(["cmd", "/c", "start", "", str(bat)], cwd=str(Path.cwd()), shell=False)
            return True, "已尝试启动后台守护进程窗口。"
        if py.exists():
            subprocess.Popen([sys.executable, str(py)], cwd=str(Path.cwd()))
            return True, "已尝试启动后台守护进程。"
        return False, "未找到 ai_auto_worker.py，无法启动后台。"
    except Exception as exc:
        return False, f"启动后台失败：{exc}"

def _safe_show_df(df: pd.DataFrame, height: int = 280):
    show_df(df, height=height)


def _parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _recent_trade_blocked(code: str, cooldown_seconds: int) -> tuple[bool, str]:
    """自动模式交易冷却：避免同一股票在几分钟内被重复执行。"""
    if not cooldown_seconds or cooldown_seconds <= 0:
        return False, ""
    df = load_paper_trades()
    if df is None or df.empty:
        return False, ""
    code = str(code).zfill(6)[-6:]
    x = df[df["code"].astype(str).str.zfill(6) == code].copy()
    if x.empty or "datetime" not in x.columns:
        return False, ""
    # load_paper_trades 默认按 datetime 倒序；保险起见仍然再取最大时间
    times = [_parse_dt(v) for v in x["datetime"].tolist()]
    times = [t for t in times if t is not None]
    if not times:
        return False, ""
    last = max(times)
    delta = (datetime.now() - last).total_seconds()
    if delta < cooldown_seconds:
        remain = int(cooldown_seconds - delta)
        return True, f"同一股票交易冷却中，距离上次虚拟交易约{int(delta)}秒，剩余约{remain}秒。"
    return False, ""


def _make_watch_decision(state: dict, strategy_id: str, reason: list[str], risk: list[str] | None = None, audit_status: str = "code_skip_ai") -> dict:
    return {
        "action": "WATCH",
        "code": state.get("code"),
        "name": state.get("name"),
        "strategy_id": strategy_id,
        "setup_type": "watch",
        "confidence": "low",
        "reason": reason,
        "risk": risk or [],
        "order": None,
        "execution_plan": ["继续等待策略触发或二次确认"],
        "invalid_if": [],
        "review_note": "脚本粗筛未放行，未调用AI。",
        "need_human_review": True,
        "audit_status": audit_status,
    }


def _run_one(
    code: str,
    name: str,
    strategy_id: str,
    virtual_cash: float,
    max_positions: int,
    force_ai: bool,
    execute_trade: bool,
    sync_trade_records: bool,
    provider: str,
    model: str,
    trade_cooldown_seconds: int = 0,
):
    """运行一只股票的一轮判断。

    流程：
    build_market_state -> evaluate_strategy -> 是否调用AI -> audit -> paper execution
    """
    strategy = load_strategy(strategy_id)
    state = build_market_state(code=code, name=name, strategy_id=strategy_id, virtual_cash=virtual_cash, max_positions=max_positions)
    rule_signal = evaluate_strategy(strategy, state)

    # 没触发时，不调用AI。这就是“每10秒脚本粗略判断，没问题才调用AI”的核心。
    if not force_ai and not rule_signal.get("should_call_ai"):
        final_decision = _make_watch_decision(
            state,
            strategy_id,
            reason=rule_signal.get("reason", ["当前未触发策略条件"]),
            risk=rule_signal.get("missing_required", []) + rule_signal.get("forbidden_hit", []),
            audit_status="code_skip_ai",
        )
        save_ai_decision_log(state, rule_signal, "未调用AI：规则未触发", final_decision, final_decision)
        return state, rule_signal, "未调用AI：规则未触发", final_decision, final_decision, {"executed": False, "message": "规则未触发，未调用AI，未执行"}

    # 自动执行时，同一只股票设置冷却；清仓类硬风控不拦截，其他交易信号先冷却。
    preferred_action = rule_signal.get("preferred_action")
    if not force_ai and preferred_action in TRADE_ACTIONS and preferred_action != "PAPER_CLEAR":
        blocked, msg = _recent_trade_blocked(code, int(trade_cooldown_seconds or 0))
        if blocked:
            final_decision = _make_watch_decision(
                state,
                strategy_id,
                reason=["策略触发，但处于自动交易冷却期，暂不调用AI"],
                risk=[msg],
                audit_status="cooldown_skip_ai",
            )
            save_ai_decision_log(state, rule_signal, "未调用AI：交易冷却中", final_decision, final_decision)
            return state, rule_signal, "未调用AI：交易冷却中", final_decision, final_decision, {"executed": False, "message": msg}

    prompt = build_ai_prompt(state, strategy, rule_signal)
    raw_text, ai_decision = call_ai_json(prompt, provider=provider, model=model)
    final_decision = audit_ai_decision(state, ai_decision, strategy)
    save_ai_decision_log(state, rule_signal, raw_text, ai_decision, final_decision)

    exec_result = {"executed": False, "message": "仅判断，未执行虚拟交易"}
    if execute_trade and final_decision.get("audit_status") == "passed" and final_decision.get("action") in TRADE_ACTIONS:
        exec_result = execute_paper_order(final_decision, state, virtual_cash=virtual_cash, sync_trade_records=sync_trade_records)
    return state, rule_signal, raw_text, ai_decision, final_decision, exec_result


def _render_one_result(code: str, name: str, state: dict, rule_signal: dict, raw_text, ai_decision: dict, final_decision: dict, exec_result: dict, expanded: bool = False):
    st.markdown(f"### {code} {name}")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1: st.metric("当前价", state.get("price"))
    with m2: st.metric("MA5", state.get("ma5"))
    with m3: st.metric("MA10", state.get("ma10"))
    with m4: st.metric("MA20", state.get("ma20"))
    with m5: st.metric("粗筛", "触发" if rule_signal.get("should_call_ai") else "未触发")
    with m6: st.metric("最终动作", final_decision.get("action"))

    with st.expander("查看本轮规则/AI/审计明细", expanded=expanded):
        t1, t2, t3 = st.tabs(["脚本粗筛", "AI原始输出", "审计后决策"])
        with t1:
            st.json(rule_signal)
            st.caption("should_call_ai=false 时不会调用AI。自动模式每10秒只做脚本粗筛，触发候选后才消耗API。")
        with t2:
            st.code(raw_text, language="json" if str(raw_text).strip().startswith("{") else "text")
        with t3:
            st.json(final_decision)
            if exec_result.get("executed"):
                st.success(exec_result.get("message"))
            else:
                st.info(exec_result.get("message"))


def _run_batch(
    selected: list[str],
    universe: dict,
    parse_code,
    strategy_id: str,
    virtual_cash: float,
    max_positions: int,
    force_ai: bool,
    execute_trade: bool,
    sync_trade_records: bool,
    provider: str,
    model: str,
    trade_cooldown_seconds: int,
    render: bool = True,
):
    results = []
    for label in selected:
        code = parse_code(label)
        name = universe.get(code, code)
        with st.spinner(f"正在粗筛/判断 {code} {name} ..."):
            state, rule_signal, raw_text, ai_decision, final_decision, exec_result = _run_one(
                code=code,
                name=name,
                strategy_id=strategy_id,
                virtual_cash=virtual_cash,
                max_positions=int(max_positions),
                force_ai=force_ai,
                execute_trade=execute_trade,
                sync_trade_records=sync_trade_records,
                provider=provider,
                model=model,
                trade_cooldown_seconds=trade_cooldown_seconds,
            )
        results.append({
            "code": code,
            "name": name,
            "state": state,
            "rule_signal": rule_signal,
            "raw_text": raw_text,
            "ai_decision": ai_decision,
            "final_decision": final_decision,
            "exec_result": exec_result,
        })
        if render:
            _render_one_result(code, name, state, rule_signal, raw_text, ai_decision, final_decision, exec_result, expanded=False)
    return results


def _fmt_money(value: float) -> str:
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return "--"


def _portfolio_summary(virtual_cash: float) -> dict:
    positions = load_positions()
    trades = load_paper_trades()
    holding_cost = 0.0
    if positions is not None and not positions.empty:
        volume = pd.to_numeric(positions.get("volume", 0), errors="coerce").fillna(0)
        cost = pd.to_numeric(positions.get("cost_price", 0), errors="coerce").fillna(0)
        holding_cost = float((volume * cost).sum())
    return {
        "virtual_cash": float(virtual_cash or 0),
        "holding_count": 0 if positions is None or positions.empty else len(positions),
        "holding_cost": holding_cost,
        "trade_count": 0 if trades is None or trades.empty else len(trades),
    }


def _heartbeat_table(hb: dict) -> pd.DataFrame:
    if not hb:
        return pd.DataFrame([{"status": "未检测到心跳"}])
    keep = ["time", "status", "pid", "strategy_id", "current_code", "selected_codes", "message"]
    return pd.DataFrame([{k: hb.get(k, "") for k in keep if k in hb}])


def page_ai_virtual_trader(universe_options_func=None, option_label_func=None, parse_code_func=None):
    st.subheader("AI交易员")
    st.caption("虚拟盘模拟，不连接券商；脚本先粗筛，触发后才调用AI。")

    strategies_all = list_strategies()
    # 只显示“买卖执行策略”，过滤掉选股评分策略和AI语言策略，避免误选后无法执行。
    strategies = {sid: name for sid, name in strategies_all.items() if ("wave" in sid or "core" in sid or "执行" in name or "趋势波段" in name)}
    if not strategies:
        st.error("未找到可执行的买卖策略文件。请检查 strategies/jzl_wave_core_v1.yaml。")
        return

    universe = universe_options_func() if universe_options_func else {}
    option_label = option_label_func or (lambda c, m: f"{c} {m.get(c, c)}")
    parse_code = parse_code_func or (lambda label: str(label).split()[0].zfill(6)[-6:])
    watch_df = load_watchlist()
    watch_codes = [c for c in watch_df["code"].astype(str).str.zfill(6).tolist() if c in universe]
    base_codes = watch_codes
    labels = [option_label(c, universe) for c in universe.keys()]

    # 页面刷新后恢复上一次“持续运行”的配置。
    # 这样 10 秒自动刷新不会把持续运行状态冲掉。
    auto_file_state = _restore_auto_running_from_file()
    saved_provider = auto_file_state.get("provider", PROVIDER_DEEPSEEK)
    saved_model = auto_file_state.get("model")
    saved_strategy_id = auto_file_state.get("strategy_id")
    saved_selected_codes = [str(x).zfill(6)[-6:] for x in auto_file_state.get("selected_codes", [])]

    summary_box = st.container()
    run_tab, settings_tab, logs_tab = st.tabs(["运行总览", "AI设置 / 策略设置", "持仓与日志"])

    with settings_tab:
        st.markdown("### AI设置")
        c1, c2, c3 = st.columns([1.2, 1.6, 1.2])
        with c1:
            provider_options = [PROVIDER_DEEPSEEK, PROVIDER_OPENAI]
            provider_index = provider_options.index(saved_provider) if saved_provider in provider_options else 0
            provider = st.selectbox("AI来源", provider_options, index=provider_index, format_func=provider_label)
        with c2:
            default_model = DEEPSEEK_MODEL_DEFAULT if provider == PROVIDER_DEEPSEEK else OPENAI_MODEL_DEFAULT
            model = st.text_input("模型名称", value=saved_model or default_model)
        with c3:
            ok, msg = check_api_key(provider)
            if ok:
                st.success("Key正常")
            else:
                st.error("Key未就绪")
            st.caption(msg)

        st.markdown("### 策略设置")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            strategy_keys = list(strategies.keys())
            strategy_index = strategy_keys.index(saved_strategy_id) if saved_strategy_id in strategy_keys else 0
            strategy_id = st.selectbox("选择策略", strategy_keys, index=strategy_index, format_func=lambda sid: f"{sid}｜{strategies[sid]}")
        with c2:
            virtual_cash = st.number_input("虚拟本金", min_value=10000.0, value=float(auto_file_state.get("virtual_cash", 100000.0)), step=10000.0)
        with c3:
            max_positions = st.number_input("最大持仓数", min_value=1, max_value=10, value=int(auto_file_state.get("max_positions", 3)), step=1)
        with c4:
            execute_trade = st.checkbox("审计通过后执行虚拟盘", value=bool(auto_file_state.get("execute_trade", True)))
        sync_trade_records = st.checkbox("同步到买卖点复盘CSV，用于K线B/S标注", value=bool(auto_file_state.get("sync_trade_records", True)))
        force_ai = st.checkbox("强制调用AI测试，不管策略是否触发；默认不建议开启", value=bool(auto_file_state.get("force_ai", False)))

        st.markdown("### 自动运行设置")
        a1, a2, a3 = st.columns(3)
        with a1:
            auto_interval = st.number_input("脚本粗筛刷新间隔，秒", min_value=5, max_value=300, value=int(auto_file_state.get("auto_interval", 10)), step=5)
        with a2:
            trade_cooldown_seconds = st.number_input("同一股票交易冷却，秒", min_value=0, max_value=3600, value=int(auto_file_state.get("trade_cooldown_seconds", 300)), step=30)
        with a3:
            show_last_detail = st.checkbox("展开最近一轮信息", value=bool(auto_file_state.get("show_last_detail", False)))

        st.markdown("### 观察股票")
        if saved_selected_codes:
            default_codes = [c for c in saved_selected_codes if c in universe][:3]
        else:
            default_codes = base_codes[:3]
        default_labels = [option_label(c, universe) for c in default_codes]
        selected = st.multiselect("最多选择3只股票，优先来自自选收藏", labels, default=default_labels)
        if len(selected) > 3:
            st.warning("最多3只，系统已截取前3只。")
            selected = selected[:3]
        if watch_codes:
            st.caption("已从收藏自选中载入默认股票。")
        else:
            st.caption("还没有收藏自选；可以手动选择完整股票池，或先到【收藏自选】添加。")

        strategy = load_strategy(strategy_id)
        with st.expander("当前策略规则", expanded=False):
            st.json(strategy)

    def _current_auto_config() -> dict:
        """保存当前页面自动运行所需的所有参数。"""
        return {
            "provider": provider,
            "model": model,
            "strategy_id": strategy_id,
            "virtual_cash": float(virtual_cash),
            "max_positions": int(max_positions),
            "force_ai": bool(force_ai),
            "execute_trade": bool(execute_trade),
            "sync_trade_records": bool(sync_trade_records),
            "auto_interval": int(auto_interval),
            "trade_cooldown_seconds": int(trade_cooldown_seconds),
            "show_last_detail": bool(show_last_detail),
            "selected_codes": [parse_code(x) for x in selected[:3]],
        }

    auto_running = bool(st.session_state.get(AUTO_RUNNING_KEY, False) or _load_auto_state_file().get("running"))
    alive, hb = _worker_recently_alive(max_age_seconds=max(180, int(auto_interval) * 10))

    with summary_box:
        summary = _portfolio_summary(float(virtual_cash))
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            metric_card("虚拟本金", _fmt_money(summary["virtual_cash"]), "纸面模拟资金", tone="positive")
        with m2:
            metric_card("持仓成本", _fmt_money(summary["holding_cost"]), f"{summary['holding_count']} 只持仓")
        with m3:
            metric_card("后台守护", "运行中" if auto_running and alive else ("待确认" if auto_running else "未开启"), hb.get("status", "--") if hb else "--", tone="positive" if auto_running and alive else "warning")
        with m4:
            metric_card("最近心跳", str(hb.get("time", "--")) if hb else "--", f"交易记录 {summary['trade_count']} 条")

    with run_tab:
        st.markdown("### 运行控制")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            run_once = st.button("运行一次 AI 虚拟交易员", type="primary", width="stretch")
        with c2:
            start_continuous = st.button("开始持续运行", width="stretch")
        with c3:
            stop_continuous = st.button("停止持续运行", width="stretch")

        if start_continuous:
            if not selected:
                st.error("请先选择至少1只观察股票，再开启持续运行。")
            else:
                _set_auto_running(True, _current_auto_config())
                st.session_state[AUTO_LAST_RUN_KEY] = 0.0
                ok_start, start_msg = _start_background_worker()
                if ok_start:
                    st.success("已开启持续运行。后台守护进程会独立轮询，不依赖页面刷新。")
                    st.caption(start_msg)
                else:
                    st.error(start_msg)
                    st.warning("请手动双击 AI交易员后台持续运行.bat。")
                st.rerun()
        if stop_continuous:
            _set_auto_running(False, _current_auto_config())
            st.info("已停止持续运行。")
            st.rerun()

        if auto_running:
            # 每次渲染只刷新状态文件，真正执行由 ai_auto_worker.py 后台守护进程负责。
            # 不再依赖 meta refresh 执行交易，避免页面刷新导致重复执行或状态丢失。
            _set_auto_running(True, _current_auto_config())
            if alive:
                st.success(f"持续运行中：后台守护进程正常。最近心跳：{hb.get('time')}，状态：{hb.get('status')}")
            else:
                st.warning("持续运行状态已开启，但暂未检测到最近心跳。请确认后台窗口是否打开，或双击 AI交易员后台持续运行.bat。")
                ok_start, start_msg = _start_background_worker()
                st.caption(start_msg)
        else:
            if alive:
                st.info(f"后台进程有心跳，但状态文件显示未开启持续运行：{hb.get('time')} / {hb.get('status')}")
            else:
                st.caption("当前未开启持续运行。")

        st.markdown("### 后台守护状态")
        show_df(_heartbeat_table(hb), height=150)
        st.caption("稳定运行建议：开启持续运行后，保持后台BAT窗口不要关闭；页面可刷新，但后台轮询不依赖浏览器。")

        def _validate_before_run() -> bool:
            ok, msg = check_api_key(provider)
            if not ok:
                st.error(msg)
                return False
            if not selected:
                st.error("请至少选择1只股票。")
                return False
            return True

        # 手动运行一次
        if run_once:
            if _validate_before_run():
                results = _run_batch(
                    selected=selected,
                    universe=universe,
                    parse_code=parse_code,
                    strategy_id=strategy_id,
                    virtual_cash=virtual_cash,
                    max_positions=int(max_positions),
                    force_ai=force_ai,
                    execute_trade=execute_trade,
                    sync_trade_records=sync_trade_records,
                    provider=provider,
                    model=model,
                    trade_cooldown_seconds=int(trade_cooldown_seconds),
                    render=True,
                )
                st.session_state[AUTO_LAST_SUMMARY_KEY] = {"time": datetime.now().strftime("%H:%M:%S"), "count": len(results)}

        # 自动运行由 ai_auto_worker.py 后台守护进程负责。
        # 页面不再在刷新时直接执行 _run_batch，避免刷新导致状态丢失或重复执行。

        # 最近一轮摘要
        last_summary = st.session_state.get(AUTO_LAST_SUMMARY_KEY)
        if last_summary:
            st.markdown("### 最近一轮自动/手动结果")
            rows = last_summary.get("rows") if isinstance(last_summary, dict) else None
            if rows:
                show_df(pd.DataFrame(rows), height=160)
            else:
                st.caption(str(last_summary))

    with logs_tab:
        if st.button("刷新持仓/日志", width="stretch"):
            st.rerun()
        hold_tab, trade_tab, ai_log_tab, worker_log_tab = st.tabs(["虚拟持仓", "虚拟交易记录", "AI决策日志", "后台守护日志"])
        with hold_tab:
            _safe_show_df(load_positions(), height=260)
        with trade_tab:
            _safe_show_df(load_paper_trades().tail(120), height=520)
        with ai_log_tab:
            _safe_show_df(load_ai_logs().tail(120), height=560)
        with worker_log_tab:
            if WORKER_LOG_PATH.exists():
                try:
                    log_df = pd.read_csv(WORKER_LOG_PATH, dtype={"code": str}, encoding="utf-8-sig").tail(120)
                    show_df(log_df, height=520)
                except Exception as exc:
                    st.caption(f"读取后台日志失败：{exc}")
            else:
                st.info("暂无后台守护日志。")

        if st.button("导出虚拟盘数据 Excel", width="stretch"):
            path = export_paper_data()
            st.success(f"已生成：{path}")
            with open(path, "rb") as f:
                st.download_button(f"下载 {Path(path).name}", f, file_name=Path(path).name, width="stretch")
