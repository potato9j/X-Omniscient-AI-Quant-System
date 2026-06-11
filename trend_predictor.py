from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline


DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DB_PATH = Path("data/omniscient_quant.sqlite3")
DEFAULT_LOG_PATH = Path("logs/predictor.log")
DEFAULT_MODEL_PATH = Path("models/predictor_latest.joblib")
DEFAULT_METADATA_PATH = Path("models/metadata.json")
FEATURE_COLUMNS = [
    "return_1",
    "return_3",
    "return_5",
    "volume_change_1",
    "price_vs_ma_3",
    "price_vs_ma_5",
    "sentiment_mean_6h",
    "sentiment_count_6h",
]


@dataclass(frozen=True)
class PredictionConfig:
    db_path: Path
    log_path: Path
    model_path: Path
    metadata_path: Path
    retrain_interval_seconds: int
    horizon_steps: int
    min_training_rows: int
    test_size: float
    random_state: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def load_config(config_path: Path) -> PredictionConfig:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    database = raw.get("database", {})
    logging_config = raw.get("logging", {})
    prediction = raw.get("prediction", {})

    return PredictionConfig(
        db_path=Path(database.get("path", DEFAULT_DB_PATH)),
        log_path=Path(logging_config.get("prediction_path", DEFAULT_LOG_PATH)),
        model_path=Path(prediction.get("model_path", DEFAULT_MODEL_PATH)),
        metadata_path=Path(prediction.get("metadata_path", DEFAULT_METADATA_PATH)),
        retrain_interval_seconds=require_positive_int(
            prediction.get("retrain_interval_seconds", 1800),
            "prediction.retrain_interval_seconds",
        ),
        horizon_steps=require_positive_int(
            prediction.get("horizon_steps", 5),
            "prediction.horizon_steps",
        ),
        min_training_rows=require_positive_int(
            prediction.get("min_training_rows", 50),
            "prediction.min_training_rows",
        ),
        test_size=float(prediction.get("test_size", 0.2)),
        random_state=int(prediction.get("random_state", 42)),
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


def ensure_prediction_table(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                horizon_steps INTEGER NOT NULL,
                current_price INTEGER NOT NULL,
                up_probability REAL NOT NULL,
                down_probability REAL NOT NULL,
                expected_direction TEXT NOT NULL,
                model_version TEXT NOT NULL,
                feature_snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_symbol_generated_at
            ON trend_predictions(symbol, generated_at)
            """
        )


def load_price_data(db_path: Path) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT symbol, collected_at, current_price, volume
            FROM price_snapshots
            ORDER BY symbol, collected_at
            """,
            conn,
        )


def load_sentiment_data(db_path: Path) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT symbol, collected_at, sentiment_score
            FROM naver_finance_news
            WHERE sentiment_score IS NOT NULL
            ORDER BY symbol, collected_at
            """,
            conn,
        )


def add_price_features(price_df: pd.DataFrame) -> pd.DataFrame:
    df = price_df.copy()
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    df["current_price"] = pd.to_numeric(df["current_price"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.sort_values(["symbol", "collected_at"])

    grouped = df.groupby("symbol", group_keys=False)
    df["return_1"] = grouped["current_price"].pct_change(1)
    df["return_3"] = grouped["current_price"].pct_change(3)
    df["return_5"] = grouped["current_price"].pct_change(5)
    df["volume_change_1"] = grouped["volume"].pct_change(1)
    df["ma_3"] = grouped["current_price"].rolling(3).mean().reset_index(level=0, drop=True)
    df["ma_5"] = grouped["current_price"].rolling(5).mean().reset_index(level=0, drop=True)
    df["price_vs_ma_3"] = (df["current_price"] / df["ma_3"]) - 1.0
    df["price_vs_ma_5"] = (df["current_price"] / df["ma_5"]) - 1.0
    return df


def add_sentiment_features(price_df: pd.DataFrame, sentiment_df: pd.DataFrame) -> pd.DataFrame:
    df = price_df.copy()
    df["sentiment_mean_6h"] = 0.0
    df["sentiment_count_6h"] = 0.0

    if sentiment_df.empty:
        return df

    sentiment = sentiment_df.copy()
    sentiment["collected_at"] = pd.to_datetime(sentiment["collected_at"], utc=True)
    sentiment["sentiment_score"] = pd.to_numeric(sentiment["sentiment_score"], errors="coerce")

    for symbol, indexes in df.groupby("symbol").groups.items():
        symbol_sentiment = sentiment[sentiment["symbol"] == symbol]
        if symbol_sentiment.empty:
            continue

        for index in indexes:
            timestamp = df.at[index, "collected_at"]
            window_start = timestamp - pd.Timedelta(hours=6)
            window = symbol_sentiment[
                (symbol_sentiment["collected_at"] <= timestamp)
                & (symbol_sentiment["collected_at"] >= window_start)
            ]
            if window.empty:
                continue
            df.at[index, "sentiment_mean_6h"] = float(window["sentiment_score"].mean())
            df.at[index, "sentiment_count_6h"] = float(window["sentiment_score"].count())

    return df


def build_training_frame(config: PredictionConfig) -> pd.DataFrame:
    price_df = load_price_data(config.db_path)
    sentiment_df = load_sentiment_data(config.db_path)
    if price_df.empty:
        return pd.DataFrame()

    df = add_price_features(price_df)
    df = add_sentiment_features(df, sentiment_df)
    grouped = df.groupby("symbol", group_keys=False)
    df["future_price"] = grouped["current_price"].shift(-config.horizon_steps)
    df["target_up"] = (df["future_price"] > df["current_price"]).astype(int)
    df = df.dropna(subset=["future_price"])
    return df


def train_model(config: PredictionConfig) -> dict[str, Any]:
    frame = build_training_frame(config)
    if len(frame) < config.min_training_rows:
        return {
            "trained": False,
            "reason": f"not enough rows: {len(frame)} < {config.min_training_rows}",
            "rows": int(len(frame)),
        }

    if frame["target_up"].nunique() < 2:
        return {
            "trained": False,
            "reason": "target has only one class",
            "rows": int(len(frame)),
        }

    split_index = max(1, int(len(frame) * (1.0 - config.test_size)))
    train_df = frame.iloc[:split_index]
    test_df = frame.iloc[split_index:]
    if test_df.empty:
        test_df = train_df

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                HistGradientBoostingClassifier(
                    max_iter=150,
                    learning_rate=0.05,
                    max_leaf_nodes=15,
                    random_state=config.random_state,
                ),
            ),
        ]
    )
    model.fit(train_df[FEATURE_COLUMNS], train_df["target_up"])

    probabilities = model.predict_proba(test_df[FEATURE_COLUMNS])[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    metrics = {
        "accuracy": float(accuracy_score(test_df["target_up"], predictions)),
        "roc_auc": None,
    }
    if test_df["target_up"].nunique() == 2:
        metrics["roc_auc"] = float(roc_auc_score(test_df["target_up"], probabilities))

    version = datetime.now(timezone.utc).strftime("predictor_%Y%m%dT%H%M%SZ")
    artifact = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "model_version": version,
        "horizon_steps": config.horizon_steps,
    }

    config.model_path.parent.mkdir(parents=True, exist_ok=True)
    config.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, config.model_path)

    metadata = {
        "model_version": version,
        "trained_at": utc_now_iso(),
        "model_type": "HistGradientBoostingClassifier",
        "rows": int(len(frame)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "horizon_steps": config.horizon_steps,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
    }
    config.metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"trained": True, **metadata}


def load_model_artifact(model_path: Path) -> dict[str, Any]:
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    artifact = joblib.load(model_path)
    if not isinstance(artifact, dict) or "model" not in artifact:
        raise ValueError(f"Invalid model artifact: {model_path}")
    return artifact


def latest_feature_rows(config: PredictionConfig) -> pd.DataFrame:
    price_df = load_price_data(config.db_path)
    sentiment_df = load_sentiment_data(config.db_path)
    if price_df.empty:
        return pd.DataFrame()
    df = add_price_features(price_df)
    df = add_sentiment_features(df, sentiment_df)
    return df.sort_values("collected_at").groupby("symbol", as_index=False).tail(1)


def save_predictions(config: PredictionConfig, predictions: list[dict[str, Any]]) -> None:
    ensure_prediction_table(config.db_path)
    with sqlite3.connect(config.db_path) as conn:
        for item in predictions:
            conn.execute(
                """
                INSERT INTO trend_predictions (
                    symbol,
                    generated_at,
                    horizon_steps,
                    current_price,
                    up_probability,
                    down_probability,
                    expected_direction,
                    model_version,
                    feature_snapshot
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["symbol"],
                    item["generated_at"],
                    item["horizon_steps"],
                    item["current_price"],
                    item["up_probability"],
                    item["down_probability"],
                    item["expected_direction"],
                    item["model_version"],
                    json.dumps(item["feature_snapshot"], ensure_ascii=False),
                ),
            )


