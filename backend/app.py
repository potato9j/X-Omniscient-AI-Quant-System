from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import connect, database_path, row_to_dict, rows_to_dicts, safe_json_loads, table_exists
from .schemas import (
    Candle,
    HealthResponse,
    MarketIndexPoint,
    MarketIndexSnapshot,
    MarketLeaderItem,
    ModelStatus,
    NewsItem,
    PredictionExplanation,
    PredictionItem,
    StockSearchItem,
)


app = FastAPI(
    title="Omniscient AI Quant System API",
    version="0.1.0",
    description="Local API for market data, news sentiment, model status, and predictions.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _count_table(table_name: str) -> int:
    db_path = database_path()
    if not db_path.exists():
        return 0
    with connect(db_path) as conn:
        if not table_exists(conn, table_name):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _latest_predictions_cte() -> str:
    return """
    latest_prediction AS (
        SELECT *
        FROM (
            SELECT
                trend_predictions.*,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol
                    ORDER BY generated_at DESC, id DESC
                ) AS prediction_rank
            FROM trend_predictions
        )
        WHERE prediction_rank = 1
    )
    """


def _latest_ohlcv_cte() -> str:
    return """
    ordered_ohlcv AS (
        SELECT
            symbol,
            trade_date,
            close_price,
            volume,
            LAG(close_price) OVER (
                PARTITION BY symbol
                ORDER BY trade_date
            ) AS previous_close
        FROM ohlcv_daily
    ),
    latest_ohlcv AS (
        SELECT *
        FROM (
            SELECT
                ordered_ohlcv.*,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol
                    ORDER BY trade_date DESC
                ) AS price_rank
            FROM ordered_ohlcv
        )
        WHERE price_rank = 1
    )
    """


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().zfill(6)


def _prediction_explanation(item: dict[str, Any]) -> PredictionExplanation:
    snapshot = safe_json_loads(item.get("feature_snapshot")) or {}
    up_probability = float(item["up_probability"])
    down_probability = float(item["down_probability"])
    direction = str(item["expected_direction"])
    dominant_probability = max(up_probability, down_probability)
    opinion = "매수 우위" if direction == "UP" else "방어 우위"

    positives: list[str] = []
    negatives: list[str] = []
    risks: list[str] = []

    return_3 = snapshot.get("return_3")
    return_5 = snapshot.get("return_5")
    volume_change = snapshot.get("volume_change_1")
    volume_vs_ma = snapshot.get("volume_vs_ma_5")
    price_vs_ma_5 = snapshot.get("price_vs_ma_5")
    volatility = snapshot.get("volatility_5")
    sentiment = snapshot.get("sentiment_mean_6h")
    sentiment_count = snapshot.get("sentiment_count_6h")

    if return_3 is not None:
        if return_3 > 0:
            positives.append(f"최근 3스텝 수익률이 {return_3 * 100:.2f}%로 단기 반등 흐름이 있습니다.")
        elif return_3 < 0:
            negatives.append(f"최근 3스텝 수익률이 {return_3 * 100:.2f}%로 단기 흐름이 약합니다.")
    if return_5 is not None:
        if return_5 > 0:
            positives.append(f"최근 5스텝 누적 흐름은 {return_5 * 100:.2f}%로 플러스입니다.")
        elif return_5 < 0:
            negatives.append(f"최근 5스텝 누적 흐름은 {return_5 * 100:.2f}%로 하락 압력이 남아 있습니다.")
    if volume_change is not None:
        if volume_change > 0.2:
            positives.append(f"직전 대비 거래량이 {volume_change * 100:.1f}% 늘어 수급 변화가 감지됩니다.")
        elif volume_change < -0.2:
            negatives.append(f"직전 대비 거래량이 {abs(volume_change) * 100:.1f}% 줄어 추세 확인 강도가 약합니다.")
    if volume_vs_ma is not None:
        if volume_vs_ma > 0.2:
            positives.append(f"5스텝 평균 대비 거래량이 {volume_vs_ma * 100:.1f}% 높아 관심도가 커졌습니다.")
        elif volume_vs_ma < -0.2:
            negatives.append(f"5스텝 평균 대비 거래량이 {abs(volume_vs_ma) * 100:.1f}% 낮아 수급 탄력이 부족합니다.")
    if price_vs_ma_5 is not None:
        if price_vs_ma_5 > 0:
            positives.append(f"가격이 5스텝 평균보다 {price_vs_ma_5 * 100:.2f}% 위에 있습니다.")
        elif price_vs_ma_5 < 0:
            negatives.append(f"가격이 5스텝 평균보다 {abs(price_vs_ma_5) * 100:.2f}% 낮아 약세 위치입니다.")
    if sentiment is not None and sentiment_count:
        if sentiment > 0.05:
            positives.append(f"최근 뉴스 감성 평균이 {sentiment:.2f}로 우호적입니다.")
        elif sentiment < -0.05:
            negatives.append(f"최근 뉴스 감성 평균이 {sentiment:.2f}로 비우호적입니다.")
    elif sentiment_count == 0:
        risks.append("최근 분석된 뉴스 감성 표본이 없어 뉴스 기반 확신도는 제한적입니다.")

    if volatility is not None:
        if volatility > 0.05:
            risks.append(f"최근 변동성이 {volatility * 100:.2f}%로 높아 예측 신뢰 구간을 넓게 봐야 합니다.")
        elif volatility < 0.01:
            risks.append("최근 변동성이 낮아 방향성 신호가 작게 나타날 수 있습니다.")

    if not positives:
        positives.append("현재 feature 조합에서 강한 상승 근거는 제한적입니다.")
    if not negatives:
        negatives.append("현재 feature 조합에서 뚜렷한 하락 근거는 제한적입니다.")
    risks.append("현재 모델은 일봉/수집 스냅샷 기반입니다. 10분봉 실시간 판단은 장중 10분 OHLCV 수집이 붙은 뒤 유효합니다.")

    generated_at = str(item["generated_at"])
    try:
        generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        valid_until = generated_dt + timedelta(days=int(item["horizon_steps"]))
        valid_until_label = (
            f"{valid_until.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')} KST까지 "
            f"또는 새 가격/뉴스 데이터 반영 전까지"
        )
    except ValueError:
        valid_until_label = f"다음 {item['horizon_steps']}개 데이터 스텝 또는 새 데이터 반영 전까지"

    return PredictionExplanation(
        symbol=str(item["symbol"]),
        generated_at=generated_at,
        valid_until_label=valid_until_label,
        headline=f"{opinion} {dominant_probability * 100:.1f}%",
        summary=(
            f"모델은 상승 {up_probability * 100:.1f}%, 하락 {down_probability * 100:.1f}%로 "
            f"{opinion}를 선택했습니다. 판단은 가격 모멘텀, 거래량 변화, 평균 대비 위치, 변동성, 뉴스 감성을 함께 반영합니다."
        ),
        positive_reasons=positives,
        negative_reasons=negatives,
        risk_notes=risks,
        feature_snapshot=snapshot,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_path = database_path()
    return HealthResponse(
        status="ok" if db_path.exists() else "missing_database",
        database_path=str(db_path),
        database_exists=db_path.exists(),
        stock_count=_count_table("stock_universe"),
        ohlcv_rows=_count_table("ohlcv_daily"),
        prediction_rows=_count_table("trend_predictions"),
    )


@app.get("/markets/summary", response_model=list[MarketIndexSnapshot])
def market_summary() -> list[MarketIndexSnapshot]:
    with connect() as conn:
        if not table_exists(conn, "market_index_snapshots"):
            return []
        rows = conn.execute(
            """
            SELECT index_code AS market, collected_at, current_value, change_value, change_rate
            FROM (
                SELECT
                    market_index_snapshots.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY index_code
                        ORDER BY collected_at DESC, id DESC
                    ) AS row_rank
                FROM market_index_snapshots
            )
            WHERE row_rank = 1
            ORDER BY market
            """
        ).fetchall()
    return [MarketIndexSnapshot(**item) for item in rows_to_dicts(rows)]


@app.get("/markets/index-series", response_model=list[MarketIndexPoint])
def market_index_series(
    market: str = Query(default="KOSPI", pattern="^(KOSPI|KOSDAQ)$"),
    limit: int = Query(default=160, ge=20, le=1000),
) -> list[MarketIndexPoint]:
    with connect() as conn:
        if not table_exists(conn, "ohlcv_daily") or not table_exists(conn, "stock_universe"):
            return []
        rows = conn.execute(
            """
            WITH base AS (
                SELECT
                    o.symbol,
                    o.trade_date,
                    o.close_price,
                    FIRST_VALUE(o.close_price) OVER (
                        PARTITION BY o.symbol
                        ORDER BY o.trade_date
                    ) AS first_close
                FROM ohlcv_daily o
                JOIN stock_universe s ON s.symbol = o.symbol
                WHERE s.market = ?
            ),
            indexed AS (
                SELECT
                    trade_date,
                    AVG(CASE WHEN first_close > 0 THEN close_price * 100.0 / first_close END) AS value
                FROM base
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT ?
            )
            SELECT ? AS market, trade_date AS time, value
            FROM indexed
            ORDER BY time ASC
            """,
            (market, limit, market),
        ).fetchall()
    return [MarketIndexPoint(**item) for item in rows_to_dicts(rows)]


@app.get("/markets/leaders", response_model=list[MarketLeaderItem])
def market_leaders(
    sort: str = Query(default="volume", pattern="^(volume|change_rate|up_probability|down_probability)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    market: str | None = Query(default=None, pattern="^(KOSPI|KOSDAQ)$"),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[MarketLeaderItem]:
    sort_columns = {
        "volume": "l.volume",
        "change_rate": "change_rate",
        "up_probability": "COALESCE(p.up_probability, 0)",
        "down_probability": "COALESCE(p.down_probability, 0)",
    }
    sort_column = sort_columns[sort]
    sort_direction = "ASC" if order == "asc" else "DESC"
    market_filter = "AND s.market = ?" if market else ""
    params: list[Any] = []
    if market:
        params.append(market)
    params.append(limit)

    with connect() as conn:
        if not table_exists(conn, "ohlcv_daily") or not table_exists(conn, "stock_universe"):
            return []
        query = f"""
            WITH {_latest_ohlcv_cte()},
            {_latest_predictions_cte()}
            SELECT
                s.symbol,
                s.name,
                s.market,
                l.trade_date,
                l.close_price,
                l.volume,
                CASE
                    WHEN l.previous_close IS NULL THEN NULL
                    ELSE l.close_price - l.previous_close
                END AS change_price,
                CASE
                    WHEN l.previous_close IS NULL OR l.previous_close = 0 THEN NULL
                    ELSE (l.close_price - l.previous_close) * 1.0 / l.previous_close
                END AS change_rate,
                p.up_probability,
                p.down_probability,
                p.expected_direction
            FROM latest_ohlcv l
            JOIN stock_universe s ON s.symbol = l.symbol
            LEFT JOIN latest_prediction p ON p.symbol = l.symbol
            WHERE s.active = 1
            {market_filter}
            ORDER BY {sort_column} {sort_direction}, s.symbol ASC
            LIMIT ?
        """
        rows = conn.execute(query, params).fetchall()
    return [MarketLeaderItem(**item) for item in rows_to_dicts(rows)]


@app.get("/markets/signals", response_model=list[MarketLeaderItem])
def market_signals(
    direction: str = Query(default="up", pattern="^(up|down)$"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[MarketLeaderItem]:
    sort_column = "p.up_probability" if direction == "up" else "p.down_probability"
    with connect() as conn:
        if not table_exists(conn, "trend_predictions"):
            return []
        query = f"""
            WITH {_latest_ohlcv_cte()},
            {_latest_predictions_cte()}
            SELECT
                s.symbol,
                s.name,
                s.market,
                l.trade_date,
                l.close_price,
                l.volume,
                CASE
                    WHEN l.previous_close IS NULL THEN NULL
                    ELSE l.close_price - l.previous_close
                END AS change_price,
                CASE
                    WHEN l.previous_close IS NULL OR l.previous_close = 0 THEN NULL
                    ELSE (l.close_price - l.previous_close) * 1.0 / l.previous_close
                END AS change_rate,
                p.up_probability,
                p.down_probability,
                p.expected_direction
            FROM latest_prediction p
            JOIN stock_universe s ON s.symbol = p.symbol
            LEFT JOIN latest_ohlcv l ON l.symbol = p.symbol
            WHERE s.active = 1
            ORDER BY {sort_column} DESC, s.symbol ASC
            LIMIT ?
        """
        rows = conn.execute(query, (limit,)).fetchall()
    return [MarketLeaderItem(**item) for item in rows_to_dicts(rows)]


@app.get("/markets/news", response_model=list[NewsItem])
def market_news(limit: int = Query(default=12, ge=1, le=50)) -> list[NewsItem]:
    with connect() as conn:
        if not table_exists(conn, "naver_finance_news"):
            return []
        rows = conn.execute(
            """
            SELECT id, symbol, title, source, published_at, url,
                   sentiment_score, ai_summary, event_tags, analyzed_at, llm_model
            FROM naver_finance_news
            ORDER BY COALESCE(published_at, collected_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [NewsItem(**item) for item in rows_to_dicts(rows)]


@app.get("/stocks/search", response_model=list[StockSearchItem])
def search_stocks(
    q: str = Query(default="", description="Symbol or Korean/English stock name fragment"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[StockSearchItem]:
    query = f"%{q.strip()}%"
    with connect() as conn:
        if not table_exists(conn, "stock_universe"):
            return []
        rows = conn.execute(
            """
            SELECT symbol, name, market, market_rank
            FROM stock_universe
            WHERE active = 1
              AND (? = '%%' OR symbol LIKE ? OR name LIKE ?)
            ORDER BY
              CASE WHEN symbol = ? THEN 0 ELSE 1 END,
              COALESCE(market_rank, 999999),
              symbol
            LIMIT ?
            """,
            (query, query, query, q.strip(), limit),
        ).fetchall()
    return [StockSearchItem(**item) for item in rows_to_dicts(rows)]


@app.get("/stocks/{symbol}", response_model=StockSearchItem)
def get_stock(symbol: str) -> StockSearchItem:
    normalized = _normalize_symbol(symbol)
    with connect() as conn:
        if not table_exists(conn, "stock_universe"):
            raise HTTPException(status_code=404, detail="stock universe is not available")
        row = conn.execute(
            """
            SELECT symbol, name, market, market_rank
            FROM stock_universe
            WHERE symbol = ? AND active = 1
            """,
            (normalized,),
        ).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail=f"stock not found: {normalized}")
    return StockSearchItem(**item)


@app.get("/stocks/{symbol}/candles", response_model=list[Candle])
def get_candles(
    symbol: str,
    limit: int = Query(default=240, ge=1, le=2000),
) -> list[Candle]:
    normalized = _normalize_symbol(symbol)
    with connect() as conn:
        if not table_exists(conn, "ohlcv_daily"):
            return []
        rows = conn.execute(
            """
            SELECT symbol, trade_date, open_price, high_price, low_price, close_price, volume
            FROM ohlcv_daily
            WHERE symbol = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (normalized, limit),
        ).fetchall()
    items = rows_to_dicts(rows)
    items.reverse()
    return [Candle(**item) for item in items]


@app.get("/stocks/{symbol}/news", response_model=list[NewsItem])
def get_news(
    symbol: str,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[NewsItem]:
    normalized = _normalize_symbol(symbol)
    with connect() as conn:
        if not table_exists(conn, "naver_finance_news"):
            return []
        rows = conn.execute(
            """
            SELECT id, symbol, title, source, published_at, url,
                   sentiment_score, ai_summary, event_tags, analyzed_at, llm_model
            FROM naver_finance_news
            WHERE symbol = ?
            ORDER BY COALESCE(published_at, collected_at) DESC, id DESC
            LIMIT ?
            """,
            (normalized, limit),
        ).fetchall()
    return [NewsItem(**item) for item in rows_to_dicts(rows)]


@app.get("/stocks/{symbol}/prediction", response_model=PredictionItem)
def get_latest_prediction(symbol: str) -> PredictionItem:
    normalized = _normalize_symbol(symbol)
    with connect() as conn:
        if not table_exists(conn, "trend_predictions"):
            raise HTTPException(status_code=404, detail="predictions are not available")
        row = conn.execute(
            """
            SELECT symbol, generated_at, horizon_steps, current_price,
                   up_probability, down_probability, expected_direction,
                   model_version, feature_snapshot
            FROM trend_predictions
            WHERE symbol = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail=f"prediction not found: {normalized}")
    item["feature_snapshot"] = safe_json_loads(item.get("feature_snapshot"))
    return PredictionItem(**item)


@app.get("/stocks/{symbol}/explanation", response_model=PredictionExplanation)
def get_prediction_explanation(symbol: str) -> PredictionExplanation:
    normalized = _normalize_symbol(symbol)
    with connect() as conn:
        if not table_exists(conn, "trend_predictions"):
            raise HTTPException(status_code=404, detail="predictions are not available")
        row = conn.execute(
            """
            SELECT symbol, generated_at, horizon_steps, current_price,
                   up_probability, down_probability, expected_direction,
                   model_version, feature_snapshot
            FROM trend_predictions
            WHERE symbol = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail=f"prediction explanation not found: {normalized}")
    return _prediction_explanation(item)


@app.get("/models/status", response_model=ModelStatus)
def model_status() -> ModelStatus:
    config_path = Path("config.yaml")
    config: dict[str, Any] = {}
    if config_path.exists():
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    prediction_config = config.get("prediction", {})
    model_path = Path(prediction_config.get("model_path", "models/predictor_latest.joblib"))
    metadata_path = Path(prediction_config.get("metadata_path", "models/metadata.json"))

    metadata = None
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    release_dir = Path("models/releases")
    releases: list[dict[str, Any]] = []
    if release_dir.exists():
        for path in sorted(release_dir.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
            releases.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                }
            )

    return ModelStatus(
        model_exists=model_path.exists(),
        metadata_exists=metadata_path.exists(),
        model_path=str(model_path),
        metadata_path=str(metadata_path),
        metadata=metadata,
        release_packages=releases,
    )
