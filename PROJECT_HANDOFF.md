# Omniscient AI Quant System - AI Agent Handoff

Last updated: 2026-06-16 00:56 KST

This is the short operational handoff for continuing the project from any Codex
session, USB drive, laptop, or desktop. It should stay concise. For detailed
development history, errors, results, and design decisions, read
[`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md).

## 1. Mission

Build a local-first Windows quant application for Korean equities.

The finished app should:

1. collect Korean market and stock data continuously;
2. collect related market and stock news;
3. analyze news sentiment with a local Gemma model through Ollama or LM Studio;
4. predict stock direction with a lightweight ML model;
5. show the result in a polished dashboard;
6. package the system into a user-friendly EXE;
7. distribute trained model updates through GitHub Releases.

Final users should not type terminal commands. The app must start required local
services, check local data/model state, and degrade gracefully if Ollama or Gemma
is unavailable.

## 2. Fixed Direction

- Do not fine-tune Gemma.
- Use Gemma only for zero-shot news sentiment analysis.
- Use a lightweight ML model for price prediction.
- Current predictor family: scikit-learn `HistGradientBoostingClassifier`.
- Use a representative 300-symbol training sample as the first baseline.
- Use on-demand backfill when a searched symbol is not ready.
- Keep local DB, logs, model binaries, and release ZIPs out of Git.
- Publish model ZIPs through GitHub Releases later.
- Follow Korean market colors: red for up/good, blue for down/bad.
- Use external securities APIs only for read-only market data.
- Do not implement buy, sell, cancel, modify, auto-trading, or account-based order execution features.

## 2.1 Product Boundary

This project is a market-data and AI analysis dashboard, not a trading bot.

Allowed:

- quote lookup;
- KOSPI/KOSDAQ index lookup;
- daily and intraday OHLCV collection;
- volume, turnover, order-book-like market data if available as read-only data;
- news collection and Gemma sentiment analysis;
- direction probability prediction;
- expected return, target price, and prediction range estimation;
- explanatory investment-support reports.

Excluded:

- buy orders;
- sell orders;
- order modification or cancellation;
- automated trading;
- order recommendations based on account balance;
- automatic portfolio rebalancing execution.

When integrating Korea Investment & Securities Open API, use only market-data
endpoints. Do not add account balance, order availability, order password, or
trading endpoints.

## 3. Repository

```text
GitHub:  potato9j/X-Omniscient-AI-Quant-System
URL:     https://github.com/potato9j/X-Omniscient-AI-Quant-System
Local:   H:\C1_GitHub Project\26.06.11 Omniscient AI Quant System
DB:      data\omniscient_quant.sqlite3
```

Codex chat history does not automatically follow the USB drive to another
computer. The files move, but the conversation may not. Start new sessions by
reading this file and then `PROJECT_TIMELINE.md`.

## 4. Current Snapshot

```text
Product completion: about 60%
Universe:           3,948 active KOSPI/KOSDAQ symbols
Daily OHLCV:        360,633 rows across 301 symbols
Prediction rows:    302 rows
Current model:      predictor_20260615T110948Z
Model accuracy:     0.5719516609584273
Model ROC AUC:      0.5514254845336174
Backend:            FastAPI read API implemented
Frontend:           React/Vite dashboard implemented and under UI iteration
Packaging:          not implemented yet
```

## 5. Main Files

```text
phase1_collector.py       Naver current price, index, and news collection
stock_universe.py         KOSPI/KOSDAQ universe refresh
historical_backfill.py    daily OHLCV backfill
backfill_status.py        backfill progress/status checks
sentiment_analyzer.py     local Gemma sentiment analysis
trend_predictor.py        lightweight prediction training/inference
model_release.py          model ZIP packaging

backend/app.py            FastAPI routes
backend/db.py             SQLite access helpers
backend/schemas.py        API response schemas

frontend/src/App.jsx      React dashboard
frontend/src/api.js       frontend API client
frontend/src/styles.css   responsive dashboard styling

run_backend.bat           start local backend
run_frontend.bat          start local Vite frontend
build_frontend.bat        build frontend
check_system.bat          quick local system check
PROJECT_TIMELINE.md       detailed development history
```

## 6. How To Run Locally

Backend:

```text
run_backend.bat
```

Frontend:

```text
run_frontend.bat
```

Expected local URLs:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

The current Codex PowerShell session may not see Node through `PATH`. If direct
commands are needed, use:

```text
C:\Program Files\nodejs\node.exe
C:\Program Files\nodejs\npm.cmd
```

## 7. Current Backend API Surface

```text
GET /health
GET /models/status
GET /stocks/search
GET /stocks/{symbol}
GET /stocks/{symbol}/candles
GET /stocks/{symbol}/news
GET /stocks/{symbol}/prediction
GET /stocks/{symbol}/explanation
GET /markets/summary
GET /markets/index-series
GET /markets/leaders
GET /markets/signals
GET /markets/news
GET /sentiment/status
POST /sentiment/analyze
```

## 8. Current Frontend Behavior

The first screen is a market insight dashboard, not a fixed Samsung Electronics
page. It shows:

- market ranking with sortable volume/change controls;
- KOSPI/KOSDAQ market chart;
- bullish and bearish expected stock lists;
- market news banner/cards with links;
- a Gemma sentiment analysis action and analyzed/total news counter;
- top metrics for universe, OHLCV rows, signals, and model version.

After a stock search, the UI switches to stock detail mode:

- the left panel becomes a stock summary;
- the center chart becomes stock candles plus prediction trajectory;
- the right panel becomes stock news and sentiment;
- the detailed explanation appears below the main dashboard.

Recent UI work added explicit responsive grid areas, safer chart sizing, better
portrait/small-screen behavior, more professional product wording, and a manual
Gemma sentiment trigger for pending news rows. The frontend now shows loading
states and retries initial API bootstrapping so a slow backend start does not
look like a broken zero-data screen. Backend CORS allows local `127.0.0.1` and
`localhost` dev ports because Vite may move from 5173 to another available port.

## 9. Verification Commands

Frontend build:

```text
cd frontend
"C:\Program Files\nodejs\npm.cmd" run build
```

Backend syntax check:

```text
python -m py_compile backend\app.py backend\db.py backend\schemas.py
```

System check:

```text
check_system.bat
```

Known issue: Vite/esbuild may fail inside the Codex sandbox with `spawn EPERM`.
If that happens, rerun the same build with approved permissions.

## 10. Known Limitations

- Current OHLCV data is daily, not true 10-minute intraday data.
- Korea Investment & Securities Open API is not integrated yet.
- The 10-minute chart control must remain disabled until intraday collection is implemented.
- Naver crawling can be blocked or break if HTML changes.
- Current model is a baseline, not evidence of profitable trading.
- News sentiment coverage is still very small.
- EXE packaging and automatic model update flow are not implemented.
- Git may not be available in PowerShell `PATH`; use GitHub connector or install/configure Git CLI when needed.

## 11. Do Not Do

- Do not restart full-market crawling unless the user explicitly asks.
- Do not commit `data/`, `logs/`, `models/`, `.deps/`, `.venv/`, `frontend/node_modules/`, or `frontend/dist/`.
- Do not delete local SQLite DB or model artifacts.
- Do not hardcode API keys.
- Do not commit `.env` files, API keys, access tokens, account numbers, or account secrets.
- Do not fine-tune Gemma.
- Do not claim real-time 10-minute behavior until intraday data exists.
- Do not add real-trading order features, even as hidden or experimental code.
- Do not call order, cancel, modify, account balance, or orderable-cash endpoints.

## 12. Next Recommended Work

1. Browser-test the responsive frontend at desktop, narrow desktop, portrait, and mobile widths.
2. Add loading and empty states that look intentional.
3. Add a read-only Korea Investment & Securities market-data API connector.
4. Add `ohlcv_intraday` storage for 1-minute/5-minute/10-minute candles.
5. Add market-hours-aware refresh logic.
6. Add expected-return and target-price prediction outputs.
7. Improve prediction explanation quality and calibration.
8. Start packaging architecture: Electron shell plus PyInstaller backend service.
9. Add GitHub Release model updater.

## 13. Update Rule

After meaningful work:

1. update this file only if the operational state changed;
2. update `PROJECT_TIMELINE.md` for detailed history, errors, results, and improvements;
3. keep this handoff short enough for a new AI agent to read quickly.
