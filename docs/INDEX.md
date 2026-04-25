---
id: INDEX-0001
title: Artifact index
version: 1.2.56
status: active
created: 2026-04-17
last_amended: 2026-04-25
supersedes: INDEX-0001@1.2.55
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Artifact index

This file is the registry of every versioned artifact in the
repository. It provides a fast lookup for agents starting a session.
The front-matter on individual artifacts is the ground truth; this
index is the cache. On conflict, front-matter wins and this index
MUST be corrected in the same session that detects the conflict.

## How to read this file

Each row shows the current versioned artifact tracked in the
repository, including any in-repo superseded artifacts that must
remain indexed for validation and auditability.

When an artifact is superseded, both the old and new files are
committed in the same commit, and this index is updated in that
commit.

Agents MUST update this index whenever they:

- Create a new artifact (add a row with initial `status: draft` or
  `active`).
- Promote an artifact from `draft` to `active`.
- Supersede an artifact (update the row to point at the new
  version).
- Deprecate or reject an artifact (update its status).

Agents MUST NOT rely on this index alone. Always open the artifact
and check its front-matter before acting on it.

Also note: every versioned artifact carries both a `status` field
(artifact lifecycle) and, for session handovers, a `session_status`
field (session lifecycle). This index tracks `status` only.

## Active artifacts

### Constitution

| id            | title                                  | version | status | path                           |
| ------------- | -------------------------------------- | ------- | ------ | ------------------------------ |
| CONST-0001    | Trading bot constitution               | 3.0.1   | active | `.specify/memory/constitution.md` |

### Project input documents (used in Phases 0-1)

| id                 | title                          | version | status | path                                           |
| ------------------ | ------------------------------ | ------- | ------ | ---------------------------------------------- |
| BRIEF-0001         | Project brief                  | 3.0.0   | active | `docs/archive/project_brief.md`                |
| CONSTRAINTS-0001   | Implementation constraints     | 1.0.0   | active | `docs/archive/implementation_constraints.md`   |

### Runbooks

| id              | title                   | version | status | path                                        |
| --------------- | ----------------------- | ------- | ------ | ------------------------------------------- |
| RUNBOOK-0001    | Session recovery        | 1.1.1   | active | `docs/operations/session_recovery.md`       |
| RUNBOOK-0002    | Bootstrap install       | 1.0.1   | active | `docs/operations/bootstrap_install.md`      |
| RUNBOOK-0003    | TradingX operator manual | 1.4.2  | active | `docs/operations/operator_manual.md`        |
| RUNBOOK-0004    | Week 1 premortem       | 1.0.0   | active | `docs/operations/week1_premortem.md`        |
| RUNBOOK-0005    | Week 1 rehearsal and gates | 1.2.1 | active | `docs/operations/week1_rehearsal_and_gates.md` |

### State files

| id          | title             | version | status | path                          |
| ----------- | ----------------- | ------- | ------ | ----------------------------- |
| STATE-0001  | Project state     | 1.0.10  | active | `docs/handover/STATE.md`      |
| INDEX-0001  | Artifact index    | 1.2.56  | active | `docs/INDEX.md` (this file)   |

### Architecture maps

| id           | title                    | version | status | path                                    |
| ------------ | ------------------------ | ------- | ------ | --------------------------------------- |
| ARCHMAP-0001 | Current architecture map | 1.4.1   | active | `docs/architecture/CURRENT_ARCHITECTURE.md` |

