from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup

from stock_universe import (
    load_config as load_universe_config,
    load_symbols_from_db,
    refresh_universe,
)


NAVER_FINANCE_BASE = "https://finance.naver.com"
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DB_PATH = Path("data/omniscient_quant.sqlite3")
DEFAULT_LOG_PATH = Path("logs/backfill.log")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass(frozen=True)
class StockTarget:
    symbol: str
    name: str | None = None


@dataclass(frozen=True)
class BackfillConfig:
    db_path: Path
    log_path: Path
    stocks: tuple[StockTarget, ...]
    markets: tuple[str, ...]
    max_symbols: int | None
    max_pages_per_symbol: int
    request_timeout_seconds: int
    retry_count: int
    retry_backoff_seconds: float


@dataclass(frozen=True)
class DailyOhlcv:
    symbol: str
    trade_date: str
    open_price: int
    high_price: int
    low_price: int
    close_price: int
    volume: int


def require_positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def normalize_stock_target(item: Any) -> StockTarget:
    if isinstance(item, str):
        return StockTarget(symbol=item.strip())
    if isinstance(item, dict):
        return StockTarget(
            symbol=str(item["symbol"]).strip(),
            name=str(item["name"]).strip() if item.get("name") else None,
        )
    raise ValueError(f"Invalid stock target: {item!r}")


def normalize_markets(raw_markets: Any) -> tuple[str, ...]:
    if not raw_markets:
        return ("KOSPI", "KOSDAQ")
    return tuple(str(market).strip().upper() for market in raw_markets)


def optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0 when set")
    return parsed


def load_config(config_path: Path) -> BackfillConfig:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    database = raw.get("database", {})
    logging_config = raw.get("logging", {})
    historical = raw.get("historical", {})
    collection = raw.get("collection", {})

    stocks = tuple(normalize_stock_target(item) for item in raw.get("stocks", []))
    if not stocks:
        raise ValueError("config.yaml must define at least one stock under `stocks`")

    return BackfillConfig(
        db_path=Path(database.get("path", DEFAULT_DB_PATH)),
        log_path=Path(logging_config.get("backfill_path", DEFAULT_LOG_PATH)),
        stocks=stocks,
        markets=normalize_markets(historical.get("markets", ["KOSPI", "KOSDAQ"])),
        max_symbols=optional_positive_int(historical.get("max_symbols"), "historical.max_symbols"),
        max_pages_per_symbol=require_positive_int(
            historical.get("max_pages_per_symbol", 500),
            "historical.max_pages_per_symbol",
        ),
        request_timeout_seconds=require_positive_int(
            historical.get("request_timeout_seconds", collection.get("request_timeout_seconds", 10)),
            "historical.request_timeout_seconds",
        ),
        retry_count=require_positive_int(
            historical.get("retry_count", collection.get("retry_count", 3)),
            "historical.retry_count",
        ),
        retry_backoff_seconds=float(
            historical.get("retry_backoff_seconds", collection.get("retry_backoff_seconds", 2.0))
        ),
    )


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(file_handler)


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": NAVER_FINANCE_BASE,
        }
    )
    return session


