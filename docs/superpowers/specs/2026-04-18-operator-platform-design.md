---
id: DESIGN-0001
title: TradingX operator platform design
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# TradingX operator platform design

## Intent

Evolve the existing local control website into a production-grade local
operator platform for one paper-trading bot. The platform should become
the primary surface for daily supervision, decision explainability,
research review, incident handling, replay, and records browsing while
staying local-only, read-only by default, and bound to the same backend
services and evidence artifacts as the CLI.

## Product shape

The platform is organized into six product views:

- `Command Center` for market-session posture, account state, exposure,
  service health, and live refresh cards.
- `Trade Intelligence` for decision traces, risk checks, broker
  outcomes, reconciliations, and per-symbol trade timelines.
- `Research Studio` for candidate comparisons, benchmark-relative
  metrics, robustness evidence, and gate summaries.
- `Incident Center` for alert severity, acknowledgment state, incident
  timelines, and operator action history.
- `Replay Lab` for replaying service cycles, blocked trades, recovery
  events, and validation milestones from persisted evidence.
- `Settings & Records` for config proposals, handovers, state docs,
  validation artifacts, and searchable project records.

## Architecture

The backend remains one local FastAPI service plus the existing React
SPA. The new operator-platform layer adds:

- read models that convert persisted artifacts and runtime state into
  chart-ready and list-ready payloads
- a normalized event timeline assembled from service cycles, trade
  intents, orders, risk events, reconciliations, alerts, validation
  reports, and operator actions
- a bounded session-orchestration layer for pre-open checks, intraday
  pulses, end-of-day reconciliation, and daily digest generation
- replay builders that reconstruct human-readable narratives without
  creating a second source of truth

The browser remains a local operator client. It never computes trading
decisions and never bypasses backend safety checks.

## Delivery slices

1. `Slice A` adds the upgraded command center plus incident center.
2. `Slice B` adds trade intelligence plus replay lab.
3. `Slice C` adds research studio and richer validation views.
4. `Slice D` adds the design-system refresh, keyboard-first workflow,
   artifact explorer, and daily-operations polish.

## Safety model

- The website remains read-only unless web write mode is enabled.
- All mutations stay behind one orchestration boundary.
- Every bounded write action leaves an auditable artifact or event.
- Errors remain explicit, sanitized, and visible in the UI.
- Live trading stays disabled at all four safety layers.

## Testing shape

- backend unit tests for read models, event normalization, replay
  assembly, incident state, and session orchestration
- API contract tests for the expanded operator-platform endpoints
- frontend tests for multi-view rendering, filters, actions, and
  degraded states
- browser-style integration coverage through the React test suite
- full repo validation through `./scripts/validate`