### Architecture decision records (ADR-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| ADR-0001 | Use Python 3.11 as the baseline runtime | 1.0.0 | active | `docs/adrs/ADR-0001-language-python-3.11.md` |
| ADR-0002 | Use uv as the package manager | 1.0.0 | active | `docs/adrs/ADR-0002-package-manager-uv.md` |
| ADR-0003 | Use Alpaca for Stage 1 and Stage 2 brokerage | 1.0.0 | active | `docs/adrs/ADR-0003-broker-alpaca.md` |
| ADR-0004 | Use SPY as the Stage 1 and Stage 2 benchmark | 1.0.1 | superseded | `docs/adrs/ADR-0004-benchmark-spy.md` |
| ADR-0005 | Preserve sequential Stage 1 through Stage 4 progression | 1.0.0 | active | `docs/adrs/ADR-0005-stage-progression-1-through-4.md` |
| ADR-0006 | Use SMTP email as the default emergency channel | 1.0.0 | active | `docs/adrs/ADR-0006-emergency-channel-smtp.md` |
| ADR-0007 | Restrict Stage 1 and Stage 2 trading to regular market hours | 1.0.0 | active | `docs/adrs/ADR-0007-market-hours-regular-only.md` |
| ADR-0008 | Require a real Alpaca paper round trip in Phase 0 | 1.0.0 | active | `docs/adrs/ADR-0008-walking-skeleton-deliverable.md` |
| ADR-0009 | Use Nautilus Trader as the backtest engine | 1.0.0 | superseded | `docs/adrs/ADR-0009-backtest-engine-nautilus-trader.md` |
| ADR-0010 | Use FastAPI with a minimal React SPA for the local control web app | 1.0.0 | active | `docs/adrs/ADR-0010-local-web-app-react-spa.md` |
| ADR-0011 | Use a normalized operator event timeline with polling refresh for the operator platform | 1.0.0 | active | `docs/adrs/ADR-0011-operator-platform-event-timeline-polling.md` |
| ADR-0012 | Use persisted trade lifecycle and drill artifacts as the Gate 3 evidence source | 1.0.0 | active | `docs/adrs/ADR-0012-gate3-evidence-lifecycle-artifacts.md` |
| ADR-0013 | Use persisted execution context to generate replay-slippage cross-check evidence | 1.0.0 | active | `docs/adrs/ADR-0013-replay-slippage-cross-check-from-persisted-execution-context.md` |
| ADR-0014 | Use a dedicated market-day automation runner with persisted run artifacts | 1.0.0 | active | `docs/adrs/ADR-0014-market-day-automation-runner.md` |
| ADR-0015 | Use a calendar-driven recurring scheduler above the bounded market-day runner | 1.0.0 | active | `docs/adrs/ADR-0015-calendar-driven-market-day-scheduler.md` |
| ADR-0016 | Use a supervised local trading appliance runtime with governed activation records | 1.0.0 | active | `docs/adrs/ADR-0016-local-trading-appliance-runtime-host.md` |
| ADR-0017 | Use policy snapshots and an append-only SQLite journal for week-1 dry-run safety | 1.0.0 | active | `docs/adrs/ADR-0017-week1-dry-run-safety-control-plane.md` |
| ADR-0018 | Use a local supervisor with a single-chat Telegram operator command plane | 1.0.0 | active | `docs/adrs/ADR-0018-telegram-operator-supervisor-control-plane.md` |
| ADR-0019 | Use a minimal pandas plus empyrical-reloaded backtest engine for Gate 1 research | 1.0.1 | active | `docs/adrs/ADR-0019-minimal-pandas-backtest-engine.md` |
| ADR-0020 | Tighten Gate 1 statistical criteria around deflated Sharpe and overfitting controls | 1.0.1 | superseded | `docs/adrs/ADR-0020-gate1-statistical-criteria.md` |
| ADR-0021 | Adopt three-tier benchmark stack in place of SPY-only benchmarking | 1.0.0 | active | `docs/adrs/ADR-0021-benchmark-stack.md` |
| ADR-0022 | Reframe Gate 1 from standalone sleeve Sharpe to benchmark-stack criteria and robustness | 1.0.0 | active | `docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md` |
| ADR-0024 | Activate Gate 1 PBO from CPCV cohort readiness | 1.0.0 | active | `docs/adrs/ADR-0024-gate1-pbo-activation.md` |
| ADR-0025 | Gate 4 live-enablement control plane and signed web writes | 1.0.0 | active | `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md` |

