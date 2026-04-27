# Wave 2 Mandate And Allocation Governance Rereview Report

Fresh adversarial rereview after fixes, using `docs/roadmap/tradingx_quant_hardening_execution_plan.md`, current repository state, `git status`, `git diff`, relevant source, schemas, fixtures, tests, validation output, `docs/reports/wave2_mandate_allocation_implementation_report.md`, `docs/reports/wave2_mandate_allocation_fix_report.md`, and `docs/reports/wave2_mandate_allocation_review_report.md`.

Committee lens applied: principal software architect, senior coding engineer, quality engineer, quantitative finance reviewer, mathematician, statistician, and scientific validation reviewer.

Relevant validation observed during this rereview:

- `git status --short` shows Wave 2 source/schema/test/report changes are uncommitted, with `tests/fixtures/mandate/` present as an untracked fixture tree.
- Focused fix-claim tests passed locally: `14 passed in 2.52s`.
- Expanded Wave 2 promotion/CLI/reporting/blocker/portfolio slice passed locally: `113 passed in 7.17s`.
- CLI default bundle: `promotion-check --strategy-id trend-following-v1 --format json` returns `max_state: "research_only"` with mandate blockers `utility_definition_missing`, `tax_account_financing_unspecified`, `jurisdiction_account_use_unknown`, `instrument_package_missing`, and `strategy_materiality_policy_missing`.
- CLI fixture bundle `tests/fixtures/mandate/external_capital_unknown` returns `max_state: "disabled"` with `external_capital_compliance_unknown`.
- CLI fixture bundle `tests/fixtures/mandate/valid` returns `max_state: "paper_shadow"` with no blockers.
- Fixture enumeration via `evaluate_promotion_manifest` produced expected blockers for the checked-in `tests/fixtures/mandate/*` cases, including `wrong_payload_hash`, `missing_replay_input`, `inactive_role`, `research_only_role`, `invalid_lower_bound_spec`, `allocation_limit_exceeded`, and `net_edge_below_threshold`.

Previous finding verification summary:

- `W2-R1`: partially fixed for wrong payload hash, wrong ledger sequence, non-existent approval ref, missing replay ref, and wrong authority ref. Not fully fixed because empty mandate approval lists are still accepted.
- `W2-R2`: fixed for taxable live/probe/production paths covered by the added tests. A separate general expected-wealth blocker remains as `W2-R7`.
- `W2-R3`: fixed for single signed mandate artifacts. Not fully fixed because semantic checks can be driven by earlier unverified duplicate artifacts instead of verified mandate artifacts.
- `W2-R4`: fixed for promotion decision `target_weights` checks and optional portfolio hooks. Not fully fixed for runtime portfolio construction because allocation limits remain optional and are not supplied by live construction call sites.
- `W2-R5`: fixed for the single-artifact invalid lower-bound spec cases covered by the added tests.
- `W2-R6`: fixed at the fixture-package level. `tests/fixtures/mandate/` now contains replayable manifest, trust root, CAS, replay, approval, and ledger records.

## Finding W2-R1

Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, Wave 2 mandate schemas, `tests/unit/test_promotion.py`

Roadmap requirement involved: Milestone 0 artifacts must include `approval_record_refs` and fields are insufficient unless backed by the signed append-only authority model (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:294-303`). Wave 2 exit requires mandate artifacts to be authority-bearing and ledger referenced (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2366-2369`).

Exact issue: A mandate artifact with `approval_record_refs: []` is accepted as authority-bearing. The verifier iterates approval refs but never requires the list to be non-empty, and the local schema validator does not support or enforce `minItems`. A production promotion can pass with every Wave 2 mandate artifact carrying zero mandate-artifact approvals.

Evidence from code, diff, tests, or validation output: `_verify_mandate_artifact_authority` checks replay refs, payload hash, ledger sequence, and authority ref, then loops over `_string_sequence(payload.get("approval_record_refs", ()))` without a non-empty check (`src/tradingx/promotion.py:1319-1360`). The schemas type `approval_record_refs` as an array only, with no `minItems` (`schemas/quant/investment_mandate.schema.json:51-56`, same pattern across the new mandate schemas). The repository schema validator supports only a small keyword set and not `minItems` (`src/tradingx/authority.py:166-178`, `src/tradingx/authority.py:257-263`). The fix tests cover a non-existent approval ref, not an empty approval list (`tests/unit/test_promotion.py:725-753`). Local adversarial probe built a production bundle where all mandate artifacts had `approval_record_refs: []`; `load_promotion_decision` returned `production ()`.

