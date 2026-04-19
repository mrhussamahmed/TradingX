---
id: RESEARCH-0009
title: TradingX week-1 dry-run controls research
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Research: TradingX week-1 dry-run controls

## Existing repo capabilities reused

- `PaperTradingLoopController` already owns the validated paper trading
  loop and existing risk gates.
- `LocalRuntimeHostManager` already owns start/stop state transitions.
- Existing artifact persistence and read models already surface evidence
  in the website and reports.
- Telegram alert credentials and transports already exist in config and
  alerting code.

## New research decisions

- Use `exchange_calendars` for exchange-aware session logic instead of
  hand-rolled clock checks.
- Use SQLite in WAL mode for the OMS journal because it is local,
  durable, and easy to back up at session close.
- Keep the week-1 universe to `SPY` only and flat-by-close to minimize
  failure modes.
- Treat Monday as `dry_run` regardless of engineering optimism.

## Non-goals

- multi-symbol expansion in week 1
- live trading enablement
- model registry promotion or research orchestration in this phase
- website-first operator surface expansion beyond what the current app
  already supports