### Design documents

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| DESIGN-0001 | TradingX operator platform design | 1.0.0 | active | `docs/superpowers/specs/2026-04-18-operator-platform-design.md` |
| DESIGN-0002 | TradingX Gate 3 operations and evidence design | 1.0.0 | active | `docs/superpowers/specs/2026-04-18-gate3-operations-evidence-design.md` |
| DESIGN-0003 | TradingX replay-slippage evidence design | 1.0.0 | active | `docs/superpowers/specs/2026-04-18-replay-slippage-evidence-design.md` |
| DESIGN-0004 | TradingX market-day automation design | 1.0.0 | active | `docs/superpowers/specs/2026-04-18-market-day-automation-design.md` |
| DESIGN-0005 | TradingX recurring market-day scheduler design | 1.0.0 | active | `docs/superpowers/specs/2026-04-18-market-day-scheduler-design.md` |
| DESIGN-0006 | TradingX local trading appliance design | 1.0.0 | active | `docs/superpowers/specs/2026-04-19-local-trading-appliance-design.md` |
| DESIGN-0007 | TradingX week-1 dry-run controls design | 1.0.0 | active | `docs/superpowers/specs/2026-04-19-week1-dry-run-controls-design.md` |
| DESIGN-0008 | TradingX operator control plane design | 1.0.0 | active | `docs/superpowers/specs/2026-04-19-operator-control-plane-design.md` |
| DESIGN-0009 | TradingX control center launcher design | 1.0.0 | active | `docs/superpowers/specs/2026-04-19-control-center-launcher-design.md` |
| DESIGN-0010 | TradingX runtime intelligence design | 1.0.0 | active | `docs/superpowers/specs/2026-04-20-runtime-intelligence-design.md` |
| DESIGN-0011 | Tranche 1.1 validation infrastructure design | 0.1.0 | draft | `docs/superpowers/specs/2026-04-21-tranche-1-1-validation-infrastructure-design.md` |
| DESIGN-0012 | TradingX operator platform redesign | 1.0.0 | active | `docs/superpowers/specs/2026-04-20-operator-platform-redesign-design.md` |
| DESIGN-0013 | Tranche 1.2 market-state features design | 0.1.0 | draft | `docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md` |
| DESIGN-0014 | Tranche 1.3 sleeves — trend-following and vol-managed beta | 0.1.0 | draft | `docs/superpowers/specs/2026-04-21-tranche-1-3-sleeves-design.md` |
| DESIGN-0015 | Tranche 1.4 portfolio construction and drawdown defense | 0.1.0 | draft | `docs/superpowers/specs/2026-04-21-tranche-1-4-portfolio-construction-and-drawdown-defense-design.md` |
| DESIGN-0016 | Tranche 1.5 live drift monitoring | 0.1.0 | draft | `docs/superpowers/specs/2026-04-21-tranche-1-5-live-drift-monitoring-design.md` |
| DESIGN-0017 | Tranche 2.1 multi-sleeve live runtime wiring | 0.1.0 | draft | `docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md` |
| DESIGN-0018 | Tranche 2.2 CPCV + PBO design | 1.0.0 | active | `docs/superpowers/specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md` |
| DESIGN-0019 | Tranche 2.1 Stage 2 sleeve position ledger attribution | 1.0.0 | active | `docs/superpowers/specs/2026-04-22-tranche-2-1-stage-2-sleeve-position-ledger-attribution-design.md` |
| DESIGN-0020 | TradingX frontend UX and information architecture | 1.0.0 | active | `docs/architecture/TradingX_Frontend_Design.md` |
| DESIGN-0021 | TradingX dashboard and design system | 1.0.0 | active | `docs/architecture/TradingX_Dashboard_And_Design_System.md` |
| DESIGN-0022 | TradingX headless control plane architecture | 1.0.0 | draft | `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md` |
| DESIGN-0023 | Headless control plane Wave 2 runtime projector design | 1.0.0 | draft | `docs/superpowers/specs/2026-04-25-wave2-postgres-runtime-projector-design.md` |

### Planning briefs (BRIEF-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| BRIEF-0002 | Tranche 1 planning brief | 1.2.0 | active | `docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md` |
| BRIEF-0003 | Tranche 2 planning brief | 1.0.0 | active | `docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md` |

### Future features ledger (FFL-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| FFL-0001 | Future features ledger | 1.0.0 | active | `docs/roadmap/future-features-ledger.md` |

