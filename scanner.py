# -*- coding: utf-8 -*-
"""腾讯股票池扫描与自选/参考监控。

本版改动重点：
1. 不再只依赖腾讯实时行情返回的股票数量。
2. 会优先读取本地 stock_universe.csv，作为完整股票池。
3. 腾讯实时行情成功的股票优先精筛；实时行情暂时失败的股票，也会作为候补进入日K精筛。
4. 自动过滤 ETF、指数、行业指数等非普通沪深A股代码。
5. 扫描时显示：股票池总数、腾讯实时有效数、最终日K精筛数。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import CORE_POOL, MAX_PRECISE_SCAN
from data_fetcher import get_all_a_spot, get_daily_kline
from data_tencent import fetch_quotes_df
from indicators import add_indicators
from strategy import evaluate_stock


# 只保留普通沪深A股、创业板、科创板。
# 排除：ETF 15/51开头、行业指数88开头、黄金AU9999等。
A_SHARE_PREFIXES = (
    "000", "001", "002", "003",
    "300", "301",
    "600", "601", "603", "605",
    "688", "689",
)


@st.cache_data(ttl=240, show_spinner=False)
def cached_all_spot() -> pd.DataFrame:
    return get_all_a_spot()


@st.cache_data(ttl=600, show_spinner=False)
def cached_daily_kline(code: str) -> pd.DataFrame:
    return get_daily_kline(code)


@st.cache_data(ttl=600, show_spinner=False)
def cached_local_universe() -> pd.DataFrame:
    """读取项目目录下的 stock_universe.csv。"""
    csv_path = Path(__file__).with_name("stock_universe.csv")
    if not csv_path.exists():
        return pd.DataFrame(columns=["code", "name", "theme"])

    try:
        df = pd.read_csv(csv_path, dtype={"code": str}, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, dtype={"code": str}, encoding="gbk")
    except Exception:
        return pd.DataFrame(columns=["code", "name", "theme"])

    # 兼容没有标准表头的情况：默认前两列为 code/name。
    if "code" not in df.columns and len(df.columns) >= 1:
        df = df.rename(columns={df.columns[0]: "code"})
    if "name" not in df.columns and len(df.columns) >= 2:
        df = df.rename(columns={df.columns[1]: "name"})
    if "theme" not in df.columns:
        df["theme"] = ""

    df["code"] = (
        df["code"]
        .astype(str)
        .str.extract(r"(\d{6})", expand=False)
        .fillna("")
        .str.zfill(6)
    )

    df = df[df["code"].str.match(r"^\d{6}$", na=False)]
    df = df[df["code"].str.startswith(A_SHARE_PREFIXES)]
    df["name"] = df["name"].astype(str).fillna("")
    df["theme"] = df["theme"].astype(str).fillna("")
    df = df.drop_duplicates(subset=["code"], keep="first")
    return df[["code", "name", "theme"]].reset_index(drop=True)


def _to_numeric_col(df: pd.DataFrame, col: str, default: float = 0.0) -> None:
    if col not in df.columns:
        df[col] = default
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)


def _normalize_spot(spot: pd.DataFrame) -> pd.DataFrame:
    if spot is None or spot.empty:
        return pd.DataFrame(columns=["code", "name", "theme"])

    df = spot.copy()
    if "code" not in df.columns:
        return pd.DataFrame(columns=["code", "name", "theme"])

    df["code"] = (
        df["code"]
        .astype(str)
        .str.extract(r"(\d{6})", expand=False)
        .fillna("")
        .str.zfill(6)
    )
    df = df[df["code"].str.match(r"^\d{6}$", na=False)]
    df = df[df["code"].str.startswith(A_SHARE_PREFIXES)]
    df = df.drop_duplicates(subset=["code"], keep="first")

    if "name" not in df.columns:
        df["name"] = df["code"]
    if "theme" not in df.columns:
        df["theme"] = ""

    for col in ["pct_chg", "amount", "turnover", "volume_ratio", "price", "close"]:
        _to_numeric_col(df, col, 0.0)

    df["has_realtime"] = True
    return df.reset_index(drop=True)


def _build_scan_base(spot: pd.DataFrame) -> pd.DataFrame:
    """本地股票池为主，腾讯实时行情为辅。

    之前只用 get_all_a_spot() 返回的数据，所以如果腾讯批量行情只成功194只，
    页面就只会显示“精筛 1/194”。
    现在改为：
    - 本地 stock_universe.csv 决定股票池总范围；
    - 腾讯实时行情成功的股票补充涨幅、成交额、换手等字段；
    - 实时行情没返回的股票仍可进入候补日K精筛。
    """
    universe = cached_local_universe()
    spot_df = _normalize_spot(spot)

    if universe.empty and spot_df.empty:
        return pd.DataFrame()

    if universe.empty:
        base = spot_df.copy()
    elif spot_df.empty:
        base = universe.copy()
        base["has_realtime"] = False
    else:
        base = universe.merge(
            spot_df,
            on="code",
            how="left",
            suffixes=("_universe", "_spot"),
        )

        base["name"] = (
            base.get("name_universe")
            .where(base.get("name_universe").notna(), base.get("name_spot"))
            if "name_universe" in base.columns and "name_spot" in base.columns
            else base.get("name", base["code"])
        )
        base["theme"] = (
            base.get("theme_universe")
            .where(base.get("theme_universe").notna(), base.get("theme_spot"))
            if "theme_universe" in base.columns and "theme_spot" in base.columns
            else base.get("theme", "")
        )

        # 只保留合并后的通用字段，避免表格出现 name_universe/name_spot 等脏字段。
        keep_cols = ["code", "name", "theme", "pct_chg", "amount", "turnover", "volume_ratio", "price", "close", "has_realtime"]
        for col in keep_cols:
            if col not in base.columns:
                base[col] = None
        base = base[keep_cols]

    for col in ["pct_chg", "amount", "turnover", "volume_ratio", "price", "close"]:
        _to_numeric_col(base, col, 0.0)

    if "has_realtime" not in base.columns:
        base["has_realtime"] = False
    base["has_realtime"] = base["has_realtime"].fillna(False).astype(bool)

    base["code"] = base["code"].astype(str).str.zfill(6)
    base = base[base["code"].str.startswith(A_SHARE_PREFIXES)]
    base = base.drop_duplicates(subset=["code"], keep="first")
    return base.reset_index(drop=True)


def _candidate_prefilter(spot: pd.DataFrame) -> pd.DataFrame:
    base = _build_scan_base(spot)
    if base.empty:
        return pd.DataFrame()

    # 不做强过滤，只做排序。
    # 目的：避免因为成交额/涨幅/实时接口失败，把大量股票挡在日K精筛外。
    base["rough_score"] = 0.0
    base["rough_score"] += base["pct_chg"].clip(-5, 10) * 2
    base["rough_score"] += (base["amount"] / 1e8).clip(0, 20)
    base["rough_score"] += base["turnover"].clip(0, 20) * 0.6
    base["rough_score"] += base["volume_ratio"].clip(0, 5) * 2

    # 腾讯实时行情成功的优先；没有实时行情的股票排后面，但不会被直接丢掉。
    base = base.sort_values(["has_realtime", "rough_score"], ascending=[False, False])

    return base.head(MAX_PRECISE_SCAN).reset_index(drop=True)


def run_market_scan(progress_bar=None, status_text=None) -> pd.DataFrame:
    spot = cached_all_spot()
    scan_base = _build_scan_base(spot)
    candidates = _candidate_prefilter(spot)

    if candidates.empty:
        if status_text is not None:
            status_text.error("没有可扫描股票：请检查 stock_universe.csv 或腾讯接口。")
        return pd.DataFrame()

    raw_spot_count = 0 if spot is None else len(spot)
    local_universe_count = len(cached_local_universe())
    merged_count = len(scan_base)
    realtime_count = int(scan_base.get("has_realtime", pd.Series(dtype=bool)).sum()) if not scan_base.empty else 0

    if status_text is not None:
        status_text.info(
            f"股票池总数：{local_universe_count}｜"
            f"腾讯实时返回：{raw_spot_count}｜"
            f"普通A股有效：{merged_count}｜"
            f"实时行情有效：{realtime_count}｜"
            f"本次日K精筛：{len(candidates)}"
        )

    results: list[dict] = []
    total = len(candidates)

    for idx, row in candidates.iterrows():
        code = str(row.get("code", "")).zfill(6)
        name = str(row.get("name", code))

        if status_text is not None:
            status_text.info(
                f"股票池总数：{local_universe_count}｜普通A股有效：{merged_count}｜"
                f"正在精筛 {idx + 1}/{total}：{code} {name}"
            )

        if progress_bar is not None:
            progress_bar.progress(min((idx + 1) / total, 1.0))

        try:
            kline = add_indicators(cached_daily_kline(code))
            item = evaluate_stock(kline, code, name)
        except Exception:
            item = None

        if item and item.get("score", 0) >= 35:
            item["theme"] = row.get("theme", "")
            item["pct_chg"] = row.get("pct_chg")
            item["amount_yi"] = round(float(row.get("amount", 0) or 0) / 1e8, 2)
            item["turnover"] = row.get("turnover")
            results.append(item)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    sort_cols = [col for col in ["score", "amount_yi"] if col in df.columns]
    if sort_cols:
        return df.sort_values(sort_cols, ascending=[False] * len(sort_cols)).reset_index(drop=True)
    return df.reset_index(drop=True)


def scan_core_pool() -> pd.DataFrame:
    results = []
    quote_df = fetch_quotes_df(CORE_POOL.keys())
    quote_map = {str(r["code"]).zfill(6): r for _, r in quote_df.iterrows()} if quote_df is not None and not quote_df.empty else {}

    for code, name in CORE_POOL.items():
        kline = add_indicators(cached_daily_kline(code))
        item = evaluate_stock(kline, code, name)
        if item is None:
            item = {
                "code": code,
                "name": name,
                "close": None,
                "score": 0,
                "suggestion": "观察",
                "daily_k_trend": "数据不足",
                "trend_status": "暂无日K",
                "ma5_relation": "五日线不足",
                "buy_point": "暂无",
                "support": None,
                "pressure": None,
                "stop_loss": None,
                "reason": "日K接口暂不可用，可先查看腾讯实时行情。",
            }
        q = quote_map.get(str(code).zfill(6))
        if q is not None:
            item["realtime_price"] = q.get("price")
            item["pct_change"] = q.get("pct_change")
            item["amount_yi"] = q.get("amount_yi")
            item["update_time"] = q.get("update_time")
        results.append(item)

    return pd.DataFrame(results)


def classify_pools(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if df is None or df.empty:
        return {"趋势池": pd.DataFrame(), "回踩池": pd.DataFrame(), "突破池": pd.DataFrame()}
    return {
        "趋势池": df[df["trend_status"].isin(["强趋势", "趋势未坏"])].copy(),
        "回踩池": df[df["is_pullback"] == True].copy(),
        "突破池": df[df["is_breakout"] == True].copy(),
    }
