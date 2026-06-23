# -*- coding: utf-8 -*-
"""板块强度分析。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from data_fetcher import get_industry_board


@st.cache_data(ttl=300, show_spinner=False)
def analyze_sector_strength() -> pd.DataFrame:
    df = get_industry_board()
    if df is None or df.empty:
        return pd.DataFrame(columns=["sector", "pct_chg", "up_count", "down_count", "turnover", "leader", "leader_pct", "strength_score"])

    for col in ["pct_chg", "up_count", "down_count", "turnover", "leader_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["strength_score"] = (
        df["pct_chg"] * 2.0
        + df["up_count"] * 0.05
        - df["down_count"] * 0.03
        + df["turnover"] * 0.5
        + df["leader_pct"] * 0.4
    )
    return df.sort_values("strength_score", ascending=False).reset_index(drop=True)