### Specifications (SPEC-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| SPEC-0001 | TradingX Stage 1 paper trading bot specification | 1.0.0 | active | `specs/001-paper-trading-bot/spec.md` |
| SPEC-0002 | TradingX local control web app specification | 1.0.0 | active | `specs/002-local-control-web-app/spec.md` |
| SPEC-0003 | TradingX operator platform specification | 1.0.0 | active | `specs/003-operator-platform/spec.md` |
| SPEC-0004 | TradingX Gate 3 operations and evidence specification | 1.0.0 | active | `specs/004-gate3-operations-evidence/spec.md` |
| SPEC-0005 | TradingX replay-slippage evidence specification | 1.0.0 | active | `specs/005-replay-slippage-evidence/spec.md` |
| SPEC-0006 | TradingX market-day automation specification | 1.0.0 | active | `specs/006-market-day-automation/spec.md` |
| SPEC-0007 | TradingX recurring market-day scheduler specification | 1.0.0 | active | `specs/007-market-day-scheduler/spec.md` |
| SPEC-0008 | TradingX local trading appliance specification | 1.0.0 | active | `specs/008-local-trading-appliance/spec.md` |
| SPEC-0009 | TradingX week-1 dry-run controls specification | 1.0.0 | active | `specs/009-week1-dry-run-controls/spec.md` |
| SPEC-0010 | TradingX operator control plane specification | 1.0.0 | active | `specs/010-operator-control-plane/spec.md` |
| SPEC-0013 | Capital growth landscape — v1 strategic roadmap | 0.1.0 | draft | `docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md` |

### Plans (PLAN-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| PLAN-0001 | TradingX Stage 1 paper trading bot implementation plan | 1.0.0 | active | `specs/001-paper-trading-bot/plan.md` |
| PLAN-0002 | TradingX local control web app implementation plan | 1.0.0 | active | `specs/002-local-control-web-app/plan.md` |
| PLAN-0003 | TradingX operator platform implementation plan | 1.0.0 | active | `specs/003-operator-platform/plan.md` |
| PLAN-0004 | TradingX Gate 3 operations and evidence implementation plan | 1.0.0 | active | `specs/004-gate3-operations-evidence/plan.md` |
| PLAN-0005 | TradingX replay-slippage evidence implementation plan | 1.0.0 | active | `specs/005-replay-slippage-evidence/plan.md` |
| PLAN-0006 | TradingX market-day automation implementation plan | 1.0.0 | active | `specs/006-market-day-automation/plan.md` |
| PLAN-0007 | TradingX recurring market-day scheduler implementation plan | 1.0.0 | active | `specs/007-market-day-scheduler/plan.md` |
| PLAN-0008 | TradingX local trading appliance implementation plan | 1.0.0 | active | `specs/008-local-trading-appliance/plan.md` |
| PLAN-0009 | TradingX week-1 dry-run controls implementation plan | 1.0.0 | active | `specs/009-week1-dry-run-controls/plan.md` |
| PLAN-0010 | TradingX operator control plane implementation plan | 1.0.0 | active | `specs/010-operator-control-plane/plan.md` |
| PLAN-0011 | TradingX operator platform redesign implementation plan | 1.0.0 | active | `specs/011-operator-platform-redesign/plan.md` |
| PLAN-0012 | TradingX runtime intelligence implementation plan | 1.0.0 | active | `specs/012-runtime-intelligence/plan.md` |
| PLAN-0013 | Headless control plane Wave 2 Postgres projections execution plan | 1.0.0 | draft | `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md` |
| PLAN-0014 | Headless control plane Wave 2 Postgres projections implementation plan | 1.0.0 | draft | `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md` |
| PLAN-0015 | Headless control plane Wave 2 Postgres connection and migrations slice plan | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md` |
| PLAN-0016 | Headless control plane Wave 2 Postgres repository contracts plan | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-plan.md` |
| PLAN-0017 | Headless control plane Wave 2 Postgres outbox checkpoint and readiness plan | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-outbox-checkpoint-readiness-plan.md` |
| PLAN-0018 | Headless control plane Wave 2 Postgres legacy bridge and tailer plan | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md` |
| PLAN-0019 | Headless control plane Wave 2 Postgres runtime projector plan | 1.0.1 | draft | `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md` |
| PLAN-0020 | Headless control plane Wave 2 Postgres documents pivot plan | 1.0.2 | draft | `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-plan.md` |
| PLAN-0021 | Headless control plane Wave 2 Postgres documents pivot implementation plan | 1.0.1 | draft | `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-implementation-plan.md` |
| PLAN-0022 | Headless control plane Wave 2 Postgres documents projector implementation plan | 1.0.1 | draft | `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-implementation-plan.md` |
| PLAN-0023 | Headless control plane Wave 2 Postgres documents projector execution plan | 1.0.1 | draft | `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-execution-plan.md` |

