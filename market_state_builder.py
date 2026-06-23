# -*- coding: utf-8 -*-
"""把行情、日K、分时、虚拟持仓整理成 AI 可读的 market_state。"""
from __future__ import annotations

from typing import Any

import pandas as pd

from data_tencent import fetch_daily_kline_tencent, fetch_intraday_minute, fetch_quotes_df
from indicators import add_indicators
from paper_trader import get_position, load_positions


def _f(x, default=None):
    try:
        if x is None or pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def _last_value(df: pd.DataFrame, col: str, default=None):
    if df is None or df.empty or col not in df.columns:
        return default
    return _f(df.iloc[-1].get(col), default)


def describe_intraday(minute: pd.DataFrame) -> tuple[str | None, dict[str, Any]]:
    if minute is None or minute.empty or "close" not in minute.columns:
        return None, {"intraday_available": False}
    df = minute.copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    if df.empty:
        return None, {"intraday_available": False}
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else last
    avg = float(df["close"].mean())
    high = float(df["close"].max())
    low = float(df["close"].min())

    if last >= avg and last >= prev:
        status = "分时站上均价线，回踩后重新走强"
    elif last >= avg:
        status = "分时站上均价线，但动能一般"
    elif last < avg and last < prev:
        status = "跌破分时均价线后偏弱"
    else:
        status = "分时均价线附近震荡"

    return status, {
        "intraday_available": True,
        "intraday_last": round(last, 4),
        "intraday_avg": round(avg, 4),
        "intraday_high": round(high, 4),
        "intraday_low": round(low, 4),
        "intraday_above_avg": last >= avg,
        "intraday_rising": last >= prev,
    }


def describe_volume(k: pd.DataFrame) -> tuple[str | None, dict[str, Any]]:
    if k is None or k.empty or "volume" not in k.columns:
        return None, {"volume_available": False}
    df = k.copy()
    if "VOL5" not in df.columns:
        df = add_indicators(df)
    last_vol = _last_value(df, "volume")
    vol5 = _last_value(df, "VOL5")
    ratio = _last_value(df, "volume_ratio")
    if not last_vol or not vol5:
        return None, {"volume_available": False}

    if ratio is None:
        ratio = last_vol / vol5 if vol5 else None
    if ratio is None:
        return None, {"volume_available": False}

    if 1.05 <= ratio <= 1.8:
        status = "成交量温和放大"
    elif ratio > 1.8:
        status = "成交量明显放大"
    elif ratio < 0.8:
        status = "成交量缩量"
    else:
        status = "成交量正常"

    return status, {
        "volume_available": True,
        "last_volume": round(last_vol, 2),
        "vol5": round(vol5, 2),
        "volume_ratio": round(float(ratio), 3),
    }


def build_market_state(code: str, name: str | None = None, strategy_id: str | None = None, virtual_cash: float = 100000.0, max_positions: int = 3) -> dict[str, Any]:
    code = str(code).zfill(6)[-6:]

    quote = fetch_quotes_df([code])
    qr = quote.iloc[0].to_dict() if quote is not None and not quote.empty else {}
    quote_name = str(qr.get("name") or name or code)

    daily = add_indicators(fetch_daily_kline_tencent(code, limit=260))
    minute = fetch_intraday_minute(code, "1")

    price = _f(qr.get("price"), None)
    if price is None:
        price = _last_value(daily, "close")

    ma5 = _last_value(daily, "MA5")
    ma10 = _last_value(daily, "MA10")
    ma20 = _last_value(daily, "MA20")
    ma60 = _last_value(daily, "MA60")
    close = _last_value(daily, "close")
    open_p = _last_value(daily, "open")
    high = _last_value(daily, "high")
    low = _last_value(daily, "low")
    high_20d = _last_value(daily, "high_20d")
    low_20d = _last_value(daily, "low_20d")

    intraday_status, intraday_metrics = describe_intraday(minute)
    volume_status, volume_metrics = describe_volume(daily)

    pos = get_position(code)
    positions = load_positions()
    holding = bool(pos.get("holding"))
    holding_volume = int(pos.get("volume") or 0)
    cost_price = pos.get("cost_price")
    current_market_value = float(price or 0) * holding_volume
    current_position_pct = current_market_value / float(virtual_cash or 1) if virtual_cash else 0

    max_positions_reached = len(positions) >= int(max_positions or 3) and not holding
    if max_positions_reached:
        position_limit = "最大持仓数量已满"
    elif holding:
        position_limit = "当前持仓中，允许按策略减仓/清仓，是否加仓需看策略限制"
    else:
        position_limit = "允许首次建仓"

    trend = "数据不足"
    if price is not None and ma20 is not None:
        if price < ma20:
            trend = "趋势破坏"
        elif ma5 is not None and ma10 is not None and ma5 >= ma10 >= ma20:
            trend = "趋势未坏，多头排列"
        else:
            trend = "趋势未坏，但均线结构一般"

    distance_ma5_pct = None
    distance_ma10_pct = None
    distance_ma20_pct = None
    if price is not None and ma5:
        distance_ma5_pct = (price / ma5 - 1) * 100
    if price is not None and ma10:
        distance_ma10_pct = (price / ma10 - 1) * 100
    if price is not None and ma20:
        distance_ma20_pct = (price / ma20 - 1) * 100

    state = {
        "code": code,
        "name": quote_name,
        "strategy_id": strategy_id,
        "price": round(float(price), 4) if price is not None else None,
        "pct_change": _f(qr.get("pct_change"), None),
        "amount_yi": _f(qr.get("amount_yi"), None),
        "update_time": qr.get("update_time", ""),
        "ma5": round(float(ma5), 4) if ma5 is not None else None,
        "ma10": round(float(ma10), 4) if ma10 is not None else None,
        "ma20": round(float(ma20), 4) if ma20 is not None else None,
        "ma60": round(float(ma60), 4) if ma60 is not None else None,
        "close": round(float(close), 4) if close is not None else None,
        "open": round(float(open_p), 4) if open_p is not None else None,
        "high": round(float(high), 4) if high is not None else None,
        "low": round(float(low), 4) if low is not None else None,
        "high_20d": round(float(high_20d), 4) if high_20d is not None else None,
        "low_20d": round(float(low_20d), 4) if low_20d is not None else None,
        "distance_ma5_pct": round(float(distance_ma5_pct), 3) if distance_ma5_pct is not None else None,
        "distance_ma10_pct": round(float(distance_ma10_pct), 3) if distance_ma10_pct is not None else None,
        "distance_ma20_pct": round(float(distance_ma20_pct), 3) if distance_ma20_pct is not None else None,
        "trend": trend,
        "holding": holding,
        "holding_volume": holding_volume,
        "cost_price": cost_price,
        "current_market_value": round(current_market_value, 2),
        "current_position_pct": round(current_position_pct, 4),
        "intraday_status": intraday_status,
        "volume_status": volume_status,
        "position_limit": position_limit,
        "max_positions_reached": max_positions_reached,
    }
    state.update(intraday_metrics)
    state.update(volume_metrics)
    return state
