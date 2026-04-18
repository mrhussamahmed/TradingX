---
id: RESEARCH-0007
title: TradingX recurring market-day scheduler research
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Research: TradingX recurring market-day scheduler

## Existing repo capabilities reused

- `AlpacaRegularHoursCalendar` already supplies real-session awareness
  through Alpaca's trading calendar.
- `MarketDayAutomationRunner` already owns one-day orchestration and
  end-of-day Gate 3 evidence refresh.
- `LocalServiceManager` provides the local pattern for background thread
  lifecycle management in the website runtime.

## Decision

Build recurrence above the existing automation runner instead of inside
it. The scheduler should answer:

- when should today launch
- has today already launched
- what is the next session if today already ran

The bounded automation runner should continue answering:

- how a single market day executes
- what evidence gets written during that day

## Non-goals

- cloud scheduling
- Telegram-based parameter editing
- native desktop scheduling
- live trading enablement
