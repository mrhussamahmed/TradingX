---
id: CONTRACT-0010
title: Week-1 dry-run controls contract
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Week-1 dry-run controls contract

## Policy and snapshot rules

- Every decision must reference an immutable `policy_snapshot_id`.
- `policy_snapshot_id` changes only at restart.
- Submit without a persisted `DecisionSnapshotV1` is a hard error.
- Hot config reload is forbidden.

## OMS rules

- The SQLite journal is append-only by application logic.
- Journal history is never rewritten during reconciliation.
- Broker state wins for current truth.
- The journal wins for historical truth.
- `client_order_id` is deterministic and retry-sequenced.

## Recovery rules

- `recovery_required` blocks all new entries.
- `/resume` or fallback clearance only requests a new reconciliation.
- Runtime transitions:
  - `recovery_required -> clearance_requested -> reconciling -> nominal`
  - or `recovery_required -> clearance_requested -> reconciling -> recovery_required`

## Week-1 session rules

- Monday is `dry_run`.
- Tuesday is earliest submit date if all go-live gates pass.
- Week 1 is `SPY` only, flat-by-close, and zero overnight.
