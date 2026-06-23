# -*- coding: utf-8 -*-
"""JZL证券分析：本地行情数据库模块。

功能：
1. 用 SQLite 保存 A股日K历史行情。
2. 从 stock_universe.csv 导入股票池。
3. 通过腾讯日K接口批量补历史数据，并支持后续增量更新。

注意：
- 数据源为腾讯免费行情接口，适合学习/研究/虚拟回测，不是交易所级数据。
- 默认取 qfq 前复权日K。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import time
from typing import Iterable, Callable

import pandas as pd

from data_tencent import fetch_daily_kline_tencent, normalize_symbol, pure_code

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "market_data.sqlite"
UNIVERSE_CSV = ROOT_DIR / "stock_universe.csv"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_conn(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(db_path: Path | str = DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_universe (
                code TEXT PRIMARY KEY,
                name TEXT,
                theme TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bars (
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                pct_chg REAL,
                turnover REAL,
                source TEXT,
                adj TEXT,
                updated_at TEXT,
                PRIMARY KEY (code, date)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_bars_code_date ON daily_bars(code, date)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT,
                strategy_id TEXT,
                codes TEXT,
                start_date TEXT,
                end_date TEXT,
                initial_cash REAL,
                final_value REAL,
                total_return REAL,
                annual_return REAL,
                max_drawdown REAL,
                win_rate REAL,
                trade_count INTEGER,
                note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_trades (
                run_id TEXT,
                datetime TEXT,
                code TEXT,
                name TEXT,
                action TEXT,
                price REAL,
                shares INTEGER,
                cash_after REAL,
                position_after INTEGER,
                reason TEXT
            )
            """
        )
        conn.commit()


def load_stock_universe(csv_path: Path | str = UNIVERSE_CSV) -> pd.DataFrame:
    p = Path(csv_path)
    if not p.exists():
        return pd.DataFrame(columns=["code", "name", "theme"])
    df = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
    if "code" not in df.columns:
        return pd.DataFrame(columns=["code", "name", "theme"])
    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    if "name" not in df.columns:
        df["name"] = df["code"]
    if "theme" not in df.columns:
        df["theme"] = ""
    df = df.dropna(subset=["code"]).drop_duplicates("code").reset_index(drop=True)
    return df[["code", "name", "theme"]]


