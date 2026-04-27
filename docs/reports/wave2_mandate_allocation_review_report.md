# Wave 2 Mandate And Allocation Governance Review Report

Fresh adversarial review based on `docs/roadmap/tradingx_quant_hardening_execution_plan.md`, current repository state, `git status`, `git diff`, source, schemas, tests, fixtures, and `docs/reports/wave2_mandate_allocation_implementation_report.md`.

Relevant validation observed during this review:

- Focused Wave 2 tests run locally: `8 passed in 2.02s`.
- Default `promotion-check --strategy-id trend-following-v1 --format json` returns `max_state: "research_only"` with mandate blockers for the checked-in config bundle.
- An adversarial temp-bundle probe using the Wave 2 test helper produced `production []` for all of these cases: no after-tax lower-bound edge evidence, inactive capital role, `ex_ante: false` benchmark, lower jurisdiction/instrument ceilings, 100% target weight with 5% max allocation, and invalid lower-bound math (`confidence_level: "2"`, negative sample size, empty stress inputs).

## Finding W2-R1

Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, `tests/unit/test_promotion.py`, Wave 2 mandate schemas

Roadmap requirement involved: Milestone 0 artifacts must be authority-bearing with `payload_hash`, `ledger_sequence`, `approval_record_refs`, `authority_ref`, and `replay_input_refs`, and fields are insufficient unless backed by the signed append-only authority model (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:297-303`). Wave 2 exit requires mandate artifacts to be authority-bearing and ledger referenced (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2366-2369`).

Exact issue: Mandate artifacts are treated as authority-bearing when metadata fields are merely present. The evaluator does not verify the artifact's embedded `payload_hash` against the CAS payload, does not verify `ledger_sequence` against the decision ledger record, does not load or verify each mandate artifact's `approval_record_refs`, does not verify `replay_input_refs`, and does not bind `authority_ref` to the trust root or ledger.

Evidence from code, diff, tests, or validation output: `_has_valid_mandate_artifact` returns true when `_has_authority_metadata` returns true (`src/tradingx/promotion.py:1227-1249`). `_append_mandate_blockers` then treats that as satisfying required artifacts (`src/tradingx/promotion.py:1164-1170`). The positive Wave 2 test helper sets every mandate `payload_hash` to `sha256:` plus 64 `a` characters, `approval_record_refs` to a non-existent `sha256:` plus 64 `b` characters, and `replay_input_refs` to a non-existent `sha256:` plus 64 `c` characters (`tests/unit/test_promotion.py:249-258`). The schema-validation test accepts these payloads as valid authority artifacts (`tests/unit/test_promotion.py:830-850`). The implementation report explicitly states the assumption that authority is granted by presence of common metadata plus ledger reference (`docs/reports/wave2_mandate_allocation_implementation_report.md:73-76`).

Why it matters: A forged or stale mandate artifact can satisfy Wave 2 blockers as long as it is referenced by a signed promotion decision. This breaks the authority boundary: the signed decision can launder unapproved, non-replayable mandate content into production.

Required fix: For each mandate artifact referenced by a promotion decision, verify its embedded `payload_hash` equals the canonical hash of the loaded CAS payload or remove redundant embedded hashes in favor of the CAS ref. Verify `ledger_sequence`, `authority_ref`, `approval_record_refs`, and `replay_input_refs` against retained artifacts and signed approvals. Missing or mismatched refs should produce `authority_artifact_invalid` or `replay_path_missing`.

Required test or validation to prove the fix: Add adversarial fixtures where each mandate artifact has a wrong `payload_hash`, wrong `ledger_sequence`, missing approval payload, wrong-scope approval, expired approval, missing replay input, and mismatched `authority_ref`; each must fail below any capital-bearing state. Add one positive artifact-only fixture with real retained mandate approval/replay refs.

## Finding W2-R2

Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, `schemas/quant/lower_bound_net_edge_spec.schema.json`, promotion decision evaluation

