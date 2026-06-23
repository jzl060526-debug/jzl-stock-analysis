# -*- coding: utf-8 -*-
"""全市场候选池生成器。"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Iterable, Callable, Any
import pandas as pd
from market_db import DB_PATH, get_daily_bars, get_universe_from_db, get_conn, init_db
from scoring_engine import score_stock_daily
from strategy_loader import load_strategy

SCORING_STRATEGY_ID = "jzl_stock_scoring_v1"
TRADE_STRATEGY_ID = "jzl_wave_core_v1"

def init_candidate_table(db_path: Path | str = DB_PATH) -> None:
    init_db(db_path)
    with get_conn(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidate_scores (
                snapshot_id TEXT, created_at TEXT, code TEXT, name TEXT, date TEXT,
                score REAL, candidate_level TEXT, setup_type TEXT, close REAL, amount_yi REAL,
                ret20_pct REAL, ret60_pct REAL, distance_ma5_pct REAL, volume_ratio REAL,
                matched_conditions TEXT, failed_filters TEXT, risk_flags TEXT, reason TEXT,
                PRIMARY KEY(snapshot_id, code)
            )
        """)
        conn.commit()

def save_candidate_scores(df: pd.DataFrame, db_path: Path | str = DB_PATH) -> str:
    init_candidate_table(db_path)
    if df is None or df.empty: return ""
    snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for r in df.itertuples(index=False):
        rows.append((snapshot_id, created_at, str(r.code).zfill(6), str(r.name), str(getattr(r, 'date', '')), float(getattr(r, 'score', 0) or 0), str(getattr(r, 'candidate_level', '')), str(getattr(r, 'setup_type', '')), float(getattr(r, 'close', 0) or 0), float(getattr(r, 'amount_yi', 0) or 0), float(getattr(r, 'ret20_pct', 0) or 0), float(getattr(r, 'ret60_pct', 0) or 0), float(getattr(r, 'distance_ma5_pct', 0) or 0), float(getattr(r, 'volume_ratio', 0) or 0), str(getattr(r, 'matched_conditions', '')), str(getattr(r, 'failed_filters', '')), str(getattr(r, 'risk_flags', '')), str(getattr(r, 'reason', ''))))
    with get_conn(db_path) as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO candidate_scores(snapshot_id, created_at, code, name, date, score, candidate_level, setup_type, close, amount_yi, ret20_pct, ret60_pct, distance_ma5_pct, volume_ratio, matched_conditions, failed_filters, risk_flags, reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
    return snapshot_id

def load_latest_candidate_scores(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    init_candidate_table(db_path)
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT MAX(snapshot_id) FROM candidate_scores").fetchone()
        if not row or not row[0]: return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM candidate_scores WHERE snapshot_id=? ORDER BY score DESC", conn, params=[row[0]])

def run_stock_scoring(codes: Iterable[str] | None = None, scoring_strategy_id: str = SCORING_STRATEGY_ID, trade_strategy_id: str = TRADE_STRATEGY_ID, start_date: str = "2021-01-01", end_date: str | None = None, progress_callback: Callable[[int, int, str], None] | None = None, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    universe = get_universe_from_db(db_path)
    if universe.empty: return pd.DataFrame()
    mapping = {str(r.code).zfill(6): str(r.name) for r in universe.itertuples(index=False)}
    code_list = list(mapping.keys()) if codes is None else [str(c).zfill(6)[-6:] for c in codes]
    scoring = load_strategy(scoring_strategy_id)
    trade_strategy = load_strategy(trade_strategy_id)
    rows: list[dict[str, Any]] = []
    for i, code in enumerate(code_list, start=1):
        if progress_callback: progress_callback(i, len(code_list), code)
        try:
            df = get_daily_bars(code, start_date, end_date, db_path=db_path)
            rows.append(score_stock_daily(code, mapping.get(code, code), df, scoring, trade_strategy))
        except Exception as exc:
            rows.append({"code": code, "name": mapping.get(code, code), "score": 0, "candidate_level": "reject", "setup_type": "error", "reason": str(exc)})
    out = pd.DataFrame(rows)
    if not out.empty:
        if "amount_yi" not in out.columns: out["amount_yi"] = 0
        out = out.sort_values(["score", "amount_yi"], ascending=[False, False]).reset_index(drop=True)
    return out
