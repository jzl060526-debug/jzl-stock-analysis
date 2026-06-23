# -*- coding: utf-8 -*-
"""腾讯接口版数据获取模块。

本文件不再调用 AkShare / 东方财富。
所有行情优先来自腾讯接口；接口失败时读取本地缓存，避免页面崩溃。
"""
from __future__ import annotations

import pandas as pd

from config import CACHE_DIR, CORE_POOL, DEFAULT_UNIVERSE, MIN_AMOUNT, SECTOR_STOCK_MAP, UNIVERSE_CSV
from data_tencent import fetch_daily_kline_tencent, fetch_quotes_df


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _read_cache(name: str) -> pd.DataFrame:
    path = CACHE_DIR / name
    if path.exists():
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _write_cache(df: pd.DataFrame, name: str) -> None:
    try:
        if df is not None and not df.empty:
            df.to_csv(CACHE_DIR / name, index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"[WARN] 写入缓存失败：{name} {e}")


def get_stock_universe_meta() -> dict[str, dict[str, str]]:
    """读取股票池元数据，包含名称和主题。"""
    if UNIVERSE_CSV.exists():
        try:
            df = pd.read_csv(UNIVERSE_CSV, dtype={"code": str}, encoding="utf-8-sig")
            if not df.empty and "code" in df.columns:
                if "name" not in df.columns:
                    df["name"] = df["code"]
                if "theme" not in df.columns:
                    df["theme"] = ""
                result: dict[str, dict[str, str]] = {}
                for _, row in df.iterrows():
                    code = str(row.get("code", "")).zfill(6)[-6:]
                    name = str(row.get("name", code))
                    theme = str(row.get("theme", ""))
                    if code and code != "000000":
                        result[code] = {"name": name, "theme": theme}
                if result:
                    return result
        except Exception as e:
            print(f"[WARN] 读取 stock_universe.csv 失败：{e}")

    return {str(code).zfill(6): {"name": name, "theme": "默认股票池"} for code, name in DEFAULT_UNIVERSE.items()}


def get_stock_universe() -> dict[str, str]:
    """读取腾讯扫描股票池。

    优先读取项目根目录 stock_universe.csv。
    CSV格式：code,name,theme
    如果文件不存在，使用 config.DEFAULT_UNIVERSE 兜底。
    """
    meta = get_stock_universe_meta()
    return {code: item.get("name", code) for code, item in meta.items()}

def _empty_spot_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "code", "name", "theme", "price", "pct_chg", "change", "volume", "amount", "amount_yi",
        "high", "low", "open", "pre_close", "turnover", "update_time",
    ])


