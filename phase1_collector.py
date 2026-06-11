from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


NAVER_FINANCE_BASE = "https://finance.naver.com"
DEFAULT_DB_PATH = Path("omniscient_quant_phase1.sqlite3")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    collected_at: str
    current_price: int
    volume: int | None


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


def fetch_soup(session: requests.Session, url: str, timeout: int = 10) -> BeautifulSoup:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def crawl_current_price(symbol: str, session: requests.Session | None = None) -> PriceSnapshot:
    """Crawl the current price and volume for one KRX stock from Naver Finance."""
    session = session or create_session()
    symbol = symbol.strip()
    url = f"{NAVER_FINANCE_BASE}/item/main.naver?code={symbol}"
    soup = fetch_soup(session, url)

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
    session: requests.Session | None = None,
    pages: int = 1,
) -> list[NewsItem]:
    """Crawl recent Naver Finance stock news for one KRX stock."""
    session = session or create_session()
    symbol = symbol.strip()
    collected_at = utc_now_iso()
    items: list[NewsItem] = []
    seen_urls: set[str] = set()

    for page in range(1, pages + 1):
        url = (
            f"{NAVER_FINANCE_BASE}/item/news_news.naver"
            f"?code={symbol}&page={page}&sm=title_entity_id.basic&clusterId="
        )
        soup = fetch_soup(session, url)

        for row in soup.select("table.type5 tr"):
            title_node = row.select_one("td.title a")
            if not title_node:
                continue

            href = title_node.get("href", "")
            news_url = normalize_news_url(href)
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


def collect_once(symbol: str, db_path: Path, news_pages: int = 1) -> None:
    session = create_session()

    snapshot = crawl_current_price(symbol, session=session)
    save_price_snapshot(db_path, snapshot)

    news_items = crawl_naver_finance_news(symbol, session=session, pages=news_pages)
    inserted_news_count = save_news_items(db_path, news_items)

    logging.info(
        "symbol=%s price=%s volume=%s news_fetched=%s news_inserted=%s",
        snapshot.symbol,
        snapshot.current_price,
        snapshot.volume,
        len(news_items),
        inserted_news_count,
    )


def run_scheduler(
    symbol: str,
    db_path: Path,
    interval_seconds: int = 600,
    news_pages: int = 1,
) -> None:
    init_db(db_path)
    logging.info(
        "Phase 1 collector started: symbol=%s db=%s interval_seconds=%s",
        symbol,
        db_path,
        interval_seconds,
    )

    while True:
        started_at = time.monotonic()
        try:
            collect_once(symbol=symbol, db_path=db_path, news_pages=news_pages)
        except Exception:
            logging.exception("collection failed")

        elapsed = time.monotonic() - started_at
        time.sleep(max(1, interval_seconds - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 collector for Omniscient AI Quant System"
    )
    parser.add_argument(
        "--symbol",
        default="005930",
        help="KRX stock code to collect, e.g. 005930 for Samsung Electronics",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=600,
        help="Collection interval. Default is 600 seconds, or 10 minutes.",
    )
    parser.add_argument(
        "--news-pages",
        type=int,
        default=1,
        help="Number of Naver Finance news pages to crawl per collection cycle",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect once and exit instead of running the 24/7 scheduler",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()
    init_db(args.db)

    if args.once:
        collect_once(symbol=args.symbol, db_path=args.db, news_pages=args.news_pages)
        return

    run_scheduler(
        symbol=args.symbol,
        db_path=args.db,
        interval_seconds=args.interval_seconds,
        news_pages=args.news_pages,
    )


if __name__ == "__main__":
    main()
