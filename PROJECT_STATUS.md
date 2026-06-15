# Project Status

Last updated: 2026-06-12 KST

This file is the handoff document for continuing the project from another PC, USB drive, or Codex workspace. Read this before starting new work.

For the full cross-session handoff, read [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) first. This file is now a shorter status snapshot.

## Current Direction

The project is a local-first AI quant dashboard for Korean equities.

Core strategy:

- Use local SQLite for collected market/news data.
- Use Gemma through Ollama or LM Studio for zero-shot news sentiment analysis.
- Use lightweight CPU-friendly machine learning for price direction prediction.
- Do not preload every KRX stock history upfront.
- Train the base model with a representative 300-symbol sample.
- Backfill searched symbols on demand inside the final app.
- Release trained model packages through GitHub Releases, not through normal Git commits.

## Repository

GitHub repository:

```text
potato9j/X-Omniscient-AI-Quant-System
```

Important local workspace used so far:

```text
H:\C1_GitHub Project\26.06.11 Omniscient AI Quant System
```

If continuing from USB or another computer, open the project folder directly in Codex. The Codex chat thread may not appear on another device, so this file is the source of truth for handoff context.

## Implemented Files

```text
phase1_collector.py       # price, index, and Naver Finance news collection
stock_universe.py         # KOSPI/KOSDAQ universe refresh
historical_backfill.py    # historical OHLCV backfill
backfill_status.py        # numeric backfill progress report
sentiment_analyzer.py     # Ollama/LM Studio Gemma sentiment analysis
trend_predictor.py        # lightweight trend prediction model
model_release.py          # release ZIP packaging for trained model artifacts
config.yaml               # runtime configuration
README.md                 # polished project documentation
```

## Local Data Status

The collected DB is local only and is not committed to GitHub.

Important local file:

```text
data/omniscient_quant.sqlite3
```

Current backfill status from `backfill_status.py`:

```text
training_target_symbols : 300
completed_training      : 298
partial_training        : 2
progress_percent        : 99.33%
symbols_with_ohlcv      : 301
ohlcv_rows              : 360633
failed_status           : 0
```

The remaining 2 symbols have less than 1,000 available rows from Naver, so the sample backfill can be considered complete.

Known short-history symbols:

```text
012210 삼미금속    # 747 rows
014950 삼익제약    # 153 rows
```

## GitHub Status

Code and documentation are synced to GitHub.

Not synced by normal commits:

```text
data/
logs/
models/
*.sqlite3
models/releases/*.zip
```

These are ignored intentionally. The model ZIP should be distributed via GitHub Releases later.

## Current Model Status

Earlier partial training and packaging were tested successfully. That test model was only a functional proof, not the final candidate.

Next proper step:

```powershell
$env:PYTHONPATH='.deps'
$env:PYTHONIOENCODING='utf-8'
$env:LOKY_MAX_CPU_COUNT='8'
python model_release.py --config config.yaml
```

This will train the model on the current OHLCV data and create a release ZIP under:

```text
models/releases/
```

## Gemma / Ollama Notes

Use:

```text
gemma4:e2b
```

Reason:

- `gemma4:e4b` failed on RTX 3070 8GB due VRAM pressure.
- `gemma4:e2b` worked through Ollama.
- `sentiment_analyzer.py` sends `think: false` to Ollama because Gemma 4 otherwise returned empty content during testing.

## Commands

Check backfill progress:

```powershell
$env:PYTHONPATH='.deps'
python backfill_status.py --config config.yaml
```

Watch logs:

```powershell
Get-Content logs\backfill.log -Encoding UTF8 -Wait -Tail 40
```

Continue sample backfill if needed:

```powershell
$env:PYTHONPATH='.deps'
python historical_backfill.py --all-symbols --training-sample --config config.yaml --max-runtime-seconds 28800
```

On-demand backfill for a searched symbol:

```powershell
$env:PYTHONPATH='.deps'
python historical_backfill.py --symbol 005930 --on-demand --config config.yaml
```

Run one news sentiment pass:

```powershell
$env:PYTHONPATH='.deps'
python sentiment_analyzer.py --once --config config.yaml
```

Train and package a model:

```powershell
$env:PYTHONPATH='.deps'
$env:PYTHONIOENCODING='utf-8'
$env:LOKY_MAX_CPU_COUNT='8'
python model_release.py --config config.yaml
```

## Next Steps

1. Treat the 300-symbol training sample as complete.
2. Train and package the first real model release ZIP.
3. Inspect model metrics and metadata.
4. Add a GitHub Release upload workflow or script.
5. Start backend API layer for dashboard consumption.
6. Build frontend dashboard.
7. Add app startup orchestration so users do not type commands in the final EXE.

## Device Handoff Rules

When moving to another PC:

1. Move the full project folder or clone the repo.
2. Also move `data/omniscient_quant.sqlite3` if you need the collected data.
3. Open the folder directly in Codex on that device.
4. Read `PROJECT_HANDOFF.md` first.
5. Do not run two devices writing to the same SQLite DB at the same time.
