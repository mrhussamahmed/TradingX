---
id: ADR-0017
title: Use policy snapshots and an append-only SQLite journal for week-1 dry-run safety
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# ADR-0017: Use policy snapshots and an append-only SQLite journal for week-1 dry-run safety

## Context

The supervised local trading appliance in `ADR-0016` tightened startup,
activation, warmup, and deterministic opportunity selection, but it
still leaves week-1 paper operations too permissive:

- execution policy is spread across code instead of one stamped artifact
- order submission is not driven by an append-only journal
- `client_order_id` is not deterministic enough for replay-safe retries
- reconciliation is too shallow and too optimistic for unsupervised
  restart safety
- Monday dry-run and Tuesday go-live gates are not first-class runtime
  concepts

The operator needs a boring, operator-first week-1 control plane that
can run on Monday, 2026-04-20 in `dry_run`, accumulate auditable
evidence, and refuse Tuesday submission unless explicit gates pass.

## Decision

Adopt a week-1 safety control plane with:

- a stamped `PolicySnapshot` artifact for every session
- a versioned `DecisionSnapshot` v1 persisted before any OMS submit
- an append-only SQLite journal in WAL mode as the OMS source of truth
- deterministic `client_order_id` generation from the decision snapshot
  and retry sequence
- two-tier reconciliation with explicit `recovery_required` flow
- a hard Monday `dry_run` posture and explicit Tuesday go-live gates

## Consequences

### Positive

- Entry caps, close ladder, halt rules, and dry-run posture become
  explicit runtime data instead of hidden code branches.
- OMS retries become idempotent and auditable.
- Reconciliation can compare broker truth, journal truth, and derived
  state without mutating history.
- Monday and Tuesday readiness become artifact-backed operational gates.

### Negative

- SQLite journal management, locking, and snapshot persistence add new
  implementation complexity.
- Existing JSON artifact flows must integrate with the journal without
  losing current evidence visibility.
- The hot path remains Python-based and therefore still relies on
  careful latency budgeting rather than a lower-level execution kernel.

## Alternatives considered

- Keep the JSON artifact store as the only order/evidence record.
  Rejected because it cannot enforce append-only OMS semantics or robust
  idempotent retry behavior.
- Delay the policy snapshot until research and governance are more
  mature. Rejected because week-1 safety depends on explicit caps and
  halts now, not later.
