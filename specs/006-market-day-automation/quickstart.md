---
id: QUICKSTART-0007
title: TradingX market-day automation quickstart
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Quickstart: TradingX market-day automation

## CLI

Run one bounded automation flow:

```bash
uv run tradingx run-market-day --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-heartbeats 3
```

## Website

Enable write mode locally if you want the action controls:

```dotenv
TRADINGX_WEB_WRITE_MODE_ENABLED=true
```

Then run:

```bash
uv run tradingx web --env-file .env
```

Open `http://127.0.0.1:8765`, go to `Gate 3 Ops`, and use the automation
controls to run pre-open, heartbeat, close, or one bounded market-day
automation flow.