def digits_to_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def fetch_soup(session: requests.Session, url: str, config: BackfillConfig) -> BeautifulSoup:
    last_error: Exception | None = None
    for attempt in range(1, config.retry_count + 1):
        try:
            response = session.get(url, timeout=config.request_timeout_seconds)
            response.raise_for_status()
            if not response.encoding:
                response.encoding = response.apparent_encoding
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= config.retry_count:
                break
            sleep_seconds = config.retry_backoff_seconds * attempt
            logging.warning(
                "request failed attempt=%s/%s url=%s error=%s retry_in=%.1fs",
                attempt,
                config.retry_count,
                url,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
    raise RuntimeError(f"Failed to fetch url={url}") from last_error


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ohlcv_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open_price INTEGER NOT NULL,
                high_price INTEGER NOT NULL,
                low_price INTEGER NOT NULL,
                close_price INTEGER NOT NULL,
                volume INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_trade_date
            ON ohlcv_daily(symbol, trade_date)
            """
        )


def parse_daily_rows(symbol: str, soup: BeautifulSoup) -> list[DailyOhlcv]:
    rows: list[DailyOhlcv] = []
    for row in soup.select("table.type2 tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) < 7:
            continue

        try:
            trade_date = datetime.strptime(cells[0], "%Y.%m.%d").date().isoformat()
        except ValueError:
            continue

        close_price = digits_to_int(cells[1])
        open_price = digits_to_int(cells[3])
        high_price = digits_to_int(cells[4])
        low_price = digits_to_int(cells[5])
        volume = digits_to_int(cells[6])
        if None in {close_price, open_price, high_price, low_price, volume}:
            continue

        rows.append(
            DailyOhlcv(
                symbol=symbol,
                trade_date=trade_date,
                open_price=int(open_price),
                high_price=int(high_price),
                low_price=int(low_price),
                close_price=int(close_price),
                volume=int(volume),
            )
        )
    return rows


def fetch_daily_page(
    symbol: str,
    page: int,
    session: requests.Session,
    config: BackfillConfig,
) -> list[DailyOhlcv]:
    url = f"{NAVER_FINANCE_BASE}/item/sise_day.naver?code={symbol}&page={page}"
    soup = fetch_soup(session, url, config)
    return parse_daily_rows(symbol, soup)


def save_daily_rows(db_path: Path, rows: list[DailyOhlcv]) -> int:
    inserted = 0
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO ohlcv_daily (
                    symbol,
                    trade_date,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.symbol,
                    row.trade_date,
                    row.open_price,
                    row.high_price,
                    row.low_price,
                    row.close_price,
                    row.volume,
                ),
            )
            inserted += cursor.rowcount
    return inserted


def backfill_symbol(symbol: str, session: requests.Session, config: BackfillConfig) -> dict[str, int]:
    fetched_total = 0
    inserted_total = 0
    empty_pages = 0

    for page in range(1, config.max_pages_per_symbol + 1):
        rows = fetch_daily_page(symbol, page, session, config)
        if not rows:
            empty_pages += 1
            if empty_pages >= 2:
                break
            continue

        fetched_total += len(rows)
        inserted_total += save_daily_rows(config.db_path, rows)
        empty_pages = 0

        if page % 25 == 0:
            logging.info(
                "backfill_progress symbol=%s page=%s fetched=%s inserted=%s",
                symbol,
                page,
                fetched_total,
                inserted_total,
            )
        time.sleep(0.15)

    return {"fetched": fetched_total, "inserted": inserted_total}


def backfill_all(config: BackfillConfig) -> dict[str, dict[str, int]]:
    init_db(config.db_path)
    session = create_session()
    results: dict[str, dict[str, int]] = {}

    for stock in config.stocks:
        logging.info("backfill_start symbol=%s name=%s", stock.symbol, stock.name)
        result = backfill_symbol(stock.symbol, session, config)
        results[stock.symbol] = result
        logging.info(
            "backfill_done symbol=%s fetched=%s inserted=%s",
            stock.symbol,
            result["fetched"],
            result["inserted"],
        )

    return results


def config_with_universe_stocks(
    config: BackfillConfig,
    config_path: Path,
    refresh: bool,
) -> BackfillConfig:
    if refresh:
        universe_config = load_universe_config(config_path)
        refresh_universe(universe_config)

    symbols = load_symbols_from_db(
        config.db_path,
        markets=config.markets,
        max_symbols=config.max_symbols,
    )
    if not symbols:
        universe_config = load_universe_config(config_path)
        refresh_universe(universe_config)
        symbols = load_symbols_from_db(
            config.db_path,
            markets=config.markets,
            max_symbols=config.max_symbols,
        )
    if not symbols:
        raise RuntimeError("No symbols found in stock_universe")

    return BackfillConfig(
        db_path=config.db_path,
        log_path=config.log_path,
        stocks=tuple(
            StockTarget(symbol=symbol.symbol, name=f"{symbol.name} ({symbol.market})")
            for symbol in symbols
        ),
        markets=config.markets,
        max_symbols=config.max_symbols,
        max_pages_per_symbol=config.max_pages_per_symbol,
        request_timeout_seconds=config.request_timeout_seconds,
        retry_count=config.retry_count,
        retry_backoff_seconds=config.retry_backoff_seconds,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Historical OHLCV backfill for Omniscient AI Quant System"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--symbol", help="Optional single symbol override")
    parser.add_argument("--all-symbols", action="store_true", help="Backfill all active symbols in stock_universe")
    parser.add_argument("--refresh-universe", action="store_true", help="Refresh KOSPI/KOSDAQ universe before backfill")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.symbol:
        config = BackfillConfig(
            db_path=config.db_path,
            log_path=config.log_path,
            stocks=(StockTarget(symbol=args.symbol),),
            markets=config.markets,
            max_symbols=config.max_symbols,
            max_pages_per_symbol=config.max_pages_per_symbol,
            request_timeout_seconds=config.request_timeout_seconds,
            retry_count=config.retry_count,
            retry_backoff_seconds=config.retry_backoff_seconds,
        )

    setup_logging(config.log_path)
    if args.all_symbols:
        config = config_with_universe_stocks(config, args.config, args.refresh_universe)
        logging.info("all_symbols_backfill_enabled symbols=%s", len(config.stocks))
    print(backfill_all(config))


if __name__ == "__main__":
    main()
