# Omniscient AI Quant System - Cross-Session Handoff

Last updated: 2026-06-15 19:55 KST

This is the primary handoff document for continuing the project from another Codex session, USB drive, laptop, desktop, or GitHub clone. If the original chat history is missing, read this file first.

## 1. Project Objective

Build a local-first Windows desktop quant application for Korean stocks.

The final app should:

- collect Korean stock price, index, volume, and news data,
- store data locally in SQLite,
- analyze news sentiment with local Gemma through Ollama or LM Studio,
- predict near-term price direction with a lightweight ML model,
- show a real-time dashboard,
- package everything as an EXE app,
- distribute trained model updates through GitHub Releases.

Final users should not type terminal commands. The app must start required local services, check DB/model state, run on-demand backfills, and show progress through the UI.

## 2. Core Decisions Already Made

- Gemma is not fine-tuned.
- Gemma is used only for zero-shot news sentiment analysis.
- Price prediction uses a separate lightweight ML model.
- Current prediction model is scikit-learn HistGradientBoostingClassifier.
- Full historical crawling for every KRX stock before release was rejected as too slow and too risky for Naver blocking.
- Base model training uses a representative 300-symbol sample.
- Specific searched symbols are prepared later through on-demand backfill.
- Code is synced to GitHub.
- DB, logs, and model binaries are not committed.
- Final trained model ZIPs should be distributed through GitHub Releases.

## 3. Current Overall Status

Product-level completion is about 40%.

Implemented:

- Phase 1 data collector,
- stock universe refresh,
- historical OHLCV backfill,
- backfill status reporting,
- Gemma sentiment analyzer,
- lightweight trend predictor,
- model ZIP packaging,
- README and status documents.

Not implemented yet:

- FastAPI backend,
- React/Vue dashboard,
- Electron/PyInstaller EXE packaging,
- automatic startup orchestration,
- GitHub Release model update flow,
- app-side model download/update.

## 4. Repository And Workspace

GitHub repository:

```text
potato9j/X-Omniscient-AI-Quant-System
https://github.com/potato9j/X-Omniscient-AI-Quant-System
```

Main local workspace used so far:

```text
H:/C1_GitHub Project/26.06.11 Omniscient AI Quant System
```

Important: Codex chat history does not automatically move with a USB drive. The project files can move, but the old conversation may not appear on another device. This file exists to solve that continuity problem.

## 5. Hardware And Runtime Constraints

Main development PC:

- NVIDIA RTX 3070, 8GB VRAM.
- VRAM overflow prevention is important.
- Ollama is installed and usable.
- Current working local model is gemma4:e2b.

Gemma notes:

- gemma4:e4b was tried and failed on RTX 3070 8GB because of VRAM/CUDA memory pressure.
- gemma4:e2b worked through Ollama.
- sentiment_analyzer.py sends think:false to Ollama because Gemma 4 returned empty content without it during testing.

Lower-spec PC notes:

- RTX 2060/2060 Super can run the final app if the prediction model is already trained and Gemma is optional or smaller.
- RTX 3080 10GB plus RTX 2060 Super 6GB cannot simply behave like one 16GB VRAM GPU.
- Multiple GPUs can run separate workloads, but one model generally must fit on one GPU unless the runtime supports sharding.
- Intel Core Ultra 7 laptop can run dashboard, SQLite queries, small backfills, and CPU scikit-learn work, but local LLM inference will be slower.

## 6. Files And Responsibilities

