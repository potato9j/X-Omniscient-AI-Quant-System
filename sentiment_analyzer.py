from __future__ import annotations

import argparse
import json
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

import requests
import yaml


DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DB_PATH = Path("data/omniscient_quant.sqlite3")
DEFAULT_LOG_PATH = Path("logs/sentiment.log")


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    base_url: str
    model: str
    timeout_seconds: int
    temperature: float
    num_ctx: int
    num_predict: int


@dataclass(frozen=True)
class SentimentConfig:
    db_path: Path
    log_path: Path
    llm: LlmConfig
    batch_size: int
    interval_seconds: int
    max_items_per_cycle: int
    max_title_chars: int


@dataclass(frozen=True)
class NewsRecord:
    id: int
    symbol: str
    title: str
    source: str | None
    published_at: str | None
    url: str


@dataclass(frozen=True)
class SentimentResult:
    score: float
    summary: str
    event_tags: list[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def load_config(config_path: Path) -> SentimentConfig:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    database = raw.get("database", {})
    logging_config = raw.get("logging", {})
    llm = raw.get("llm", {})
    sentiment = raw.get("sentiment", {})

    return SentimentConfig(
        db_path=Path(database.get("path", DEFAULT_DB_PATH)),
        log_path=Path(logging_config.get("sentiment_path", DEFAULT_LOG_PATH)),
        llm=LlmConfig(
            provider=str(llm.get("provider", "ollama")).strip().lower(),
            base_url=str(llm.get("base_url", "http://localhost:11434")).rstrip("/"),
            model=str(llm.get("model", "gemma4:e2b")),
            timeout_seconds=require_positive_int(llm.get("timeout_seconds", 120), "llm.timeout_seconds"),
            temperature=float(llm.get("temperature", 0.0)),
            num_ctx=require_positive_int(llm.get("num_ctx", 4096), "llm.num_ctx"),
            num_predict=require_positive_int(llm.get("num_predict", 256), "llm.num_predict"),
        ),
        batch_size=require_positive_int(sentiment.get("batch_size", 1), "sentiment.batch_size"),
        interval_seconds=require_positive_int(
            sentiment.get("interval_seconds", 600),
            "sentiment.interval_seconds",
        ),
        max_items_per_cycle=require_positive_int(
            sentiment.get("max_items_per_cycle", 20),
            "sentiment.max_items_per_cycle",
        ),
        max_title_chars=require_positive_int(
            sentiment.get("max_title_chars", 240),
            "sentiment.max_title_chars",
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


def ensure_db_columns(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(naver_finance_news)").fetchall()
        }
        required = {
            "sentiment_score": "REAL",
            "ai_summary": "TEXT",
            "event_tags": "TEXT",
            "analyzed_at": "TEXT",
            "llm_model": "TEXT",
            "llm_raw_response": "TEXT",
        }
        for column, ddl_type in required.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE naver_finance_news ADD COLUMN {column} {ddl_type}")


def fetch_pending_news(db_path: Path, limit: int) -> list[NewsRecord]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, symbol, title, source, published_at, url
            FROM naver_finance_news
            WHERE analyzed_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        NewsRecord(
            id=int(row["id"]),
            symbol=str(row["symbol"]),
            title=str(row["title"]),
            source=row["source"],
            published_at=row["published_at"],
            url=str(row["url"]),
        )
        for row in rows
    ]


def clamp_score(score: float) -> float:
    return max(-1.0, min(1.0, score))


def build_prompt(record: NewsRecord, max_title_chars: int) -> str:
    title = record.title[:max_title_chars]
    return f"""
You are a Korean equity news sentiment analyst.
Analyze only the likely short-term impact on the stock price of the target symbol.
Return strict JSON only. Do not include markdown.

JSON schema:
{{
  "sentiment_score": number between -1.0 and 1.0,
  "summary": "Korean one-sentence summary under 80 characters",
  "event_tags": ["short Korean tags, max 5"]
}}

Scoring:
- +1.0 means strongly positive for stock price.
- 0.0 means neutral or unclear.
- -1.0 means strongly negative for stock price.

Target symbol: {record.symbol}
Source: {record.source or "unknown"}
Published at: {record.published_at or "unknown"}
Title: {title}
""".strip()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))

    if not isinstance(value, dict):
        raise ValueError("LLM response JSON must be an object")
    return value


