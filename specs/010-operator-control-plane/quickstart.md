---
id: QUICKSTART-0011
title: TradingX operator control plane quickstart
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Quickstart: TradingX operator control plane

## Telegram mode

- Set `TRADINGX_TELEGRAM_BOT_TOKEN`
- Set `TRADINGX_TELEGRAM_CHAT_ID`
- Start the supervisor
- Use `/status`, `/positions`, `/today`, `/halt`, `/resume`,
  `/flatten`, and `/kill`

## CLI fallback mode

- Start the supervisor without Telegram credentials
- Use the persisted control files and fallback CLI paths documented in
  the week-1 runbook

## Supervisor output

- runtime lock stays owned for the session
- control files live under `data/control/`
- supervisor state lives under
  `artifacts/operator_platform/supervisor/`
