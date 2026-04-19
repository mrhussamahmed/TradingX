---
id: RESEARCH-0010
title: TradingX operator control plane research
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Research: TradingX operator control plane

## Existing repo capabilities reused

- Telegram alert transport and config fields already exist.
- The week-1 safety pack already provides the runtime lock, policy
  snapshots, decision snapshots, OMS journal, and dry-run report.
- The scheduler already exposes a stop-event seam suitable for a
  supervisor-owned child process.
- The paper portfolio and execution gateways already expose the broker
  reads and close-position action needed for week-1 flattening.

## New research decisions

- Use Telegram polling via the Bot API instead of webhooks because the
  project is local-only.
- Use a separate local child process for the trading scheduler so the
  operator command plane and the trading workload stay isolated.
- Keep restart policy disabled by default and bounded when enabled.

## Non-goals

- multi-user Telegram auth
- cloud-hosted control planes
- website redesign or major website control expansion
- live trading enablement
