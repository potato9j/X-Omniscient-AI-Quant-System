from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as clock_time, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
import yaml
from bs4 import BeautifulSoup


NAVER_FINANCE_BASE = "https://finance.naver.com"
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DB_PATH = Path("data/omniscient_quant.sqlite3")
DEFAULT_LOG_PATH = Path("logs/collector.log")
KST = ZoneInfo("Asia/Seoul")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass(frozen=True)
class StockTarget:
    symbol: str
    name: str | None = None


@dataclass(frozen=True)
class IndexTarget:
    code: str
    name: str | None = None


@dataclass(frozen=True)
class CollectorConfig:
    db_path: Path
    log_path: Path
    stocks: tuple[StockTarget, ...]
    indices: tuple[IndexTarget, ...]
    price_interval_seconds: int
    news_interval_seconds: int
    request_timeout_seconds: int
    retry_count: int
    retry_backoff_seconds: float
    news_pages: int
    skip_price_collection_outside_market: bool


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    collected_at: str
    current_price: int
    volume: int | None


@dataclass(frozen=True)
class MarketIndexSnapshot:
    index_code: str
    collected_at: str
    current_value: float
    change_value: float | None
    change_rate: float | None


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    collected_at: str
    title: str
    source: str | None
    published_at: str | None
    url: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digits_to_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def number_to_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"-?[\d,]+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


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


def normalize_index_target(item: Any) -> IndexTarget:
    if isinstance(item, str):
        return IndexTarget(code=item.strip().upper())
    if isinstance(item, dict):
        return IndexTarget(
            code=str(item["code"]).strip().upper(),
            name=str(item["name"]).strip() if item.get("name") else None,
        )
    raise ValueError(f"Invalid index target: {item!r}")