def predict_latest(config: PredictionConfig) -> list[dict[str, Any]]:
    artifact = load_model_artifact(config.model_path)
    model = artifact["model"]
    feature_columns = artifact.get("feature_columns", FEATURE_COLUMNS)
    model_version = str(artifact.get("model_version", "unknown"))
    horizon_steps = int(artifact.get("horizon_steps", config.horizon_steps))

    latest_rows = latest_feature_rows(config)
    if latest_rows.empty:
        return []

    probabilities = model.predict_proba(latest_rows[feature_columns])[:, 1]
    generated_at = utc_now_iso()
    predictions: list[dict[str, Any]] = []
    for row, up_probability in zip(latest_rows.to_dict("records"), probabilities):
        up = float(up_probability)
        down = float(1.0 - up)
        predictions.append(
            {
                "symbol": row["symbol"],
                "generated_at": generated_at,
                "horizon_steps": horizon_steps,
                "current_price": int(row["current_price"]),
                "up_probability": up,
                "down_probability": down,
                "expected_direction": "UP" if up >= 0.5 else "DOWN",
                "model_version": model_version,
                "feature_snapshot": {
                    name: None if pd.isna(row.get(name)) else float(row.get(name))
                    for name in feature_columns
                },
            }
        )

    save_predictions(config, predictions)
    return predictions


def run_scheduler(config: PredictionConfig) -> None:
    logging.info("trend predictor started db=%s model=%s", config.db_path, config.model_path)
    while True:
        started_at = time.monotonic()
        result = train_model(config)
        logging.info("training_result=%s", result)
        if result.get("trained"):
            predictions = predict_latest(config)
            logging.info("predictions_saved=%s", len(predictions))
        elapsed = time.monotonic() - started_at
        time.sleep(max(1.0, config.retrain_interval_seconds - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 3 trend prediction trainer for Omniscient AI Quant System"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--predict", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    setup_logging(config.log_path)
    ensure_prediction_table(config.db_path)

    if args.daemon:
        run_scheduler(config)
        return

    if args.train:
        print(json.dumps(train_model(config), ensure_ascii=False, indent=2))
        return

    if args.predict:
        print(json.dumps(predict_latest(config), ensure_ascii=False, indent=2))
        return

    print(json.dumps(train_model(config), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
