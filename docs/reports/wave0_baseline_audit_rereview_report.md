# Wave 0 Fresh Adversarial Re-Review Report

## W0-RR-001

- Severity: high
- Affected file or component: `docs/reports/wave0_baseline_audit_fix_report.md`; `docs/reports/tradingx_quant_hardening_execution_tracker.md`
- Roadmap requirement involved: Wave 0 handoff must record validation command results; metric/promotion and blocker inventories must be reviewable from repeatable commands.
- Exact issue: The fix validation commands recorded for W0-003 and W0-004 are not valid inventory commands. They escape regex alternation as `\|`, so the exact commands return no matches while the reports claim they "Produced inventory evidence."
- Evidence: `docs/reports/wave0_baseline_audit_fix_report.md:17-18` and tracker line 25 record `rg` commands using `\|`. Running the exact recorded commands returned exit code 1 with no output. Running the corrected alternation finds relevant surfaces, including `StructuredRuntimeLogger` in `src/tradingx/runtime_logging.py:31`, `write_evaluation_evidence` in `src/tradingx/persistence/__init__.py:100`, `write_validation_report` at line 307, `write_pbo_report` at line 324, and blocker strings in `src/tradingx/controlplane/projections.py:14-22`.
- Why it matters: Wave 0 is the baseline anchor. A false validation trail means later reviewers cannot reproduce the inventory evidence used to close W0-003/W0-004.
- Required fix: Replace the escaped-pipe `rg` commands with valid alternation, or use repeated `-e` patterns, in the fix report and tracker.
- Required test or validation to prove the fix: Rerun the corrected commands and record non-empty output or a saved output artifact showing the matched files and lines.

## W0-RR-002

- Severity: high
- Affected file or component: `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`
- Roadmap requirement involved: Inventory blocker-like strings in roadmap, code, tests, fixtures, CLI outputs, and web/report payloads, and record deterministic-cap status.
- Exact issue: The blocker inventory still omits roadmap-originated blocker codes. It lists current code/test blocker-like strings, but does not enumerate the roadmap's deterministic V5 blockers or provisional registry seed codes.
- Evidence: The roadmap requires roadmap blocker strings to be inventoried at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2131-2133`. It defines deterministic blockers and caps at lines 99-123, including `authority_artifact_invalid`, `ledger_key_worm_controls_missing`, `state_action_contract_missing`, and `drift_monitor_spec_missing`. It also requires Wave 1's first registry seed to include roadmap-named codes at lines 2020-2042, including `capacity_extrapolation_risk`, `unsupported_side`, `short_support_missing`, `pending_threshold`, `legacy_statistical_evidence`, `unsupported_cost_bucket`, `unrecorded_material_change`, and `dependency_scope_unresolved`. The handoff table at lines 81-107 does not include those rows; line 108 only gives a generic note.
- Why it matters: Wave 1's blocker registry is supposed to start from this baseline. Omitting roadmap-named blockers lets the next wave miss required caps or treat known roadmap blockers as newly discovered.
- Required fix: Add rows for every roadmap-defined deterministic and provisional blocker code, including source line/path, current meaning, deterministic cap, and required registry or migration treatment.
- Required test or validation to prove the fix: Run a corrected inventory over `docs/roadmap/tradingx_quant_hardening_execution_plan.md` and the handoff, then verify every roadmap blocker code appears in the handoff table or has an explicit exclusion reason.

## W0-RR-003

- Severity: medium
- Affected file or component: `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`
- Roadmap requirement involved: Inventory current metric-producing and promotion-implying surfaces, including web runtime report generation and artifact writers.
- Exact issue: The metric/promotion inventory omits concrete web runtime report-generation surfaces and several promotion-implying CLI report commands.
- Evidence: The roadmap explicitly includes "web runtime report generation" at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2127-2130`. The handoff table at lines 56-78 lists `/api/actions/gate-report`, web read models, and broad writer categories, but does not list `src/tradingx/web/runtime.py`. Current code has web runtime report generation in `LocalWebActionRunner.generate_gate_report` at `src/tradingx/web/runtime.py:524`, `generate_decision_report` at line 575, `generate_gate3_report` at line 746, `generate_gate3_package` at line 760, and `generate_replay_slippage_report` at line 776. The FastAPI routes expose these at `src/tradingx/web/app.py:1193-1281`. CLI report surfaces also exist in `src/tradingx/__main__.py:187-286` and execute at lines 665-830.
- Why it matters: These are exactly the user-facing paths that can produce or display evidence and promotion-like packages. If Wave 1 relies on the handoff, these surfaces can miss legacy/non-authority labeling or V5 gating.
- Required fix: Add explicit handoff rows for web runtime report generation and report-like CLI commands, classifying each as metric-bearing, promotion-implying, operational-only, or legacy/non-authority.
- Required test or validation to prove the fix: Run a corrected inventory for report-generation methods/routes/commands and verify each matched surface is represented in the handoff.