Why it matters: Mandate approval can be removed entirely while preserving the semantic mandate payload hash, allowing capital-bearing production authority without any signed approval for the mandate artifacts themselves.

Required fix: Explicitly reject empty `approval_record_refs` for every mandate artifact before the approval loop. Also require non-empty `operator_identity_ref`, `role_registry_ref`, and `authority_boundary_ref` for mandate approval records, matching the stricter promotion-decision approval checks. Consider adding schema support for `minItems` or keeping this as semantic validation if the schema subset stays intentionally small.

Required test or validation to prove the fix: Add fixture and helper-driven tests where each mandate artifact kind has `approval_record_refs: []`; each case must produce `authority_artifact_invalid` and cap below any capital-bearing state. Add tests with empty approval identity, role registry, and authority boundary fields for mandate approvals.

## Finding W2-R3

Severity: high

Affected file or component: `src/tradingx/promotion.py`, mandate semantic evaluation

Roadmap requirement involved: `strategy_capital_role` includes `research_only` and `inactive` roles (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:315`). Wave 2 requires capital role, benchmark policy, jurisdiction/account-use status, instrument-package status, and materiality-policy blockers (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2334-2337`). Capital-bearing promotion cannot pass without mandate artifacts, and those artifacts must be authority-bearing (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2366-2369`).

Exact issue: Semantic blockers are evaluated from the first artifact of a kind in `artifact_refs`, not from the authority-verified mandate artifact. A non-authority duplicate can therefore mask a stricter signed mandate artifact of the same kind. The concrete tested bypass is an unsigned `strategy_capital_role` with `growth_candidate` placed before a signed `strategy_capital_role` with `research_only`; production is allowed with no blockers.

Evidence from code, diff, tests, or validation output: `_mandate_authority_status` returns only `valid_kinds`, not a verified payload map (`src/tradingx/promotion.py:1266-1306`). `_first_strategy_artifact` returns the first payload matching kind and strategy, regardless of authority verification (`src/tradingx/promotion.py:1538-1549`). `_append_mandate_semantic_blockers` reads capital role and benchmark semantics through `_first_strategy_artifact` (`src/tradingx/promotion.py:1678-1707`). The generic content-addressed artifact schema allows `kind`, `strategy_id`, and `capital_role`, so a non-authority role artifact is schema-valid (`schemas/quant/content_addressed_artifact.schema.json:6-23`). Local adversarial probe inserted an unsigned `strategy_capital_role: growth_candidate` before a signed `strategy_capital_role: research_only`; `load_promotion_decision` returned `production ()`.

Why it matters: Signed mandate constraints are not authoritative if an earlier stale or unsigned duplicate can drive semantic evaluation. This can authorize production for a strategy whose signed mandate role explicitly caps it at research-only.

Required fix: Have `_mandate_authority_status` return the verified mandate payloads by kind, not only kind names. Semantic evaluators must read only verified mandate payloads. Reject duplicate mandate artifacts for the same `(strategy_id, kind)` unless there is an explicit versioning and supersession rule; if duplicates are allowed, combine them with strictest-cap semantics and reject conflicts.

Required test or validation to prove the fix: Add adversarial fixtures with an unsigned duplicate before a signed `research_only` or `inactive` capital role, a permissive duplicate before signed low promotion ceilings, and conflicting duplicate signed artifacts. Each must fail closed or apply the strictest signed mandate cap.

## Finding W2-R4

Severity: high

Affected file or component: `src/tradingx/portfolio/blueprint.py`, `src/tradingx/portfolio/construction.py`, `src/tradingx/portfolio/live_construction.py`, runtime portfolio construction

Roadmap requirement involved: `capital_allocation_policy` defines initial allocation, max strategy/sleeve allocation, scale-up/down rules, cooldowns, and repeated-look controls (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:319`). Wave 2 write scope includes portfolio blueprint and construction (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2317-2319`). Prior W2-R4 required portfolio construction to refuse or clamp only through an auditable blocker-backed authority decision.

Exact issue: Allocation limits are optional hooks, not enforced by runtime construction. Promotion `target_weights` now checks allocation policy, but portfolio construction accepts an empty default `allocation_limits=()` and live construction does not pass allocation limits at all. Therefore a runtime portfolio path can still build weights from an over-budget blueprint unless the caller manually supplies limits.

Evidence from code, diff, tests, or validation output: `build_portfolio_target_weight_history` has `allocation_limits: tuple[StrategyAllocationLimit, ...] = ()` and validates only the supplied optional tuple (`src/tradingx/portfolio/construction.py:31-44`). `_combine_sleeve_weights` also defaults to `allocation_limits=()` (`src/tradingx/portfolio/construction.py:152-161`). The live cycle path calls `_combine_sleeve_weights` without allocation limits (`src/tradingx/portfolio/live_construction.py:61-64`). `rg` over source found no production call site that passes non-empty `allocation_limits`. The tests prove only the manually supplied hook path (`tests/unit/test_portfolio_blueprint.py:76-104`, `tests/unit/test_portfolio_construction.py:243-266`).

Why it matters: A signed mandate may cap a strategy at 5%, but a live/runtime blueprint with a 10% budget can still flow through construction if no caller remembers to pass the optional limit tuple. That leaves capital allocation authority unenforced at the runtime boundary.

Required fix: Plumb signed allocation limits from the promotion/mandate authority bundle into activation and runtime portfolio construction, or make allocation limits a required parameter for authority-gated portfolio construction paths. Live construction should fail closed when a strategy has a signed allocation policy but no verified allocation limit is supplied.

Required test or validation to prove the fix: Add an integration test through the live/runtime portfolio construction path with a signed `capital_allocation_policy.max_strategy_allocation=0.05` and a blueprint budget above 0.05; it must fail without relying on a test-only manually passed `allocation_limits` argument. Add a passing test for a budget at or below the signed limit.

## Finding W2-R7

Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, expected-wealth evaluation

Roadmap requirement involved: Capital-bearing promotion or capital increase requires lower-bound net edge above a predeclared threshold after costs, slippage, financing, relevant taxes, capacity stress, and benchmark comparison (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:331-344`). Enforcement blocks include `net edge lower bound below threshold for capital-bearing promotion` (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:464-471`). Acceptance criteria require positive EV to be lower-bound based, not point-estimate based (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:477-490`).