```text
README.md                  polished project overview
PROJECT_STATUS.md          older short status snapshot
PROJECT_HANDOFF.md         this cross-session handoff file
.gitignore                 ignores local DB/log/model artifacts
requirements.txt           Python dependencies
config.yaml                runtime configuration
phase1_collector.py        current price, market index, and Naver news collector
stock_universe.py          KOSPI/KOSDAQ stock universe refresh
historical_backfill.py     historical OHLCV backfill and on-demand backfill
backfill_status.py         numeric backfill progress report
sentiment_analyzer.py      Gemma sentiment analysis through Ollama/LM Studio
trend_predictor.py         lightweight price-direction predictor
model_release.py           trains/packages model release ZIPs
data/                      local SQLite DB, ignored by Git
logs/                      runtime logs, ignored by Git
models/                    local model artifacts, ignored by Git
.deps/                     local dependency folder, ignored by Git
.venv/                     local venv, ignored by Git
```

## 7. Current Config Snapshot

Important values from config.yaml:

```yaml
database.path: data/omniscient_quant.sqlite3
llm.provider: ollama
llm.base_url: http://localhost:11434
llm.model: gemma4:e2b
prediction.model_path: models/predictor_latest.joblib
prediction.metadata_path: models/metadata.json
prediction.horizon_steps: 5
prediction.min_training_rows: 50
historical.training_max_symbols: 300
historical.training_max_pages_per_symbol: 100
historical.on_demand_max_pages_per_symbol: 100
historical.sleep_min_seconds: 0.8
historical.sleep_max_seconds: 1.6
```

## 8. Current Local DB Status

Measured on 2026-06-15 19:55 KST from data/omniscient_quant.sqlite3.

Backfill status:

```text
active_universe          : 3948
training_target_symbols  : 300
completed_training       : 298
partial_training         : 2
progress_percent         : 99.33%
symbols_with_ohlcv       : 301
ohlcv_rows               : 360633
failed_status            : 0
latest                   : symbol=027580 status=completed page=100 fetched=1000 inserted=1000 updated=2026-06-12T05:13:30
```

The representative 300-symbol sample is effectively complete. The remaining 2 partial symbols appear to have short available Naver history rather than crawler failure.

Known short-history examples:

```text
012210: 747 rows
014950: 153 rows
```

SQLite tables:

```text
market_index_snapshots
naver_finance_news
ohlcv_backfill_status
ohlcv_daily
price_snapshots
sqlite_sequence
stock_universe
trend_predictions
```

Table counts:

```text
stock_universe          : 3948
ohlcv_daily             : 360633
price_snapshots         : 3
market_index_snapshots  : 2
naver_finance_news      : 40
trend_predictions       : 0
ohlcv_backfill_status   : 296
sentiment_done          : 1
ohlcv_date_range        : 2006-02-28 to 2026-06-11
ohlcv_symbols           : 301
```

Important: data/omniscient_quant.sqlite3 is local only and is not committed to GitHub. Copy it separately when moving to another PC.

## 9. Model Artifact Status

Existing local model artifacts:

```text
models/predictor_latest.joblib                                  162972 bytes
models/metadata.json                                               643 bytes
models/releases/predictor_20260611T093144Z_manifest.json          1108 bytes
models/releases/predictor_20260611T093144Z.zip                   72411 bytes
```

These were generated on 2026-06-11 18:31:46 KST.

Important: this was only a functional proof package, not the final model release. It was trained before the larger representative sample completed.

Proof model metadata:

```text
model_version : predictor_20260611T093144Z
model_type    : HistGradientBoostingClassifier
rows          : 32699
train_rows    : 26159
test_rows     : 6540
horizon_steps : 5
accuracy      : 0.5226299694189602
roc_auc       : 0.5158903371880934
```

Next model action: retrain and package a real candidate using the current 360,633-row OHLCV sample.

## 10. Phase Completion

Phase 0 - Repository and docs: 90%

Done:

- workspace initialized,
- GitHub repo connected,
- core Python files created,
- .gitignore configured,
- README polished,
- PROJECT_STATUS.md created,
- PROJECT_HANDOFF.md created.

Remaining:

- local git command is not available in current PowerShell PATH,
- continue using GitHub connector or install/configure Git CLI later.

Phase 1 - 24/7 collection pipeline: 80%