def get_all_a_spot() -> pd.DataFrame:
    """腾讯股票池实时行情。

    注意：腾讯 qt 接口适合批量代码查询，但不负责提供完整全A股票名录。
    因此这里使用 stock_universe.csv / DEFAULT_UNIVERSE 作为股票池。
    """
    universe_meta = get_stock_universe_meta()
    universe = {code: item.get("name", code) for code, item in universe_meta.items()}
    theme_map = {code: item.get("theme", "") for code, item in universe_meta.items()}
    codes = list(universe.keys())

    df = fetch_quotes_df(codes)
    if df is not None and not df.empty:
        # 腾讯返回名称优先；若为空则用本地股票池名称补齐
        df["code"] = df["code"].astype(str).str.zfill(6)
        df["name"] = df.apply(lambda r: r.get("name") or universe.get(str(r.get("code")).zfill(6), str(r.get("code"))), axis=1)
        df["theme"] = df["code"].map(theme_map).fillna("")

        for col in ["price", "pct_chg", "change", "volume", "amount", "amount_yi", "high", "low", "open", "pre_close", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[~df["name"].astype(str).str.contains("ST|退", na=False)]
        df = df[df["price"].fillna(0) > 0]
        df = df[df["amount"].fillna(0) >= MIN_AMOUNT]  # V3中MIN_AMOUNT默认为0，仅剔除明显无成交额硬过滤

        keep_cols = _empty_spot_df().columns.tolist()
        for col in keep_cols:
            if col not in df.columns:
                df[col] = None
        df = df[keep_cols].copy().reset_index(drop=True)
        _write_cache(df, "all_a_spot_tencent.csv")
        return df

    cached = _read_cache("all_a_spot_tencent.csv")
    if not cached.empty:
        print("[WARN] 腾讯股票池行情失败，使用本地缓存 all_a_spot_tencent.csv")
        return cached

    print("[ERROR] 腾讯股票池行情失败，且没有可用缓存。")
    return _empty_spot_df()


def _empty_kline_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"])


def _normalize_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_kline_df()
    out = df.copy()
    for col in _empty_kline_df().columns:
        if col not in out.columns:
            out[col] = None
    out = out[_empty_kline_df().columns.tolist()].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = _to_numeric(out, ["open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"])
    out = out.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return out


def get_daily_kline(code: str, period: str = "daily", adjust: str = "qfq") -> pd.DataFrame:
    """腾讯日K，失败后读取本地缓存。"""
    code = str(code).zfill(6)[-6:]
    cache_name = f"daily_tencent_{code}.csv"

    df = fetch_daily_kline_tencent(code)
    df = _normalize_kline_df(df)
    if not df.empty:
        _write_cache(df, cache_name)
        return df

    cached = _read_cache(cache_name)
    if not cached.empty:
        return _normalize_kline_df(cached)

    print(f"[ERROR] 腾讯日K失败且无缓存：{code}")
    return _empty_kline_df()


def get_indices_overview() -> pd.DataFrame:
    """腾讯指数行情。"""
    index_symbols = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
    }
    df = fetch_quotes_df(index_symbols.keys())
    if df is not None and not df.empty:
        df["symbol"] = df["symbol"].astype(str)
        df["name"] = df["symbol"].map(index_symbols).fillna(df.get("name"))
        result = pd.DataFrame({
            "code": df["symbol"],
            "name": df["name"],
            "price": df["price"],
            "pct_chg": df["pct_chg"],
            "change": df["change"],
            "amount": df["amount"],
        })
        return result.reset_index(drop=True)

    return pd.DataFrame([
        {"code": "sh000001", "name": "上证指数", "price": None, "pct_chg": None, "change": None, "amount": None},
        {"code": "sz399001", "name": "深证成指", "price": None, "pct_chg": None, "change": None, "amount": None},
        {"code": "sz399006", "name": "创业板指", "price": None, "pct_chg": None, "change": None, "amount": None},
    ])


def get_industry_board() -> pd.DataFrame:
    """用腾讯代表股行情聚合生成板块热度。

    腾讯公开接口不直接提供稳定的东方财富行业板块表。
    本函数用每个观察方向的代表股涨跌幅、上涨家数、成交额粗略构造板块强度。
    """
    rows = []
    for sector, codes in SECTOR_STOCK_MAP.items():
        q = fetch_quotes_df(codes)
        if q is None or q.empty:
            rows.append({
                "sector": sector, "pct_chg": 0.0, "market_value": None, "turnover": 0.0,
                "up_count": 0, "down_count": 0, "leader": "--", "leader_pct": 0.0,
            })
            continue

        q["pct_chg"] = pd.to_numeric(q["pct_chg"], errors="coerce").fillna(0)
        q["amount"] = pd.to_numeric(q["amount"], errors="coerce").fillna(0)
        q["turnover"] = pd.to_numeric(q["turnover"], errors="coerce").fillna(0)
        leader_row = q.sort_values("pct_chg", ascending=False).iloc[0]
        total_amount = q["amount"].sum()
        weight = q["amount"] / total_amount if total_amount > 0 else None
        pct = float((q["pct_chg"] * weight).sum()) if weight is not None else float(q["pct_chg"].mean())

        rows.append({
            "sector": sector,
            "pct_chg": round(pct, 2),
            "market_value": None,
            "turnover": round(float(q["turnover"].mean()), 2),
            "up_count": int((q["pct_chg"] > 0).sum()),
            "down_count": int((q["pct_chg"] < 0).sum()),
            "leader": leader_row.get("name", "--"),
            "leader_pct": round(float(leader_row.get("pct_chg", 0)), 2),
        })

    return pd.DataFrame(rows)
