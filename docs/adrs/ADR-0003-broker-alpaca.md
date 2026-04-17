---
id: ADR-0003
title: Use Alpaca for Stage 1 and Stage 2 brokerage
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0003: Use Alpaca for Stage 1 and Stage 2 brokerage

## Status

Accepted.

## Context

- `.specify/memory/constitution.md` pins Alpaca as the Stage 1 and
  Stage 2 broker and paper-trading environment.
- `docs/archive/implementation_constraints.md` pins Alpaca endpoints,
  paper-first operation, and the `alpaca-py` SDK.
- Phase 0 requires a real paper-trading round trip against Alpaca's
  paper environment.

## Decision

Use Alpaca as the only Stage 1 and Stage 2 broker adapter. The walking
skeleton, smoke tests, and initial execution stack target Alpaca paper
trading only.

## Consequences

- Broker-facing abstractions are shaped around Alpaca paper trading first.
- Live trading credentials remain unused and disabled until Gate 4.
- A broker change would require a superseding ADR and operator approval.
