---
id: STATE-0001
title: Project state
version: 1.0.6
status: active
created: 2026-04-17
last_amended: 2026-04-19
supersedes: STATE-0001@1.0.5
superseded_by: null
author_session: SESS-2026-04-19-028
---

# Current project state

- Active session: SESS-2026-04-19-028
- Active branch: main
- Active phase: 15
- Last completed gate: 0.5
- Walking skeleton: implemented; credentialed Alpaca paper smoke run passed
  on 2026-04-17
- Live trading enabled: no (disabled at all four layers)

## Pending items

- Phase 0 is complete and pushed to `origin/main`.
- `SPEC-0001` is active at `specs/001-paper-trading-bot/spec.md`.
- `PLAN-0001` is active at `specs/001-paper-trading-bot/plan.md`.
- `TASKS-0001` is active at `specs/001-paper-trading-bot/tasks.md`.
- `ADR-0019` supersedes `ADR-0009` and selects a minimal
  pandas-plus-empyrical research backtest engine for Gate 1 and Gate 2
  rehabilitation.
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
- `ADR-0014` selects a dedicated market-day automation runner with
  persisted run artifacts.
- `ADR-0015` selects a calendar-driven recurring scheduler above the
  bounded market-day runner.
- `ADR-0016` selects a supervised local trading appliance runtime with
  governed activation records, deterministic first-run selection, and
  proposal-only learning outputs.
- `ADR-0017` selects policy snapshots and an append-only SQLite journal
  as the week-1 dry-run safety control plane.
- `ADR-0018` selects a local supervisor plus a single-chat Telegram
  command plane for week-1 operator control.
- `ARCHMAP-0001` is the canonical one-page runtime/appliance
  architecture pointer for future development and must be updated when
  canonical architecture files or precedence change.
- `RUNBOOK-0003` is now the official operator instruction manual and
  must be updated whenever startup, operation, dashboard, validation, or
  recovery behavior changes.
- `RUNBOOK-0004` records the approved week-1 premortem and its mapped
  controls.
- `RUNBOOK-0005` defines the Sunday rehearsal, Monday dry-run review,
  and `GATES-0001` Tuesday readiness flow.
- `week1-rehearsal` now generates the canonical Sunday ops artifacts
  under `artifacts/ops/`, including the rehearsal result,
  reconciliation review, operator-control verification, and the
  recorded paper-account starting state.
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
- `DESIGN-0004`, `SPEC-0006`, `PLAN-0006`, `TASKS-0006`,
  `RESEARCH-0006`, `DATAMODEL-0006`, `QUICKSTART-0007`, and
  `CONTRACT-0007` are active and the market-day automation
  implementation is now merged into `main`.
- `DESIGN-0005`, `SPEC-0007`, `PLAN-0007`, `TASKS-0007`,
  `RESEARCH-0007`, `DATAMODEL-0007`, `QUICKSTART-0008`, and
  `CONTRACT-0008` are active and the recurring market-day scheduler
  implementation is now merged into `main`.
- `DESIGN-0006`, `SPEC-0008`, `PLAN-0008`, `TASKS-0008`,
  `RESEARCH-0008`, `DATAMODEL-0008`, `QUICKSTART-0009`, and
  `CONTRACT-0009` are active and the local trading appliance
  implementation is now merged into `main`.
- `DESIGN-0007`, `SPEC-0009`, `PLAN-0009`, `TASKS-0009`,
  `RESEARCH-0009`, `DATAMODEL-0009`, `QUICKSTART-0010`, and
  `CONTRACT-0010` are active and the week-1 dry-run safety pack is now
  merged into `main`.
- `DESIGN-0008`, `SPEC-0010`, `PLAN-0010`, `TASKS-0010`,
  `RESEARCH-0010`, `DATAMODEL-0010`, `QUICKSTART-0011`, and
  `CONTRACT-0011` are active and define the week-1 operator control
  plane with a local supervisor, control files, and Telegram commands.
- Week-1 runtime entry points now enforce a single-writer process lock
  on `data/runtime.pid` so a second process cannot silently operate
  against the same local data root.
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
  - a `run-market-day` workflow that performs pre-open, bounded
    heartbeat, closeout, and automatic Gate 3 evidence refresh as one
    persisted automation run
  - a `run-market-scheduler` workflow that polls the regular-hours
    market calendar, launches at most one market-day automation run per
    trading day, persists durable schedule artifacts, and exposes live
    next-run status
  - a supervised local trading appliance runtime host with explicit
    startup states, governed strategy activation records, approved
    model-weight snapshots, historical warmup artifacts, deterministic
    opportunity selection records, and proposal-only post-trade
    learning artifacts
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
  divergence, automation history, recurring scheduler state, and
  promotion actions.
- `tradingx web` now also exposes a `Runtime Host` panel in the
  command center for one-click local bot start/stop, warmup readiness,
  active strategy/model visibility, ranked opportunity inspection, and
  bounded learning-proposal refresh.
- `tradingx run-operator-supervisor` now owns the week-1 unattended
  parent process: it holds the runtime lock, supervises the long-running
  market-day child process, persists state under
  `artifacts/operator_platform/supervisor/`, and optionally polls
  Telegram for `/status`, `/positions`, `/today`, `/halt`, `/resume`,
  `/flatten`, and `/kill` when Telegram credentials are configured.
- Week-1 runtime observability is now fully wired through structured
  JSONL component logs under `data/logs/`, with default `100 MB`
  rotation and `30` retained rotated files per component, plus explicit
  `decision_snapshot_id` and `cycle_correlation_id` tagging in the
  controller, service, supervisor, and Telegram command paths.
- Week-1 control files now live under `data/control/` and are consumed
  by the paper trading controller so operator halts block new entry
  intents without blocking exits.
- Validation is green on `main`;
  `./scripts/validate` passed with the expected closed-market smoke
  skip, plus frontend tests and frontend build verification.
- The operator-platform UI keeps the premium control-room redesign while
  extending it with replay-slippage cross-check status, automation
  summary, bounded market-day run controls, and recurring scheduler
  controls.
- The next execution step is to run
  `uv run tradingx run-operator-supervisor --env-file .env --symbols SPY --quantity 1 --interval-seconds 300`
  for week-1 unattended dry-run control, or keep using the website
  runtime-host path if Telegram is not needed.
