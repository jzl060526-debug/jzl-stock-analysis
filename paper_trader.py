# -*- coding: utf-8 -*-
"""AI虚拟盘：只做纸面模拟，不连接券商，不真实下单。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import uuid
from typing import Any

import pandas as pd

from config import BASE_DIR, OUTPUT_DIR

PAPER_POSITIONS_CSV = BASE_DIR / "paper_positions.csv"
PAPER_TRADES_CSV = BASE_DIR / "paper_trades.csv"
AI_DECISION_LOG_CSV = BASE_DIR / "ai_decision_log.csv"

POSITION_COLUMNS = ["code", "name", "volume", "cost_price", "updated_at"]
TRADE_COLUMNS = ["id", "datetime", "date", "code", "name", "strategy_id", "action", "side", "action_type", "price", "volume", "amount", "reason", "risk", "note"]
LOG_COLUMNS = ["id", "datetime", "code", "name", "strategy_id", "raw_action", "final_action", "audit_status", "rule_signal", "raw_ai_text", "final_decision", "market_state"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype={"code": str}, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, dtype={"code": str}, encoding="gbk")
    except Exception:
        return pd.DataFrame(columns=columns)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns].copy()


def load_positions() -> pd.DataFrame:
    df = _read_csv(PAPER_POSITIONS_CSV, POSITION_COLUMNS)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("").str.zfill(6)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    df["cost_price"] = pd.to_numeric(df["cost_price"], errors="coerce").fillna(0.0)
    df = df[df["volume"] > 0]
    return df.reset_index(drop=True)


def save_positions(df: pd.DataFrame) -> None:
    out = df.copy() if df is not None else pd.DataFrame(columns=POSITION_COLUMNS)
    for c in POSITION_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out[POSITION_COLUMNS]
    out.to_csv(PAPER_POSITIONS_CSV, index=False, encoding="utf-8-sig")


def load_paper_trades() -> pd.DataFrame:
    df = _read_csv(PAPER_TRADES_CSV, TRADE_COLUMNS)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("").str.zfill(6)
    for c in ["price", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("datetime", ascending=False).reset_index(drop=True)


def load_ai_logs() -> pd.DataFrame:
    df = _read_csv(AI_DECISION_LOG_CSV, LOG_COLUMNS)
    if df.empty:
        return df
    return df.sort_values("datetime", ascending=False).reset_index(drop=True)


def get_position(code: str) -> dict[str, Any]:
    code = str(code).zfill(6)[-6:]
    df = load_positions()
    if df.empty or code not in set(df["code"]):
        return {"code": code, "holding": False, "volume": 0, "cost_price": None}
    r = df[df["code"] == code].iloc[0].to_dict()
    return {"code": code, "holding": True, "volume": int(r.get("volume") or 0), "cost_price": float(r.get("cost_price") or 0)}


def _round_lot(shares: float) -> int:
    return max(int(shares // 100) * 100, 0)


def execute_paper_order(decision: dict[str, Any], market_state: dict[str, Any], virtual_cash: float = 100000.0, sync_trade_records: bool = False) -> dict[str, Any]:
    """按审计后的决策执行虚拟盘。"""
    action = decision.get("action")
    if action not in {"PAPER_BUY", "PAPER_ADD", "PAPER_SELL", "PAPER_CLEAR"}:
        return {"executed": False, "message": "非交易动作，无需执行"}

    code = str(decision.get("code") or market_state.get("code")).zfill(6)[-6:]
    name = str(decision.get("name") or market_state.get("name") or code)
    strategy_id = str(decision.get("strategy_id") or market_state.get("strategy_id") or "")
    price = float(market_state.get("price") or 0)
    if price <= 0:
        return {"executed": False, "message": "当前价格无效，无法执行虚拟单"}

    order = decision.get("order") or {}
    position_pct = float(order.get("position_pct") or 0)

    pos_df = load_positions()
    current = get_position(code)
    current_volume = int(current.get("volume") or 0)
    current_cost = float(current.get("cost_price") or 0) if current.get("cost_price") is not None else 0.0

    side = ""
    action_type = ""
    volume = 0

    if action in {"PAPER_BUY", "PAPER_ADD"}:
        target_amount = float(virtual_cash) * position_pct
        volume = _round_lot(target_amount / price)
        if volume <= 0:
            return {"executed": False, "message": "虚拟买入金额不足100股，未执行"}
        side = "买入"
        action_type = "建仓" if current_volume <= 0 else "加仓"
        new_volume = current_volume + volume
        new_cost = (current_cost * current_volume + price * volume) / new_volume if new_volume > 0 else price

        if pos_df.empty or code not in set(pos_df["code"].astype(str).str.zfill(6)):
            new_row = {"code": code, "name": name, "volume": new_volume, "cost_price": round(new_cost, 4), "updated_at": _now()}
            pos_df = pd.concat([pos_df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            idx = pos_df[pos_df["code"].astype(str).str.zfill(6) == code].index[0]
            pos_df.loc[idx, ["name", "volume", "cost_price", "updated_at"]] = [name, new_volume, round(new_cost, 4), _now()]
        save_positions(pos_df)

    elif action in {"PAPER_SELL", "PAPER_CLEAR"}:
        if current_volume <= 0:
            return {"executed": False, "message": "没有虚拟持仓，无法卖出"}
        if action == "PAPER_CLEAR":
            volume = current_volume
            action_type = "清仓"
        else:
            volume = _round_lot(current_volume * position_pct)
            if volume <= 0:
                volume = min(current_volume, 100)
            volume = min(volume, current_volume)
            action_type = "减仓"
        side = "卖出"
        new_volume = current_volume - volume
        if not pos_df.empty and code in set(pos_df["code"].astype(str).str.zfill(6)):
            idx = pos_df[pos_df["code"].astype(str).str.zfill(6) == code].index[0]
            if new_volume <= 0:
                pos_df = pos_df.drop(index=idx)
            else:
                pos_df.loc[idx, ["volume", "updated_at"]] = [new_volume, _now()]
            save_positions(pos_df)

    amount = round(price * volume, 2)
    reason_text = "；".join(map(str, decision.get("reason") or []))
    risk_text = "；".join(map(str, decision.get("risk") or []))
    plan_text = "；".join(map(str, decision.get("execution_plan") or []))
    invalid_text = "；".join(map(str, decision.get("invalid_if") or []))
    review_note = str(decision.get("review_note") or "")
    note_text = (
        "AI虚拟盘自动记录，不是真实交易。"
        + "AI理由：" + reason_text
        + "｜风险：" + risk_text
        + ("｜后续计划：" + plan_text if plan_text else "")
        + ("｜失效条件：" + invalid_text if invalid_text else "")
        + ("｜复盘备注：" + review_note if review_note else "")
    )
    row = {
        "id": uuid.uuid4().hex[:12],
        "datetime": _now(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "code": code,
        "name": name,
        "strategy_id": strategy_id,
        "action": action,
        "side": side,
        "action_type": action_type,
        "price": round(price, 4),
        "volume": int(volume),
        "amount": amount,
        "reason": reason_text,
        "risk": risk_text,
        "note": note_text,
    }
    trades = load_paper_trades()
    trades = pd.concat([trades, pd.DataFrame([row])], ignore_index=True)
    trades.to_csv(PAPER_TRADES_CSV, index=False, encoding="utf-8-sig")

    if sync_trade_records:
        try:
            from trade_journal import add_trade_record
            add_trade_record(
                datetime.now().date(), code, name, side, action_type, price, int(volume),
                reason=f"AI虚拟盘｜{strategy_id}｜" + row["reason"],
                note=note_text,
                position_status="已清仓" if action_type == "清仓" else "持仓中",
            )
        except Exception:
            pass

    return {"executed": True, "message": f"已执行虚拟{side}{action_type}：{code} {name} {volume}股 @ {price}", "trade": row}


def save_ai_decision_log(market_state: dict[str, Any], rule_signal: dict[str, Any], raw_ai_text: str, ai_decision: dict[str, Any], final_decision: dict[str, Any]) -> None:
    logs = load_ai_logs()
    row = {
        "id": uuid.uuid4().hex[:12],
        "datetime": _now(),
        "code": str(market_state.get("code") or "").zfill(6)[-6:],
        "name": market_state.get("name", ""),
        "strategy_id": market_state.get("strategy_id", ""),
        "raw_action": ai_decision.get("action") if isinstance(ai_decision, dict) else "",
        "final_action": final_decision.get("action") if isinstance(final_decision, dict) else "",
        "audit_status": final_decision.get("audit_status", ""),
        "rule_signal": json.dumps(rule_signal, ensure_ascii=False),
        "raw_ai_text": raw_ai_text,
        "final_decision": json.dumps(final_decision, ensure_ascii=False),
        "market_state": json.dumps(market_state, ensure_ascii=False),
    }
    logs = pd.concat([logs, pd.DataFrame([row])], ignore_index=True)
    logs.to_csv(AI_DECISION_LOG_CSV, index=False, encoding="utf-8-sig")


def export_paper_data() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"paper_trader_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        load_positions().to_excel(writer, index=False, sheet_name="虚拟持仓")
        load_paper_trades().to_excel(writer, index=False, sheet_name="虚拟交易")
        load_ai_logs().to_excel(writer, index=False, sheet_name="AI决策日志")
    return path
