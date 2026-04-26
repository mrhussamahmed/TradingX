# Wave 2 Mandate And Allocation Governance Final Review Report

Fresh adversarial final re-review after second fixes, using the Wave 2 roadmap, current repository state, git status, git diff, source, schemas, tests, fixtures, validation outputs, implementation/fix reports, and prior review reports.

Committee lens applied: principal software architect, senior coding engineer, quality engineer, quantitative finance reviewer, mathematician, statistician, and scientific validation reviewer.

Validation observed during this review:

- `git status --short` still shows Wave 2 source/schema/test/report changes uncommitted, with `tests/fixtures/mandate/` untracked.
- Focused second-fix tests passed locally: `7 passed in 1.40s`.
- Expanded Wave 2 promotion/CLI/reporting/blocker/portfolio slice passed locally: `123 passed in 11.24s`.
- Default CLI bundle: `promotion-check --strategy-id trend-following-v1 --format json` returns `max_state: "research_only"` with mandate blockers `utility_definition_missing`, `tax_account_financing_unspecified`, `jurisdiction_account_use_unknown`, `instrument_package_missing`, and `strategy_materiality_policy_missing`.
- Fixture enumeration through `evaluate_promotion_manifest` produced expected states/blockers for `valid`, `external_capital_unknown`, `materiality_policy_missing`, `empty_approval_refs`, `unsigned_duplicate_role`, `signed_duplicate_conflict`, `tax_exempt_missing_edge`, `allocation_limit_exceeded`, `ceiling_exceeded`, `inactive_role`, `invalid_lower_bound_spec`, `missing_replay_input`, `net_edge_below_threshold`, `non_ex_ante_benchmark`, `research_only_role`, and `wrong_payload_hash`.

Previous finding verification summary:

- `W2-R1`: fixed for wrong payload hash, wrong ledger sequence, missing/empty mandate approval refs, missing replay refs, wrong authority refs, and empty mandate approval identity fields. Evidence: `src/tradingx/promotion.py:1348-1377`; focused tests passed.
- `W2-R2`: fixed for taxable missing, pre-tax-only, and below-threshold lower-bound evidence cases. Evidence: `tests/unit/test_promotion.py:859-931`; focused tests passed.
- `W2-R3`: fixed for unverified duplicate masking and conflicting signed duplicates. Evidence: `src/tradingx/promotion.py:1280-1308`, `src/tradingx/promotion.py:1667-1707`; focused tests and fixtures passed.
- `W2-R4`: not fully fixed. See `W2-FR1`.
- `W2-R5`: fixed for invalid lower-bound spec semantics. Evidence: `src/tradingx/promotion.py:1773-1816`; fixture `invalid_lower_bound_spec` returns `research_only` with `lower_bound_net_edge_undefined`.
- `W2-R6`: fixed at the fixture-package level. Evidence: `tests/fixtures/mandate/*` now include `manifest.json`, `trust_root.json`, CAS payloads, and ledger records; fixture enumeration replayed successfully.
- `W2-R7`: partially fixed for missing tax-exempt reports and incomplete stress inputs. Not fully fixed for lower-bound evidence completeness. See `W2-FR2`.

## Finding W2-FR1

Severity: high

Affected file or component: `src/tradingx/portfolio/blueprint.py`, `src/tradingx/portfolio/construction.py`, `src/tradingx/portfolio/live_construction.py`, `src/tradingx/runtime_portfolio.py`, activation/runtime allocation governance

