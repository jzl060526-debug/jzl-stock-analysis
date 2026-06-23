# -*- coding: utf-8 -*-
"""AI交易员后台守护进程。

用途：
1. 让“持续运行”不依赖浏览器页面刷新。
2. 页面关掉、Streamlit页面刷新、浏览器缓存变化，都不影响后台粗筛轮询。
3. 每一轮都会写入心跳文件和日志，方便确认它是否真的在运行。

启动方式：
- 双击：AI交易员后台持续运行.bat
- 或命令行：python ai_auto_worker.py

停止方式：
- 在页面点击“停止持续运行”；或
- 双击：停止AI交易员后台.bat；或
- 关闭后台BAT窗口。
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# 固定工作目录为本文件所在目录，避免从其他目录启动时找不到 data/strategies。
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

from ai_agent import call_ai_json, check_api_key, build_ai_prompt, PROVIDER_DEEPSEEK, DEEPSEEK_MODEL_DEFAULT
from ai_decision_audit import audit_ai_decision
from data_fetcher import get_stock_universe
from market_state_builder import build_market_state
from paper_trader import execute_paper_order, load_paper_trades, save_ai_decision_log
from strategy_engine import evaluate_strategy
from strategy_loader import load_strategy

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_PATH = DATA_DIR / "ai_auto_trader_state.json"
HEARTBEAT_PATH = DATA_DIR / "ai_auto_worker_heartbeat.json"
WORKER_LOG_PATH = DATA_DIR / "ai_auto_worker_log.csv"

TRADE_ACTIONS = {"PAPER_BUY", "PAPER_ADD", "PAPER_SELL", "PAPER_CLEAR"}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    last_error: Exception | None = None
    for i in range(6):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{i}.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.08 * (i + 1))
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
    if last_error:
        raise last_error


def load_state() -> dict[str, Any]:
    state = load_json(STATE_PATH, {})
    return state if isinstance(state, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    state = dict(state or {})
    state["updated_at"] = now_str()
    save_json(STATE_PATH, state)


def write_heartbeat(status: str, extra: dict[str, Any] | None = None) -> None:
    hb = {
        "pid": os.getpid(),
        "time": now_str(),
        "status": status,
    }
    if extra:
        hb.update(extra)
    save_json(HEARTBEAT_PATH, hb)


def append_worker_log(row: dict[str, Any]) -> None:
    WORKER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["datetime", "event", "code", "name", "strategy_id", "action", "audit_status", "message"]
    exists = WORKER_LOG_PATH.exists()
    with WORKER_LOG_PATH.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        out = {k: row.get(k, "") for k in fieldnames}
        w.writerow(out)


def parse_dt(value: str):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def recent_trade_blocked(code: str, cooldown_seconds: int) -> tuple[bool, str]:
    """同一股票交易冷却，避免同一信号附近重复买卖。"""
    if not cooldown_seconds or cooldown_seconds <= 0:
        return False, ""
    try:
        df = load_paper_trades()
    except Exception:
        return False, ""
    if df is None or df.empty or "code" not in df.columns or "datetime" not in df.columns:
        return False, ""
    code = str(code).zfill(6)[-6:]
    x = df[df["code"].astype(str).str.zfill(6) == code].copy()
    if x.empty:
        return False, ""
    times = [parse_dt(v) for v in x["datetime"].tolist()]
    times = [t for t in times if t is not None]
    if not times:
        return False, ""
    last = max(times)
    delta = (datetime.now() - last).total_seconds()
    if delta < cooldown_seconds:
        remain = int(cooldown_seconds - delta)
        return True, f"同一股票交易冷却中，距离上次虚拟交易约{int(delta)}秒，剩余约{remain}秒。"
    return False, ""


def make_watch_decision(state: dict[str, Any], strategy_id: str, reason: list[str], risk: list[str] | None = None, audit_status: str = "code_skip_ai") -> dict[str, Any]:
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


def name_for_code(code: str) -> str:
    code = str(code).zfill(6)[-6:]
    try:
        universe = get_stock_universe()
        return str(universe.get(code) or code)
    except Exception:
        return code


def run_one_code(code: str, state_cfg: dict[str, Any]) -> dict[str, Any]:
    """运行单只股票一轮：脚本粗筛 → 触发才调用AI → 审计 → 虚拟执行。"""
    code = str(code).zfill(6)[-6:]
    name = name_for_code(code)
    strategy_id = str(state_cfg.get("strategy_id") or "jzl_wave_core_v1")
    provider = str(state_cfg.get("provider") or PROVIDER_DEEPSEEK)
    model = str(state_cfg.get("model") or DEEPSEEK_MODEL_DEFAULT)
    virtual_cash = float(state_cfg.get("virtual_cash") or 100000.0)
    max_positions = int(state_cfg.get("max_positions") or 3)
    force_ai = bool(state_cfg.get("force_ai", False))
    execute_trade = bool(state_cfg.get("execute_trade", True))
    sync_trade_records = bool(state_cfg.get("sync_trade_records", True))
    cooldown = int(state_cfg.get("trade_cooldown_seconds") or 300)

    strategy = load_strategy(strategy_id)
    market_state = build_market_state(code=code, name=name, strategy_id=strategy_id, virtual_cash=virtual_cash, max_positions=max_positions)
    rule_signal = evaluate_strategy(strategy, market_state)

    if not force_ai and not rule_signal.get("should_call_ai"):
        final_decision = make_watch_decision(
            market_state,
            strategy_id,
            reason=rule_signal.get("reason", ["当前未触发策略条件"]),
            risk=(rule_signal.get("missing_required") or []) + (rule_signal.get("forbidden_hit") or []),
            audit_status="code_skip_ai",
        )
        save_ai_decision_log(market_state, rule_signal, "未调用AI：规则未触发", final_decision, final_decision)
        return {"code": code, "name": name, "action": "WATCH", "audit_status": "code_skip_ai", "message": "规则未触发，未调用AI"}

    preferred_action = rule_signal.get("preferred_action")
    if not force_ai and preferred_action in TRADE_ACTIONS and preferred_action != "PAPER_CLEAR":
        blocked, msg = recent_trade_blocked(code, cooldown)
        if blocked:
            final_decision = make_watch_decision(
                market_state,
                strategy_id,
                reason=["策略触发，但处于自动交易冷却期，暂不调用AI"],
                risk=[msg],
                audit_status="cooldown_skip_ai",
            )
            save_ai_decision_log(market_state, rule_signal, "未调用AI：交易冷却中", final_decision, final_decision)
            return {"code": code, "name": name, "action": "WATCH", "audit_status": "cooldown_skip_ai", "message": msg}

    ok, key_msg = check_api_key(provider)
    if not ok:
        final_decision = make_watch_decision(market_state, strategy_id, reason=["策略触发，但AI Key不可用"], risk=[key_msg], audit_status="api_key_error")
        save_ai_decision_log(market_state, rule_signal, "未调用AI：API Key不可用", final_decision, final_decision)
        return {"code": code, "name": name, "action": "WATCH", "audit_status": "api_key_error", "message": key_msg}

    prompt = build_ai_prompt(market_state, strategy, rule_signal)
    raw_text, ai_decision = call_ai_json(prompt, provider=provider, model=model)
    final_decision = audit_ai_decision(market_state, ai_decision, strategy)
    save_ai_decision_log(market_state, rule_signal, raw_text, ai_decision, final_decision)

    exec_msg = "仅判断，未执行虚拟交易"
    if execute_trade and final_decision.get("audit_status") == "passed" and final_decision.get("action") in TRADE_ACTIONS:
        result = execute_paper_order(final_decision, market_state, virtual_cash=virtual_cash, sync_trade_records=sync_trade_records)
        exec_msg = result.get("message", "")

    return {
        "code": code,
        "name": name,
        "action": final_decision.get("action"),
        "audit_status": final_decision.get("audit_status"),
        "message": exec_msg,
    }


def run_cycle() -> None:
    state = load_state()
    selected_codes = [str(x).zfill(6)[-6:] for x in state.get("selected_codes", [])][:3]
    if not selected_codes:
        write_heartbeat("idle_no_codes", {"message": "没有选择观察股票"})
        append_worker_log({"datetime": now_str(), "event": "idle_no_codes", "message": "没有选择观察股票"})
        return

    strategy_id = str(state.get("strategy_id") or "jzl_wave_core_v1")
    write_heartbeat("running_cycle", {"selected_codes": selected_codes, "strategy_id": strategy_id})

    results = []
    for code in selected_codes:
        try:
            write_heartbeat("running_code", {"selected_codes": selected_codes, "strategy_id": strategy_id, "current_code": code})
            r = run_one_code(code, state)
            results.append(r)
            append_worker_log({
                "datetime": now_str(),
                "event": "cycle_result",
                "code": r.get("code"),
                "name": r.get("name"),
                "strategy_id": strategy_id,
                "action": r.get("action"),
                "audit_status": r.get("audit_status"),
                "message": r.get("message"),
            })
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            append_worker_log({"datetime": now_str(), "event": "code_error", "code": code, "strategy_id": strategy_id, "message": msg})
            results.append({"code": code, "action": "ERROR", "message": msg})

    write_heartbeat("cycle_done", {"selected_codes": selected_codes, "strategy_id": strategy_id, "results": results})


def main() -> None:
    print("=" * 70)
    print("JZL证券分析 AI交易员后台守护进程")
    print("状态文件:", STATE_PATH)
    print("心跳文件:", HEARTBEAT_PATH)
    print("日志文件:", WORKER_LOG_PATH)
    print("关闭此窗口可停止后台；或在页面点击停止持续运行。")
    print("=" * 70)

    write_heartbeat("worker_started", {"pid": os.getpid()})
    append_worker_log({"datetime": now_str(), "event": "worker_started", "message": f"pid={os.getpid()}"})

    while True:
        try:
            state = load_state()
            if not state.get("running"):
                write_heartbeat("stopped", {"message": "状态文件显示未开启持续运行"})
                time.sleep(2)
                continue

            interval = int(state.get("auto_interval") or 10)
            if interval < 5:
                interval = 5

            cycle_started = time.time()
            run_cycle()
            elapsed = time.time() - cycle_started
            sleep_seconds = max(1, interval - elapsed)
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            write_heartbeat("worker_keyboard_interrupt", {})
            append_worker_log({"datetime": now_str(), "event": "worker_keyboard_interrupt", "message": "用户关闭后台窗口"})
            break
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            write_heartbeat("worker_error", {"message": msg, "traceback": traceback.format_exc()[-4000:]})
            append_worker_log({"datetime": now_str(), "event": "worker_error", "message": msg})
            # 无论单轮发生什么错误，不退出守护进程，避免漏掉后续行情。
            time.sleep(5)


if __name__ == "__main__":
    main()
