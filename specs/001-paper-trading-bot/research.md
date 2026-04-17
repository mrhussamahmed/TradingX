---
id: RESEARCH-0001
title: TradingX Stage 1 planning research
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Research decisions

## Decision 1 — Keep one Python package for the Stage 1 bot

**Decision**: Preserve a single `src/tradingx/` service and grow it by
adding narrowly-scoped modules rather than splitting into multiple apps,
workers, or services.

**Rationale**: The current repo already has a working Phase 0 walking
skeleton in one package. The operator model is single-user, the runtime
is local or one-node, and the constitution favors the simplest structure
that remains auditable.

**Alternatives considered**:

- Separate API, scheduler, and execution services: rejected because it
  adds deployment and state-coordination complexity before the bot has
  earned it.
- Immediate subpackage decomposition: rejected because the current code
  volume does not yet justify deeper nesting.

## Decision 2 — Use Nautilus Trader as the backtest engine

**Decision**: Select Nautilus Trader for backtesting and replay-driven
strategy validation in later implementation phases.

**Rationale**: Nautilus Trader's official documentation emphasizes one
event-driven architecture spanning backtesting and live deployment, plus
official Python 3.11 support in the latest stable installation guide.
That aligns with TradingX's need to reduce divergence between strategy
research, paper execution, and any future live-readiness work. By
contrast, VectorBT PRO's official materials emphasize high-speed
vectorized research and paid private-repository access. That is useful
for research, but it is a weaker fit for a repo-first project whose main
Phase 1 concern is research-to-paper/live parity.

**Alternatives considered**:

- VectorBT PRO: rejected as the primary engine because its official
  positioning is research-centric and proprietary.
- Building a custom backtester: rejected by the implementation
  constraints unless the approved options fail.

## Decision 3 — Separate strategy evaluation from the trading loop

**Decision**: Treat strategy evaluation as an offline evidence-producing
pipeline that feeds candidate recommendations into the paper bot, rather
than embedding exploratory evaluation inside the runtime trading loop.

**Rationale**: The constitution forbids nondeterministic generative-AI
decisioning in any trading loop and requires honest benchmark-relative
evidence before promotion. Keeping evaluation offline preserves
repeatability and makes evidence packs independently auditable.

**Alternatives considered**:

- Shared experimental logic inside the live paper loop: rejected because
  it mixes research concerns with execution safety.

## Decision 4 — Use contract-first event records for operator oversight

**Decision**: Standardize trade outcomes, blocked trades, alerts, and
gate decisions as explicit records with stable fields before wiring real
Telegram, SMTP, and ClickUp adapters.

**Rationale**: The operator surfaces are intentionally bounded. Stable
records let the bot write one auditable event once, then fan it out to
the correct bounded interface without losing traceability.

**Alternatives considered**:

- Free-form log messages only: rejected because they are hard to validate
  and weak as evidence.
- Adapter-specific payloads as the primary truth: rejected because they
  couple business meaning to transport details.

## Decision 5 — Delay the persistence-engine lock-in

**Decision**: Introduce a persistence boundary now, but defer the
concrete runtime store until the later state-recovery phase needs it.

**Rationale**: Phase 0 already records smoke evidence as filesystem
artifacts, while the constitution's strong persistence requirements do
not arrive until restart recovery and operational maturity work. A thin
boundary preserves that future choice without forcing an unnecessary
database commitment in this session.

**Alternatives considered**:

- Choose a database immediately: rejected as premature complexity.
- Keep all state in memory with no boundary: rejected because later
  recovery work would require invasive refactoring.

## Sources

- Nautilus Trader overview and live-trading docs:
  [nautilustrader.io/docs/latest](https://nautilustrader.io/docs/latest/)
  and [nautilustrader.io/docs/latest/concepts/live/](https://nautilustrader.io/docs/latest/concepts/live/)
  (retrieved 2026-04-17).
- Nautilus Trader installation guide:
  [nautilustrader.io/docs/latest/getting_started/installation](https://nautilustrader.io/docs/latest/getting_started/installation)
  (retrieved 2026-04-17).
- VectorBT PRO getting started and portfolio feature pages:
  [vectorbt.pro](https://vectorbt.pro/) and
  [vectorbt.pro/features/portfolio/](https://vectorbt.pro/features/portfolio/)
  (retrieved 2026-04-17).