def import_universe_to_db(csv_path: Path | str = UNIVERSE_CSV, db_path: Path | str = DB_PATH) -> int:
    init_db(db_path)
    df = load_stock_universe(csv_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [(str(r.code).zfill(6), str(r.name), str(r.theme), now) for r in df.itertuples(index=False)]
    with get_conn(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO stock_universe(code, name, theme, updated_at)
            VALUES(?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                theme=excluded.theme,
                updated_at=excluded.updated_at
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def get_universe_from_db(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    init_db(db_path)
    with get_conn(db_path) as conn:
        return pd.read_sql_query("SELECT code, name, theme FROM stock_universe ORDER BY code", conn)


def upsert_daily_bars(code: str, df: pd.DataFrame, db_path: Path | str = DB_PATH, source: str = "tencent", adj: str = "qfq") -> int:
    init_db(db_path)
    if df is None or df.empty:
        return 0
    x = df.copy()
    x["code"] = pure_code(code)
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]:
        if col not in x.columns:
            x[col] = None
        x[col] = pd.to_numeric(x[col], errors="coerce")
    x = x.dropna(subset=["date", "close"]).drop_duplicates(["code", "date"])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (
            r.code,
            r.date,
            None if pd.isna(r.open) else float(r.open),
            None if pd.isna(r.high) else float(r.high),
            None if pd.isna(r.low) else float(r.low),
            None if pd.isna(r.close) else float(r.close),
            None if pd.isna(r.volume) else float(r.volume),
            None if pd.isna(r.amount) else float(r.amount),
            None if pd.isna(r.pct_chg) else float(r.pct_chg),
            None if pd.isna(r.turnover) else float(r.turnover),
            source,
            adj,
            now,
        )
        for r in x.itertuples(index=False)
    ]
    with get_conn(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO daily_bars(code, date, open, high, low, close, volume, amount, pct_chg, turnover, source, adj, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(code, date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                amount=excluded.amount,
                pct_chg=excluded.pct_chg,
                turnover=excluded.turnover,
                source=excluded.source,
                adj=excluded.adj,
                updated_at=excluded.updated_at
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def get_daily_bars(code: str, start_date: str | None = None, end_date: str | None = None, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    init_db(db_path)
    code = pure_code(code)
    sql = "SELECT * FROM daily_bars WHERE code=?"
    params: list = [code]
    if start_date:
        sql += " AND date>=?"
        params.append(str(start_date))
    if end_date:
        sql += " AND date<=?"
        params.append(str(end_date))
    sql += " ORDER BY date"
    with get_conn(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def last_bar_date(code: str, db_path: Path | str = DB_PATH) -> str | None:
    init_db(db_path)
    code = pure_code(code)
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT MAX(date) FROM daily_bars WHERE code=?", (code,)).fetchone()
    return row[0] if row and row[0] else None


def db_stats(db_path: Path | str = DB_PATH) -> dict:
    init_db(db_path)
    with get_conn(db_path) as conn:
        stock_count = conn.execute("SELECT COUNT(*) FROM stock_universe").fetchone()[0]
        bar_count = conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
        covered = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_bars").fetchone()[0]
        row = conn.execute("SELECT MIN(date), MAX(date) FROM daily_bars").fetchone()
    size_mb = Path(db_path).stat().st_size / 1024 / 1024 if Path(db_path).exists() else 0
    return {
        "db_path": str(db_path),
        "db_size_mb": round(size_mb, 2),
        "stock_count": stock_count,
        "covered_stocks": covered,
        "bar_count": bar_count,
        "min_date": row[0] if row else None,
        "max_date": row[1] if row else None,
    }


def build_history_for_codes(
    codes: Iterable[str],
    start_date: str = "2021-01-01",
    end_date: str | None = None,
    db_path: Path | str = DB_PATH,
    sleep_seconds: float = 0.12,
    progress_callback: Callable[[int, int, str, int], None] | None = None,
) -> dict:
    """从腾讯接口批量拉取历史日K并写入数据库。"""
    init_db(db_path)
    codes = [pure_code(c) for c in codes]
    codes = list(dict.fromkeys([c for c in codes if len(c) == 6]))
    end = pd.to_datetime(end_date or datetime.now().strftime("%Y-%m-%d"))
    start = pd.to_datetime(start_date)
    days = max(260, int((end - start).days * 0.75) + 120)
    limit = min(max(days, 300), 2500)
    ok = 0
    fail = 0
    bars = 0
    errors: list[str] = []
    for i, code in enumerate(codes, start=1):
        try:
            df = fetch_daily_kline_tencent(code, limit=limit)
            if df is not None and not df.empty:
                df = df[(pd.to_datetime(df["date"]) >= start) & (pd.to_datetime(df["date"]) <= end)].copy()
                n = upsert_daily_bars(code, df, db_path=db_path)
                ok += 1
                bars += n
            else:
                fail += 1
                errors.append(f"{code}: 无数据")
        except Exception as e:
            fail += 1
            errors.append(f"{code}: {e}")
        if progress_callback:
            progress_callback(i, len(codes), code, bars)
        if sleep_seconds:
            time.sleep(float(sleep_seconds))
    return {"codes": len(codes), "ok": ok, "fail": fail, "bars": bars, "errors": errors[:30]}


def update_latest_for_codes(
    codes: Iterable[str],
    db_path: Path | str = DB_PATH,
    lookback_days: int = 30,
    sleep_seconds: float = 0.08,
    progress_callback: Callable[[int, int, str, int], None] | None = None,
) -> dict:
    """增量更新：从最近日期往前回看一段，重新覆盖写入。"""
    init_db(db_path)
    codes = [pure_code(c) for c in codes]
    today = datetime.now().strftime("%Y-%m-%d")
    ok = fail = bars = 0
    errors: list[str] = []
    for i, code in enumerate(codes, start=1):
        try:
            last = last_bar_date(code, db_path)
            if last:
                start = (pd.to_datetime(last) - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            else:
                start = "2021-01-01"
            df = fetch_daily_kline_tencent(code, limit=2600)
            if df is not None and not df.empty:
                df = df[(pd.to_datetime(df["date"]) >= pd.to_datetime(start)) & (pd.to_datetime(df["date"]) <= pd.to_datetime(today))].copy()
                n = upsert_daily_bars(code, df, db_path=db_path)
                ok += 1
                bars += n
            else:
                fail += 1
                errors.append(f"{code}: 无数据")
        except Exception as e:
            fail += 1
            errors.append(f"{code}: {e}")
        if progress_callback:
            progress_callback(i, len(codes), code, bars)
        if sleep_seconds:
            time.sleep(float(sleep_seconds))
    return {"codes": len(codes), "ok": ok, "fail": fail, "bars": bars, "errors": errors[:30]}


if __name__ == "__main__":
    init_db()
    n = import_universe_to_db()
    print("imported universe", n)
    print(db_stats())
