# -*- coding: utf-8 -*-
"""JZL全市场评分引擎。"""
from __future__ import annotations
from typing import Any
import pandas as pd
from backtester import prepare_daily_indicators
from strategy_engine import build_conditions

def _f(x, default=None):
    try:
        if x is None or pd.isna(x): return default
        return float(x)
    except Exception:
        return default

def prepare_score_frame(daily_df: pd.DataFrame, trade_strategy: dict[str, Any] | None = None) -> pd.DataFrame:
    x = prepare_daily_indicators(daily_df, trade_strategy)
    x["ret20_pct"] = x["close"].pct_change(20) * 100
    x["ret60_pct"] = x["close"].pct_change(60) * 100
    x["amount_yi"] = pd.to_numeric(x.get("amount", 0), errors="coerce") / 1e8
    x["volatility20_pct"] = x["close"].pct_change().rolling(20).std() * (252 ** 0.5) * 100
    x["high_20d"] = x["high"].rolling(20).max().shift(1)
    x["low_20d"] = x["low"].rolling(20).min().shift(1)
    return x

def _state_from_last_row(row: pd.Series) -> dict[str, Any]:
    close = _f(row.get("close")); ma5 = _f(row.get("ma5")); ma10 = _f(row.get("ma10")); ma20 = _f(row.get("ma20"))
    return {
        "price": close, "open": _f(row.get("open")), "high": _f(row.get("high")), "low": _f(row.get("low")), "close": close,
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": _f(row.get("ma60")),
        "high_20d": _f(row.get("high_20d") or row.get("prev_20_high")), "low_20d": _f(row.get("low_20d")),
        "volume_ratio": _f(row.get("volume_ratio")), "pct_change": _f(row.get("ret_pct"), 0) or 0,
        "distance_ma5_pct": _f(row.get("distance_ma5_pct")),
        "distance_ma10_pct": (close / ma10 - 1) * 100 if close and ma10 else None,
        "distance_ma20_pct": (close / ma20 - 1) * 100 if close and ma20 else None,
        "intraday_available": False, "intraday_above_avg": False, "intraday_rising": False,
        "volume_available": _f(row.get("volume_ratio")) is not None,
        "holding": False, "max_positions_reached": False,
    }

def _build_extended_conditions(row: pd.Series, base: dict[str, bool], scoring: dict[str, Any]) -> dict[str, bool]:
    p = scoring.get("parameters") or {}
    min_price = float(p.get("min_price", 2.0)); max_price = float(p.get("max_price", 300.0)); min_amount_yi = float(p.get("min_amount_yi", 0.30))
    ret20_good_pct = float(p.get("recent_ret20_good_pct", 5.0)); ret60_good_pct = float(p.get("recent_ret60_good_pct", 10.0))
    max_down = float(p.get("max_down_day_pct", -7.0)); vol_warn = float(p.get("volatility_warning_pct", 80.0))
    max_dist = float(p.get("max_distance_ma5_penalty_pct", 8.0)); severe_dist = float(p.get("severe_distance_ma5_penalty_pct", 12.0))
    close = _f(row.get("close"), 0) or 0; amount_yi = _f(row.get("amount_yi"), 0) or 0
    ret20 = _f(row.get("ret20_pct"), 0) or 0; ret60 = _f(row.get("ret60_pct"), 0) or 0
    day_ret = _f(row.get("ret_pct"), 0) or 0; vol20 = _f(row.get("volatility20_pct"), 0) or 0
    dist_ma5 = _f(row.get("distance_ma5_pct"), 0) or 0
    ext = dict(base)
    ext.update({
        "sufficient_daily_data": bool(not base.get("insufficient_daily_data", True)),
        "price_in_reasonable_range": min_price <= close <= max_price,
        "liquidity_ok": amount_yi >= min_amount_yi,
        "liquidity_weak": amount_yi < min_amount_yi,
        "amount_ok": amount_yi >= min_amount_yi,
        "ret20_positive": ret20 > 0,
        "ret60_positive": ret60 > 0,
        "ret20_good": ret20 >= ret20_good_pct,
        "ret60_good": ret60 >= ret60_good_pct,
        "not_price_below_ma20": not base.get("price_below_ma20", False),
        "not_trend_broken": not base.get("trend_broken", False),
        "not_volume_big_drop": not base.get("volume_big_drop", False),
        "not_high_volume_upper_shadow_failed": not base.get("high_volume_upper_shadow_failed", False),
        "not_distance_ma5_too_high": dist_ma5 <= max_dist,
        "distance_ma5_not_too_high": dist_ma5 <= max_dist,
        "severe_distance_ma5_too_high": dist_ma5 > severe_dist,
        "big_down_day": day_ret <= max_down,
        "not_big_down_day": day_ret > max_down,
        "volatility_not_extreme": vol20 <= vol_warn or vol20 == 0,
    })
    return ext