Roadmap requirement involved: `capital_allocation_policy` defines initial allocation and max strategy/sleeve allocation (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:319`). Wave 2 write scope includes portfolio blueprint and construction (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2317-2319`). Capital allocation blocks include scale-up/capital allocation controls (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:457-475`).

Exact issue: Runtime allocation enforcement is still optional blueprint metadata, not signed mandate authority. `PortfolioBlueprint.strategy_allocation_limits` defaults to empty, `validate_blueprint_allocation_limits` returns immediately when no limit tuple is present, and runtime portfolio planning calls `build_portfolio_cycle_target_weights` without an explicit signed allocation-limit override. No production code creates `StrategyAllocationLimit` from the verified signed `capital_allocation_policy`.

Evidence from code, diff, tests, or validation output: `PortfolioBlueprint` defaults `strategy_allocation_limits=()` (`src/tradingx/portfolio/blueprint.py:26-37`). `validate_blueprint_allocation_limits` does nothing when the tuple is empty (`src/tradingx/portfolio/blueprint.py:55-61`). The loader treats missing `strategy_allocation_limits` as an empty list (`src/tradingx/portfolio/blueprint.py:113-115`). Runtime planning calls `build_portfolio_cycle_target_weights` without allocation limits (`src/tradingx/runtime_portfolio.py:388-398`). Activation only verifies promotion state/action authority and does not extract allocation limits from mandate artifacts (`src/tradingx/activation.py:257-288`). Source search for `StrategyAllocationLimit(` finds only the blueprint loader and tests, not production mandate-to-runtime plumbing. The added live-construction test proves only the blueprint-embedded limit path (`tests/unit/test_portfolio_live_construction.py:286-323`). Local adversarial probe with a blueprint budget of `0.10` and no blueprint limits returned `{'SPY': Decimal('0.1')}` with no error.

Why it matters: A signed mandate can cap `trend-following-v1` at 5%, but a live runtime blueprint without manually copied optional limits can still build a 10% target. That leaves the runtime boundary dependent on duplicate configuration rather than the signed allocation authority Wave 2 is supposed to enforce.

Required fix: Derive runtime `StrategyAllocationLimit` records from the verified signed `capital_allocation_policy` during promotion/activation, persist or carry those limits with the blueprint activation, and fail closed when an active strategy has signed allocation policy authority but runtime construction has no matching verified limit. Remove reliance on manually duplicated blueprint limit fields as the authority source.

Required test or validation to prove the fix: Add an activation-to-runtime integration test with a signed `capital_allocation_policy.max_strategy_allocation=0.05` and a blueprint budget of `0.10` that omits `strategy_allocation_limits`; runtime construction must fail with `allocation_policy_limit_exceeded`. Add a passing case where the derived signed cap is `0.10` or the blueprint budget is `0.05`.

## Finding W2-FR2

Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, `schemas/quant/content_addressed_artifact.schema.json`, expected-wealth validation

Roadmap requirement involved: Capital-bearing promotion requires lower-bound net edge above the predeclared threshold after costs, slippage, financing, applicable borrow/dividend effects, tax handling, capacity stress, and benchmark comparison (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:331-344`). Acceptance requires positive EV to be lower-bound based, not point-estimate based (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:477-490`).

Exact issue: A `lower_bound_net_edge_report` can authorize production without binding the reported lower bound to benchmark pairing, estimator family, confidence/posterior level, tax-status consistency, slippage, or the predeclared lower-bound spec. The evaluator only checks that a report exists, taxable accounts say `after_tax`, stress inputs contain `cost`, `tax`, `financing`, and `capacity`, and `lower_bound_net_edge >= pass_threshold`.

Evidence from code, diff, tests, or validation output: `_expected_wealth_blocker` reads the first `lower_bound_net_edge_report` and checks only `pre_tax_or_after_tax`, a four-item stress-input subset, and decimal threshold comparison (`src/tradingx/promotion.py:1834-1870`). The generic content-addressed artifact schema requires only `schema_version` and `kind`; `estimator_family`, `confidence_level`, `benchmark_pairing`, `stress_inputs`, `lower_bound_net_edge`, and `pass_threshold` are optional properties (`schemas/quant/content_addressed_artifact.schema.json:6-47`). The predeclared spec schema requires benchmark/estimator/confidence metadata (`schemas/quant/lower_bound_net_edge_spec.schema.json:17-26`), but the report is not required to reference or match that spec. Local adversarial probe replaced the report with only `schema_version`, `kind`, `strategy_id`, `pre_tax_or_after_tax`, `stress_inputs`, `lower_bound_net_edge`, and `pass_threshold`; `load_promotion_decision` returned `production ()`.

Why it matters: The economic gate can be satisfied by a bare scalar lower-bound claim. Without report-to-spec binding and benchmark/estimator/confidence/slippage checks, the system cannot tell whether the lower bound was computed with the predeclared method, against the mandated benchmark, after all required frictions, or with statistically valid confidence.

Required fix: Add a dedicated `lower_bound_net_edge_report` schema or semantic validator requiring report-to-spec reference/hash, estimator family, confidence/posterior level, horizon, benchmark pairing, slippage/cost/financing/capacity/tax stress coverage, tax-status consistency with the mandate, sample/effective-sample metadata, and pass/fail threshold. Compare those fields to the verified `lower_bound_net_edge_spec` before allowing live/probe/production.

Required test or validation to prove the fix: Add adversarial tests where a production request has a positive lower-bound scalar but omits benchmark pairing, estimator family, confidence level, spec reference, slippage stress, or tax-status consistency; each must emit `lower_bound_net_edge_undefined` or a stricter blocker. Add a positive fixture where the report references and matches the signed spec and includes all required friction/stress metadata.
