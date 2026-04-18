---
id: QUICKSTART-0009
title: TradingX local trading appliance quickstart
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Quickstart: TradingX local trading appliance

## Start the local site

```bash
uv run tradingx web --env-file .env
```

Open `http://127.0.0.1:8765`.

## Start the bot from the website

Enable write mode in `.env`, then use the runtime-host controls in the
website to start the bot. The website will:

- warm up the configured universe
- load the active activation record and model snapshot
- rank the current universe
- start the supervised runtime in a trading-ready or fail-closed state

## Bounded CLI verification

```bash
uv run tradingx runtime-start --env-file .env --symbols SPY,QQQ,IWM --quantity 1
```

Use the website for normal operation; the CLI entry point exists for
verification and diagnostics.

## Expected outputs

- runtime-host state in the website and CLI
- activation and model snapshot summaries
- historical warmup artifact under `artifacts/operator_platform/runtime_host/`
- opportunity-selection artifact under
  `artifacts/operator_platform/opportunity_selections/`
- learning proposals under
  `artifacts/operator_platform/model_weight_proposals/`