def parse_sentiment_response(text: str) -> SentimentResult:
    payload = extract_json_object(text)
    score = clamp_score(float(payload.get("sentiment_score", 0.0)))
    summary = str(payload.get("summary", "")).strip()
    raw_tags = payload.get("event_tags", [])
    tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []

    return SentimentResult(
        score=score,
        summary=summary[:160],
        event_tags=tags[:5],
    )


def call_ollama(prompt: str, config: LlmConfig) -> str:
    response = requests.post(
        f"{config.base_url}/api/chat",
        json={
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {
                "temperature": config.temperature,
                "num_ctx": config.num_ctx,
                "num_predict": config.num_predict,
            },
        },
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("message", {}).get("content", "")).strip()


def call_lmstudio(prompt: str, config: LlmConfig) -> str:
    response = requests.post(
        f"{config.base_url}/v1/chat/completions",
        json={
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.temperature,
            "max_tokens": config.num_predict,
        },
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"]).strip()


def analyze_news(record: NewsRecord, config: SentimentConfig) -> tuple[SentimentResult, str]:
    prompt = build_prompt(record, config.max_title_chars)
    if config.llm.provider == "ollama":
        raw_response = call_ollama(prompt, config.llm)
    elif config.llm.provider in {"lmstudio", "lm_studio"}:
        raw_response = call_lmstudio(prompt, config.llm)
    else:
        raise ValueError(f"Unsupported llm.provider: {config.llm.provider}")

    return parse_sentiment_response(raw_response), raw_response


def save_sentiment_result(
    db_path: Path,
    record_id: int,
    result: SentimentResult,
    model: str,
    raw_response: str,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE naver_finance_news
            SET sentiment_score = ?,
                ai_summary = ?,
                event_tags = ?,
                analyzed_at = ?,
                llm_model = ?,
                llm_raw_response = ?
            WHERE id = ?
            """,
            (
                result.score,
                result.summary,
                json.dumps(result.event_tags, ensure_ascii=False),
                utc_now_iso(),
                model,
                raw_response,
                record_id,
            ),
        )


def analyze_once(config: SentimentConfig) -> int:
    ensure_db_columns(config.db_path)
    records = fetch_pending_news(config.db_path, config.max_items_per_cycle)
    if not records:
        logging.info("no pending news to analyze")
        return 0

    analyzed_count = 0
    for record in records:
        try:
            result, raw_response = analyze_news(record, config)
            save_sentiment_result(
                config.db_path,
                record.id,
                result,
                config.llm.model,
                raw_response,
            )
            analyzed_count += 1
            logging.info(
                "sentiment news_id=%s symbol=%s score=%.3f tags=%s",
                record.id,
                record.symbol,
                result.score,
                result.event_tags,
            )
        except Exception:
            logging.exception("sentiment analysis failed news_id=%s symbol=%s", record.id, record.symbol)

        if config.batch_size == 1:
            time.sleep(0.2)

    return analyzed_count


def run_scheduler(config: SentimentConfig) -> None:
    logging.info(
        "sentiment analyzer started provider=%s model=%s db=%s interval=%ss",
        config.llm.provider,
        config.llm.model,
        config.db_path,
        config.interval_seconds,
    )
    while True:
        started_at = time.monotonic()
        analyze_once(config)
        elapsed = time.monotonic() - started_at
        time.sleep(max(1.0, config.interval_seconds - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 2 Gemma sentiment analyzer for Omniscient AI Quant System"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    setup_logging(config.log_path)
    logging.info("loaded config path=%s", args.config)

    if args.once:
        analyze_once(config)
        return

    run_scheduler(config)


if __name__ == "__main__":
    main()