def _condition_score(conditions: list[str], conds: dict[str, bool], weight: float):
    if not conditions: return 0.0, [], []
    hits = [c for c in conditions if conds.get(c, False)]
    missing = [c for c in conditions if not conds.get(c, False)]
    return weight * len(hits) / max(1, len(conditions)), hits, missing

def score_stock_daily(code: str, name: str, daily_df: pd.DataFrame, scoring_strategy: dict[str, Any], trade_strategy: dict[str, Any]) -> dict[str, Any]:
    if daily_df is None or daily_df.empty or len(daily_df) < int((scoring_strategy.get("parameters") or {}).get("min_history_bars", 80)):
        return {"code": str(code).zfill(6), "name": name, "score": 0.0, "candidate_level": "reject", "setup_type": "reject", "reason": "历史数据不足"}
    x = prepare_score_frame(daily_df, trade_strategy)
    row = x.iloc[-1]
    state = _state_from_last_row(row)
    base = build_conditions(state, trade_strategy)
    conds = _build_extended_conditions(row, base, scoring_strategy)
    filters = ((scoring_strategy.get("filters") or {}).get("must_pass") or [])
    failed_filters = [c for c in filters if not conds.get(c, False)]
    if failed_filters:
        return {"code": str(code).zfill(6), "name": name, "date": str(pd.to_datetime(row.get("date")).date()) if row.get("date") is not None else "", "score": 0.0, "candidate_level": "reject", "setup_type": "reject", "matched_conditions": "", "failed_filters": ";".join(failed_filters), "risk_flags": ";".join(failed_filters), "reason": "硬过滤未通过", "close": _f(row.get("close")), "amount_yi": _f(row.get("amount_yi")), "ret20_pct": _f(row.get("ret20_pct")), "ret60_pct": _f(row.get("ret60_pct")), "distance_ma5_pct": _f(row.get("distance_ma5_pct")), "volume_ratio": _f(row.get("volume_ratio"))}
    total = 0.0; matched_all = []; detail = {}
    for key, obj in (scoring_strategy.get("score_items") or {}).items():
        s, hits, _ = _condition_score(list(obj.get("conditions") or []), conds, float(obj.get("weight", 0)))
        total += s; matched_all.extend(hits); detail[key] = round(s, 2)
    risk_flags = []
    for cond, penalty in (scoring_strategy.get("risk_penalty") or {}).items():
        if conds.get(cond, False): total += float(penalty); risk_flags.append(cond)
    total = max(0.0, min(100.0, total))
    levels = scoring_strategy.get("candidate_level") or {}
    core = float(levels.get("core_candidate", 80)); watch = float(levels.get("watch_candidate", 70)); weak = float(levels.get("weak_watch", 60))
    level = "core_candidate" if total >= core else "watch_candidate" if total >= watch else "weak_watch" if total >= weak else "reject"
    if conds.get("breakout_20d_high") and conds.get("volume_mild_expand"):
        setup_type = "breakout_candidate"
    elif conds.get("price_pullback_to_ma5_or_ma10") and conds.get("pullback_volume_shrink"):
        setup_type = "pullback_candidate"
    elif conds.get("trend_not_broken") and conds.get("volume_healthy"):
        setup_type = "trend_candidate"
    else:
        setup_type = "watch"
    return {"code": str(code).zfill(6), "name": name, "date": str(pd.to_datetime(row.get("date")).date()) if row.get("date") is not None else "", "score": round(total, 2), "candidate_level": level, "setup_type": setup_type, "close": round(_f(row.get("close"), 0) or 0, 3), "amount_yi": round(_f(row.get("amount_yi"), 0) or 0, 3), "ret20_pct": round(_f(row.get("ret20_pct"), 0) or 0, 2), "ret60_pct": round(_f(row.get("ret60_pct"), 0) or 0, 2), "distance_ma5_pct": round(_f(row.get("distance_ma5_pct"), 0) or 0, 2), "volume_ratio": round(_f(row.get("volume_ratio"), 0) or 0, 2), "matched_conditions": ";".join(sorted(set(matched_all))), "failed_filters": "", "risk_flags": ";".join(risk_flags), "score_detail": detail, "reason": f"{level}｜{setup_type}｜score={round(total, 2)}"}