Roadmap requirement involved: `after_tax_edge_missing_for_taxable_account` caps taxable capital without after-tax lower-bound net edge evidence at `paper_trading` (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:104`). Taxable production or live-probe capital requires after-tax lower-bound net edge evidence unless hard-capped below live use (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:333-347`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:468-485`).

Exact issue: A taxable production decision can pass with only an after-tax declaration and a lower-bound net edge spec. There is no evaluator that requires actual after-tax lower-bound net edge evidence, no check for a mandate hard cap below live use, and no path that emits `after_tax_edge_missing_for_taxable_account`.

Evidence from code, diff, tests, or validation output: `_MANDATE_BLOCKER_CODES` lists `after_tax_edge_missing_for_taxable_account` (`src/tradingx/promotion.py:175-183`), but `_append_mandate_blockers` only appends missing artifacts, tax-account unspecified, jurisdiction unknown, external-capital unknown, and missing simple-equity instrument package (`src/tradingx/promotion.py:1164-1191`). `_tax_account_financing_unspecified` returns false when the mandate says `tax_modeled=True`, `pre_tax_or_after_tax="after_tax"`, taxable status is non-empty, and tax assumptions are non-empty (`src/tradingx/promotion.py:1284-1303`). Local adversarial probe: `all_wave2_artifacts_but_no_edge_evidence production []`.

Why it matters: The system can authorize taxable production based on a declared method, not evidence that the after-tax lower bound is above the threshold. That is a direct lower-bound expected-wealth failure and can produce live capital allocation from a point-estimate or no-estimate claim.

Required fix: Add a required evidence artifact for lower-bound net edge results, including after-tax status for taxable accounts, benchmark pairing, costs, slippage, financing, capacity stress, estimator, confidence/posterior level, and threshold result. If taxable live/probe/production is requested and that artifact is missing or pre-tax only, emit `after_tax_edge_missing_for_taxable_account` unless the mandate itself hard-caps below live use.

Required test or validation to prove the fix: Add tests where a taxable production request has all Wave 2 mandate artifacts but lacks after-tax lower-bound evidence; it must cap at `paper_trading` with `after_tax_edge_missing_for_taxable_account`. Add separate passing, failing, pre-tax-only, and hard-capped mandate fixtures.

## Finding W2-R3

Severity: high

Affected file or component: `src/tradingx/promotion.py`, `schemas/quant/benchmark_policy.schema.json`, `schemas/quant/jurisdiction_account_use_manifest.schema.json`, `schemas/quant/instrument_support_package.schema.json`, `schemas/quant/strategy_capital_role.schema.json`

Roadmap requirement involved: Benchmarks must be ex-ante and mandate-compatible (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:309`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:480`). The jurisdiction/account-use manifest includes a live-trading ceiling (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:311`). Instrument packages include a promotion ceiling (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:313`). Capital roles include `research_only` and `inactive` (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:315`).

Exact issue: Mandate artifact semantics are not enforced. A benchmark policy with `ex_ante: false`, a `strategy_capital_role` of `inactive`, a jurisdiction `live_trading_ceiling` below production, or an instrument `promotion_ceiling` below production still satisfies the presence checks and allows a `production` decision.

Evidence from code, diff, tests, or validation output: The schemas model `ex_ante`, `live_trading_ceiling`, `promotion_ceiling`, and `capital_role` as fields (`schemas/quant/benchmark_policy.schema.json:18-40`, `schemas/quant/jurisdiction_account_use_manifest.schema.json:17-60`, `schemas/quant/instrument_support_package.schema.json:17-54`, `schemas/quant/strategy_capital_role.schema.json:30-39`), but `_append_mandate_blockers` never reads those semantic fields (`src/tradingx/promotion.py:1147-1191`). Local adversarial probe output: `inactive_role production []`, `hindsight_benchmark production []`, `policy_ceilings_lower_than_request production []`.

Why it matters: The system can grant capital-bearing authority to an explicitly inactive strategy, use a hindsight benchmark, or exceed a declared jurisdiction/instrument ceiling. This defeats mandate compatibility and creates hidden coupling between arbitrary JSON strings and production authority.

Required fix: Add semantic evaluators for mandate artifacts. `capital_role=research_only` should cap at `research_only`, `inactive` should cap at `disabled` or equivalent explicit inactive cap, `ex_ante` must be true for capital-bearing promotion, and jurisdiction/instrument ceilings must be parsed as promotion states and folded into strictest-cap logic.

Required test or validation to prove the fix: Add tests for inactive role, research-only role, `ex_ante: false`, non-investable/incompatible benchmarks, `live_trading_ceiling: paper_trading`, and `promotion_ceiling: research_only`; each must produce the expected blocker and strictest cap.

## Finding W2-R4

Severity: high

Affected file or component: `src/tradingx/promotion.py`, portfolio allocation governance, `schemas/quant/capital_allocation_policy.schema.json`

