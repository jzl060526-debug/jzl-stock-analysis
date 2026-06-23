# -*- coding: utf-8 -*-
"""腾讯行情接口模块。所有外部行情尽量从腾讯接口获取。"""
from __future__ import annotations

import re
from typing import Iterable

import pandas as pd
import requests

TENCENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://gu.qq.com/",
}


def pure_code(code: str) -> str:
    """提取6位股票/指数代码。"""
    return re.sub(r"\D", "", str(code)).zfill(6)[-6:]


def market_prefix(code: str) -> str:
    """根据A股代码推断腾讯市场前缀。"""
    raw = str(code).lower().strip()
    if raw.startswith(("sh", "sz", "bj")) and len(raw) >= 8:
        return raw[:2]

    c = pure_code(code)
    if c.startswith(("6", "9")):
        return "sh"
    if c.startswith(("8", "4")):
        return "bj"
    return "sz"


def normalize_symbol(code: str) -> str:
    """转成腾讯行情符号，如 sh603876 / sz000878。"""
    raw = str(code).lower().strip()
    if raw.startswith(("sh", "sz", "bj")) and len(raw) >= 8:
        return raw[:2] + pure_code(raw)
    return f"{market_prefix(code)}{pure_code(code)}"


def _safe_float(x, default=None):
    try:
        if x in [None, "", "--", "-", "None"]:
            return default
        return float(x)
    except Exception:
        return default


def _request_text(url: str, *, timeout: int = 10) -> str:
    resp = requests.get(url, timeout=timeout, headers=TENCENT_HEADERS)
    resp.raise_for_status()
    # 腾讯 qt 接口通常是 GBK；如果失败，再让 requests 自动猜。
    try:
        resp.encoding = "gbk"
        return resp.text
    except Exception:
        return resp.content.decode("gbk", errors="ignore")


def fetch_quotes_df(codes: Iterable[str], chunk_size: int = 80) -> pd.DataFrame:
    """批量获取腾讯实时行情。

    输入可以是 603876 / sh603876 / sz399001。
    输出字段统一为 V2 系统使用的字段。
    """
    symbols = [normalize_symbol(c) for c in codes]
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return pd.DataFrame()

    rows = []

    for i in range(0, len(symbols), chunk_size):
        part = symbols[i:i + chunk_size]
        url = "https://qt.gtimg.cn/q=" + ",".join(part)
        try:
            text = _request_text(url, timeout=10)
        except Exception as e:
            print(f"[ERROR] 腾讯实时行情失败：{e}")
            continue

        for line in text.replace(";\r\n", ";\n").split(";\n"):
            if "~" not in line or "=\"" not in line:
                continue
            try:
                symbol = line.split("=")[0].replace("v_", "").strip()
                raw = line.split('"')[1]
                parts = raw.split("~")
                if len(parts) < 40:
                    continue

                code = pure_code(parts[2])
                name = parts[1]
                price = _safe_float(parts[3])
                pre_close = _safe_float(parts[4])
                open_price = _safe_float(parts[5])
                volume_hand = _safe_float(parts[6])
                change = _safe_float(parts[31]) if len(parts) > 31 else None
                pct_change = _safe_float(parts[32]) if len(parts) > 32 else None
                high = _safe_float(parts[33]) if len(parts) > 33 else None
                low = _safe_float(parts[34]) if len(parts) > 34 else None
                amount_wan = _safe_float(parts[37]) if len(parts) > 37 else None
                turnover = _safe_float(parts[38]) if len(parts) > 38 else None
                update_time = parts[30] if len(parts) > 30 else ""

                amount_yi = round((amount_wan or 0) / 10000, 3) if amount_wan is not None else None

                rows.append({
                    "symbol": symbol,
                    "code": code,
                    "name": name,
                    "price": price,
                    "pct_change": pct_change,
                    "pct_chg": pct_change,
                    "change": change,
                    "open": open_price,
                    "pre_close": pre_close,
                    "high": high,
                    "low": low,
                    "volume_hand": volume_hand,
                    "volume": volume_hand,
                    "amount_yi": amount_yi,
                    "amount": amount_yi * 1e8 if amount_yi is not None else None,
                    "turnover": turnover,
                    "update_time": update_time,
                })
            except Exception as e:
                print(f"[WARN] 腾讯行情解析失败：{e}")

    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ["price", "pct_change", "pct_chg", "change", "open", "pre_close", "high", "low", "volume", "amount", "amount_yi", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _parse_kline_rows(rows) -> pd.DataFrame:
    parsed = []
    for r in rows or []:
        parts = r.split(" ") if isinstance(r, str) else list(r)
        if len(parts) < 6:
            continue
        try:
            parsed.append({
                "date": pd.to_datetime(str(parts[0]), errors="coerce"),
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]) if len(parts) > 6 else None,
                "pct_chg": None,
                "turnover": None,
            })
        except Exception:
            continue
    df = pd.DataFrame(parsed)
    if not df.empty:
        df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return df


def fetch_daily_kline_tencent(code: str, limit: int = 260) -> pd.DataFrame:
    """腾讯复权日K。"""
    symbol = normalize_symbol(code)
    param = f"{symbol},day,,,{limit},qfq"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    try:
        resp = requests.get(url, params={"param": param}, timeout=12, headers=TENCENT_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        node = data.get("data", {}).get(symbol, {})
        rows = node.get("qfqday") or node.get("day") or []
        return _parse_kline_rows(rows)
    except Exception as e:
        print(f"[ERROR] 腾讯日K失败：{code} {e}")
        return pd.DataFrame()


def fetch_intraday_minute(code: str, period: str = "5") -> pd.DataFrame:
    """腾讯分钟线：支持 1/5/15/30/60。"""
    symbol = normalize_symbol(code)
    period = str(period)
    url = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
    param = f"{symbol},m{period},,,320"
    try:
        resp = requests.get(url, params={"param": param}, timeout=10, headers=TENCENT_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        node = data.get("data", {}).get(symbol, {})
        rows = node.get(f"m{period}", []) or []
    except Exception as e:
        print(f"[ERROR] 腾讯分钟线失败：{code} {e}")
        return pd.DataFrame()

    parsed = []
    for r in rows:
        parts = r.split(" ") if isinstance(r, str) else list(r)
        if len(parts) < 5:
            continue
        try:
            parsed.append({
                "datetime": pd.to_datetime(str(parts[0]), errors="coerce"),
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]) if len(parts) > 5 else None,
            })
        except Exception:
            continue

    df = pd.DataFrame(parsed)
    if not df.empty:
        df = df.dropna(subset=["datetime", "close"]).sort_values("datetime").reset_index(drop=True)
    return df
