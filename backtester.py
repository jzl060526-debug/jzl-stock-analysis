# -*- coding: utf-8 -*-
"""JZL证券分析：策略历史回测模块。

这是日线级虚拟回测，默认不调用AI。AI用于回测结果复盘，不用于逐笔历史交易，避免成本和不可复现问题。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import math
import uuid
from typing import Any

import pandas as pd

from market_db import get_daily_bars, get_conn, init_db, DB_PATH


@dataclass
class BacktestConfig:
    initial_cash: float = 100000.0
    start_date: str = "2021-01-01"
    end_date: str | None = None
    buy_position_pct: float = 0.20
    add_position_pct: float = 0.10
    reduce_position_pct: float = 0.30
    max_single_stock_pct: float = 0.30
    max_add_times: int = 2
    lot_size: int = 100
    fee_rate: float = 0.0003
    slippage_pct: float = 0.0000


def _safe_float(x, default=None):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def prepare_daily_indicators(df: pd.DataFrame, strategy: dict[str, Any] | None = None) -> pd.DataFrame:
    x = df.copy().sort_values("date").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    x["ma5"] = x["close"].rolling(5).mean()
    x["ma10"] = x["close"].rolling(10).mean()
    x["ma20"] = x["close"].rolling(20).mean()
    x["ma60"] = x["close"].rolling(60).mean()
    x["vol_ma5"] = x["volume"].rolling(5).mean()
    x["vol_ma20"] = x["volume"].rolling(20).mean()
    x["volume_ratio"] = x["volume"] / x["vol_ma5"]
    x["ret_pct"] = x["close"].pct_change() * 100
    x["prev_20_high"] = x["high"].rolling(20).max().shift(1)
    x["upper_shadow_pct"] = (x["high"] - x[["open", "close"]].max(axis=1)) / x["close"] * 100
    x["body_pct"] = (x["close"] - x["open"]) / x["open"] * 100
    x["distance_ma5_pct"] = (x["close"] / x["ma5"] - 1) * 100
    return x


def _conditions(row: pd.Series, prev: pd.Series | None, position_shares: int, add_times: int, cfg: BacktestConfig, strategy: dict[str, Any]) -> dict[str, bool]:
    p = strategy.get("parameters") or {}
    near_ma5 = float(p.get("near_ma5_pct", 2.5))
    near_ma10 = float(p.get("near_ma10_pct", 3.5))
    near_ma20 = float(p.get("near_ma20_pct", 4.5))
    max_dist_buy = float(p.get("max_distance_ma5_buy_pct", 6.0))
    max_dist_add = float(p.get("max_distance_ma5_add_pct", 4.5))
    far_reduce = float(p.get("far_above_ma5_reduce_pct", 8.0))
    shrink_max = float(p.get("volume_shrink_max_ratio", 0.90))
    vol_min = float(p.get("volume_healthy_min_ratio", 0.60))
    vol_max = float(p.get("volume_healthy_max_ratio", 1.80))
    vol_mild_min = float(p.get("volume_mild_expand_min_ratio", 1.05))
    vol_mild_max = float(p.get("volume_mild_expand_max_ratio", 1.80))
    vol_big = float(p.get("volume_big_expand_ratio", 1.80))
    big_drop = float(p.get("big_drop_pct", -3.0))
    upper_shadow = float(p.get("upper_shadow_pct", 3.0))

    close = _safe_float(row.get("close"))
    ma5 = _safe_float(row.get("ma5"))
    ma10 = _safe_float(row.get("ma10"))
    ma20 = _safe_float(row.get("ma20"))
    ma60 = _safe_float(row.get("ma60"))
    vol_ratio = _safe_float(row.get("volume_ratio"), 0)
    ret = _safe_float(row.get("ret_pct"), 0)
    high = _safe_float(row.get("high"))
    prev20 = _safe_float(row.get("prev_20_high"))
    dist_ma5 = _safe_float(row.get("distance_ma5_pct"), 0)
    up_shadow = _safe_float(row.get("upper_shadow_pct"), 0)

    enough = close is not None and ma20 is not None and ma5 is not None and ma10 is not None
    near5 = enough and abs(close / ma5 - 1) * 100 <= near_ma5
    near10 = enough and abs(close / ma10 - 1) * 100 <= near_ma10
    near20 = enough and abs(close / ma20 - 1) * 100 <= near_ma20
    price_above_ma20 = enough and close > ma20
    trend_not_broken = price_above_ma20 and (ma10 is not None and ma20 is not None and ma10 >= ma20 * 0.995)
    trend_broken = enough and close < ma20 and ma5 < ma10
    volume_healthy = vol_ratio is not None and vol_min <= vol_ratio <= vol_max
    pullback_volume_shrink = vol_ratio is not None and vol_ratio <= shrink_max
    mild_expand = vol_ratio is not None and vol_mild_min <= vol_ratio <= vol_mild_max
    big_expand = vol_ratio is not None and vol_ratio >= vol_big
    breakout = high is not None and prev20 is not None and high >= prev20
    high_volume_big_bear = bool(big_expand and ret is not None and ret <= big_drop)
    upper_fail = bool(up_shadow >= upper_shadow and vol_ratio >= vol_mild_min and ret <= 0)
    pullback_then_recover = False
    if prev is not None and enough:
        prev_close = _safe_float(prev.get("close"))
        prev_ma10 = _safe_float(prev.get("ma10"))
        if prev_close and prev_ma10:
            pullback_then_recover = prev_close <= prev_ma10 * (1 + near_ma10 / 100) and close > ma10

    return {
        "insufficient_daily_data": not enough,
        "insufficient_intraday_data": False,  # 历史日线回测不使用分时，默认不阻塞。
        "insufficient_volume_data": vol_ratio is None or vol_ratio == 0 or math.isnan(vol_ratio),
        "sector_strength_ok": True,
        "stock_stronger_than_sector": True,
        "sector_turns_weak": False,
        "sector_turns_weak_and_stock_breaks_ma10": False,
        "price_above_ma5": enough and close > ma5,
        "price_above_ma10": enough and close > ma10,
        "price_above_ma20": price_above_ma20,
        "price_below_ma10": enough and close < ma10,
        "price_below_ma20": enough and close < ma20,
        "ma5_above_ma10": enough and ma5 > ma10,
        "ma10_above_ma20": enough and ma10 > ma20,
        "ma20_above_ma60": ma20 is not None and ma60 is not None and ma20 > ma60,
        "trend_not_broken": trend_not_broken,
        "trend_broken": trend_broken,
        "price_below_ma20_and_trend_broken": enough and close < ma20 and trend_broken,
        "price_near_ma5": near5,
        "price_near_ma10": near10,
        "price_near_ma20": near20,
        "price_near_ma5_or_ma10_or_ma20": near5 or near10 or near20,
        "price_pullback_to_ma5_or_ma10": near5 or near10,
        "breakout_20d_high": breakout,
        "near_major_resistance_without_breakout": prev20 is not None and high is not None and high >= prev20 * 0.985 and not breakout,
        "volume_mild_expand": mild_expand,
        "volume_big_expand": big_expand,
        "pullback_volume_shrink": pullback_volume_shrink,
        "volume_healthy": volume_healthy,
        "volume_not_support": vol_ratio is not None and vol_ratio < vol_min,
        "volume_big_drop": high_volume_big_bear,
        "volume_up_price_stagnant": vol_ratio >= vol_mild_min and abs(ret) < 0.5,
        "intraday_support_strong": True,   # 日线回测中用收盘强度替代，不作为阻塞。
        "intraday_recover_vwap": True,
        "intraday_failed_breakout": upper_fail,
        "weak_intraday_rebound": False,
        "weak_intraday_rebound_after_rise": upper_fail,
        "pullback_then_recover": pullback_then_recover,
        "no_big_bearish_breakdown": not high_volume_big_bear,
        "high_volume_big_bearish_breakdown": high_volume_big_bear,
        "high_volume_upper_shadow_failed": upper_fail,
        "failed_rebound_after_breakdown": trend_broken and ret <= 0,
        "already_holding": position_shares > 0,
        "not_holding": position_shares <= 0,
        "profit_position": position_shares > 0,  # 具体盈亏在主循环中补充
        "position_allowed": True,
        "max_positions_reached": False,
        "add_times_not_exceeded": add_times < cfg.max_add_times,
        "distance_ma5_too_high": dist_ma5 is not None and dist_ma5 > max_dist_buy,
        "distance_ma5_too_high_for_add": dist_ma5 is not None and dist_ma5 > max_dist_add,
        "price_far_above_ma5": dist_ma5 is not None and dist_ma5 > far_reduce,
        "cost_not_too_high": True,
    }


def _conditions_list(rule_obj) -> list[str]:
    if not rule_obj:
        return []
    if isinstance(rule_obj, dict):
        if "required_any" in rule_obj:
            return list(rule_obj.get("required_any") or [])
        if "required" in rule_obj:
            return list(rule_obj.get("required") or [])
        if "conditions" in rule_obj:
            return list(rule_obj.get("conditions") or [])
    if isinstance(rule_obj, list):
        return list(rule_obj)
    return []


def _hit_any(names: list[str], conds: dict[str, bool]) -> list[str]:
    return [n for n in names if conds.get(n, False)]


def _missing(names: list[str], conds: dict[str, bool]) -> list[str]:
    return [n for n in names if not conds.get(n, False)]


def _lot_shares(amount: float, price: float, lot_size: int) -> int:
    if price <= 0 or amount <= 0:
        return 0
    shares = int(amount // price // lot_size * lot_size)
    return max(0, shares)


def run_single_stock_backtest(code: str, name: str, strategy: dict[str, Any], cfg: BacktestConfig, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    df = get_daily_bars(code, cfg.start_date, cfg.end_date, db_path=db_path)
    if df is None or df.empty or len(df) < 80:
        return {"error": f"{code} 数据不足，无法回测"}
    x = prepare_daily_indicators(df, strategy)

    cash = float(cfg.initial_cash)
    shares = 0
    cost = 0.0
    add_times = 0
    trades: list[dict] = []
    equity_rows: list[dict] = []
    pending_action = None
    pending_reason = ""

    buy_pct = float(((strategy.get("buy_rules") or {}).get("order") or {}).get("position_pct", cfg.buy_position_pct))
    add_pct = float(((strategy.get("add_rules") or {}).get("order") or {}).get("position_pct", cfg.add_position_pct))
    reduce_pct = float((((strategy.get("sell_rules") or {}).get("reduce") or {}).get("order") or {}).get("position_pct", cfg.reduce_position_pct))

    for i in range(60, len(x)):
        row = x.iloc[i]
        prev = x.iloc[i - 1] if i > 0 else None
        today_open = float(row["open"])
        today_close = float(row["close"])
        dt = row["date"]

        # 先执行昨日收盘后产生的信号，按今日开盘成交，避免未来函数。
        if pending_action:
            action = pending_action
            exec_price = today_open * (1 + cfg.slippage_pct if action in ["BUY", "ADD"] else 1 - cfg.slippage_pct)
            if action == "BUY" and shares <= 0:
                amount = cfg.initial_cash * buy_pct
                qty = _lot_shares(min(amount, cash), exec_price, cfg.lot_size)
                if qty > 0:
                    fee = qty * exec_price * cfg.fee_rate
                    cash -= qty * exec_price + fee
                    shares += qty
                    cost = exec_price
                    add_times = 0
                    trades.append({"datetime": str(dt.date()), "code": code, "name": name, "action": "BUY", "price": exec_price, "shares": qty, "cash_after": cash, "position_after": shares, "reason": pending_reason})
            elif action == "ADD" and shares > 0:
                amount = cfg.initial_cash * add_pct
                qty = _lot_shares(min(amount, cash), exec_price, cfg.lot_size)
                if qty > 0:
                    fee = qty * exec_price * cfg.fee_rate
                    old_value = shares * cost
                    cash -= qty * exec_price + fee
                    shares += qty
                    cost = (old_value + qty * exec_price) / shares
                    add_times += 1
                    trades.append({"datetime": str(dt.date()), "code": code, "name": name, "action": "ADD", "price": exec_price, "shares": qty, "cash_after": cash, "position_after": shares, "reason": pending_reason})
            elif action == "SELL" and shares > 0:
                qty = int(shares * reduce_pct // cfg.lot_size * cfg.lot_size)
                qty = max(cfg.lot_size, qty) if shares >= cfg.lot_size else shares
                qty = min(qty, shares)
                if qty > 0:
                    fee = qty * exec_price * cfg.fee_rate
                    cash += qty * exec_price - fee
                    shares -= qty
                    if shares <= 0:
                        cost = 0.0
                        add_times = 0
                    trades.append({"datetime": str(dt.date()), "code": code, "name": name, "action": "SELL", "price": exec_price, "shares": qty, "cash_after": cash, "position_after": shares, "reason": pending_reason})
            elif action == "CLEAR" and shares > 0:
                qty = shares
                fee = qty * exec_price * cfg.fee_rate
                cash += qty * exec_price - fee
                shares = 0
                cost = 0.0
                add_times = 0
                trades.append({"datetime": str(dt.date()), "code": code, "name": name, "action": "CLEAR", "price": exec_price, "shares": qty, "cash_after": cash, "position_after": shares, "reason": pending_reason})
            pending_action = None
            pending_reason = ""

        # 记录权益
        equity = cash + shares * today_close
        equity_rows.append({"date": dt, "equity": equity, "cash": cash, "shares": shares, "close": today_close})

        # 用今日收盘数据生成明日开盘执行信号。
        conds = _conditions(row, prev, shares, add_times, cfg, strategy)
        if shares > 0 and cost > 0:
            conds["profit_position"] = today_close > cost
        # 清仓最高优先级
        force_clear = _hit_any(_conditions_list(((strategy.get("hard_risk_rules") or {}).get("force_clear") or {})), conds)
        clear_hit = _hit_any(_conditions_list(strategy.get("clear_rules") or {}), conds)
        if shares > 0 and (force_clear or clear_hit):
            pending_action = "CLEAR"
            pending_reason = ";".join(force_clear or clear_hit)
            continue
        # 减仓
        reduce_hit = _hit_any(_conditions_list(((strategy.get("sell_rules") or {}).get("reduce") or {})), conds)
        if shares > 0 and reduce_hit:
            pending_action = "SELL"
            pending_reason = ";".join(reduce_hit)
            continue
        # 加仓
        add_required = _conditions_list((strategy.get("add_rules") or {}).get("required") or [])
        add_forbidden = _conditions_list({"required_any": (strategy.get("add_rules") or {}).get("forbidden") or []})
        if shares > 0 and add_required and not _missing(add_required, conds) and not _hit_any(add_forbidden, conds):
            pending_action = "ADD"
            pending_reason = ";".join(add_required)
            continue
        # 首次买入 count based
        buy_cfg = strategy.get("buy_rules") or {}
        buy_conditions = list(buy_cfg.get("conditions") or [])
        forbidden = list(buy_cfg.get("forbidden") or []) + _conditions_list(((strategy.get("hard_risk_rules") or {}).get("forbid_buy") or {}))
        hit = _hit_any(buy_conditions, conds)
        forbid_hit = _hit_any(forbidden, conds)
        min_count = int(buy_cfg.get("required_min_count", 5))
        if shares <= 0 and len(hit) >= min_count and not forbid_hit:
            pending_action = "BUY"
            pending_reason = ";".join(hit)
            continue

    # 尾盘权益
    final_close = float(x.iloc[-1]["close"])
    final_value = cash + shares * final_close
    equity_df = pd.DataFrame(equity_rows)
    trades_df = pd.DataFrame(trades)
    metrics = calc_metrics(equity_df, trades_df, cfg.initial_cash, final_value)
    return {"code": code, "name": name, "equity": equity_df, "trades": trades_df, "metrics": metrics}


def calc_metrics(equity_df: pd.DataFrame, trades_df: pd.DataFrame, initial_cash: float, final_value: float) -> dict[str, Any]:
    total_return = final_value / initial_cash - 1 if initial_cash else 0
    if equity_df is None or equity_df.empty:
        max_dd = 0
        annual = 0
    else:
        eq = equity_df["equity"].astype(float)
        dd = eq / eq.cummax() - 1
        max_dd = float(dd.min())
        days = max(1, (pd.to_datetime(equity_df["date"].max()) - pd.to_datetime(equity_df["date"].min())).days)
        annual = (final_value / initial_cash) ** (365 / days) - 1 if initial_cash and final_value > 0 else 0
    win_rate = None
    if trades_df is not None and not trades_df.empty:
        # 粗略按 BUY->SELL/CLEAR 配对
        wins = 0
        total = 0
        last_buy = None
        for r in trades_df.itertuples(index=False):
            if r.action in ["BUY", "ADD"]:
                last_buy = r.price if last_buy is None else last_buy
            elif r.action in ["SELL", "CLEAR"] and last_buy is not None:
                total += 1
                wins += 1 if r.price > last_buy else 0
                if r.action == "CLEAR":
                    last_buy = None
        win_rate = wins / total if total else None
    return {
        "final_value": round(float(final_value), 2),
        "total_return": round(float(total_return), 4),
        "annual_return": round(float(annual), 4),
        "max_drawdown": round(float(max_dd), 4),
        "win_rate": None if win_rate is None else round(float(win_rate), 4),
        "trade_count": 0 if trades_df is None else int(len(trades_df)),
    }


def save_backtest_run(strategy_id: str, codes: list[str], cfg: BacktestConfig, result: dict[str, Any], db_path: Path | str = DB_PATH) -> str:
    init_db(db_path)
    run_id = datetime.now().strftime("BT%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
    metrics = result.get("metrics") or {}
    trades = result.get("trades")
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs(run_id, created_at, strategy_id, codes, start_date, end_date, initial_cash, final_value, total_return, annual_return, max_drawdown, win_rate, trade_count, note)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), strategy_id, ",".join(codes), cfg.start_date, cfg.end_date or "",
                cfg.initial_cash, metrics.get("final_value"), metrics.get("total_return"), metrics.get("annual_return"), metrics.get("max_drawdown"), metrics.get("win_rate"), metrics.get("trade_count"), "script_backtest",
            ),
        )
        if trades is not None and not trades.empty:
            rows = []
            for r in trades.itertuples(index=False):
                rows.append((run_id, str(r.datetime), str(r.code), str(r.name), str(r.action), float(r.price), int(r.shares), float(r.cash_after), int(r.position_after), str(r.reason)))
            conn.executemany("INSERT INTO backtest_trades VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    return run_id
