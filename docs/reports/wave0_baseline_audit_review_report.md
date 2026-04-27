# Wave 0 Fresh Adversarial Review Report

## W0-001

- Severity: high
- Affected file or component: `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`
- Roadmap requirement involved: Wave 0 handoff must record exact current branch, commit SHA, repo status, Python version, and validation results.
- Exact issue: The handoff does not record the exact current repository status. It records an initial branch, implementation branch, commit, Python version, and pre-existing dirty roadmap diff, but omits the actual `git status --short --branch` state for the reviewed checkout.
- Evidence: Roadmap lines 2119-2122 require exact current branch and repo status. Handoff lines 5-12 only list `Initial branch observed`, `Implementation branch created`, commit, Python version, and pre-existing roadmap diff. Current `git status --short --branch` is:
  ```text
  ## codex/tradingx-quant-hardening
   M docs/roadmap/tradingx_quant_hardening_execution_plan.md
  ?? docs/reports/
  ?? docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md
  ```
- Why it matters: Wave 0 is the baseline anchor. Without the exact repo status, later reviewers cannot distinguish pre-existing roadmap changes, Wave 0 report files, untracked files, and any accidental worktree drift.
- Required fix: Add a literal current repo-status snapshot to the handoff, including branch and untracked files, preferably from `git status --short --branch --untracked-files=all`.
- Required test or validation to prove the fix: Rerun `git status --short --branch --untracked-files=all` and verify the handoff contains the exact reviewed status.

## W0-002

- Severity: medium
- Affected file or component: `docs/reports/tradingx_quant_hardening_execution_tracker.md`
- Roadmap requirement involved: Execution tracker must list all waves, statuses, report locations, validation commands, and final result.
- Exact issue: The tracker lists the Wave 0 handoff at a non-existent path under `docs/reports/` instead of the actual required handoff under `docs/superpowers/plans/`.
- Evidence: Tracker line 25 lists Wave 0 handoff as `docs/reports/wave0_baseline_audit_handoff.md`. `find docs/reports -maxdepth 1 -type f -print` shows only `tradingx_quant_hardening_execution_tracker.md` and `wave0_baseline_audit_implementation_report.md`. The actual handoff exists at `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`.
- Why it matters: The tracker is supposed to be the orchestration index. A bad handoff location breaks traceability and can cause later waves to review the wrong or missing baseline artifact.
- Required fix: Update the Wave 0 tracker row to point to `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`.
- Required test or validation to prove the fix: Run `test -f docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md` and confirm the tracker references that exact path.

## W0-003

- Severity: high
- Affected file or component: Wave 0 metric/promotion inventory in `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`
- Roadmap requirement involved: Inventory metric-producing and promotion-implying surfaces, including structured logs and artifact writers.
- Exact issue: The handoff omits structured runtime logs and concrete artifact writer surfaces from the required inventory.
- Evidence: Roadmap lines 2127-2130 explicitly require `structured logs` and `artifact writers`. Handoff lines 33-42 list gate-report, controller/reporting/web/readmodels, evidence dataclasses, and `TrialsLedger`, but do not list `StructuredRuntimeLogger` or artifact writers. Code evidence exists: `src/tradingx/runtime_logging.py` lines 31-76 defines `StructuredRuntimeLogger.log(...)` writing JSONL records; `src/tradingx/persistence/__init__.py` lines 82-130 defines `FilesystemArtifactStore` writers for trade intents, orders, risk events, reconciliation, evaluation evidence, gate assessments, service cycles, and runtime plans; lines 307-325 define validation/PBO report writers. `src/tradingx/controller.py` lines 1459-1470 writes evaluation evidence/operator alerts, and lines 1542-1556 writes validation reports and gate assessments.
- Why it matters: These are exactly the surfaces that can leak metrics, imply promotion, or become mistaken for authority in Wave 1. Missing them from the baseline means the next wave can fail to guard or relabel them.
- Required fix: Expand the handoff inventory to explicitly list structured log producers and artifact writer categories, with file paths and whether each is metric-bearing, promotion-implying, operational-only, or legacy/non-authority.
- Required test or validation to prove the fix: Run an inventory command such as `rg -n "StructuredRuntimeLogger|def write_|write_validation_report|write_evaluation_evidence|write_pbo_report|write_gate_assessment" src/tradingx` and verify every relevant surface is represented in the handoff or explicitly marked not applicable.

## W0-004

- Severity: high
- Affected file or component: Wave 0 blocker-like string inventory in `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`
- Roadmap requirement involved: Inventory current blocker-like strings in roadmap, code, tests, fixtures, CLI outputs, and web/report payloads, and record which are missing deterministic caps.
- Exact issue: The blocker-like inventory is incomplete and does not record deterministic-cap status per discovered blocker-like string.
- Evidence: Handoff lines 44-48 list only `missing_requirements`, `unprojected_sources`, `operator_hold`, `requested_mode_unknown`, `dry_run_enabled`, `live_enable_evidence_missing`, `manual_kill_switch_active`, and `market_data_degraded`, plus a generic note about validation/drift. Code contains additional blocker-like strings not listed, including `outbox_dedupe_constraint_missing`, `missing_sources`, `initial_import_incomplete`, `write_path_inactive`, `stale_sources`, `lagging_sources`, `not_ready_sources`, and `blocked` in `src/tradingx/controlplane/projections.py` lines 13-23 and 105-117, 123-128, 230-287. Other omitted blocker-like diagnostics include `insufficient_bars` in `src/tradingx/historical.py` lines 59-62 and sleeve failure reasons such as `halt_by_operator`, `drift_alarm_live`, `sleeve_sharpe_below_threshold_6m`, `regime_stressed`, and `insufficient_history` in `src/tradingx/types.py` lines 337-345.
- Why it matters: Wave 1's blocker registry depends on this baseline. Missing blocker-like strings create a path for unregistered blockers, inconsistent caps, and promotion/reporting behavior outside the deterministic registry.
- Required fix: Replace the narrative blocker note with a table of discovered blocker-like strings, source path, emitting surface, current meaning, whether it has a deterministic V5 cap, and required registry/migration treatment.
- Required test or validation to prove the fix: Run a repeatable inventory command over `docs`, `src`, `tests`, config, and fixtures, then verify each discovered blocker-like string appears in the handoff table or has a documented exclusion reason.
