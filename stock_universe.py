from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup


NAVER_FINANCE_BASE = "https://finance.naver.com"
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DB_PATH = Path("data/omniscient_quant.sqlite3")
DEFAULT_LOG_PATH = Path("logs/universe.log")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
MARKET_TO_SOSOK = {
    "KOSPI": "0",
    "KOSDAQ": "1",
}


@dataclass(frozen=True)
class StockSymbol:
    symbol: str
    name: str
    market: str
    market_rank: int | None = None


@dataclass(frozen=True)
class UniverseConfig:
    db_path: Path
    log_path: Path
    markets: tuple[str, ...]
    max_pages_per_market: int
    request_timeout_seconds: int
    retry_count: int
    retry_backoff_seconds: float


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def normalize_markets(raw_markets: Any) -> tuple[str, ...]:
    if not raw_markets:
        return ("KOSPI", "KOSDAQ")
    markets = tuple(str(market).strip().upper() for market in raw_markets)
    invalid = [market for market in markets if market not in MARKET_TO_SOSOK]
    if invalid:
        raise ValueError(f"Unsupported markets: {invalid}")
    return markets


def load_config(config_path: Path) -> UniverseConfig:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    database = raw.get("database", {})
    logging_config = raw.get("logging", {})
    universe = raw.get("universe", {})
    collection = raw.get("collection", {})

    return UniverseConfig(
        db_path=Path(database.get("path", DEFAULT_DB_PATH)),
        log_path=Path(logging_config.get("universe_path", DEFAULT_LOG_PATH)),
        markets=normalize_markets(universe.get("markets", ["KOSPI", "KOSDAQ"])),
        max_pages_per_market=require_positive_int(
            universe.get("max_pages_per_market", 80),
            "universe.max_pages_per_market",
        ),
        request_timeout_seconds=require_positive_int(
            universe.get("request_timeout_seconds", collection.get("request_timeout_seconds", 10)),
            "universe.request_timeout_seconds",
        ),
        retry_count=require_positive_int(
            universe.get("retry_count", collection.get("retry_count", 3)),
            "universe.retry_count",
        ),
        retry_backoff_seconds=float(
            universe.get("retry_backoff_seconds", collection.get("retry_backoff_seconds", 2.0))
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


def fetch_soup(session: requests.Session, url: str, config: UniverseConfig) -> BeautifulSoup:
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
            CREATE TABLE IF NOT EXISTS stock_universe (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market TEXT NOT NULL,
                source TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                market_rank INTEGER,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(stock_universe)").fetchall()
        }
        if "market_rank" not in columns:
            conn.execute("ALTER TABLE stock_universe ADD COLUMN market_rank INTEGER")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_stock_universe_market
            ON stock_universe(market, active)
            """
        )


def parse_symbols_from_market_page(
    market: str,
    soup: BeautifulSoup,
    page: int,
) -> list[StockSymbol]:
    symbols: dict[str, StockSymbol] = {}
    for link in soup.select("a[href*='/item/main.naver?code=']"):
        href = urljoin(NAVER_FINANCE_BASE, link.get("href", ""))
        parsed = urlparse(href)
        code = parse_qs(parsed.query).get("code", [""])[0]
        if not re.fullmatch(r"\d{6}", code):
            continue
        name = link.get_text(" ", strip=True)
        if not name:
            continue
        market_rank = ((page - 1) * 50) + len(symbols) + 1
        symbols[code] = StockSymbol(
            symbol=code,
            name=name,
            market=market,
            market_rank=market_rank,
        )
    return list(symbols.values())


def fetch_market_symbols(
    market: str,
    session: requests.Session,
    config: UniverseConfig,
) -> list[StockSymbol]:
    sosok = MARKET_TO_SOSOK[market]
    symbols: dict[str, StockSymbol] = {}
    empty_pages = 0

    for page in range(1, config.max_pages_per_market + 1):
        url = f"{NAVER_FINANCE_BASE}/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
        soup = fetch_soup(session, url, config)
        page_symbols = parse_symbols_from_market_page(market, soup, page)
        if not page_symbols:
            empty_pages += 1
            if empty_pages >= 2:
                break
            continue

        for symbol in page_symbols:
            symbols[symbol.symbol] = symbol
        empty_pages = 0

        if page % 10 == 0:
            logging.info("universe_progress market=%s page=%s symbols=%s", market, page, len(symbols))
        time.sleep(0.1)

    return list(symbols.values())


def save_universe_symbols(db_path: Path, symbols: list[StockSymbol]) -> int:
    seen_at = utc_now_iso()
    saved = 0
    with sqlite3.connect(db_path) as conn:
        for symbol in symbols:
            conn.execute(
                """
                INSERT INTO stock_universe (
                    symbol,
                    name,
                    market,
                    source,
                    active,
                    market_rank,
                    last_seen_at,
                    updated_at
                )
                VALUES (?, ?, ?, 'naver_market_sum', 1, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    market = excluded.market,
                    active = 1,
                    market_rank = excluded.market_rank,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (
                    symbol.symbol,
                    symbol.name,
                    symbol.market,
                    symbol.market_rank,
                    seen_at,
                    seen_at,
                ),
            )
            saved += 1
    return saved


def refresh_universe(config: UniverseConfig) -> list[StockSymbol]:
    init_db(config.db_path)
    session = create_session()
    all_symbols: list[StockSymbol] = []

    for market in config.markets:
        logging.info("universe_refresh_start market=%s", market)
        symbols = fetch_market_symbols(market, session, config)
        saved = save_universe_symbols(config.db_path, symbols)
        all_symbols.extend(symbols)
        logging.info("universe_refresh_done market=%s fetched=%s saved=%s", market, len(symbols), saved)

    return all_symbols


def load_symbols_from_db(
    db_path: Path,
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    max_symbols: int | None = None,
) -> list[StockSymbol]:
    init_db(db_path)
    placeholders = ",".join("?" for _ in markets)
    query = f"""
        SELECT symbol, name, market, market_rank
        FROM stock_universe
        WHERE active = 1
          AND market IN ({placeholders})
        ORDER BY
            CASE market WHEN 'KOSPI' THEN 0 WHEN 'KOSDAQ' THEN 1 ELSE 2 END,
            COALESCE(market_rank, 999999),
            symbol
    """
    params: list[Any] = list(markets)
    if max_symbols is not None:
        query += " LIMIT ?"
        params.append(max_symbols)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        StockSymbol(
            symbol=str(row[0]),
            name=str(row[1]),
            market=str(row[2]),
            market_rank=int(row[3]) if row[3] is not None else None,
        )
        for row in rows
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KOSPI/KOSDAQ stock universe refresh for Omniscient AI Quant System"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    setup_logging(config.log_path)
    symbols = refresh_universe(config)
    print({"symbols": len(symbols), "markets": list(config.markets)})


if __name__ == "__main__":
    main()
