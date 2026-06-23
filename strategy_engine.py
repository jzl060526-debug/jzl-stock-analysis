# -*- coding: utf-8 -*-
"""JZL策略规则引擎：脚本执行硬条件，AI只做解释与建议。"""
from __future__ import annotations

from typing import Any


def _num(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _pct_limit(strategy: dict[str, Any], key: str, default: float) -> float:
    try:
        return float((strategy.get("parameters") or {}).get(key, default))
    except Exception:
        return default


def build_conditions(state: dict[str, Any], strategy: dict[str, Any] | None = None) -> dict[str, bool]:
    strategy = strategy or {}
    price = _num(state.get("price"))
    open_p = _num(state.get("open"))
    high = _num(state.get("high"))
    low = _num(state.get("low"))
    close = _num(state.get("close"))
    ma5 = _num(state.get("ma5"))
    ma10 = _num(state.get("ma10"))
    ma20 = _num(state.get("ma20"))
    ma60 = _num(state.get("ma60"))
    high20 = _num(state.get("high_20d"))
    low20 = _num(state.get("low_20d"))
    dist_ma5 = _num(state.get("distance_ma5_pct"))
    dist_ma10 = _num(state.get("distance_ma10_pct"))
    dist_ma20 = _num(state.get("distance_ma20_pct"))
    vol_ratio = _num(state.get("volume_ratio"))
    pct_change = _num(state.get("pct_change"), 0)
    current_position_pct = _num(state.get("current_position_pct"), 0) or 0
    cost_price = _num(state.get("cost_price"))

    near_ma5_pct = _pct_limit(strategy, "near_ma5_pct", 2.5)
    near_ma10_pct = _pct_limit(strategy, "near_ma10_pct", 3.5)
    near_ma20_pct = _pct_limit(strategy, "near_ma20_pct", 4.5)
    max_dist_buy = _pct_limit(strategy, "max_distance_ma5_buy_pct", 6.0)
    max_dist_add = _pct_limit(strategy, "max_distance_ma5_add_pct", 4.5)
    far_above_ma5_reduce = _pct_limit(strategy, "far_above_ma5_reduce_pct", 8.0)
    vol_shrink_max = _pct_limit(strategy, "volume_shrink_max_ratio", 0.90)
    vol_healthy_min = _pct_limit(strategy, "volume_healthy_min_ratio", 0.60)
    vol_healthy_max = _pct_limit(strategy, "volume_healthy_max_ratio", 1.80)
    vol_mild_min = _pct_limit(strategy, "volume_mild_expand_min_ratio", 1.05)
    vol_mild_max = _pct_limit(strategy, "volume_mild_expand_max_ratio", 1.80)
    vol_big = _pct_limit(strategy, "volume_big_expand_ratio", 1.80)
    breakout_tol = _pct_limit(strategy, "breakout_high_tolerance_pct", 0.5)
    upper_shadow_pct = _pct_limit(strategy, "upper_shadow_pct", 3.0)
    big_drop_pct = _pct_limit(strategy, "big_drop_pct", -3.0)

    daily_ok = price is not None and ma5 is not None and ma10 is not None and ma20 is not None
    intraday_ok = bool(state.get("intraday_available"))
    volume_ok_data = bool(state.get("volume_available")) and vol_ratio is not None

    price_above_ma5 = price is not None and ma5 is not None and price > ma5
    price_above_ma10 = price is not None and ma10 is not None and price > ma10
    price_above_ma20 = price is not None and ma20 is not None and price > ma20
    price_below_ma10 = price is not None and ma10 is not None and price < ma10
    price_below_ma20 = price is not None and ma20 is not None and price < ma20

    ma5_above_ma10 = ma5 is not None and ma10 is not None and ma5 > ma10
    ma10_above_ma20 = ma10 is not None and ma20 is not None and ma10 > ma20
    ma20_above_ma60 = ma20 is not None and ma60 is not None and ma20 > ma60

    price_near_ma5 = dist_ma5 is not None and abs(dist_ma5) <= near_ma5_pct
    price_near_ma10 = dist_ma10 is not None and abs(dist_ma10) <= near_ma10_pct
    price_near_ma20 = dist_ma20 is not None and abs(dist_ma20) <= near_ma20_pct
    price_near_ma5_or_ma10_or_ma20 = price_near_ma5 or price_near_ma10 or price_near_ma20
    price_pullback_to_ma5_or_ma10 = price_near_ma5 or price_near_ma10

    breakout_20d_high = price is not None and high20 is not None and price >= high20 * (1 - breakout_tol / 100)
    near_major_resistance_without_breakout = high20 is not None and price is not None and price >= high20 * 0.97 and not breakout_20d_high

    volume_mild_expand = vol_ratio is not None and vol_mild_min <= vol_ratio <= vol_mild_max
    volume_big_expand = vol_ratio is not None and vol_ratio > vol_big
    pullback_volume_shrink = vol_ratio is not None and vol_ratio <= vol_shrink_max
    volume_healthy = vol_ratio is not None and vol_healthy_min <= vol_ratio <= vol_healthy_max
    volume_not_support = vol_ratio is not None and vol_ratio < 0.8
    volume_big_drop = volume_big_expand and pct_change <= big_drop_pct
    volume_up_price_stagnant = volume_big_expand and -0.5 <= pct_change <= 1.0

    intraday_above = bool(state.get("intraday_above_avg"))
    intraday_rising = bool(state.get("intraday_rising"))
    intraday_support_strong = intraday_ok and intraday_above and intraday_rising
    intraday_recover_vwap = intraday_ok and intraday_above
    intraday_failed_breakout = intraday_ok and not intraday_above and pct_change > 1.0
    weak_intraday_rebound = intraday_ok and not intraday_above
    weak_intraday_rebound_after_rise = weak_intraday_rebound and pct_change > 1.0

    upper_shadow_failed = False
    if high is not None and price is not None and price > 0:
        upper_shadow_failed = (high / price - 1) * 100 >= upper_shadow_pct
    high_volume_upper_shadow_failed = upper_shadow_failed and volume_big_expand

    high_volume_big_bearish_breakdown = volume_big_expand and price_below_ma20
    trend_broken = str(state.get("trend")) == "趋势破坏" or price_below_ma20
    trend_not_broken = daily_ok and not trend_broken and price_above_ma20
    price_below_ma20_and_trend_broken = price_below_ma20 and trend_broken

    already_holding = bool(state.get("holding"))
    profit_position = already_holding and cost_price is not None and price is not None and price > cost_price
    max_positions_reached = bool(state.get("max_positions_reached"))
    position_allowed = not max_positions_reached
    add_times_not_exceeded = True  # 当前版本尚未按单票统计加仓次数，预留为True

    distance_ma5_too_high = dist_ma5 is not None and dist_ma5 > max_dist_buy
    distance_ma5_too_high_for_add = dist_ma5 is not None and dist_ma5 > max_dist_add
    price_far_above_ma5 = dist_ma5 is not None and dist_ma5 > far_above_ma5_reduce

    pullback_then_recover = (price_near_ma5 or price_near_ma10 or price_near_ma20) and intraday_recover_vwap
    no_big_bearish_breakdown = not high_volume_big_bearish_breakdown and not trend_broken
    failed_rebound_after_breakdown = already_holding and trend_broken and weak_intraday_rebound

    # 板块/相对强度当前没有稳定数据源，先作为中性条件；后续接板块强度后再替换
    sector_strength_ok = bool(state.get("sector_strength_ok", True))
    stock_stronger_than_sector = bool(state.get("stock_stronger_than_sector", True))
    sector_turns_weak = bool(state.get("sector_turns_weak", False))
    sector_turns_weak_and_stock_breaks_ma10 = sector_turns_weak and price_below_ma10

    return {
        "insufficient_daily_data": not daily_ok,
        "insufficient_intraday_data": not intraday_ok,
        "insufficient_volume_data": not volume_ok_data,
        "sector_strength_ok": sector_strength_ok,
        "stock_stronger_than_sector": stock_stronger_than_sector,
        "sector_turns_weak": sector_turns_weak,
        "sector_turns_weak_and_stock_breaks_ma10": sector_turns_weak_and_stock_breaks_ma10,
        "price_above_ma5": price_above_ma5,
        "price_above_ma10": price_above_ma10,
        "price_above_ma20": price_above_ma20,
        "price_below_ma10": price_below_ma10,
        "price_below_ma20": price_below_ma20,
        "ma5_above_ma10": ma5_above_ma10,
        "ma10_above_ma20": ma10_above_ma20,
        "ma20_above_ma60": ma20_above_ma60,
        "trend_not_broken": trend_not_broken,
        "trend_broken": trend_broken,
        "price_below_ma20_and_trend_broken": price_below_ma20_and_trend_broken,
        "price_near_ma5": price_near_ma5,
        "price_near_ma10": price_near_ma10,
        "price_near_ma20": price_near_ma20,
        "price_near_ma5_or_ma10_or_ma20": price_near_ma5_or_ma10_or_ma20,
        "price_pullback_to_ma5_or_ma10": price_pullback_to_ma5_or_ma10,
        "breakout_20d_high": breakout_20d_high,
        "near_major_resistance_without_breakout": near_major_resistance_without_breakout,
        "volume_mild_expand": volume_mild_expand,
        "volume_big_expand": volume_big_expand,
        "pullback_volume_shrink": pullback_volume_shrink,
        "volume_healthy": volume_healthy,
        "volume_not_support": volume_not_support,
        "volume_big_drop": volume_big_drop,
        "volume_up_price_stagnant": volume_up_price_stagnant,
        "intraday_support_strong": intraday_support_strong,
        "intraday_recover_vwap": intraday_recover_vwap,
        "intraday_failed_breakout": intraday_failed_breakout,
        "weak_intraday_rebound": weak_intraday_rebound,
        "weak_intraday_rebound_after_rise": weak_intraday_rebound_after_rise,
        "pullback_then_recover": pullback_then_recover,
        "no_big_bearish_breakdown": no_big_bearish_breakdown,
        "high_volume_big_bearish_breakdown": high_volume_big_bearish_breakdown,
        "high_volume_upper_shadow_failed": high_volume_upper_shadow_failed,
        "failed_rebound_after_breakdown": failed_rebound_after_breakdown,
        "already_holding": already_holding,
        "not_holding": not already_holding,
        "profit_position": profit_position,
        "position_allowed": position_allowed,
        "max_positions_reached": max_positions_reached,
        "add_times_not_exceeded": add_times_not_exceeded,
        "distance_ma5_too_high": distance_ma5_too_high,
        "distance_ma5_too_high_for_add": distance_ma5_too_high_for_add,
        "price_far_above_ma5": price_far_above_ma5,
        "cost_not_too_high": True,
    }


def _conditions_list(rule_obj: Any) -> list[str]:
    if isinstance(rule_obj, dict):
        if isinstance(rule_obj.get("required_any"), list):
            return list(rule_obj.get("required_any") or [])
        if isinstance(rule_obj.get("required"), list):
            return list(rule_obj.get("required") or [])
        if isinstance(rule_obj.get("conditions"), list):
            return list(rule_obj.get("conditions") or [])
    if isinstance(rule_obj, list):
        return list(rule_obj)
    return []


def _hit_any(names: list[str], conditions: dict[str, bool]) -> list[str]:
    return [x for x in names if conditions.get(x, False)]


def _missing_all(names: list[str], conditions: dict[str, bool]) -> list[str]:
    return [x for x in names if not conditions.get(x, False)]


def evaluate_strategy(strategy: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """返回是否需要调用AI，以及触发类型。"""
    conditions = build_conditions(state, strategy)

    # 1. 强制清仓：硬风控最高优先级
    force_clear_rules = _conditions_list(((strategy.get("hard_risk_rules") or {}).get("force_clear") or {}))
    force_clear_hit = _hit_any(force_clear_rules, conditions)
    if state.get("holding") and force_clear_hit:
        return {
            "should_call_ai": True,
            "signal_type": "force_clear",
            "preferred_action": "PAPER_CLEAR",
            "reason": ["触发硬风控清仓规则"],
            "matched_conditions": force_clear_hit,
            "missing_required": [],
            "forbidden_hit": [],
            "conditions": conditions,
        }

    clear_rules = _conditions_list(strategy.get("clear_rules") or strategy.get("clear") or {})
    clear_hit = _hit_any(clear_rules, conditions)
    if state.get("holding") and clear_hit:
        return {
            "should_call_ai": True,
            "signal_type": "clear",
            "preferred_action": "PAPER_CLEAR",
            "reason": ["触发清仓规则"],
            "matched_conditions": clear_hit,
            "missing_required": [],
            "forbidden_hit": [],
            "conditions": conditions,
        }

    # 2. 减仓：持仓时优先于加仓
    reduce_rules = _conditions_list(((strategy.get("sell_rules") or {}).get("reduce") or {}))
    reduce_hit = _hit_any(reduce_rules, conditions)
    if state.get("holding") and reduce_hit:
        return {
            "should_call_ai": True,
            "signal_type": "reduce",
            "preferred_action": "PAPER_SELL",
            "reason": ["触发减仓观察规则"],
            "matched_conditions": reduce_hit,
            "missing_required": [],
            "forbidden_hit": [],
            "conditions": conditions,
        }

    # 3. 禁止买入：命中后直接WATCH，不调用AI
    forbid_buy_rules = _conditions_list(((strategy.get("hard_risk_rules") or {}).get("forbid_buy") or {}))
    hard_forbid_hit = _hit_any(forbid_buy_rules, conditions)

    # 4. 加仓：持仓时才看加仓规则
    add_cfg = strategy.get("add_rules") or {}
    add_required = list(add_cfg.get("required") or [])
    add_forbidden = list(add_cfg.get("forbidden") or [])
    add_missing = _missing_all(add_required, conditions)
    add_forbid_hit = _hit_any(add_forbidden, conditions)
    if state.get("holding") and add_required and not add_missing and not add_forbid_hit and not hard_forbid_hit:
        return {
            "should_call_ai": True,
            "signal_type": "add",
            "preferred_action": "PAPER_ADD",
            "reason": ["触发加仓规则"],
            "matched_conditions": add_required,
            "missing_required": [],
            "forbidden_hit": [],
            "conditions": conditions,
        }

    # 5. 首次买入：支持count_based
    buy_cfg = strategy.get("buy_rules") or {}
    buy_conditions = list(buy_cfg.get("conditions") or buy_cfg.get("required") or [])
    buy_forbidden = list(buy_cfg.get("forbidden") or [])
    buy_hits = _hit_any(buy_conditions, conditions)
    buy_missing = _missing_all(buy_conditions, conditions)
    buy_forbid_hit = _hit_any(buy_forbidden, conditions) + hard_forbid_hit
    buy_mode = buy_cfg.get("mode", "all_required")
    min_count = int(buy_cfg.get("required_min_count") or len(buy_conditions) or 0)

    if not state.get("holding") and buy_conditions:
        if buy_mode == "count_based":
            buy_ok = len(buy_hits) >= min_count
        else:
            buy_ok = len(buy_missing) == 0
        if buy_ok and not buy_forbid_hit:
            return {
                "should_call_ai": True,
                "signal_type": "buy_candidate",
                "preferred_action": "PAPER_BUY",
                "reason": [f"触发买入候选：满足{len(buy_hits)}/{len(buy_conditions)}条，要求至少{min_count}条"],
                "matched_conditions": buy_hits,
                "missing_required": buy_missing,
                "forbidden_hit": [],
                "conditions": conditions,
            }

    return {
        "should_call_ai": False,
        "signal_type": "watch",
        "preferred_action": "WATCH",
        "reason": ["当前未触发策略候选，或命中禁止项，代码层不调用AI"],
        "matched_conditions": buy_hits if 'buy_hits' in locals() else [],
        "missing_required": buy_missing if 'buy_missing' in locals() else [],
        "forbidden_hit": buy_forbid_hit if 'buy_forbid_hit' in locals() else hard_forbid_hit,
        "conditions": conditions,
    }
