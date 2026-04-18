---
id: RESEARCH-0006
title: TradingX market-day automation research
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Research: TradingX market-day automation

## Reuse opportunities

- `PaperTradingService.run(..., max_cycles=1)` already provides one
  bounded service cycle and persists service-cycle artifacts.
- `generate_replay_slippage_evidence(...)` already turns execution
  records into replay summaries without live data access.
- `build_gate3_readiness_report(...)` and
  `build_gate3_promotion_package(...)` already produce the core Gate 3
  artifacts.
- `LocalWebActionRunner` already owns write-mode orchestration for the
  website and is the right integration point for automation actions.

## Gaps

- The current session actions only write digest snapshots; they do not
  run trading or refresh Gate 3 evidence.
- There is no persisted record for one bounded market-day automation
  execution.
- The website cannot show whether pre-open, heartbeat, close, and daily
  refreshes were run as one coherent flow.

## Implementation direction

- Add one backend automation module rather than spreading orchestration
  across `service.py`, CLI logic, and web runtime helpers.
- Persist automation-run artifacts under `artifacts/operator_platform/`
  because the records are operator-control artifacts, not broker or
  paper-loop primitives.
- Keep the automation runner bounded and synchronous so it stays easy to
  test and safe to call from the CLI or local website.
