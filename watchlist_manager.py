# -*- coding: utf-8 -*-
"""自选收藏管理。"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

try:
    from config import WATCHLIST_CSV, CORE_POOL
except Exception:
    WATCHLIST_CSV = Path(__file__).resolve().parent / "watchlist.csv"
    CORE_POOL = {}

COLUMNS = ["code", "name", "group", "note", "created_at"]


def _now() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def load_watchlist() -> pd.DataFrame:
    if WATCHLIST_CSV.exists():
        try:
            df = pd.read_csv(WATCHLIST_CSV, dtype={"code": str}, encoding="utf-8-sig")
        except Exception:
            df = pd.DataFrame(columns=COLUMNS)
    else:
        df = pd.DataFrame(columns=COLUMNS)
        for code, name in CORE_POOL.items():
            df.loc[len(df)] = [str(code).zfill(6), name, "自选", "自动初始化", _now()]
        save_watchlist(df)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["code"] = df["code"].astype(str).str.zfill(6).str[-6:]
    df = df.drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)
    return df[COLUMNS]


def save_watchlist(df: pd.DataFrame) -> None:
    out = df.copy() if df is not None else pd.DataFrame(columns=COLUMNS)
    for col in COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["code"] = out["code"].astype(str).str.zfill(6).str[-6:]
    out = out[out["code"].str.match(r"^\d{6}$", na=False)].drop_duplicates(subset=["code"], keep="last")
    WATCHLIST_CSV.parent.mkdir(parents=True, exist_ok=True)
    out[COLUMNS].to_csv(WATCHLIST_CSV, index=False, encoding="utf-8-sig")


def add_watch(code: str, name: str = "", group: str = "自选", note: str = "") -> None:
    code = str(code).zfill(6)[-6:]
    df = load_watchlist()
    df = df[df["code"] != code].copy()
    df.loc[len(df)] = [code, name or code, group or "自选", note or "", _now()]
    save_watchlist(df)


def remove_watch(code: str) -> None:
    code = str(code).zfill(6)[-6:]
    df = load_watchlist()
    save_watchlist(df[df["code"] != code].copy())


def watchlist_options(universe: dict[str, str] | None = None) -> dict[str, str]:
    df = load_watchlist()
    universe = universe or {}
    out = {}
    for _, r in df.iterrows():
        code = str(r.get("code", "")).zfill(6)[-6:]
        name = str(r.get("name", "")) or universe.get(code, code)
        out[code] = universe.get(code, name)
    return out
