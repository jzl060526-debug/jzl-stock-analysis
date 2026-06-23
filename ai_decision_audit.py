# -*- coding: utf-8 -*-
"""AI 决策审计器：AI 可以建议，代码负责批准/拦截。"""
from __future__ import annotations

from typing import Any

ALLOWED_ACTIONS = {"WATCH", "NO_ACTION", "PAPER_BUY", "PAPER_ADD", "PAPER_SELL", "PAPER_CLEAR"}
TRADE_ACTIONS = {"PAPER_BUY", "PAPER_ADD", "PAPER_SELL", "PAPER_CLEAR"}
BUY_ACTIONS = {"PAPER_BUY", "PAPER_ADD"}
SELL_ACTIONS = {"PAPER_SELL", "PAPER_CLEAR"}


def _blocked(data: dict[str, Any], action: str, reason: list[str], risk: list[str] | None = None) -> dict[str, Any]:
    return {
        "action": action,
        "code": data.get("code"),
        "name": data.get("name"),
        "strategy_id": data.get("strategy_id"),
        "reason": reason,
        "risk": risk or [],
        "order": None,
        "need_human_review": True,
        "audit_status": "blocked" if action in {"WATCH", "NO_ACTION"} else "passed",
    }


def audit_ai_decision(market_state: dict[str, Any], decision: dict[str, Any], strategy: dict[str, Any] | None = None) -> dict[str, Any]:
    """审计本地 AI 输出，防止乱买、越权、缺字段、仓位超限。"""
    if not isinstance(decision, dict):
        return _blocked(market_state, "NO_ACTION", ["AI输出不是JSON对象，已拦截"], [str(type(decision))])

    action = decision.get("action")
    if action not in ALLOWED_ACTIONS:
        return _blocked(market_state, "NO_ACTION", ["AI输出了非法action，已拦截"], [f"非法action：{action}"])

    strategy = strategy or {}
    allowed_by_strategy = set(strategy.get("allowed_actions") or ALLOWED_ACTIONS)
    if action not in allowed_by_strategy:
        return _blocked(market_state, "WATCH", ["AI动作不在当前策略允许范围内，已拦截"], [f"当前策略不允许：{action}"])

    # 非交易动作允许 order = null
    if action in {"WATCH", "NO_ACTION"}:
        out = decision.copy()
        out.setdefault("code", market_state.get("code"))
        out.setdefault("name", market_state.get("name"))
        out.setdefault("strategy_id", market_state.get("strategy_id"))
        out["order"] = None
        out.setdefault("need_human_review", True)
        out["audit_status"] = "passed"
        return out

    # 交易动作必须有 order
    order = decision.get("order")
    if not isinstance(order, dict):
        return _blocked(market_state, "WATCH", ["AI给出交易动作，但order缺失或格式错误，已拦截"], ["缺少price_mode/position_pct"])
    if "price_mode" not in order:
        return _blocked(market_state, "WATCH", ["AI给出交易动作，但order缺少price_mode，已拦截"], ["缺少price_mode"])
    if "position_pct" not in order:
        return _blocked(market_state, "WATCH", ["AI给出交易动作，但order缺少position_pct，已拦截"], ["缺少position_pct"])

    try:
        pct = float(order.get("position_pct"))
    except Exception:
        return _blocked(market_state, "WATCH", ["AI给出的position_pct不是数字，已拦截"], [str(order.get("position_pct"))])

    if pct <= 0 or pct > 1:
        return _blocked(market_state, "WATCH", ["AI给出的position_pct越界，已拦截"], [f"position_pct={pct}"])

    # 买入/加仓强制检查数据完整性与趋势风控
    if action in BUY_ACTIONS:
        missing = []
        if not market_state.get("intraday_status"):
            missing.append("缺少分时承接状态")
        if not market_state.get("volume_status"):
            missing.append("缺少成交量状态")
        if not market_state.get("position_limit"):
            missing.append("缺少仓位限制")
        if market_state.get("max_positions_reached") is True:
            missing.append("最大持仓数量已满")
        if missing:
            return _blocked(market_state, "WATCH", ["AI尝试买入/加仓，但数据不足或仓位不允许，已被代码风控拦截"], missing)

        price = market_state.get("price")
        ma20 = market_state.get("ma20")
        if price is not None and ma20 is not None:
            try:
                if float(price) < float(ma20):
                    return _blocked(market_state, "WATCH", ["AI尝试买入/加仓，但价格低于MA20，已拦截"], ["趋势位置不合格"])
            except Exception:
                pass
        if str(market_state.get("trend")) == "趋势破坏":
            return _blocked(market_state, "WATCH", ["AI尝试买入/加仓，但趋势已经破坏，已拦截"], ["趋势破坏禁止开仓"])

        risk_cfg = strategy.get("risk_control") or {}
        max_single = risk_cfg.get("max_single_stock_pct")
        current_pct = market_state.get("current_position_pct", 0) or 0
        try:
            if max_single is not None and float(current_pct) + pct > float(max_single) + 1e-9:
                return _blocked(market_state, "WATCH", ["AI买入/加仓后会超过单票仓位上限，已拦截"], [f"当前{current_pct:.2f}，新增{pct:.2f}，上限{max_single}"])
        except Exception:
            pass

    # 卖出/清仓必须已经持仓
    if action in SELL_ACTIONS and not market_state.get("holding"):
        return _blocked(market_state, "WATCH", ["AI尝试卖出/清仓，但当前没有虚拟持仓，已拦截"], ["无持仓不可卖出"])

    out = decision.copy()
    out.setdefault("code", market_state.get("code"))
    out.setdefault("name", market_state.get("name"))
    out.setdefault("strategy_id", market_state.get("strategy_id"))
    out.setdefault("need_human_review", True)
    out["audit_status"] = "passed"
    return out
