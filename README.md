# Omniscient AI Quant System

Local-first AI quant dashboard project for Korean equities.

## Current Status

Phase 1 is in progress and currently provides a production-oriented Naver Finance collector:

- Multiple KRX stock price and volume collection
- KOSPI/KOSDAQ index collection
- Naver Finance news collection
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
