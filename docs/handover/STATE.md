---
id: STATE-0001
title: Project state
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Current project state

- Active session: SESS-2026-04-18-017
- Active branch: codex/replay-slippage-evidence
- Active phase: 9
- Last completed gate: 0.5
- Walking skeleton: implemented; credentialed Alpaca paper smoke run passed
  on 2026-04-17
- Live trading enabled: no (disabled at all four layers)

## Pending items

- Phase 0 is complete and pushed to `origin/main`.
- `SPEC-0001` is active at `specs/001-paper-trading-bot/spec.md`.
- `PLAN-0001` is active at `specs/001-paper-trading-bot/plan.md`.
- `TASKS-0001` is active at `specs/001-paper-trading-bot/tasks.md`.
- `ADR-0009` selects Nautilus Trader as the backtest engine.
- `GATES-0001` defines the Stage 1 gate evidence baseline.
- `TASKS-0001` implementation is complete and merged into `main`.
- `codex/paper-service-upgrades` has been merged into `main`.
- `codex/gate-validation-reporting` has been merged into `main`.
- `codex/benchmark-series-prep` has been merged into `main`.
- `codex/gate-decision-layer` has been merged into `main`.
- `002-local-control-web-app` has been merged into `main` with the
  local control website implementation and its artifact chain.
- `ADR-0010` selects FastAPI plus a minimal React SPA for the local
  control web app.
- `ADR-0011` selects a normalized operator-event timeline with
  polling-based refresh for the operator platform.
- `ADR-0012` selects persisted trade-lifecycle and drill artifacts as
  the Gate 3 evidence source.
- `ADR-0013` selects persisted execution context as the replay-slippage
  evidence source.
- `SPEC-0002`, `PLAN-0002`, `TASKS-0002`, `RESEARCH-0002`,
  `DATAMODEL-0002`, `QUICKSTART-0003`, and `CONTRACT-0003` are active
  and define the local website feature set.
- `DESIGN-0001`, `SPEC-0003`, `PLAN-0003`, `TASKS-0003`,
  `RESEARCH-0003`, `DATAMODEL-0003`, `QUICKSTART-0004`, and
  `CONTRACT-0004` are active on `codex/operator-platform`, and the
  operator-platform implementation is complete and validated there.
- `DESIGN-0002`, `SPEC-0004`, `PLAN-0004`, `TASKS-0004`,
  `RESEARCH-0004`, `DATAMODEL-0004`, `QUICKSTART-0005`, and
  `CONTRACT-0005` are active on `codex/gate3-operations-evidence`, and
  the Gate 3 operations-and-evidence implementation is complete and
  validated there.
- `DESIGN-0003`, `SPEC-0005`, `PLAN-0005`, `TASKS-0005`,
  `RESEARCH-0005`, `DATAMODEL-0005`, `QUICKSTART-0006`, and
  `CONTRACT-0006` are active on `codex/replay-slippage-evidence`, and
  the replay-slippage evidence implementation is complete and validated
  there.
- The current repository now provides:
  - a deterministic paper trading loop with recovery and auditable risk
    decisions
  - a recurring paper-service runtime that scans a bounded symbol
    universe and persists service-cycle summaries
  - deterministic exit logic for existing positions via take-profit and
    stop-loss thresholds
  - an offline mandatory-candidate evaluation pipeline with persisted
    evidence packs
  - Gate 1 and Gate 2 validation-report generation from benchmark close
    series, including persisted validation reports and gate assessments
  - a `prepare-benchmark-closes` workflow that fetches Alpaca daily
    benchmark closes into metadata-rich artifacts and lets `gate-report`
    infer dividend-adjusted status safely
  - a `decision-report` workflow that combines the latest validation
    artifacts with current paper-evidence summaries into one
    operator-ready gate brief and alert preview
  - Gate 3 execution-lifecycle, closed-trade, recovery-drill,
    alert-drill, and market-session artifacts
  - `gate3-report` and `gate3-package` workflows that turn persisted
    paper evidence into a readiness report and promotion package
  - dedicated recovery-drill and alert-drill commands for bounded
    operational exercises
  - a `replay-slippage-report` workflow that persists replay-simulator
    cross-check records and divergence summaries from paper execution
    context
  - richer operator alerts, including optional Telegram and SMTP
    delivery and evidence-report summaries for paper-service runs
- `tradingx web`, which serves a local-only React dashboard over FastAPI
  for:
  - paper-service and bounded loop controls behind an explicit
    write-mode flag
  - evidence browsing for operator alerts, service cycles, and
    validation reports
  - gate-state and recommendation visibility
  - project-intelligence panels for handovers and state
  - safe config proposals written under `config/proposals/`
  - an operator-platform expansion with a command center, trade
    intelligence, research studio, incident center, replay lab, records
    explorer, daily session actions, and a command palette
- `tradingx web` now also exposes a dedicated `Gate 3 Ops` view for
  readiness, drills, market-session checkpoints, replay-slippage
  divergence, and promotion actions.
- Validation is green on `codex/replay-slippage-evidence`;
  `./scripts/validate` passed with the expected closed-market smoke
  skip, plus frontend tests and frontend build verification.
- The operator-platform UI keeps the premium control-room redesign while
  extending it with replay-slippage cross-check status and refresh
  controls.
- Next execution step on this branch is operator review and promotion of
  `codex/replay-slippage-evidence` into `main`.