def load_config(config_path: Path) -> CollectorConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    database = raw.get("database", {})
    logging_config = raw.get("logging", {})
    collection = raw.get("collection", {})

    stocks = tuple(normalize_stock_target(item) for item in raw.get("stocks", []))
    if not stocks:
        raise ValueError("config.yaml must define at least one stock under `stocks`")

    indices = tuple(normalize_index_target(item) for item in raw.get("indices", []))

    return CollectorConfig(
        db_path=Path(database.get("path", DEFAULT_DB_PATH)),
        log_path=Path(logging_config.get("path", DEFAULT_LOG_PATH)),
        stocks=stocks,
        indices=indices,
        price_interval_seconds=require_positive_int(
            collection.get("price_interval_seconds", 60),
            "collection.price_interval_seconds",
        ),
        news_interval_seconds=require_positive_int(
            collection.get("news_interval_seconds", 600),
            "collection.news_interval_seconds",
        ),
        request_timeout_seconds=require_positive_int(
            collection.get("request_timeout_seconds", 10),
            "collection.request_timeout_seconds",
        ),
        retry_count=require_positive_int(
            collection.get("retry_count", 3),
            "collection.retry_count",
        ),
        retry_backoff_seconds=float(collection.get("retry_backoff_seconds", 2.0)),
        news_pages=require_positive_int(
            collection.get("news_pages", 1),
            "collection.news_pages",
        ),
        skip_price_collection_outside_market=bool(
            collection.get("skip_price_collection_outside_market", False)
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


def is_regular_market_time(now: datetime | None = None) -> bool:
    current = now.astimezone(KST) if now else datetime.now(KST)
    if current.weekday() >= 5:
        return False
    return clock_time(9, 0) <= current.time() <= clock_time(15, 30)


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


def fetch_soup(
    session: requests.Session,
    url: str,
    timeout: int,
    retry_count: int,
    retry_backoff_seconds: float,
) -> BeautifulSoup:
    last_error: Exception | None = None

    for attempt in range(1, retry_count + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            if not response.encoding:
                response.encoding = response.apparent_encoding
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retry_count:
                break
            sleep_seconds = retry_backoff_seconds * attempt
            logging.warning(
                "request failed attempt=%s/%s url=%s error=%s retry_in=%.1fs",
                attempt,
                retry_count,
                url,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Failed to fetch url={url}") from last_error


def extract_volume(soup: BeautifulSoup) -> int | None:
    volume_label = "\uac70\ub798\ub7c9"

    for th in soup.select("table.no_info th"):
        text = th.get_text(" ", strip=True)
        if volume_label not in text:
            continue

        sibling = th.find_next_sibling("td")
        if sibling:
            volume_node = sibling.select_one("span.blind")
            volume = digits_to_int(volume_node.get_text(strip=True) if volume_node else None)
            if volume is not None:
                return volume

        match = re.search(rf"{volume_label}\s+([\d,]+)", text)
        if match:
            return digits_to_int(match.group(1))

    for dd in soup.select("dl.blind dd"):
        text = dd.get_text(" ", strip=True)
        match = re.search(rf"^{volume_label}\s+([\d,]+)", text)
        if match:
            return digits_to_int(match.group(1))

    return None


def crawl_current_price(
    symbol: str,
    session: requests.Session,
    config: CollectorConfig,
) -> PriceSnapshot:
    symbol = symbol.strip()
    url = f"{NAVER_FINANCE_BASE}/item/main.naver?code={symbol}"
    soup = fetch_soup(
        session,
        url,
        config.request_timeout_seconds,
        config.retry_count,
        config.retry_backoff_seconds,
    )

    price_node = soup.select_one("p.no_today span.blind")
    if not price_node:
        raise ValueError(f"Could not find current price for symbol={symbol}")

    current_price = digits_to_int(price_node.get_text(strip=True))
    if current_price is None:
        raise ValueError(f"Could not parse current price for symbol={symbol}")

    return PriceSnapshot(
        symbol=symbol,
        collected_at=utc_now_iso(),
        current_price=current_price,
        volume=extract_volume(soup),
    )


def crawl_market_index(
    index_code: str,
    session: requests.Session,
    config: CollectorConfig,
) -> MarketIndexSnapshot:
    index_code = index_code.strip().upper()
    url = f"{NAVER_FINANCE_BASE}/sise/sise_index.naver?code={index_code}"
    soup = fetch_soup(
        session,
        url,
        config.request_timeout_seconds,
        config.retry_count,
        config.retry_backoff_seconds,
    )

    value_node = soup.select_one("em#now_value")
    if not value_node:
        value_node = soup.select_one("p.no_today span.blind")
    current_value = number_to_float(value_node.get_text(" ", strip=True) if value_node else None)
    if current_value is None:
        raise ValueError(f"Could not parse market index value for code={index_code}")

    change_value = None
    change_rate = None
    change_node = soup.select_one("span#change_value_and_rate")
    if change_node:
        change_text = change_node.get_text(" ", strip=True)
        numbers = re.findall(r"-?[\d,]+(?:\.\d+)?", change_text)
        if numbers:
            change_value = float(numbers[0].replace(",", ""))
        if len(numbers) >= 2:
            change_rate = float(numbers[1].replace(",", ""))

    return MarketIndexSnapshot(
        index_code=index_code,
        collected_at=utc_now_iso(),
        current_value=current_value,
        change_value=change_value,
        change_rate=change_rate,
    )


def normalize_news_url(href: str) -> str:
    absolute = urljoin(NAVER_FINANCE_BASE, href)
    parsed = urlparse(absolute)
    query = parse_qs(parsed.query)
    article_id = query.get("article_id", [""])[0]
    office_id = query.get("office_id", [""])[0]

    if article_id and office_id:
        return (
            f"{NAVER_FINANCE_BASE}/item/news_read.naver"
            f"?article_id={article_id}&office_id={office_id}"
        )
    return absolute


def crawl_naver_finance_news(
    symbol: str,
    session: requests.Session,
    config: CollectorConfig,
) -> list[NewsItem]:
    symbol = symbol.strip()
    collected_at = utc_now_iso()
    items: list[NewsItem] = []
    seen_urls: set[str] = set()

    for page in range(1, config.news_pages + 1):
        url = (
            f"{NAVER_FINANCE_BASE}/item/news_news.naver"
            f"?code={symbol}&page={page}&sm=title_entity_id.basic&clusterId="
        )
        soup = fetch_soup(
            session,
            url,
            config.request_timeout_seconds,
            config.retry_count,
            config.retry_backoff_seconds,
        )

        for row in soup.select("table.type5 tr"):
            title_node = row.select_one("td.title a")
            if not title_node:
                continue

            news_url = normalize_news_url(title_node.get("href", ""))
            if news_url in seen_urls:
                continue
            seen_urls.add(news_url)

            source_node = row.select_one("td.info")
            date_node = row.select_one("td.date")
            items.append(
                NewsItem(
                    symbol=symbol,
                    collected_at=collected_at,
                    title=title_node.get_text(" ", strip=True),
                    source=source_node.get_text(" ", strip=True) if source_node else None,
                    published_at=date_node.get_text(" ", strip=True) if date_node else None,
                    url=news_url,
                )
            )

    return items


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                current_price INTEGER NOT NULL,
                volume INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_price_symbol_collected_at
            ON price_snapshots(symbol, collected_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_index_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_code TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                current_value REAL NOT NULL,
                change_value REAL,
                change_rate REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_index_code_collected_at
            ON market_index_snapshots(index_code, collected_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS naver_finance_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT,
                published_at TEXT,
                url TEXT NOT NULL UNIQUE,
                sentiment_score REAL,
                ai_summary TEXT,
                event_tags TEXT,
                analyzed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_symbol_published_at
            ON naver_finance_news(symbol, published_at)
            """
        )
        ensure_column(conn, "naver_finance_news", "event_tags", "TEXT")


def ensure_column(conn: sqlite3.Connection, table_name: str, column: str, ddl_type: str) -> None:
    columns = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {ddl_type}")


def save_price_snapshot(db_path: Path, snapshot: PriceSnapshot) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO price_snapshots (
                symbol,
                collected_at,
                current_price,
                volume
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                snapshot.symbol,
                snapshot.collected_at,
                snapshot.current_price,
                snapshot.volume,
            ),
        )


def save_market_index_snapshot(db_path: Path, snapshot: MarketIndexSnapshot) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO market_index_snapshots (
                index_code,
                collected_at,
                current_value,
                change_value,
                change_rate
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                snapshot.index_code,
                snapshot.collected_at,
                snapshot.current_value,
                snapshot.change_value,
                snapshot.change_rate,
            ),
        )


def save_news_items(db_path: Path, news_items: Iterable[NewsItem]) -> int:
    inserted = 0
    with sqlite3.connect(db_path) as conn:
        for item in news_items:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO naver_finance_news (
                    symbol,
                    collected_at,
                    title,
                    source,
                    published_at,
                    url
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.symbol,
                    item.collected_at,
                    item.title,
                    item.source,
                    item.published_at,
                    item.url,
                ),
            )
            inserted += cursor.rowcount
    return inserted


def collect_prices(config: CollectorConfig, session: requests.Session) -> None:
    if config.skip_price_collection_outside_market and not is_regular_market_time():
        logging.info("price collection skipped outside regular KRX market hours")
        return

    for stock in config.stocks:
        try:
            snapshot = crawl_current_price(stock.symbol, session=session, config=config)
            save_price_snapshot(config.db_path, snapshot)
            logging.info(
                "stock_price symbol=%s price=%s volume=%s",
                snapshot.symbol,
                snapshot.current_price,
                snapshot.volume,
            )
        except Exception:
            logging.exception("stock price collection failed symbol=%s", stock.symbol)

    for index in config.indices:
        try:
            snapshot = crawl_market_index(index.code, session=session, config=config)
            save_market_index_snapshot(config.db_path, snapshot)
            logging.info(
                "market_index code=%s value=%s change=%s rate=%s",
                snapshot.index_code,
                snapshot.current_value,
                snapshot.change_value,
                snapshot.change_rate,
            )
        except Exception:
            logging.exception("market index collection failed code=%s", index.code)


def collect_news(config: CollectorConfig, session: requests.Session) -> None:
    for stock in config.stocks:
        try:
            news_items = crawl_naver_finance_news(
                stock.symbol,
                session=session,
                config=config,
            )
            inserted_count = save_news_items(config.db_path, news_items)
            logging.info(
                "news symbol=%s fetched=%s inserted=%s",
                stock.symbol,
                len(news_items),
                inserted_count,
            )
        except Exception:
            logging.exception("news collection failed symbol=%s", stock.symbol)


def collect_once(config: CollectorConfig) -> None:
    init_db(config.db_path)
    session = create_session()
    collect_prices(config, session)
    collect_news(config, session)


def run_scheduler(config: CollectorConfig) -> None:
    init_db(config.db_path)
    session = create_session()
    next_news_at = 0.0

    logging.info(
        "Phase 1 collector started stocks=%s indices=%s db=%s price_interval=%ss news_interval=%ss",
        [stock.symbol for stock in config.stocks],
        [index.code for index in config.indices],
        config.db_path,
        config.price_interval_seconds,
        config.news_interval_seconds,
    )

    while True:
        loop_started_at = time.monotonic()
        collect_prices(config, session)

        now = time.monotonic()
        if now >= next_news_at:
            collect_news(config, session)
            next_news_at = now + config.news_interval_seconds

        elapsed = time.monotonic() - loop_started_at
        sleep_seconds = max(1.0, config.price_interval_seconds - elapsed)
        time.sleep(sleep_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 collector for Omniscient AI Quant System"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect once and exit instead of running the scheduler",
    )
    parser.add_argument(
        "--symbol",
        help="Optional single KRX stock code override for quick tests",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.symbol:
        config = CollectorConfig(
            db_path=config.db_path,
            log_path=config.log_path,
            stocks=(StockTarget(symbol=args.symbol),),
            indices=config.indices,
            price_interval_seconds=config.price_interval_seconds,
            news_interval_seconds=config.news_interval_seconds,
            request_timeout_seconds=config.request_timeout_seconds,
            retry_count=config.retry_count,
            retry_backoff_seconds=config.retry_backoff_seconds,
            news_pages=config.news_pages,
            skip_price_collection_outside_market=config.skip_price_collection_outside_market,
        )

    setup_logging(config.log_path)
    logging.info("loaded config path=%s", args.config)

    if args.once:
        collect_once(config)
        return

    run_scheduler(config)


if __name__ == "__main__":
    main()
