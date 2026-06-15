from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    database_path: str
    database_exists: bool
    stock_count: int = 0
    ohlcv_rows: int = 0
    prediction_rows: int = 0


class StockSearchItem(BaseModel):
    symbol: str
    name: str
    market: str
    market_rank: int | None = None


class MarketIndexSnapshot(BaseModel):
    market: str
    collected_at: str | None = None
    current_value: float | None = None
    change_value: float | None = None
    change_rate: float | None = None


class MarketIndexPoint(BaseModel):
    market: str
    time: str
    value: float


class MarketLeaderItem(BaseModel):
    symbol: str
    name: str
    market: str
    trade_date: str
    close_price: int
    volume: int
    change_price: int | None = None
    change_rate: float | None = None
    up_probability: float | None = None
    down_probability: float | None = None
    expected_direction: str | None = None


class Candle(BaseModel):
    symbol: str
    trade_date: str
    open_price: int
    high_price: int
    low_price: int
    close_price: int
    volume: int


class NewsItem(BaseModel):
    id: int
    symbol: str
    title: str
    source: str | None = None
    published_at: str | None = None
    url: str
    sentiment_score: float | None = None
    ai_summary: str | None = None
    event_tags: str | None = None
    analyzed_at: str | None = None
    llm_model: str | None = None


class PredictionItem(BaseModel):
    symbol: str
    generated_at: str
    horizon_steps: int
    current_price: int
    up_probability: float
    down_probability: float
    expected_direction: str
    model_version: str
    feature_snapshot: Any = Field(default=None)


class PredictionExplanation(BaseModel):
    symbol: str
    generated_at: str
    valid_until_label: str
    headline: str
    summary: str
    positive_reasons: list[str]
    negative_reasons: list[str]
    risk_notes: list[str]
    feature_snapshot: dict[str, Any] | None = None


class ModelStatus(BaseModel):
    model_exists: bool
    metadata_exists: bool
    model_path: str
    metadata_path: str
    metadata: dict[str, Any] | None = None
    release_packages: list[dict[str, Any]]


class SentimentStatus(BaseModel):
    total_news: int
    analyzed_news: int
    pending_news: int
    provider: str
    model: str
    job_status: str
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_analyzed_count: int = 0
    last_error: str | None = None


class SentimentAnalyzeResponse(BaseModel):
    status: str
    accepted: bool
    pending_news: int
    message: str
