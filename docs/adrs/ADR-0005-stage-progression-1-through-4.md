---
id: ADR-0005
title: Preserve sequential Stage 1 through Stage 4 progression
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0005: Preserve sequential Stage 1 through Stage 4 progression

## Status

Accepted.

## Context

- `.specify/memory/constitution.md` defines a four-stage progression and
  explicitly prohibits a single unrestricted "god mode."
- `docs/archive/project_brief.md` says all current work is Stage 1 only.
- Phase and gate boundaries depend on keeping paper equities, live
  equities, crypto expansion, and multi-strategy allocation separate.

## Decision

Honor the constitution's sequential progression:

1. Stage 1 paper US equities.
2. Stage 2 live US equities with capped capital.
3. Stage 3 isolated crypto strategy only after explicit authorization
   and a constitution amendment.
4. Stage 4 multi-strategy capital allocation only after Stage 3 proves out.

## Consequences

- Phase 0 scaffolding targets Stage 1 paper trading only.
- No crypto, derivatives, or multi-strategy work enters `src/` now.
- Any attempt to skip gates or combine stages is a governance violation.
