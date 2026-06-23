# -*- coding: utf-8 -*-
"""趋势波段评分、日K趋势分类与交易剧本。"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from config import ADD_SCORE, TRY_SCORE, WATCH_SCORE, MAX_20D_RISE, PULLBACK_RANGE


def _is_num(x) -> bool:
    try:
        return x is not None and not pd.isna(x) and math.isfinite(float(x))
    except Exception:
        return False


def classify_suggestion(score: int) -> str:
    if score >= ADD_SCORE:
        return "可加仓"
    if score >= TRY_SCORE:
        return "可试仓"
    if score >= WATCH_SCORE:
        return "观察"
    return "不操作"


def classify_daily_k_trend(
    close: float,
    prev_close: float | None,
    ma5: Any,
    ma10: Any,
    ma20: Any,
    prev_high_20: Any,
    prev_low_20: Any,
    volume_expand: bool,
    volume_shrink: bool,
) -> tuple[str, str]:
    """按波段语境对日K结构做分类。

    分类目的不是预测涨跌，而是把盘面结构分清楚：
    - 突破主升：多头排列 + 收盘突破20日前高 + 站上五日线。
    - 趋势主升：多头排列 + 收盘站上五日线，但尚未突破前高。
    - 缩量回踩：趋势未坏，靠近MA10/MA20并缩量。
    - 反抽：整体趋势偏弱，但短线向上修复，容易冲高回落。
    - 完全弱：跌破MA20且均线空头/跌破前低，暂不适合波段进攻。
    - 震荡观察：介于强弱之间，等待方向选择。
    """
    if not (_is_num(close) and _is_num(ma5) and _is_num(ma10) and _is_num(ma20)):
        return "数据不足", "均线数据不足，暂不做日K趋势分类。"

    close_f = float(close)
    ma5_f = float(ma5)
    ma10_f = float(ma10)
    ma20_f = float(ma20)

    strong_alignment = ma5_f > ma10_f > ma20_f
    weak_alignment = ma5_f < ma10_f < ma20_f
    above_ma5 = close_f >= ma5_f
    above_ma20 = close_f >= ma20_f

    is_breakout = _is_num(prev_high_20) and close_f > float(prev_high_20)
    is_breakdown = _is_num(prev_low_20) and close_f < float(prev_low_20)
    near_ma10 = abs(close_f / ma10_f - 1) <= PULLBACK_RANGE if ma10_f else False
    near_ma20 = abs(close_f / ma20_f - 1) <= PULLBACK_RANGE if ma20_f else False
    is_rebound = _is_num(prev_close) and close_f > float(prev_close)

    if is_breakout and strong_alignment and above_ma5:
        return "突破主升", "多头排列，收盘突破20日前高，且站上五日线。"

    if strong_alignment and above_ma5:
        return "趋势主升", "MA5>MA10>MA20，收盘站上五日线，趋势处于主升观察区。"

    if above_ma20 and (near_ma10 or near_ma20) and volume_shrink:
        return "缩量回踩", "趋势未破，价格靠近MA10/MA20并缩量，属于波段回踩观察。"

    if (not above_ma20) and (weak_alignment or is_breakdown):
        return "完全弱", "收盘跌破MA20，且均线空头或跌破20日前低，波段进攻条件不足。"

    if (not above_ma20) and (is_rebound or close_f >= ma5_f):
        return "反抽", "股价仍在MA20下方，短线反弹修复，需警惕冲高回落。"

    if above_ma20:
        return "趋势未坏", "收盘仍在MA20上方，但主升结构尚未完全确认。"

    return "震荡观察", "日K结构处于强弱过渡区，等待重新站上关键均线。"


def evaluate_stock(df: pd.DataFrame, code: str, name: str) -> dict[str, Any] | None:
    if df is None or df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None
    prev_high_20 = df["high"].iloc[-21:-1].max() if "high" in df.columns and len(df) > 21 else None
    prev_low_20 = df["low"].iloc[-21:-1].min() if "low" in df.columns and len(df) > 21 else None

    close = float(last.get("close", 0) or 0)
    prev_close = float(prev.get("close")) if prev is not None and _is_num(prev.get("close")) else None
    ma5 = last.get("MA5")
    ma10 = last.get("MA10")
    ma20 = last.get("MA20")
    volume_shrink = bool(last.get("volume_shrink", False))
    volume_expand = bool(last.get("volume_expand", False))
    rise_20d = last.get("rise_20d")

    score = 0
    reasons: list[str] = []

    if _is_num(ma5) and _is_num(ma10) and _is_num(ma20) and ma5 > ma10 > ma20:
        score += 30
        trend_status = "强趋势"
        reasons.append("MA5>MA10>MA20，多头排列")
    elif _is_num(ma20) and close > float(ma20):
        score += 15
        trend_status = "趋势未坏"
        reasons.append("收盘价仍在MA20上方")
    else:
        score -= 20
        trend_status = "弱势"
        reasons.append("收盘价低于MA20或均线结构偏弱")

    daily_k_trend, daily_k_reason = classify_daily_k_trend(
        close=close,
        prev_close=prev_close,
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        prev_high_20=prev_high_20,
        prev_low_20=prev_low_20,
        volume_expand=volume_expand,
        volume_shrink=volume_shrink,
    )
    reasons.append(daily_k_reason)

    if daily_k_trend == "突破主升":
        score += 10
    elif daily_k_trend == "趋势主升":
        score += 5
    elif daily_k_trend == "反抽":
        score -= 5
    elif daily_k_trend == "完全弱":
        score -= 15

    if _is_num(ma5):
        ma5_deviation_pct = round((close / float(ma5) - 1) * 100, 2)
        ma5_relation = "站上五日线" if close >= float(ma5) else "跌破五日线"
    else:
        ma5_deviation_pct = None
        ma5_relation = "五日线不足"

    if volume_expand:
        score += 15
        volume_status = "放量"
        reasons.append("成交量大于5日均量的1.5倍")
    elif volume_shrink:
        score += 10
        volume_status = "缩量"
        reasons.append("成交量小于5日均量")
    else:
        score += 5
        volume_status = "正常"
        reasons.append("量能正常")

    is_breakout = False
    if _is_num(prev_high_20) and close > float(prev_high_20):
        is_breakout = True
        score += 30
        buy_point = "突破"
        reasons.append("收盘价突破20日前高")
    else:
        buy_point = "趋势观察"

    near_ma10 = _is_num(ma10) and abs(close / float(ma10) - 1) <= PULLBACK_RANGE
    near_ma20 = _is_num(ma20) and abs(close / float(ma20) - 1) <= PULLBACK_RANGE
    is_pullback = bool((near_ma10 or near_ma20) and volume_shrink and _is_num(ma20) and close >= float(ma20))

    if is_pullback:
        score += 25
        buy_point = "缩量回踩"
        reasons.append("价格靠近MA10/MA20且缩量，符合回踩观察条件")
    elif not is_breakout:
        score += 10 if trend_status in ["强趋势", "趋势未坏"] else -10

    if _is_num(rise_20d) and float(rise_20d) > MAX_20D_RISE:
        score -= 15
        reasons.append("20日涨幅偏高，追高风险增加")

    support_candidates = [x for x in [ma20, prev_low_20] if _is_num(x)]
    support = round(max(support_candidates), 2) if support_candidates else None
    stop_loss = round(float(ma20), 2) if _is_num(ma20) else support
    pressure = round(float(prev_high_20), 2) if _is_num(prev_high_20) else None
    final_score = int(max(0, min(100, score)))

    return {
        "code": str(code).zfill(6),
        "name": name,
        "close": round(close, 2),
        "score": final_score,
        "suggestion": classify_suggestion(final_score),
        "daily_k_trend": daily_k_trend,
        "trend_status": trend_status,
        "ma5_relation": ma5_relation,
        "ma5_deviation_pct": ma5_deviation_pct,
        "volume_status": volume_status,
        "buy_point": buy_point,
        "is_breakout": is_breakout,
        "is_pullback": is_pullback,
        "MA5": round(float(ma5), 2) if _is_num(ma5) else None,
        "MA10": round(float(ma10), 2) if _is_num(ma10) else None,
        "MA20": round(float(ma20), 2) if _is_num(ma20) else None,
        "support": support,
        "pressure": pressure,
        "stop_loss": stop_loss,
        "rise_20d": round(float(rise_20d) * 100, 2) if _is_num(rise_20d) else None,
        "reason": "；".join(reasons),
    }


def generate_trade_script(row: dict[str, Any]) -> str:
    name = row.get("name", "目标股票")
    close = row.get("close", "--")
    support = row.get("support", "--")
    pressure = row.get("pressure", "--")
    stop_loss = row.get("stop_loss", "--")
    suggestion = row.get("suggestion", "观察")
    trend = row.get("trend_status", "--")
    daily_k_trend = row.get("daily_k_trend", "--")
    ma5_relation = row.get("ma5_relation", "--")
    ma5 = row.get("MA5", "--")
    buy_point = row.get("buy_point", "--")
    score = row.get("score", "--")

    return f"""
{name} 交易剧本

当前价格：{close}
日K趋势：{daily_k_trend}
趋势状态：{trend}
五日线状态：{ma5_relation}，MA5={ma5}
买点类型：{buy_point}
评分：{score}
系统建议：{suggestion}

买入区间：
- 优先观察支撑位附近：{support}
- 若缩量回踩MA10/MA20并企稳，可考虑小仓试探。
- 若放量突破压力位：{pressure}，可考虑确认仓，但不追满仓。

加仓条件：
- 日K处于“突破主升”或“趋势主升”。
- 价格站上五日线，板块同步走强。
- 个股放量突破或回踩后重新转强。
- 加仓只做100股或小比例确认，不一次打满。

减仓条件：
- 日K转为“反抽”且冲高回落。
- 跌破五日线后无法快速收回。
- 跌破MA10且量能放大。
- 板块强度明显下降。

止损条件：
- 日K转为“完全弱”。
- 跌破MA20或前低。
- 参考止损位：{stop_loss}

风险提示：
- 本系统不自动下单。
- 评分只代表规则匹配程度，不代表确定性预测。
- 最终买卖由你人工决策。
""".strip()
