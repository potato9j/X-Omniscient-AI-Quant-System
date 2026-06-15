# Omniscient AI Quant System - Development Timeline

This document records the detailed development history of the Omniscient AI Quant System. It is intentionally more granular than `PROJECT_HANDOFF.md` so future reviewers can understand how the project evolved, what failed, and why design or engineering decisions were made.

Last updated: 2026-06-16 00:56 KST

## Reading Guide

- `PROJECT_HANDOFF.md` is the short operational handoff.
- `PROJECT_TIMELINE.md` is the detailed engineering history.
- Local-only artifacts such as `data/`, `logs/`, `.deps/`, `frontend/node_modules/`, `frontend/dist/`, and `models/` are intentionally not committed.
- The current local database is `data/omniscient_quant.sqlite3`.

## Current Snapshot

| Area | Current State |
| --- | --- |
| Data universe | 3,948 active KOSPI/KOSDAQ symbols |
| Historical OHLCV | 360,633 daily rows across 301 symbols |
| Training sample | 300-symbol representative sample, effectively complete at 99.33% |
| News rows | 40 Naver Finance news rows |
| Sentiment rows | 2 rows analyzed by Gemma |
| Prediction rows | 302 latest prediction rows |
| Current model | `predictor_20260615T110948Z` |
| Model rows | 359,130 feature rows |
| Model metrics | Accuracy 0.5719516609584273, ROC AUC 0.5514254845336174 |
| Backend | FastAPI read API implemented |
| Frontend | React/Vite dashboard implemented and under active UI/UX iteration |
| Packaging | Not implemented yet |

## Version Log

### v0.1.0 - Phase 1 Collector Bootstrap

| Field | Details |
| --- | --- |
| Date | 2026-06-11 |
| Goal | Build the first local data collection pipeline for Korean equities. |
| Work | Implemented Naver Finance current price, volume, index, and news collection. Added SQLite persistence. |
| Files | `phase1_collector.py`, `config.yaml`, `requirements.txt` |
| Execution result | Collector code could store selected stock prices, KOSPI/KOSDAQ index snapshots, and Naver Finance news rows. |
| Errors | Initial dependency issues around HTML parsing dependencies were expected; `beautifulsoup4` and `requests` were added. |
| Improvement | Established the first data schema: `price_snapshots`, `market_index_snapshots`, `naver_finance_news`. |
| Notes | This phase used Naver Finance because no paid/official market API key was required yet. |

### v0.2.0 - Stock Universe And Historical Backfill

| Field | Details |
| --- | --- |
| Date | 2026-06-11 to 2026-06-12 |
| Goal | Move from a few watched symbols to a broad KOSPI/KOSDAQ universe and historical daily OHLCV. |
| Work | Implemented universe refresh and historical daily backfill. Added representative training sample mode and searched-symbol on-demand mode. |
| Files | `stock_universe.py`, `historical_backfill.py`, `backfill_status.py` |
| Execution result | `stock_universe` reached 3,948 active symbols. Historical sample reached 360,633 OHLCV rows. |
| Errors | Full deep crawling for every stock was too slow and carried Naver blocking risk. |
| Improvement | Strategy changed to a 300-symbol representative base sample plus on-demand backfill for searched symbols. |
| Notes | This decision reduced runtime and made the final app more practical. |

### v0.2.1 - Backfill Progress Completion

| Field | Details |
| --- | --- |
| Date | 2026-06-12 |
| Goal | Complete the training sample enough for baseline model training. |
| Work | Continued/resumed the sample backfill until only short-history symbols remained partial. |
| Execution result | Backfill status: 298 completed, 2 partial, 99.33% progress, 0 failed statuses. |
| Errors | Two symbols had shorter available histories rather than crawler failures. |
| Improvement | Treated the sample as effectively complete rather than forcing impossible 1,000-row histories. |
| Known short-history symbols | `012210` with 747 rows, `014950` with 153 rows. |

### v0.3.0 - Local Gemma Sentiment Engine

| Field | Details |
| --- | --- |
| Date | 2026-06-11 |
| Goal | Add local LLM sentiment scoring for news. |
| Work | Implemented Ollama/LM Studio-compatible sentiment analyzer. |
| Files | `sentiment_analyzer.py`, `config.yaml` |
| Execution result | One real news sentiment row was analyzed and stored. |
| Errors | `gemma4:e4b` failed on RTX 3070 8GB due VRAM/CUDA pressure. Gemma 4 initially returned empty output unless `think: false` was sent. |
| Improvement | Standardized on `gemma4:e2b` for the current local setup and added `think: false` behavior. |
| Decision | Gemma is not fine-tuned. It is used only for zero-shot news analysis. |