Exact issue: Expected-wealth evidence is required only when the investment mandate says `taxable_or_tax_exempt_status == "taxable"`. Non-taxable or tax-exempt capital-bearing production can pass with no `lower_bound_net_edge_report` at all.

Evidence from code, diff, tests, or validation output: `_expected_wealth_blocker` returns `None` when the requested state is below live, when the mandate hard-caps below live, when the mandate is missing, and then also returns `None` for any mandate whose taxable status is not exactly `taxable` (`src/tradingx/promotion.py:1847-1865`). The added W2-R2 tests cover taxable missing/pre-tax/below-threshold cases only (`tests/unit/test_promotion.py:789-861`). Local adversarial probe changed the mandate to tax-exempt, omitted `lower_bound_net_edge_report`, requested production, and `load_promotion_decision` returned `production ()`.

Why it matters: The general expected-wealth rule is the economic core of Wave 2. A non-taxable account still needs lower-bound positive edge after costs, financing, capacity stress, and benchmark comparison. The current branch allows production with no edge evidence merely because after-tax evidence is not required.

Required fix: Require lower-bound net edge evidence for all capital-bearing live/probe/production promotion. Use taxable status only to decide whether that evidence must be after-tax. For tax-exempt or non-taxable mandates, still require cost, slippage, financing where applicable, capacity stress, benchmark pairing, estimator/confidence metadata, pass threshold, and `lower_bound_net_edge >=` or `>` the declared pass rule as specified.

Required test or validation to prove the fix: Add tests for tax-exempt and tax-deferred production with no lower-bound report, pre-cost/pre-capacity reports, and below-threshold reports; all must cap below capital-bearing use with `lower_bound_net_edge_undefined` or `net_edge_lower_bound_below_threshold`. Add a positive non-taxable case with complete lower-bound evidence.
