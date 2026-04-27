# Wave 8 Live Probe And Operational Safety — Implementation Report

Last updated: 2026-04-26

## Goal

Implement Milestone 9 so live-probe trading is a bounded operational
experiment with role-bounded approval, fresh safety drills,
broker-timeout state transitions, idempotency, reconciliation, and
post-probe recertification.

## Files changed

Source:

- `src/tradingx/live_probe_governance.py` (new) — builders for
  `authority_boundary`, `pre_trade_control_manifest`,
  `operational_safety_drill`, `live_probe_plan`,
  `live_probe_run_record`, `live_probe_recertification_report`,
  `broker_timeout_state_transition`, `runtime_override_event`,
  `reconciliation_incident`. Includes `_CORE_CONTROL_DISABLE_VERBS` set.
- `src/tradingx/promotion.py` — `evaluate_live_probe_blockers`, new
  blocker codes, cross-bundle `post_probe_recertification_missing` rule
  when run record exists without matching recertification report.

Schemas (new): nine Wave 8 schemas as listed above.

Tests:

- `tests/unit/test_live_probe_governance_wave8.py` — 21 tests covering
  the six artifact-side red tests plus evaluator re-derivation,
  cross-bundle recertification gate, and core-control disable verbs.

## Required red tests

| Roadmap red test | Implementation |
|---|---|
| Missing price collar yields `pre_trade_control_missing` | `test_missing_price_collar_yields_pre_trade_control_missing` |
| Expired live-probe approval blocks live route | `test_expired_live_probe_approval_blocks_live_route` |
| Timeout state cannot retry until reconciliation | `test_timeout_state_cannot_retry_until_reconciliation` |
| No-signal probe is inconclusive unless extension predeclared | `test_no_signal_probe_is_inconclusive_unless_extension_predeclared` |
| Manual exception attempting to disable kill switch is rejected | `test_manual_exception_disabling_kill_switch_is_rejected` |
| Unresolved reconciliation incident blocks production eligibility | `test_unresolved_reconciliation_incident_blocks_production_eligibility` |

The last two roadmap red tests (route authority token at the
risk/execution boundary; bypass via direct `TradingClient`) target
runtime-execution paths and are deferred to a runtime wiring wave.
This is captured as residual risk #1.

## Adversarial reviews

Two loops were run.

- Loop 1 (combined Reviewer A + B): three critical findings — dead
  code (`post_probe_recertification_missing`), `action`-verb override
  bypass, run-record `status="pass"` with `min_activity=false` bypass —
  all fixed. High-priority `status="fail"` no-block, `decimal-string`
  format completeness, schema enums for status fields — partially
  fixed; remainder deferred.
- Loop 2 (fresh reviewer): builder/evaluator drift on
  `live_probe_inconclusive` — fixed (builder now mirrors evaluator).
  Disable-verb list duplication — acknowledged with both inlined; full
  deduplication via shared module export deferred. `second_approver_required`
  now also requires `len(signatures) >= 2`. Cross-bundle `run_refs`
  linkage check, recertification freshness, and verb fuzzy match
  deferred.

A truly clean reviewer session was not available. Reviewers were
spawned with the smallest practical context.

## Validation

- Wave 8 focused tests: 21 passed.
- Affected suite (promotion, blocker_registry): passed.
- Full unit/contract/integration suite: 1151 passed, 98 skipped.
- `ruff check`, `mypy`, touched-file Black: clean.
- `python3 scripts/check_index.py`: passed.

## Accepted residual risks

1. **Runtime-execution red tests deferred.** Roadmap §1644-1666 lists
   two runtime-execution checks (route authority token at the
   risk/execution boundary; direct-`TradingClient` bypass). This wave
   does not modify `src/tradingx/execution.py` /
   `src/tradingx/risk.py` / `src/tradingx/runtime_host.py`. The
   artifact authority surface is in place; runtime wiring is deferred
   to a future operational-hardening wave.
2. **Recertification freshness window absent.** A months-old
   recertification report passes the evaluator. Future enhancement.
3. **Schema enums for status fields deferred.** `minimum_activity_status`,
   `drill_status`, etc. are plain strings. Builder/evaluator both
   interpret them with `_normal_form`, but typos are surface-only.
4. **Disable-verb list duplicated** in `live_probe_governance.py` and
   `promotion.py`. Both are short and explicit; full deduplication
   via shared module export is a future cleanup.
5. **`run_refs` cross-linkage** between run record and recertification
   report not validated.
6. **CLI subcommands not wired.** Roadmap §1649-1657 lists five CLI
   subcommands; builders are ready but the CLI handlers are deferred.
7. **`./scripts/validate` Black drift**: unchanged.

## Commit

```
TradingX quant hardening: complete Wave 8 - Live Probe And Operational Safety
```