Done:

- phase1_collector.py implemented,
- selected stock price/volume collection,
- KOSPI/KOSDAQ index snapshot collection,
- Naver Finance news collection,
- SQLite persistence,
- repeated scheduler logic.

Remaining:

- add Korea Investment Securities API later,
- improve market-hours logic,
- add app-level service controls,
- add health checks and retry UI.

Phase 1.5 - Universe and historical backfill: 95%

Done:

- KOSPI/KOSDAQ universe refresh,
- 3,948 active symbols loaded,
- training sample backfill mode,
- on-demand backfill mode,
- status tracking,
- random request pacing,
- representative sample effectively complete.

Remaining:

- refresh universe again if market_rank is stale,
- strengthen against Naver HTML changes,
- expose on-demand progress in UI.

Phase 2 - Gemma sentiment engine: 60%

Done:

- sentiment_analyzer.py implemented,
- Ollama/LM Studio API integration,
- gemma4:e2b selected,
- one real sentiment row processed,
- think:false handling added.

Remaining:

- batch analyze collected news,
- add queue/state handling,
- add Ollama missing-model fallback,
- improve prompt and response validation.

Phase 3 - Trend prediction: 65%

Done:

- trend_predictor.py implemented,
- OHLCV, volume, volatility, moving-average, sentiment, and market-code features,
- scikit-learn model training,
- model metadata saving,
- model_release.py packaging.

Remaining:

- retrain on 360,633-row sample,
- add time-series validation,
- add probability calibration checks,
- write predictions into trend_predictions,
- integrate with backend.

Phase 4 - Backend API: 0%

Planned:

- FastAPI backend,
- health endpoint,
- stock search,
- candles,
- news,
- sentiment,
- prediction,
- model status,
- on-demand backfill endpoints.

Phase 5 - Dashboard UI: 0%

Planned:

- React or Vue frontend,
- Korean market color rule: red for rise/good news, blue for fall/bad news,
- left market-leader panel,
- top search/macro panel,
- right news/sentiment panel,
- center candle chart and dotted prediction path,
- bottom AI opinion and expected return panel.

Phase 6 - EXE packaging: 0%

Planned:

- Electron or PyInstaller-based desktop app,
- users launch an EXE only,
- local service startup hidden from user,
- DB/model/Ollama checks,
- degraded mode if Gemma is unavailable.

Phase 7 - Release/update system: 10%

Done:

- local model ZIP packaging exists.

Remaining:

- GitHub Release upload script/workflow,
- model manifest version checks,
- app-side model download/update.

## 11. Timeline

2026-06-11:

- Started from GitHub repo direction.
- Implemented Phase 1 Naver Finance current-price/news collection and SQLite persistence.
- Added KOSPI/KOSDAQ index collection.
- Added config and dependencies.
- Confirmed final app must not require terminal commands from users.
- Decided Gemma should not be fine-tuned.
- Decided Gemma should score news sentiment only.
- Added sentiment_analyzer.py.
- Added trend_predictor.py.
- Added model_release.py.
- Added stock universe collection and historical backfill.
- Changed data strategy from full-market deep crawl to representative sample plus on-demand symbol backfill.
- Started sample backfill.

2026-06-12:

- Backfill progressed overnight.
- Observed approximate milestones: 56.33%, 77%, 80.67%, 91%, 97%, then 99.33%.
- Latest completed symbol recorded around 2026-06-12 05:13 KST.
- Remaining 2 partial symbols identified as short-history cases.
- README was polished.
- PROJECT_STATUS.md was created.

2026-06-15:

- User identified cross-device continuity problem: USB project files move, but Codex chat/session does not reliably move.
- Verified current DB status.
- Created detailed PROJECT_HANDOFF.md.
- Updated local README to point to PROJECT_HANDOFF.md.
- Updated local PROJECT_STATUS.md to point to PROJECT_HANDOFF.md.

