# -*- coding: utf-8 -*-
"""命令行构建/更新行情数据库。

用法示例：
  python build_history_db.py --mode first --n 30 --start 2021-01-01
  python build_history_db.py --mode all --start 2021-01-01
  python build_history_db.py --mode update --n 30
"""
from __future__ import annotations
import argparse
from datetime import datetime

from market_db import init_db, import_universe_to_db, get_universe_from_db, build_history_for_codes, update_latest_for_codes, db_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["first", "all", "update"], default="first")
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--sleep", type=float, default=0.12)
    args = parser.parse_args()

    init_db()
    n = import_universe_to_db()
    print(f"股票池已导入/更新：{n}只")
    uni = get_universe_from_db()
    codes = uni["code"].astype(str).str.zfill(6).tolist()
    if args.mode == "first":
        codes = codes[:args.n]
        print(f"开始构建前{len(codes)}只历史日K：{args.start} -> {args.end}")
        res = build_history_for_codes(codes, args.start, args.end, sleep_seconds=args.sleep, progress_callback=lambda i,t,c,b: print(f"{i}/{t} {c} bars={b}"))
    elif args.mode == "all":
        print(f"开始构建全部{len(codes)}只历史日K：{args.start} -> {args.end}")
        res = build_history_for_codes(codes, args.start, args.end, sleep_seconds=args.sleep, progress_callback=lambda i,t,c,b: print(f"{i}/{t} {c} bars={b}"))
    else:
        codes = codes[:args.n] if args.n else codes
        print(f"开始增量更新{len(codes)}只")
        res = update_latest_for_codes(codes, sleep_seconds=args.sleep, progress_callback=lambda i,t,c,b: print(f"{i}/{t} {c} bars={b}"))
    print(res)
    print(db_stats())


if __name__ == "__main__":
    main()
