---
id: INDEX-0001
title: Artifact index
version: 1.2.1
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: INDEX-0001@1.2.0
superseded_by: null
author_session: SESS-2026-04-17-002
---

# Artifact index

This file is the registry of every versioned artifact in the
repository. It provides a fast lookup for agents starting a session.
The front-matter on individual artifacts is the ground truth; this
index is the cache. On conflict, front-matter wins and this index
MUST be corrected in the same session that detects the conflict.

## How to read this file

Each row shows the current `active` version of an artifact.
Superseded versions are not listed here; they live in their own
files with `status: superseded` and a `superseded_by` pointer.

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

### State files

| id          | title             | version | status | path                          |
| ----------- | ----------------- | ------- | ------ | ----------------------------- |
| STATE-0001  | Project state     | 1.0.0   | active | `docs/handover/STATE.md`      |
| INDEX-0001  | Artifact index    | 1.2.1   | active | `docs/INDEX.md` (this file)   |

### Architecture decision records (ADR-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| ADR-0001 | Use Python 3.11 as the baseline runtime | 1.0.0 | active | `docs/adrs/ADR-0001-language-python-3.11.md` |
| ADR-0002 | Use uv as the package manager | 1.0.0 | active | `docs/adrs/ADR-0002-package-manager-uv.md` |
| ADR-0003 | Use Alpaca for Stage 1 and Stage 2 brokerage | 1.0.0 | active | `docs/adrs/ADR-0003-broker-alpaca.md` |
| ADR-0004 | Use SPY as the Stage 1 and Stage 2 benchmark | 1.0.0 | active | `docs/adrs/ADR-0004-benchmark-spy.md` |
| ADR-0005 | Preserve sequential Stage 1 through Stage 4 progression | 1.0.0 | active | `docs/adrs/ADR-0005-stage-progression-1-through-4.md` |
| ADR-0006 | Use SMTP email as the default emergency channel | 1.0.0 | active | `docs/adrs/ADR-0006-emergency-channel-smtp.md` |
| ADR-0007 | Restrict Stage 1 and Stage 2 trading to regular market hours | 1.0.0 | active | `docs/adrs/ADR-0007-market-hours-regular-only.md` |
| ADR-0008 | Require a real Alpaca paper round trip in Phase 0 | 1.0.0 | active | `docs/adrs/ADR-0008-walking-skeleton-deliverable.md` |

### Specifications (SPEC-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| _(none yet — Phase 1 will add the first spec via `/speckit.specify`)_ |

### Plans (PLAN-NNNN)

| id       | title | version | status | path |
| -------- | ----- | ------- | ------ | ---- |
| _(none yet — Phase 2 will add the first plan via `/speckit.plan`)_ |

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
| SESS-*      | Session handovers      | 2               | SESS-2026-04-17-002    | `docs/handover/SESSIONS/`       |

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
