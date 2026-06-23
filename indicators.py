# -*- coding: utf-8 -*-
"""技术指标计算。"""
from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    for col in ["open", "close", "high", "low", "volume", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    if df.empty:
        return df

    df["MA5"] = df["close"].rolling(5).mean()
    df["MA10"] = df["close"].rolling(10).mean()
    df["MA20"] = df["close"].rolling(20).mean()
    df["MA60"] = df["close"].rolling(60).mean()
    df["VOL5"] = df["volume"].rolling(5).mean() if "volume" in df.columns else None
    df["VOL20"] = df["volume"].rolling(20).mean() if "volume" in df.columns else None
    df["high_20d"] = df["high"].rolling(20).max() if "high" in df.columns else None
    df["low_20d"] = df["low"].rolling(20).min() if "low" in df.columns else None
    df["rise_20d"] = df["close"] / df["close"].shift(20) - 1

    if "volume" in df.columns:
        df["volume_ratio"] = df["volume"] / df["VOL5"]
        df["volume_expand"] = df["volume"] > df["VOL5"] * 1.5
        df["volume_shrink"] = df["volume"] < df["VOL5"]
    else:
        df["volume_ratio"] = None
        df["volume_expand"] = False
        df["volume_shrink"] = False

    return df
