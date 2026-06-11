from __future__ import annotations

import argparse
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DB_PATH = Path("data/omniscient_quant.sqlite3")


def load_config(config_path: Path) -> dict[str, Any]:
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def selected_training_symbols(
    conn: sqlite3.Connection,
    markets: list[str],
    max_symbols: int,
) -> list[str]:
    if not markets:
        markets = ["KOSPI", "KOSDAQ"]

    per_market = max(1, (max_symbols + len(markets) - 1) // len(markets))
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(stock_universe)").fetchall()
    }
    order_expression = "COALESCE(market_rank, 999999), symbol" if "market_rank" in columns else "symbol"
    selected: list[str] = []
    for market in markets:
        rows = conn.execute(
            f"""
            SELECT symbol
            FROM stock_universe
            WHERE active = 1
              AND market = ?
            ORDER BY {order_expression}
            LIMIT ?
            """,
            (market, per_market),
        ).fetchall()
        selected.extend(str(row[0]) for row in rows)
    return selected[:max_symbols]


def count_symbol_rows(conn: sqlite3.Connection, symbol: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    return int(row[0]) if row else 0


def fetch_status(config_path: Path) -> dict[str, Any]:
    raw = load_config(config_path)
    db_path = Path(raw.get("database", {}).get("path", DEFAULT_DB_PATH))
    historical = raw.get("historical", {})
    markets = [str(item).upper() for item in historical.get("markets", ["KOSPI", "KOSDAQ"])]
    target_symbols = int(historical.get("training_max_symbols", historical.get("max_symbols", 300)))
    target_pages = int(
        historical.get("training_max_pages_per_symbol", historical.get("max_pages_per_symbol", 100))
    )
    target_rows_per_symbol = target_pages * 10

    with sqlite3.connect(db_path) as conn:
        active_universe = conn.execute(
            "SELECT COUNT(*) FROM stock_universe WHERE active = 1"
        ).fetchone()[0]
        ohlcv_rows = conn.execute("SELECT COUNT(*) FROM ohlcv_daily").fetchone()[0]
        symbols_with_ohlcv = conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM ohlcv_daily"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM ohlcv_backfill_status WHERE status = 'failed'"
        ).fetchone()[0]
        latest = conn.execute(
            """
            SELECT symbol, status, pages_attempted, fetched_rows, inserted_rows, updated_at
            FROM ohlcv_backfill_status
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()

        selected = selected_training_symbols(conn, markets, target_symbols)
        completed = 0
        partial = 0
        for symbol in selected:
            rows = count_symbol_rows(conn, symbol)
            if rows >= target_rows_per_symbol:
                completed += 1
            elif rows > 0:
                partial += 1

    progress = (completed / len(selected) * 100.0) if selected else 0.0
    return {
        "active_universe": int(active_universe),
        "training_target_symbols": len(selected),
        "target_rows_per_symbol": target_rows_per_symbol,
        "completed_training_symbols": completed,
        "partial_training_symbols": partial,
        "progress_percent": progress,
        "symbols_with_ohlcv": int(symbols_with_ohlcv),
        "ohlcv_rows": int(ohlcv_rows),
        "failed_status": int(failed),
        "latest": latest,
    }


def print_status(status: dict[str, Any]) -> None:
    latest = status["latest"]
    print("Omniscient Backfill Status")
    print(f"active_universe          : {status['active_universe']}")
    print(f"training_target_symbols : {status['training_target_symbols']}")
    print(f"completed_training      : {status['completed_training_symbols']}")
    print(f"partial_training        : {status['partial_training_symbols']}")
    print(f"progress_percent        : {status['progress_percent']:.2f}%")
    print(f"symbols_with_ohlcv      : {status['symbols_with_ohlcv']}")
    print(f"ohlcv_rows              : {status['ohlcv_rows']}")
    print(f"failed_status           : {status['failed_status']}")
    if latest:
        print(
            "latest                  : "
            f"symbol={latest[0]} status={latest[1]} page={latest[2]} "
            f"fetched={latest[3]} inserted={latest[4]} updated={latest[5]}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show historical backfill progress")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--watch", type=int, help="Refresh every N seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.watch:
        while True:
            os.system("cls")
            print_status(fetch_status(args.config))
            time.sleep(args.watch)
    print_status(fetch_status(args.config))


if __name__ == "__main__":
    main()