### v0.4.0 - Lightweight Trend Prediction

| Field | Details |
| --- | --- |
| Date | 2026-06-11 |
| Goal | Build a low-VRAM prediction model separate from Gemma. |
| Work | Implemented feature engineering and scikit-learn model training. |
| Files | `trend_predictor.py` |
| Model | `HistGradientBoostingClassifier` |
| Features | Returns, volume changes, moving average deviation, intraday return, high-low range, volatility, sentiment mean/count, market code. |
| Execution result | The first proof model trained successfully. |
| Errors | Early proof model was trained before full sample completion, so it was not final. |
| Improvement | Established model metadata and feature schema. |

### v0.4.1 - Model Release Packaging

| Field | Details |
| --- | --- |
| Date | 2026-06-11 |
| Goal | Package model artifacts for later GitHub Release distribution. |
| Work | Added ZIP packaging for model, metadata, and manifest. |
| Files | `model_release.py` |
| Execution result | Created proof package `predictor_20260611T093144Z.zip`. |
| Metrics | Accuracy 0.5226299694189602, ROC AUC 0.5158903371880934. |
| Improvement | Created a repeatable local model release artifact format. |
| Note | Proof package was not final. |

### v0.4.2 - First Real Baseline Model Candidate

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Train on the completed representative sample instead of the earlier partial sample. |
| Work | Ran `model_release.py` against the current SQLite database. |
| Execution result | Created `predictor_20260615T110948Z.zip`. |
| Metrics | Accuracy 0.5719516609584273, ROC AUC 0.5514254845336174. |
| Rows | 359,130 feature rows, 287,304 train rows, 71,826 test rows. |
| Errors | First run failed with `PermissionError: [WinError 5]` inside scikit-learn/joblib thread pool creation. |
| Improvement | Re-ran training with single-thread environment variables: `LOKY_MAX_CPU_COUNT=1`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`. |
| Follow-up | Saved 302 latest predictions into `trend_predictions`. |

### v0.5.0 - FastAPI Backend

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Add a local API layer for the future dashboard. |
| Work | Implemented FastAPI app, SQLite helpers, and response schemas. |
| Files | `backend/__init__.py`, `backend/db.py`, `backend/schemas.py`, `backend/app.py` |
| Endpoints | `/health`, `/stocks/search`, `/stocks/{symbol}`, `/stocks/{symbol}/candles`, `/stocks/{symbol}/news`, `/stocks/{symbol}/prediction`, `/models/status` |
| Execution result | FastAPI `TestClient` verified read endpoints. Real HTTP `/health` also worked. |
| Errors | `fastapi` was missing from `.deps`; installing without network permission failed. |
| Improvement | Installed `fastapi`, `uvicorn[standard]`, and `httpx2`. Added them to `requirements.txt`. |
| Runtime issue | Codex shell can appear stuck when launching long-running `uvicorn` servers. |
| Improvement | Added `run_backend.bat` and later enabled Uvicorn `--reload`. |

### v0.5.1 - Market Screen Backend Endpoints

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Support a real market landing screen instead of opening directly to Samsung Electronics. |
| Work | Added market summary, synthetic index series, rankings, signals, market news, and prediction explanation endpoints. |
| Files | `backend/app.py`, `backend/schemas.py` |
| Endpoints | `/markets/summary`, `/markets/index-series`, `/markets/leaders`, `/markets/signals`, `/markets/news`, `/stocks/{symbol}/explanation` |
| Execution result | New endpoints passed FastAPI `TestClient` checks. |
| Errors | The user saw `API error 404` because an old backend process was still running and did not include the new `/markets/*` routes. |
| Improvement | Stopped the stale Python process and updated `run_backend.bat` to use reload mode. |

### v0.6.0 - First React/Vite Dashboard

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Move from static HTML to a real frontend app. |
| Work | Installed Node.js and created a React/Vite dashboard with `lightweight-charts` and `lucide-react`. |
| Files | `frontend/package.json`, `frontend/vite.config.js`, `frontend/src/api.js`, `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/src/styles.css` |
| Execution result | `npm install` completed and `npm run build` passed. |
| Errors | `node`, `npm`, and `npx` were installed but not visible to the existing Codex PowerShell PATH. |
| Improvement | Used direct paths: `C:\Program Files\nodejs\node.exe` and `C:\Program Files\nodejs\npm.cmd`. |
| Additional error | First normal Vite build failed with `spawn EPERM` because esbuild process spawning was blocked in the sandbox. |
| Improvement | Re-ran the build with approved permissions; build succeeded. |
| Audit | `npm audit --json` reported 0 vulnerabilities after install. |

### v0.6.1 - Market Landing Screen And Stock Detail Mode

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Make the first screen a basic market dashboard rather than a fixed Samsung Electronics detail page. |
| Work | Added market view and stock detail view. Search switches the UI into detail mode. |
| Result | First launch now shows market ranking, KOSPI/KOSDAQ chart, bullish/bearish signal lists, and market news. |
| Stock detail behavior | Left panel becomes stock summary instead of search results. Detailed prediction explanation appears below the main panels. |
| Errors | User reported the layout still did not resize fluidly and the wording felt low-end. |
| Improvement | Began redesigning responsive grid and product language. |

### v0.6.2 - Responsive UX And Product Tone Pass

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Improve resizing behavior, portrait behavior, and perceived product quality. |
| Work | Replaced loose grid sizing with explicit grid areas. Reworked responsive breakpoints. Replaced low-quality text labels. |
| Files | `frontend/src/App.jsx`, `frontend/src/styles.css` |
| UI language changes | `시장 기본 화면` became `시장 인사이트`. Main market title became `국내 증시 인사이트`. `실시간 랭킹` became `마켓 랭킹` because the data is still daily-based. |
| Layout changes | Added named grid areas: left, center, right. Prevented panel overlap. Reworked topbar, main grid, chart height, news panel, ranking panel, and single-column behavior. |
| Responsive behavior | Added desktop, medium desktop, portrait, narrow, and short-height layouts. Sticky side panels are disabled where they hurt usability. |
| Execution result | `npm run build` passed after the redesign. |
| Remaining issue | True 10-minute zoom cannot be implemented until an intraday 10-minute OHLCV table and collector exist. |

### v0.6.3 - Browser Geometry Verification And Documentation Split

| Field | Details |
| --- | --- |
| Date | 2026-06-15 |
| Goal | Verify that the revised dashboard no longer overlaps at common screen sizes and split operational handoff from detailed learning history. |
| Work | Ran browser-based layout checks against the live Vite app at desktop, narrow desktop, and portrait dimensions. Rewrote `PROJECT_HANDOFF.md` into a short operational handoff and kept detailed chronology in this file. |
| Files | `PROJECT_HANDOFF.md`, `PROJECT_TIMELINE.md` |
| Viewports tested | 1536x900 wide desktop, 1024x768 narrow desktop, 430x900 portrait. |
| Execution result | All tested viewports reported `bodyOverflowX: 0` and no bounding-box overlap between left, center, right, chart, toolbar, signal, and news regions. |
| Console result | Browser console error/warning log returned empty during verification. |
| Build result | The preceding Vite production build passed successfully. |
| Error observed | Raw PowerShell `Get-Content` displayed some Korean JSX strings as mojibake because the source is UTF-8 and the console path was not decoding it correctly. `rg` and Vite build confirmed the source itself was valid. |
| Improvement | `PROJECT_HANDOFF.md` now stays focused on mission, current state, run commands, API surface, limitations, and next work. This file remains the detailed engineering timeline. |

### v0.6.4 - Gemma Sentiment Trigger Integration

| Field | Details |
| --- | --- |
| Date | 2026-06-16 |
| Goal | Make the dashboard visibly reflect Gemma news sentiment analysis instead of only showing stored scores when they already exist. |
| Problem | The frontend read `sentiment_score` from `naver_finance_news`, but the app did not start the analyzer or expose sentiment progress. The local DB had 40 news rows but only 1 analyzed row, so most cards showed `미분석`. |
| Work | Added sentiment status and trigger APIs. Added a frontend `감성 분석` button, analyzed/total counter, background polling, and automatic news refresh after analysis finishes. |
| Files | `backend/app.py`, `backend/schemas.py`, `frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/styles.css`, `run_backend.bat` |
| Backend endpoints | `GET /sentiment/status`, `POST /sentiment/analyze?limit=...` |
| Runtime behavior | `POST /sentiment/analyze` starts a background job that calls the existing Gemma/Ollama analyzer for pending news rows. The default UI trigger analyzes up to 5 pending rows per click. |
| Verification | Ollama was running with `gemma4:e2b`. A 1-row analysis test completed successfully, increasing analyzed news from 1/40 to 2/40. The newly analyzed row received score `0.7` and a Korean summary. |
| Frontend verification | Browser reload showed the right news panel with `감성 분석`, `2/40`, `0.70`, `-0.30`, and remaining `미분석` cards. |
| Build result | `npm run build` passed after the frontend changes. Backend `py_compile` passed. |
| Error observed | Backend was initially checked on temporary port 8001 after an interrupted long-running `uvicorn` command; the frontend expects port 8000. |
| Improvement | `run_backend.bat` was changed to use `PYTHONPATH=.;.deps` and no `--reload`, making double-click backend startup more stable on port 8000. |

### v0.6.5 - Startup Loading And API Retry Fix

| Field | Details |
| --- | --- |
| Date | 2026-06-16 |
| Goal | Stop the dashboard from looking broken when the frontend appears before backend data has finished loading. |
| Problem | The user saw `Failed to fetch`, zero metrics, empty ranking, empty news, and no visible data. The backend later responded normally, but the initial frontend state made the app look nonfunctional. |
| Work | Added frontend boot loading state, initial API retry loop, loading labels for metrics/ranking/news/signals, and safer sentiment counter fallback. |
| Files | `frontend/src/App.jsx` |
| Verification | Browser reload immediately showed `데이터 동기화 중`, `...`, `랭킹 불러오는 중`, `뉴스 불러오는 중`; after about 5 seconds it showed universe `3,948`, OHLCV `360,633`, signals `302`, 30 ranking rows, 12 news cards, and sentiment `2/40`. |
| Build result | `npm run build` passed after the frontend change. |
| Improvement | A slow backend start or first failed API call now causes a controlled loading/retry state instead of a misleading zero-data screen. |

### v0.6.6 - Local Dev CORS Port Fix

| Field | Details |
| --- | --- |
| Date | 2026-06-16 |
| Goal | Fix browser-side API blocking when Vite runs on a port other than 5173. |
| Problem | The user still saw `Failed to fetch`, and Chrome DevTools showed CORS errors from origin `http://127.0.0.1:5179` to backend `http://127.0.0.1:8000`. The backend only allowed `5173`, while Vite moved to `5179` because another dev server was already using `5173`. |
| Work | Added FastAPI CORS `allow_origin_regex` for local `127.0.0.1` and `localhost` ports. Restarted the backend so the new CORS middleware config applied. |
| Files | `backend/app.py` |
| Verification | `curl -i -H "Origin: http://127.0.0.1:5179" http://127.0.0.1:8000/health` returned `access-control-allow-origin: http://127.0.0.1:5179`. Browser verification on `http://127.0.0.1:5179/` showed universe `3,948`, OHLCV `360,633`, signals `302`, 30 ranking rows, 12 news cards, sentiment `2/40`, and no browser error logs. |
| Improvement | The dashboard now works even if Vite chooses 5174, 5179, or another local dev port. |

### v0.6.7 - Read-Only Market Data API Scope Decision

| Field | Details |
| --- | --- |
| Date | 2026-06-16 |
| Goal | Fix the product boundary before adding external securities APIs. |
| Decision | Korea Investment & Securities Open API, or any other securities API, will be used only for read-only market data: quotes, indices, daily candles, intraday candles, volume, turnover, and other non-order market data. |
| Explicit exclusion | The product will not include buy orders, sell orders, order modification, order cancellation, automated trading, account-balance-based order recommendation, or automatic portfolio rebalancing execution. |
| Reason | The user wants a released app that provides market data, sentiment analysis, direction prediction, expected return, and target-price estimation without legal or product risk from trade execution features. |
| Implementation impact | Future API work should start with read-only quote/index/intraday endpoints, local token handling, `.env`-style secrets, and `ohlcv_intraday` storage. Do not design order tables, order APIs, account-balance workflows, or trading UI. |
| Prediction impact | Intraday API data is needed to improve short-horizon movement analysis and to support expected-return/target-price regression instead of drawing a hardcoded forecast line. |

## Error Log

| Date | Error | Cause | Resolution |
| --- | --- | --- | --- |
| 2026-06-11 | Larger Gemma model failed on RTX 3070 8GB | VRAM pressure | Use `gemma4:e2b` for local sentiment inference |
| 2026-06-11 | Gemma returned empty content | Model/runtime behavior with thinking output | Send `think: false` |
| 2026-06-15 | `PermissionError: [WinError 5]` during model training | scikit-learn/joblib thread pool creation in Windows sandbox | Limit thread counts to 1 |
| 2026-06-15 | `ModuleNotFoundError: fastapi` | Backend dependency missing from `.deps` | Install FastAPI and add to `requirements.txt` |
| 2026-06-15 | `pip install` could not reach package index | Network restricted by sandbox | Re-run with approved network permission |
| 2026-06-15 | Starlette `TestClient` required `httpx2` | Newer Starlette dependency requirement | Add and install `httpx2` |
| 2026-06-15 | PowerShell `Start-Process` failed with `Path/PATH` duplicate | Environment variable casing conflict | Avoid keeping long-running servers attached to Codex; use batch files |
| 2026-06-15 | Vite build failed with `spawn EPERM` | esbuild worker process blocked by sandbox | Re-run build with approved permissions |
| 2026-06-15 | Frontend showed `API error 404` | Stale backend process did not include new `/markets/*` endpoints | Stop old backend process and restart `run_backend.bat` |
| 2026-06-15 | UI panels overlapped and resized poorly | Flexible grid without explicit layout areas and sticky panels in constrained widths | Reworked CSS with named grid areas and responsive breakpoints |
| 2026-06-15 | PowerShell displayed Korean JSX text as mojibake | UTF-8 source was read through a non-UTF-8 console path | Treat `rg`, browser output, and Vite build as authoritative unless the browser also shows broken text |
| 2026-06-16 | Dashboard did not visibly apply news sentiment | Analyzer existed as a separate script but was not connected to the API/frontend workflow | Added sentiment status/trigger APIs and a frontend analysis action |
| 2026-06-16 | Backend verification appeared stuck on `uvicorn` | Direct server command is long-running by design and was started on temporary port 8001 | Switched runtime verification back to `run_backend.bat` on port 8000 |
| 2026-06-16 | Dashboard appeared as zero-data / `Failed to fetch` | Frontend loaded before API data was ready and had no boot retry/loading state | Added initial API retry and explicit loading labels |
| 2026-06-16 | CORS blocked API despite backend returning 200 | Vite was running on `127.0.0.1:5179`, but backend CORS only allowed `5173` | Added local dev port CORS regex and restarted backend |

## Design Decision Log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-06-11 | Do not fine-tune Gemma | Fine-tuning is heavy, VRAM-sensitive, and unnecessary for news sentiment scoring |
| 2026-06-11 | Use Gemma only for sentiment analysis | Keeps local LLM workload bounded |
| 2026-06-11 | Use lightweight ML for prediction | Better fit for CPU/GPU constraints and frequent retraining |
| 2026-06-11 | Use representative sample plus on-demand backfill | Avoids long full-market crawling and reduces blocking risk |
| 2026-06-15 | Use GitHub Releases for model packages | Keeps large binary model artifacts out of normal commits |
| 2026-06-15 | Use FastAPI as local backend | Simple local API for React/Electron |
| 2026-06-15 | Use React/Vite and Lightweight Charts | Practical frontend stack for financial dashboard UI |
| 2026-06-15 | Separate market landing screen from stock detail screen | First launch should help users orient to the market, not force a single stock |
| 2026-06-15 | Disable 10-minute chart control for now | Current DB has daily OHLCV, not true 10-minute candles |
| 2026-06-15 | Keep `PROJECT_HANDOFF.md` short and move detailed history to `PROJECT_TIMELINE.md` | New AI agents need a fast operational entry point, while the user wants a complete learning record |
| 2026-06-16 | Use a manual sentiment trigger before full automation | It gives immediate user-visible control without running Gemma continuously in the first dashboard version |
| 2026-06-16 | Keep the product read-only with no real-trading features | Reduces legal/product risk and keeps the app focused on analysis, prediction, and reporting |
| 2026-06-16 | Use securities API only for market data | Intraday quotes/candles improve prediction quality without requiring account/order workflows |

## Next Engineering Targets

1. Add read-only Korea Investment & Securities API integration:
   - app key/app secret loading from local-only config.
   - token caching.
   - current quote lookup.
   - KOSPI/KOSDAQ index lookup.
   - intraday candle lookup when supported.
   - no order, cancel, modify, balance, or account trading endpoints.
2. Add real intraday collection:
   - 1-minute or 10-minute OHLCV table.
   - Market-hours-aware scheduler.
   - API endpoint for intraday candles.
3. Add expected-return and target-price prediction:
   - future return labels.
   - target price.
   - lower/upper prediction range.
   - chart forecast line based on model output, not a hardcoded percentage.
4. Improve market screen:
   - True sector/industry grouping.
   - Macro indicators.
   - Real market-wide economic news feeds.
5. Improve model validation:
   - Walk-forward validation.
   - Calibration checks.
   - Separate daily/intraday model horizons.
6. Improve packaging:
   - Electron shell.
   - Python backend launcher.
   - GitHub Release model updater.
7. Improve UI quality:
   - Browser screenshot verification at desktop, tablet/portrait, and narrow widths.
   - Better empty/loading states.
   - Reduce any remaining text overflow.
