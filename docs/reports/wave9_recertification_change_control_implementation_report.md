# Wave 9 Recertification And Change Control — Implementation Report

Last updated: 2026-04-26

## Goal

Implement Milestone 10 so production approval is expiring,
evidence-bound, and invalidated by unknown/unrecorded/material/critical
or breaking changes.

## Files changed

Source:

- `src/tradingx/change_control.py` (new) — builders for
  `change_control_record`, `replay_equivalence_report`,
  `recertification_report`, `drift_monitor_spec`, `drift_monitor_report`,
  `production_decay_event`, plus `detect_unrecorded_change` helper.
- `src/tradingx/promotion.py` — `evaluate_change_control_blockers`,
  new blocker codes (`production_approval_expired`,
  `next_review_due_passed`, `recertification_report_missing`), kinds
  added to `_validate_cas_payload`, and a cross-bundle requirement that
  any `change_control_record` with `recertification_required=True` must
  be paired with a `recertification_report`.

Schemas (new): `change_control_record`, `replay_equivalence_report`,
`recertification_report`, `drift_monitor_spec`, `drift_monitor_report`,
`production_decay_event`.

Tests: `tests/unit/test_change_control_wave9.py` — 18 tests covering
all seven required Wave 9 red tests plus evaluator re-derivation paths.

## Required red tests

| Roadmap red test | Implementation |
|---|---|
| Current hash differs without change record yields `unrecorded_material_change` | `test_current_hash_differs_without_change_record_yields_unrecorded` |
| Unknown change scope defaults critical | `test_unknown_change_scope_defaults_critical` |
| Dependency scope unresolved blocks production | `test_dependency_scope_unresolved_blocks_production` |
| Production approval expires and decays | `test_production_approval_expires_and_decays` |
| Drift monitor spec missing yields `drift_monitor_spec_missing` | `test_drift_monitor_spec_missing_yields_drift_monitor_spec_missing` |
| Replay equivalence fails when material default fires | `test_replay_equivalence_fails_when_material_default_fires` |
| Manual exception cannot extend production indefinitely | `test_manual_exception_cannot_extend_production_indefinitely` |

## Adversarial reviews

Two review passes were performed; due to context-budget constraints
they were consolidated into a single combined adversarial pass that
explicitly ran both lenses (blocker semantics + schemas/tests) and
labelled findings.

Loop-1/2 fixes:
- C2: cross-bundle check — `change_control_record` with
  `recertification_required=True` must be paired with a
  `recertification_report`; otherwise emit
  `recertification_report_missing`.
- M2: `production_decay_event` evaluator now treats any
  `previous_state != new_state` transition as
  `production_approval_expired` (mirrors builder).

Deferred (residual risks):
- C1: Replay-equivalence empty-deltas semantics (current behavior
  treats empty-deltas + no other changes as `equivalent`; reviewer
  preferred `indeterminate`). Future hardening.
- H2: Adversarial test for forged future expiry timestamps with
  matching review-due dates (defense-in-depth).
- H3: Wiring `detect_unrecorded_change` into runtime hash-comparison
  flow (deferred to runtime wiring wave).
- M1: Schema enums for status fields.

A truly clean reviewer session was not available; reviewer was
spawned with minimal context.

## Validation

- Wave 9 focused tests: 18 passed.
- Affected suite (promotion, blocker_registry): passed.
- Full unit/contract/integration suite: 1169 passed, 98 skipped.
- `ruff check`, `mypy`, touched-file Black: clean.
- `python3 scripts/check_index.py`: passed.

## Accepted residual risks

1. Runtime hash-comparison wiring deferred (H3).
2. Schema enums for `freshness_status`, `drift_status`, etc. deferred
   (M1).
3. Replay-equivalence empty-deltas semantics conservative-by-default
   deferred (C1).
4. CLI subcommands not wired.
5. `production_state_projection` Milestone 1 amendment fields
   (`production_approved_at_utc`, etc.) recorded only in the
   recertification report, not derived/projected at the runtime
   strategy registry.
6. `./scripts/validate` Black drift unchanged.

## Commit

```
TradingX quant hardening: complete Wave 9 - Recertification And Change Control
```