## 12. Commands For Future Agents

Run from the project root.

Check backfill status:

```powershell
$env:PYTHONPATH='.deps'
python backfill_status.py --config config.yaml
```

Train and package the next real model candidate:

```powershell
$env:PYTHONPATH='.deps'
$env:PYTHONIOENCODING='utf-8'
$env:LOKY_MAX_CPU_COUNT='8'
python model_release.py --config config.yaml
```

Run on-demand backfill for a searched stock:

```powershell
$env:PYTHONPATH='.deps'
python historical_backfill.py --symbol 005930 --on-demand --config config.yaml
```

Run one sentiment pass:

```powershell
$env:PYTHONPATH='.deps'
python sentiment_analyzer.py --once --config config.yaml
```

Run prediction training directly:

```powershell
$env:PYTHONPATH='.deps'
$env:PYTHONIOENCODING='utf-8'
$env:LOKY_MAX_CPU_COUNT='8'
python trend_predictor.py --train --config config.yaml
```

Do not restart the all-symbol deep backfill unless the user explicitly asks. The current strategy is representative training plus on-demand searched-symbol backfill.

## 13. Immediate Next Work

The next engineering step should be:

1. Treat the representative OHLCV sample as complete.
2. Train and package the first real model release candidate using model_release.py.
3. Inspect models/metadata.json after training.
4. Decide whether baseline metrics are acceptable for the first app integration.
5. Start the FastAPI backend layer.

Recommended next command:

```powershell
$env:PYTHONPATH='.deps'
$env:PYTHONIOENCODING='utf-8'
$env:LOKY_MAX_CPU_COUNT='8'
python model_release.py --config config.yaml
```

## 14. Cross-Device Handoff Rules

When moving to another PC:

1. Clone the GitHub repo or copy the whole USB project folder.
2. If using existing collected data, also copy data/omniscient_quant.sqlite3.
3. If using existing local models, also copy models/.
4. Open the project folder directly in Codex.
5. Read PROJECT_HANDOFF.md first.
6. Run backfill_status.py to verify local DB state.
7. Do not run two devices writing to the same SQLite DB at the same time.

## 15. API Key Status

No API key is required for the current Naver-based prototype.

Possible future keys for a production-grade source:

```text
KIS_APP_KEY
KIS_APP_SECRET
KIS_ACCOUNT_NO
```

Do not hardcode API keys. Use .env or OS environment variables.

## 16. Known Risks

Naver crawling risk:

- Naver can block requests or change HTML selectors.
- Current sample/on-demand strategy reduces risk but is not equivalent to an official API.

Data quality risk:

- The representative sample is suitable for a baseline, not a final trading-grade system.

Model risk:

- The proof model showed weak metrics, around 52.26% accuracy and 51.59% ROC AUC.
- This is a baseline, not evidence of profitable prediction.

LLM availability risk:

- Final app must handle missing Ollama, missing model, insufficient VRAM, stopped API, and malformed LLM output.

Cross-device risk:

- GitHub does not contain local DB/model artifacts. Copy them separately or regenerate them.

## 17. Rules For Future AI Agents

- Read this file first.
- Do not assume chat history exists.
- Do not restart full-market crawling unless explicitly requested.
- Do not commit data/, logs/, or models/.
- Do not delete local DB or model artifacts.
- Prefer phase-scoped changes.
- Verify DB status before reporting progress percentages.
- Respect Korean market colors in UI: red for 상승/호재 and blue for 하락/악재.
- Keep the final user experience command-free.
- Ask for API keys only when a real API integration requires them.

## 18. Update Procedure

After every meaningful work session, update this file with:

- timestamp,
- files changed,
- commands run,
- DB/model counts if relevant,
- phase completion changes,
- what remains,
- exact next recommended action.

This file replaces unavailable chat history. Keep it accurate enough that a new AI agent can continue without asking the user to restate the project.
