# TradingX Quant Hardening Execution Tracker

Source roadmap: `docs/roadmap/tradingx_quant_hardening_execution_plan.md`

Base branch observed at start: `main`

Base commit observed at start: `71ab9c19afa077cdd83dc27742ae67de5f25159f`

Pre-existing working-tree changes observed before implementation:

- `docs/roadmap/tradingx_quant_hardening_execution_plan.md` was already modified.
- This tracker treats the current working-tree roadmap as the source of truth and does not require staging the roadmap file.

Model visibility:

- Main Codex model: exact runtime model is not exposed by the local tool interface beyond GPT-5-based Codex session context.
- Reviewer subagent model: the subagent interface exposes `gpt-5.5` as the strongest listed model override, with `xhigh` reasoning available.
- Reviewer forcing: reviewer subagents will be spawned with `model="gpt-5.5"` and `reasoning_effort="xhigh"` unless tool output shows this is unavailable.
- Limitation: the tool interface does not provide a post-launch runtime model attestation for subagents; any visible downgrade will stop execution.

## Wave Tracker

| Wave | Name | Status | Implementation Report | Review Report | Fix Report(s) | Handoff | Validation Commands | Final Result |
|---|---|---|---|---|---|---|---|---|
| 0 | Plan Anchoring And Baseline Audit | completed | `docs/reports/wave0_baseline_audit_implementation_report.md` | `docs/reports/wave0_baseline_audit_review_report.md`; `docs/reports/wave0_baseline_audit_rereview_report.md`; `docs/reports/wave0_baseline_audit_final_review_report.md` | `docs/reports/wave0_baseline_audit_fix_report.md` | `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`; `docs/reports/wave0_baseline_audit_handoff.md` | `uv run pytest tests/unit/test_activation.py tests/unit/test_live_enablement.py tests/unit/test_risk.py tests/unit/test_pbo_compute.py`; `uv run pytest tests/unit/test_controlplane_repository_contracts.py tests/unit/test_controlplane_runtime_projector.py`; `uv run mypy src/tradingx`; `uv run ruff check .`; `git status --short --branch --untracked-files=all`; `rg -n -e StructuredRuntimeLogger -e "def write_" -e write_validation_report -e write_evaluation_evidence -e write_pbo_report -e write_gate_assessment src/tradingx`; `rg -n -e generate_gate_report -e generate_decision_report -e generate_gate3_report -e generate_gate3_package -e generate_replay_slippage_report -e evidence-report -e decision-report -e gate-report -e gate3-report -e gate3-package -e replay-slippage-report -e dry-run-report -e gates-0001-status -e live-disable-status -e runtime-plan src/tradingx/web/runtime.py src/tradingx/web/app.py src/tradingx/__main__.py`; `rg -n -e sharpe -e cagr -e max_drawdown -e forecast_metrics -e backtest_metrics -e recommendation -e write_text -e "print\\(json" src/tradingx scripts`; `uv run python docs/reports/check_wave0_inventory.py --output docs/reports/wave0_inventory_checker_output.md`; `test -f docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md` | Completed; third review findings fixed; review loop cap reached |
| 1 | Governance Spine First Slice | pending | `docs/reports/wave1_governance_spine_implementation_report.md` | `docs/reports/wave1_governance_spine_review_report.md` | TBD | `docs/reports/wave1_governance_spine_handoff.md` | Wave-specific tests; selected integration tests; `uv run ruff check .`; `uv run black --check .`; `uv run mypy src/tradingx` | Pending |
| 2 | Mandate And Allocation Governance | pending | `docs/reports/wave2_mandate_allocation_implementation_report.md` | `docs/reports/wave2_mandate_allocation_review_report.md` | TBD | `docs/reports/wave2_mandate_allocation_handoff.md` | Wave-specific tests; relevant regression tests; static analysis | Pending |
| 3 | Experiment Registration And Data Provenance | pending | `docs/reports/wave3_experiment_data_provenance_implementation_report.md` | `docs/reports/wave3_experiment_data_provenance_review_report.md` | TBD | `docs/reports/wave3_experiment_data_provenance_handoff.md` | Wave-specific tests; relevant validation/PBO/web regressions; static analysis | Pending |
| 4 | Statistical Evidence Engine | pending | `docs/reports/wave4_statistical_evidence_engine_implementation_report.md` | `docs/reports/wave4_statistical_evidence_engine_review_report.md` | TBD | `docs/reports/wave4_statistical_evidence_engine_handoff.md` | Wave-specific tests; validation/PBO regressions; static analysis | Pending |
| 5 | Cost, Quote Quality, And Capacity | pending | `docs/reports/wave5_cost_quote_capacity_implementation_report.md` | `docs/reports/wave5_cost_quote_capacity_review_report.md` | TBD | `docs/reports/wave5_cost_quote_capacity_handoff.md` | Wave-specific tests; execution/cost/backtest regressions; static analysis | Pending |
| 6 | Portfolio Utility, Optimizer, Forecasts, And Sizing | pending | `docs/reports/wave6_portfolio_optimizer_forecast_sizing_implementation_report.md` | `docs/reports/wave6_portfolio_optimizer_forecast_sizing_review_report.md` | TBD | `docs/reports/wave6_portfolio_optimizer_forecast_sizing_handoff.md` | Wave-specific tests; portfolio/sizing/evaluation regressions; static analysis | Pending |
| 7 | Short-Side Capability And Financing | pending | `docs/reports/wave7_short_side_financing_implementation_report.md` | `docs/reports/wave7_short_side_financing_review_report.md` | TBD | `docs/reports/wave7_short_side_financing_handoff.md` | Wave-specific tests; risk/execution/runtime regressions; static analysis | Pending |
| 8 | Live Probe And Operational Safety | pending | `docs/reports/wave8_live_probe_operational_safety_implementation_report.md` | `docs/reports/wave8_live_probe_operational_safety_review_report.md` | TBD | `docs/reports/wave8_live_probe_operational_safety_handoff.md` | Wave-specific tests; live enablement/risk/execution regressions; static analysis | Pending |
| 9 | Recertification And Change Control | pending | `docs/reports/wave9_recertification_change_control_implementation_report.md` | `docs/reports/wave9_recertification_change_control_review_report.md` | TBD | `docs/reports/wave9_recertification_change_control_handoff.md` | Wave-specific tests; activation/runtime validation regressions; static analysis | Pending |
| 10 | Legacy Path Retirement And Hardening | pending | `docs/reports/wave10_legacy_retirement_hardening_implementation_report.md` | `docs/reports/wave10_legacy_retirement_hardening_review_report.md` | TBD | `docs/reports/wave10_legacy_retirement_hardening_handoff.md` | Wave-specific tests; legacy bypass regression tests; static analysis; `./scripts/validate` if environment permits | Pending |
| Final | Integrated Review And Merge Readiness | pending | `docs/reports/tradingx_quant_hardening_final_summary.md` | `docs/reports/tradingx_quant_hardening_final_integrated_review.md` | TBD | Not applicable | Full regression and static analysis; final reviewer-requested checks | Pending |

## Review Rule

Every adversarial review must be performed in a separate reviewer subagent/thread where the tool interface supports it. The reviewer must reconstruct findings from repository files, git status, git diff, tests, validation output, roadmap sections, saved implementation reports, and saved review reports. The implementation report is only a checklist of claims to verify, not proof.

User update on 2026-04-26: fresh adversarial review loops are capped at three iterations per wave. If the third review still produces findings, fix and validate those findings deterministically, document that the review cap was reached, and do not spawn a fourth reviewer for that wave.

## Commit Rule

Create one local commit per completed wave, staging only files changed for that wave. Do not push or merge without explicit approval.
