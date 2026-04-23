---
id: ADR-0024
title: Activate Gate 1 PBO from CPCV cohort readiness
version: 1.0.0
status: active
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: gpt-5-codex-2026-04-23
---

# ADR-0024: Activate Gate 1 PBO from CPCV cohort readiness

## Status

Accepted on 2026-04-23. This ADR becomes operational with the Gate 1
PBO activation implementation that lands alongside it.

## Context

- [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
  and [DESIGN-0018](/docs/superpowers/specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md)
  reserved PBO as a tranche 2 hard gate, but Stage 1 intentionally
  stopped at CPCV record accrual and standalone PBO computation.
- Stage 1 already writes CPCV trial records from the Gate 1 controller,
  and the repository now has the persistence/model seams needed to turn
  PBO into a real validation criterion without reopening that plumbing.
- The activation still needs a readiness boundary so a clean new cohort
  does not fail only because CPCV history is immature.
- The current Gate 1 batch shape still includes the non-sleeve baseline
  candidate, so evaluation-level PBO activation must decide how that
  batch receives the criterion.

## Decision

1. Gate 1 now computes **one evaluation-level PBO payload per controller
   run**, not per candidate.
2. `GateValidationController` owns the readiness checks, CPCV record
   loading, `compute_pbo(...)` call, and `PBOReport` write. Validation
   logic remains store-free.
3. PBO activation uses two readiness gates:
   - **Gate 3 readiness:** at least one CPCV cohort has
     `earliest_recorded_at_utc <= now - 182 days`
   - **Gate 4 readiness:** the current evaluation's
     `cohort_window_id` has `strategy_config_count >= 50` and exactly
     45 CPCV paths
4. If readiness is not met, criterion `pbo_overfitting` is
   **`pending`**, not failed.
5. If readiness is met, `compute_pbo(...)` produces a `PBOReport` and
   Gate 1 enforces `PBO <= 0.30` as a hard pass/fail criterion.
6. `MixedCohortWindowError` remains a **hard integrity failure** because
   it indicates corrupted or mis-keyed CPCV records, not a normal low-
   readiness state.
7. The evaluation-level PBO payload is fanned out across the whole Gate
   1 batch, including the current non-sleeve baseline candidate, so the
   registry shape does not leave one candidate permanently `pending`.
8. `ValidationCriterionResult` now supports an explicit tri-state
   `status`:
   - `pass`
   - `fail`
   - `pending`
   Readers must derive the effective status from `passed` when `status`
   is missing or `null`, because legacy payloads serialized through the
   generic persistence path already store `"status": null`.
9. Each Gate 1 run writes a **unique** `PBOReport` artifact. Reruns of
   the same cohort must not overwrite earlier reports.

## Consequences

### Positive

- Gate 1 now has an operational overfitting guard rather than a deferred
  note in documentation.
- The activation preserves the controller/validation boundary: store
  reads and cohort readiness stay in the controller, while validation
  only consumes an optional evaluation-level PBO payload.
- The per-run `PBOReport` artifact gives a concrete audit trail for
  reruns and the first activation event.

### Negative

- Gate 1 now has an explicit tri-state criterion, so downstream
  reporting and legacy payload readers must honor `pending` correctly
  rather than treating every `passed == false` criterion as failed.
- The batch-wide payload means the non-sleeve baseline candidate now
  carries the same PBO criterion as the sleeve-backed candidates. This
  is an implementation convenience tied to the current registry shape,
  not a statement that the baseline itself generated CPCV records.

## Alternatives considered

- **Keep PBO pending until every candidate can own its own CPCV/PBO
  payload.** Rejected because the current Gate 1 batch shape would leave
  the non-sleeve baseline permanently special-cased and reopen Stage 1
  plumbing.
- **Compute/store PBO inside validation.** Rejected because it would
  reintroduce store dependencies into `validation.py`, which the Stage 1
  review explicitly moved out into the controller.
- **Treat readiness misses as hard failures.** Rejected because that
  would block new cohorts for expected maturity reasons instead of
  recording an honest pending state.

## Sources

- [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
- [DESIGN-0018](/docs/superpowers/specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md)
- [2026-04-23 Tranche 2.2 Stage 2 PBO activation plan](/docs/superpowers/plans/2026-04-23-tranche-2-2-stage-2-pbo-activation-plan.md)
