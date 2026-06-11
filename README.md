# Omniscient AI Quant System

Local-first AI quant dashboard project for Korean equities.

## Current Status

Phase 1 is in progress and currently provides a production-oriented Naver Finance collector:

- Multiple KRX stock price and volume collection
- KOSPI/KOSDAQ index collection
- Naver Finance news collection
- KOSPI/KOSDAQ stock universe refresh
- Historical daily OHLCV backfill for all active symbols
- SQLite persistence
- Config-driven scheduler
- Retry and rotating file logs
- Prepared news columns for Phase 2 sentiment analysis

## Phase 1 Quick Start

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run one collection cycle:

```powershell
python phase1_collector.py --once --config config.yaml
```

Run as a scheduler:

```powershell
python phase1_collector.py --config config.yaml
```

The default config collects stock prices every 60 seconds and news every 600 seconds.

## Configuration

Edit `config.yaml` to change:

- SQLite DB path
- log path
- stock symbols
- market indices
- price/news intervals
- request retry settings

## API Keys

No API key is required for the current Naver Finance based Phase 1 collector.

Korea Investment & Securities Open API integration will need credentials later:

- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- account/product settings depending on the selected endpoint

## Phase 2 Gemma Sentiment Analysis

Recommended local setup for RTX 3070 8GB:

```powershell
ollama pull gemma4:e2b
ollama run gemma4:e2b
```

Run one sentiment analysis cycle after Phase 1 has collected news:

```powershell
python sentiment_analyzer.py --once --config config.yaml
```

Run as a scheduler:

```powershell
python sentiment_analyzer.py --config config.yaml
```

The analyzer reads pending rows from `naver_finance_news`, calls the configured local LLM, and updates:

- `sentiment_score`
- `ai_summary`
- `event_tags`
- `analyzed_at`
- `llm_model`

## Phase 3 Trend Prediction

The first prediction engine is a lightweight CPU-friendly scikit-learn model. It trains on collected price snapshots and Gemma sentiment scores, then writes prediction rows to SQLite.

Backfill historical daily OHLCV before training the release model:

```powershell
python historical_backfill.py --config config.yaml
```

For a release-grade base model, refresh the full KOSPI/KOSDAQ universe and backfill all active symbols:

```powershell
python stock_universe.py --config config.yaml
python historical_backfill.py --all-symbols --config config.yaml
```

For long-running backfills, use a runtime limit and rerun the same command. Completed symbols are tracked in SQLite and skipped automatically:

```powershell
python historical_backfill.py --all-symbols --config config.yaml --max-runtime-seconds 28800
```

Train once:

```powershell
python trend_predictor.py --train --config config.yaml
```

Predict with the latest saved model:

```powershell
python trend_predictor.py --predict --config config.yaml
```

Run as a background trainer:

```powershell
python trend_predictor.py --daemon --config config.yaml
```

Create a distributable model package for GitHub Releases:

```powershell
python model_release.py --config config.yaml
```

The release package is written under `models/releases/` and contains:

- `predictor_latest.joblib`
- `metadata.json`
- `manifest.json` with artifact hashes and feature schema version

In the final packaged app, these commands will be started internally by the EXE. End users should only open the app normally.
