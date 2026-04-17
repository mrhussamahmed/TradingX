---
id: ADR-0008
title: Require a real Alpaca paper round trip in Phase 0
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0008: Require a real Alpaca paper round trip in Phase 0

## Status

Accepted.

## Context

- The constitution's walking-skeleton principle requires governance to
  coexist with working code inside Phase 0.
- `docs/operations/bootstrap_install.md` makes the paper-trading round
  trip a mandatory step, not optional follow-on work.
- Gate 0.5 is defined as an operational proof that the bot can fetch
  data, place paper orders, receive fills, and reconcile state.

## Decision

Phase 0 is not considered complete unless the repository contains a real
Alpaca paper-trading round trip, exercised by a smoke test that can pass
 with valid paper credentials and skip cleanly when those credentials are
 absent.

## Consequences

- The initial source tree must include a minimal but real controller,
  data, execution, portfolio, and risk path.
- Validation cannot claim Gate 0.5 without a working paper round trip.
- If scaffolding work crowds out the skeleton, the session must stop and ask.