Roadmap requirement involved: `capital_allocation_policy` defines initial allocation, max strategy/sleeve allocation, scale-up/down rules, cooldowns, and repeated-look controls (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:319`). Scale-up requires lower-bound edge, capacity, costs, drawdown/CDaR, and cooldown support (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:432-439`). Wave 2 write scope includes `src/tradingx/portfolio/blueprint.py` and `src/tradingx/portfolio/construction.py` (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2315-2320`).

Exact issue: The allocation policy is only presence-checked. The decision evaluator does not compare requested `target_weights` or proposed allocation against `initial_allocation`, `max_strategy_allocation`, `max_sleeve_allocation`, cooldown, reserve policy, or churn controls. The portfolio write-scope files were not changed.

Evidence from code, diff, tests, or validation output: `_evaluate_verified_decision_blockers` reads `target_weights` only to detect negative weights (`src/tradingx/promotion.py:1114-1127`). `_append_mandate_blockers` checks only whether `capital_allocation_policy` exists (`src/tradingx/promotion.py:1164-1170`). The schema has allocation fields (`schemas/quant/capital_allocation_policy.schema.json:18-50`), but there is no evaluator for them. The diff stat shows changes only to `promotion.py`, `__main__.py`, `reporting.py`, and tests, not `portfolio/blueprint.py` or `portfolio/construction.py`. Local adversarial probe: `allocation_exceeds_policy production []` with `target_weights={"SPY":"1"}` and `max_strategy_allocation="0.05"`.

Why it matters: A strategy can be authorized for 100% target exposure while the mandate says the max strategy allocation is 5%. That is a concrete risk-budget and capital-allocation breach.

Required fix: Parse allocation policy decimals and compare them with the requested/proposed allocation in the promotion decision or a capital-scaling decision artifact. Enforce max strategy/sleeve allocation, initial allocation, reserve policy, cooldown, and churn controls through strictest-cap blockers. Wire the same policy into portfolio construction or blueprint validation so runtime allocation cannot exceed authority.

Required test or validation to prove the fix: Add tests where target weights exceed max strategy allocation, exceed sleeve allocation, violate initial allocation, violate cooldown, and violate reserve policy. Add an integration test showing portfolio construction refuses or clamps only through an auditable blocker-backed authority decision, not silent normalization.

## Finding W2-R5

Severity: high

Affected file or component: `schemas/quant/lower_bound_net_edge_spec.schema.json`, `src/tradingx/promotion.py`

Roadmap requirement involved: `lower_bound_net_edge_spec` must predeclare a valid estimator, confidence/posterior level, horizon, benchmark pairing, serial-dependence correction, skew/fat-tail treatment, minimum effective sample size, Bayesian prior/sensitivity when applicable, stress inputs, and pass/fail threshold (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:323-344`). Missing or undefined lower-bound net edge caps at `research_only` (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:109-110`).

Exact issue: The lower-bound net edge spec schema accepts mathematically invalid and statistically unusable values, and the evaluator does not validate semantics. A confidence level of `2`, negative effective sample size, no stress inputs, no serial-dependence correction, and no fat-tail treatment still satisfy Wave 2 authority.

Evidence from code, diff, tests, or validation output: The schema uses unconstrained strings/integers for confidence, sample size, correction, stress inputs, and treatment (`schemas/quant/lower_bound_net_edge_spec.schema.json:17-48`). The repository's validator supports types, enums, const, arrays, and formats but no numeric ranges or minItems. `_append_mandate_blockers` only checks that `lower_bound_net_edge_spec` exists (`src/tradingx/promotion.py:1164-1170`). Local adversarial probe: `invalid_lower_bound_spec_math production []`.

Why it matters: A malformed lower-bound spec can be treated as a valid predeclared economic-edge method. That makes later statistical validation non-replayable and permits invalid confidence/posterior claims.

Required fix: Add semantic validation for lower-bound specs: confidence/posterior in `(0, 1)`, positive minimum effective sample size, required benchmark pairing, required cost/tax/financing/capacity stress inputs, valid HAC/block-bootstrap or equivalent serial-dependence correction, explicit skew and fat-tail handling, and Bayesian prior plus sensitivity policy when Bayesian.

Required test or validation to prove the fix: Add schema/evaluator tests for confidence `0`, `1`, `2`, negative sample sizes, empty stress inputs, missing tax stress for taxable accounts, missing benchmark pairing, `serial_dependence_correction=none`, `fat_tail_treatment=none`, and Bayesian specs without prior sensitivity; each invalid case must emit `lower_bound_net_edge_undefined` or a stricter blocker.

## Finding W2-R6

Severity: medium

Affected file or component: `tests/fixtures/mandate/`, Wave 2 review package

Roadmap requirement involved: Wave 2 write scope includes `tests/fixtures/mandate/` (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2315-2330`). Test placeholders must live under explicit fixture roots and use test-only signer identities (`docs/roadmap/tradingx_quant_hardening_execution_plan.md:2340-2344`). Review packages must be reconstructable from fixtures, artifacts, and command output.

Exact issue: `tests/fixtures/mandate/` contains only README marker files, not signed mandate bundles or retained CAS/ledger artifacts. The only Wave 2 "valid" artifacts are generated in Python helper functions with fake metadata and temporary directories.

Evidence from code, diff, tests, or validation output: `find tests/fixtures/mandate -maxdepth 2 -type f` shows only `valid/README.md`, `external_capital_unknown/README.md`, and `materiality_policy_missing/README.md`, each containing a one-line marker. The implementation report lists only those README files under fixtures (`docs/reports/wave2_mandate_allocation_implementation_report.md:30-32`). `_wave2_mandate_artifacts` in `tests/unit/test_promotion.py:261-487` builds all Wave 2 payloads in-memory.

Why it matters: Reviewers cannot replay a signed Wave 2 mandate positive path or fail-closed path from retained fixtures. This also allowed the fake `payload_hash` and missing approval/replay refs in W2-R1 to become the positive path.

Required fix: Add real fixture bundles under `tests/fixtures/mandate/valid`, `external_capital_unknown`, `materiality_policy_missing`, and adversarial cases. Each should include manifest, trust root, ledger records, CAS payloads, retained replay inputs, approvals, and mandate artifacts with verifiable refs.

Required test or validation to prove the fix: Add fixture-driven tests that run `promotion-check --artifact-root tests/fixtures/mandate/<case>` and assert exact output. The schema validation test should load retained fixture payloads, not only in-memory helper payloads.