### Review reports (REPORT-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| REPORT-0001 | Headless control plane Wave 1 adversarial review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-23-headless-control-plane-wave1-review-handoff.md` |
| REPORT-0002 | Headless control plane Wave 2 planning adversarial review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-review-handoff.md` |
| REPORT-0003 | Headless control plane Wave 2 implementation plan adversarial review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-review-handoff.md` |
| REPORT-0004 | Headless control plane Wave 2 foundation implementation adversarial review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-foundation-review-handoff.md` |
| REPORT-0005 | Headless control plane Wave 2 Postgres connection and migrations plan review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-review-handoff.md` |
| REPORT-0006 | Headless control plane Wave 2 Postgres repository contracts implementation plan review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-review-handoff.md` |
| REPORT-0007 | Headless control plane Wave 2 Postgres legacy bridge and tailer plan review handoff | 1.0.0 | draft | `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-review-handoff.md` |
| REPORT-0008 | Headless control plane Wave 2 Postgres runtime projector plan review handoff | 1.0.1 | draft | `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-review-handoff.md` |

### Task lists (TASKS-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| TASKS-0001 | TradingX Stage 1 paper trading bot task list | 1.0.0 | active | `specs/001-paper-trading-bot/tasks.md` |
| TASKS-0002 | TradingX local control web app task list | 1.0.0 | active | `specs/002-local-control-web-app/tasks.md` |
| TASKS-0003 | TradingX operator platform task list | 1.0.0 | active | `specs/003-operator-platform/tasks.md` |
| TASKS-0004 | TradingX Gate 3 operations and evidence task list | 1.0.0 | active | `specs/004-gate3-operations-evidence/tasks.md` |
| TASKS-0005 | TradingX replay-slippage evidence task list | 1.0.0 | active | `specs/005-replay-slippage-evidence/tasks.md` |
| TASKS-0006 | TradingX market-day automation task list | 1.0.0 | active | `specs/006-market-day-automation/tasks.md` |
| TASKS-0007 | TradingX recurring market-day scheduler task list | 1.0.0 | active | `specs/007-market-day-scheduler/tasks.md` |
| TASKS-0008 | TradingX local trading appliance task list | 1.0.0 | active | `specs/008-local-trading-appliance/tasks.md` |
| TASKS-0009 | TradingX week-1 dry-run controls task list | 1.0.1 | active | `specs/009-week1-dry-run-controls/tasks.md` |
| TASKS-0010 | TradingX operator control plane task list | 1.0.1 | active | `specs/010-operator-control-plane/tasks.md` |

### Research notes

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| RESEARCH-0001 | TradingX Stage 1 planning research | 1.0.0 | active | `specs/001-paper-trading-bot/research.md` |
| RESEARCH-0002 | TradingX local control web app research | 1.0.0 | active | `specs/002-local-control-web-app/research.md` |
| RESEARCH-0003 | TradingX operator platform research | 1.0.0 | active | `specs/003-operator-platform/research.md` |
| RESEARCH-0004 | TradingX Gate 3 operations and evidence research | 1.0.0 | active | `specs/004-gate3-operations-evidence/research.md` |
| RESEARCH-0005 | TradingX replay-slippage evidence research | 1.0.0 | active | `specs/005-replay-slippage-evidence/research.md` |
| RESEARCH-0006 | TradingX market-day automation research | 1.0.0 | active | `specs/006-market-day-automation/research.md` |
| RESEARCH-0007 | TradingX recurring market-day scheduler research | 1.0.0 | active | `specs/007-market-day-scheduler/research.md` |
| RESEARCH-0008 | TradingX local trading appliance research | 1.0.0 | active | `specs/008-local-trading-appliance/research.md` |
| RESEARCH-0009 | TradingX week-1 dry-run controls research | 1.0.0 | active | `specs/009-week1-dry-run-controls/research.md` |
| RESEARCH-0010 | TradingX operator control plane research | 1.0.0 | active | `specs/010-operator-control-plane/research.md` |

### Data models

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| DATAMODEL-0001 | TradingX Stage 1 planning data model | 1.0.0 | active | `specs/001-paper-trading-bot/data-model.md` |
| DATAMODEL-0002 | TradingX local control web app data model | 1.0.0 | active | `specs/002-local-control-web-app/data-model.md` |
| DATAMODEL-0003 | TradingX operator platform data model | 1.0.0 | active | `specs/003-operator-platform/data-model.md` |
| DATAMODEL-0004 | TradingX Gate 3 operations and evidence data model | 1.0.0 | active | `specs/004-gate3-operations-evidence/data-model.md` |
| DATAMODEL-0005 | TradingX replay-slippage evidence data model | 1.0.0 | active | `specs/005-replay-slippage-evidence/data-model.md` |
| DATAMODEL-0006 | TradingX market-day automation data model | 1.0.0 | active | `specs/006-market-day-automation/data-model.md` |
| DATAMODEL-0007 | TradingX recurring market-day scheduler data model | 1.0.0 | active | `specs/007-market-day-scheduler/data-model.md` |
| DATAMODEL-0008 | TradingX local trading appliance data model | 1.0.0 | active | `specs/008-local-trading-appliance/data-model.md` |
| DATAMODEL-0009 | TradingX week-1 dry-run controls data model | 1.0.0 | active | `specs/009-week1-dry-run-controls/data-model.md` |
| DATAMODEL-0010 | TradingX operator control plane data model | 1.0.0 | active | `specs/010-operator-control-plane/data-model.md` |

### Quickstarts

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| QUICKSTART-0001 | TradingX Stage 1 planning quickstart | 1.0.0 | active | `specs/001-paper-trading-bot/quickstart.md` |
| QUICKSTART-0003 | TradingX local control web app quickstart | 1.0.0 | active | `specs/002-local-control-web-app/quickstart.md` |
| QUICKSTART-0004 | TradingX operator platform quickstart | 1.0.0 | active | `specs/003-operator-platform/quickstart.md` |
| QUICKSTART-0005 | TradingX Gate 3 operations and evidence quickstart | 1.0.0 | active | `specs/004-gate3-operations-evidence/quickstart.md` |
| QUICKSTART-0006 | TradingX replay-slippage evidence quickstart | 1.0.0 | active | `specs/005-replay-slippage-evidence/quickstart.md` |
| QUICKSTART-0007 | TradingX market-day automation quickstart | 1.0.0 | active | `specs/006-market-day-automation/quickstart.md` |
| QUICKSTART-0008 | TradingX recurring market-day scheduler quickstart | 1.0.0 | active | `specs/007-market-day-scheduler/quickstart.md` |
| QUICKSTART-0009 | TradingX local trading appliance quickstart | 1.0.0 | active | `specs/008-local-trading-appliance/quickstart.md` |
| QUICKSTART-0010 | TradingX week-1 dry-run controls quickstart | 1.0.0 | active | `specs/009-week1-dry-run-controls/quickstart.md` |
| QUICKSTART-0011 | TradingX operator control plane quickstart | 1.0.0 | active | `specs/010-operator-control-plane/quickstart.md` |

### Contracts (CONTRACT-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| CONTRACT-0001 | Trading loop contract | 1.0.0 | active | `specs/001-paper-trading-bot/contracts/trading_loop.md` |
| CONTRACT-0002 | Operator alerts and evidence contract | 1.0.0 | active | `specs/001-paper-trading-bot/contracts/operator_evidence.md` |
| CONTRACT-0003 | Local control web app API contract | 1.0.0 | active | `specs/002-local-control-web-app/contracts/web_app_api.md` |
| CONTRACT-0004 | Operator platform API contract | 1.0.0 | active | `specs/003-operator-platform/contracts/operator_platform_api.md` |
| CONTRACT-0005 | Gate 3 operations and evidence API contract | 1.0.0 | active | `specs/004-gate3-operations-evidence/contracts/gate3_operations_api.md` |
| CONTRACT-0006 | Replay slippage API contract | 1.0.0 | active | `specs/005-replay-slippage-evidence/contracts/replay_slippage_api.md` |
| CONTRACT-0007 | Market-day automation API contract | 1.0.0 | active | `specs/006-market-day-automation/contracts/market_day_automation_api.md` |
| CONTRACT-0008 | Market-day scheduler API contract | 1.0.0 | active | `specs/007-market-day-scheduler/contracts/market_day_scheduler_api.md` |
| CONTRACT-0009 | Local trading appliance API contract | 1.0.0 | active | `specs/008-local-trading-appliance/contracts/local_trading_appliance_api.md` |
| CONTRACT-0010 | Week-1 dry-run controls contract | 1.0.0 | active | `specs/009-week1-dry-run-controls/contracts/week1_dry_run_controls.md` |
| CONTRACT-0011 | Operator control plane contract | 1.0.0 | active | `specs/010-operator-control-plane/contracts/operator_control_plane.md` |

### Validation gate definitions

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| GATES-0001 | Stage 1 acceptance gates | 1.3.1 | active | `docs/validation/acceptance_gates.md` |

### Session handovers (SESS-*)

Session handovers live in `docs/handover/SESSIONS/` and are indexed
by filename. Because they are produced on every session and would
otherwise dominate this table, they are tracked **by convention**
rather than by per-session INDEX rows:

- Every session handover file MUST carry YAML front-matter per
  Principle VIII (including both `status` and `session_status`
  fields). The front-matter IS the ground truth for the artifact,
  as it is for every other artifact.
- This INDEX tracks the AGGREGATE state of the session-handover
  collection, not each individual session. The aggregate row
  below is updated whenever the active session changes or when a
  previously-open session is closed.
- To find a specific session handover, sort files in
  `docs/handover/SESSIONS/` by filename (they are time-ordered by
  session ID) and open the one you need.
- This is a documented exception to the "INDEX lists every
  versioned artifact" rule. Rationale: a long-running project will
  accumulate thousands of session handovers; per-row listing would
  make INDEX unreadable and force merge conflicts on every session
  close. The aggregate-row approach preserves Principle VIII's
  intent (discoverability, ground-truth front-matter) without the
  scaling problem.

| id pattern  | description            | count (current) | latest active          | path                            |
| ----------- | ---------------------- | --------------- | ---------------------- | ------------------------------- |
| SESS-*      | Session handovers      | 28              | SESS-2026-04-19-028    | `docs/handover/SESSIONS/`       |

### Recovery records (RECOVERY-NNNN)

Recovery records are produced by the session_recovery runbook when
a session is abandoned. They ARE tracked per-row in this INDEX
because they are rare and individually significant (each one
documents an incident).

| id              | title | version | status | path |
| --------------- | ----- | ------- | ------ | ---- |
| _(none yet)_    |       |         |        |      |

### Configuration schemas

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| _(none yet — Phase 3 will add schemas for capital, broker, risk)_ |

### Validation reports (VALIDATION-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| _(none yet — Phase 9 will add the Gate-1 and Gate-2 validation reports)_ |

### ADR templates

| id                  | title                       | version | status | path                                              |
| ------------------- | --------------------------- | ------- | ------ | ------------------------------------------------- |
| ADRTPL-0001         | Strategy evaluation ADR template | 1.0.0 | active | `docs/adrs/templates/strategy_evaluation.md`      |

## Pre-repository supersession history (historical only)

The constitution and the brief were iterated through several versions
BEFORE this repository existed (during the design-and-review process
conducted entirely in pre-Phase-0 chat sessions). Those pre-repo
versions were never committed to this repository and are not retained
here. This is not a violation of the constitution's "superseded
documents stay in the repository" rule — that rule applies to
artifacts that existed in the repo and were subsequently superseded.
Pre-repository drafts are out of scope.

The pre-repository chain for reference only:

- CONST-0001: 1.0.0 → 2.0.0 → 2.1.0 → 2.2.0 → 2.2.1 → 3.0.0 → 3.0.1 (live).
  Only 3.0.1 lives in this repo.
- BRIEF-0001: 2.2.x → 3.0.0 (live). Only 3.0.0 lives in this repo.
- INDEX-0001: 1.0.0 → 1.1.0 → 1.2.0 → 1.2.1 (live). Only 1.2.1 lives in
  this repo.
- RUNBOOK-0001 (session recovery): 1.0.0 → 1.1.0 → 1.1.1 (live). Only
  1.1.1 lives in this repo.
- RUNBOOK-0002 (bootstrap install): 1.0.0 → 1.0.1 (live). Only 1.0.1
  lives in this repo.

## In-repository supersession rule (going forward)

From this commit onward, any artifact that is superseded WITHIN the
repository's history MUST have its superseded version retained as a
readable file alongside the active version, per constitution
Principle VIII rule #2. The repository becomes the source of truth
for the full supersession chain starting now.
