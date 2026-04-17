---
id: ADR-0006
title: Use SMTP email as the default emergency channel
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0006: Use SMTP email as the default emergency channel

## Status

Accepted.

## Context

- `.specify/memory/constitution.md` pins Telegram as the primary
  operator channel and SMTP email as the default emergency fallback.
- `docs/archive/implementation_constraints.md` repeats the SMTP gate
  structure for Phase 8, Gate 3, and Gate 4.
- Phase 0 does not implement SMTP yet, but the scaffold must preserve
  the emergency-channel contract.

## Decision

Use SMTP email as the default emergency-alert channel whenever the
primary Telegram path is unavailable.

## Consequences

- SMTP credentials are part of the `.env` skeleton from Phase 0 onward.
- Future alerting work must wire SMTP into the alert pipeline before the
  end of Phase 8 and validate it at Gates 3 and 4.
- Replacing SMTP requires a superseding ADR and operator approval.
