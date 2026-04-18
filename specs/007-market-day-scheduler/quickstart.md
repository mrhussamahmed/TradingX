---
id: QUICKSTART-0008
title: TradingX recurring market-day scheduler quickstart
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Quickstart: TradingX recurring market-day scheduler

## Run from CLI

```bash
uv run tradingx run-market-scheduler --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300
```

Use `--max-scheduled-days 1` for a bounded scheduler run during local
verification.

## Run from the website

Start the local site:

```bash
uv run tradingx web --env-file .env
```

Enable write mode in `.env`, then use the `Gate 3 Ops` scheduler panel
to start or stop unattended market-day scheduling.

## Expected outputs

- scheduler status from CLI or web
- one persisted schedule record per launched trading day under
  `artifacts/operator_platform/market_day_schedules/`
- existing market-day automation artifacts and Gate 3 evidence from the
  launched run
