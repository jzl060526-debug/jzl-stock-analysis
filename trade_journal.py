# -*- coding: utf-8 -*-
"""买卖点记录、交易本子、已清仓股票粗略收益率。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import uuid

import pandas as pd

from config import TRADE_RECORDS_CSV, NOTEBOOK_CSV, OUTPUT_DIR

TRADE_COLUMNS = [
    "id", "date", "code", "name", "side", "action_type", "price", "volume", "amount",
    "reason", "note", "position_status", "created_at", "updated_at",
]

NOTE_COLUMNS = ["id", "date", "code", "name", "title", "content", "tags", "created_at", "updated_at"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype={"code": str}, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, dtype={"code": str}, encoding="gbk")
    except Exception:
        return pd.DataFrame(columns=columns)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns].copy()


def load_trade_records() -> pd.DataFrame:
    df = _read_csv(TRADE_RECORDS_CSV, TRADE_COLUMNS)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("").str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df.loc[df["amount"].isna(), "amount"] = df["price"].fillna(0) * df["volume"].fillna(0)
    df = df.dropna(subset=["date"])
    return df.sort_values(["date", "created_at"]).reset_index(drop=True)


def save_trade_records(df: pd.DataFrame) -> None:
    out = df.copy() if df is not None else pd.DataFrame(columns=TRADE_COLUMNS)
    for c in TRADE_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out[TRADE_COLUMNS]
    out.to_csv(TRADE_RECORDS_CSV, index=False, encoding="utf-8-sig")


def add_trade_record(date, code, name, side, action_type, price, volume, reason="", note="", position_status="持仓中") -> None:
    df = load_trade_records()
    code = str(code).zfill(6)[-6:]
    price_f = float(price or 0)
    volume_i = int(volume or 0)
    if str(action_type) == "清仓":
        position_status = "已清仓"
    row = {
        "id": uuid.uuid4().hex[:12],
        "date": pd.to_datetime(date).strftime("%Y-%m-%d"),
        "code": code,
        "name": str(name or code),
        "side": str(side),
        "action_type": str(action_type),
        "price": price_f,
        "volume": volume_i,
        "amount": round(price_f * volume_i, 2),
        "reason": str(reason or ""),
        "note": str(note or ""),
        "position_status": str(position_status or "持仓中"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_trade_records(df)


def filter_records(df: pd.DataFrame, code: str | None = None, start_date=None, end_date=None, status: str | None = None) -> pd.DataFrame:
    out = df.copy() if df is not None else pd.DataFrame(columns=TRADE_COLUMNS)
    if out.empty:
        return out
    if code:
        c = str(code).zfill(6)[-6:]
        out = out[out["code"] == c]
    if start_date:
        out = out[out["date"] >= pd.to_datetime(start_date)]
    if end_date:
        out = out[out["date"] <= pd.to_datetime(end_date)]
    if status and status != "全部":
        out = out[out["position_status"].astype(str) == status]
    return out.reset_index(drop=True)


def closed_position_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["code", "name", "first_buy_date", "close_date", "buy_avg", "sell_avg", "rough_return_pct", "buy_volume", "sell_volume"])
    rows = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date")
        name = str(g["name"].dropna().iloc[-1]) if "name" in g.columns and not g["name"].dropna().empty else code
        is_closed = (g["action_type"].astype(str).str.contains("清仓", na=False).any() or g["position_status"].astype(str).eq("已清仓").any())
        if not is_closed:
            continue
        buy = g[g["side"].astype(str).str.contains("买", na=False)]
        sell = g[g["side"].astype(str).str.contains("卖", na=False)]
        buy_vol = float(buy["volume"].sum()) if not buy.empty else 0.0
        sell_vol = float(sell["volume"].sum()) if not sell.empty else 0.0
        buy_amt = float((buy["price"] * buy["volume"]).sum()) if not buy.empty else 0.0
        sell_amt = float((sell["price"] * sell["volume"]).sum()) if not sell.empty else 0.0
        buy_avg = buy_amt / buy_vol if buy_vol > 0 else None
        sell_avg = sell_amt / sell_vol if sell_vol > 0 else None
        rough_return = ((sell_avg - buy_avg) / buy_avg * 100) if buy_avg and sell_avg else None
        rows.append({
            "code": code,
            "name": name,
            "first_buy_date": buy["date"].min().strftime("%Y-%m-%d") if not buy.empty else "",
            "close_date": sell["date"].max().strftime("%Y-%m-%d") if not sell.empty else "",
            "buy_avg": round(buy_avg, 3) if buy_avg is not None else None,
            "sell_avg": round(sell_avg, 3) if sell_avg is not None else None,
            "rough_return_pct": round(rough_return, 2) if rough_return is not None else None,
            "buy_volume": int(buy_vol),
            "sell_volume": int(sell_vol),
        })
    return pd.DataFrame(rows).sort_values("close_date", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def export_trades(df: pd.DataFrame, fmt: str = "xlsx") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "csv":
        path = OUTPUT_DIR / f"trade_records_export_{stamp}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path
    path = OUTPUT_DIR / f"trade_records_export_{stamp}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="买卖点记录")
        closed_position_summary(df).to_excel(writer, index=False, sheet_name="已清仓股票")
    return path


def load_notebook() -> pd.DataFrame:
    df = _read_csv(NOTEBOOK_CSV, NOTE_COLUMNS)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("").str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def add_note(date, code, name, title, content, tags="") -> None:
    df = load_notebook()
    row = {
        "id": uuid.uuid4().hex[:12],
        "date": pd.to_datetime(date).strftime("%Y-%m-%d"),
        "code": str(code).zfill(6)[-6:] if code else "",
        "name": str(name or ""),
        "title": str(title or "交易笔记"),
        "content": str(content or ""),
        "tags": str(tags or ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(NOTEBOOK_CSV, index=False, encoding="utf-8-sig")


def export_notebook(df: pd.DataFrame) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"trade_notebook_export_{stamp}.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    return path
