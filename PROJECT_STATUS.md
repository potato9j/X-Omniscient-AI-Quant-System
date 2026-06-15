# Project Status

Last updated: 2026-06-15 KST

This is a short status snapshot. For operational continuation, read
[`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md). For detailed development history,
read [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md).

## Current Direction

The project is a local-first AI quant dashboard for Korean equities.

Core strategy:

- Use local SQLite for collected market/news data.
- Use Gemma through Ollama or LM Studio for zero-shot news sentiment analysis.
- Use lightweight machine learning for price direction prediction.
- Do not fine-tune Gemma.
- Train the base model with a representative 300-symbol sample.
- Backfill searched symbols on demand inside the final app.
- Release trained model packages through GitHub Releases, not normal commits.

## Current Local Snapshot

```text
Universe:           3,948 active KOSPI/KOSDAQ symbols
Daily OHLCV:        360,633 rows across 301 symbols
Prediction rows:    302 rows
Current model:      predictor_20260615T110948Z
Model accuracy:     0.5719516609584273
Model ROC AUC:      0.5514254845336174
Backend:            FastAPI read API implemented
Frontend:           React/Vite dashboard implemented
Packaging:          not implemented yet
```

## Implemented Areas

- Naver Finance price/index/news collection.
- KOSPI/KOSDAQ universe refresh.
- Historical daily OHLCV backfill.
- Local Gemma sentiment analyzer.
- Lightweight prediction model and model ZIP packaging.
- FastAPI backend read API.
- React/Vite dashboard with market landing and stock detail modes.
- Responsive UI pass for desktop, narrow, and portrait viewports.

## Local Artifacts Not Committed

These are intentionally ignored:

```text
data/
logs/
models/
*.sqlite3
frontend/node_modules/
frontend/dist/
```

Move `data/omniscient_quant.sqlite3` separately if another computer needs the
current collected data.

## Current Run Commands

Backend:

```text
run_backend.bat
```

Frontend:

```text
run_frontend.bat
```

Frontend build:

```text
build_frontend.bat
```

System check:

```text
check_system.bat
```

## Next Steps

1. Add real intraday OHLCV collection.
2. Add market-hours-aware refresh logic.
3. Improve prediction validation and calibration.
4. Improve loading and empty UI states.
5. Start EXE packaging architecture with Electron plus a Python backend launcher.
6. Add GitHub Release model updater.
