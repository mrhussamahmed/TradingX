---
id: QUICKSTART-0005
title: TradingX Gate 3 operations and evidence quickstart
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Quickstart: TradingX Gate 3 operations and evidence

## Generate a Gate 3 readiness report

```bash
uv run tradingx gate3-report --env-file .env
```

## Generate a Gate 3 promotion package

```bash
uv run tradingx gate3-package --env-file .env
```

## Run a recovery drill

```bash
uv run tradingx recovery-drill --env-file .env --symbol SPY
```

## Run an SMTP alert drill

```bash
uv run tradingx alert-drill --env-file .env --channel smtp
```

## Start the website

```bash
uv run tradingx web --env-file .env
```

Open `http://127.0.0.1:8765` and review the Gate 3 readiness panel. To
enable drill and session actions in the browser, set
`TRADINGX_WEB_WRITE_MODE_ENABLED=true` first.
