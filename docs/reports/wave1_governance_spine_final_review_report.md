# Finding W1-R3-001

Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, `tests/fixtures/promotion/paper_shadow_placeholder`, `tests/fixtures/promotion/valid`, `config/strategy/promotion/trend-following-v1`

Roadmap requirement involved: Milestone 1 core rule at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:508-521`; schema semantics at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:552-558`; CLI acceptance criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:637-641`; Wave 1 design tasks 8 and 14 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2235-2248`; exit criterion at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2298-2299`.

Exact issue: A `paper_shadow`-eligible decision can be produced from a bundle that contains only a key/WORM policy, a state-action contract, a retained replay stub, and an approval. The evaluator does not recompute blockers from the capability manifest, promotion evidence artifacts, placeholder mandate, benchmark, wealth thesis, utility, allocation, tax/account, jurisdiction/account-use, or instrument-package artifacts required by the roadmap. Instead, absence of those classes is non-blocking unless the signed `promotion_decision.payload.blocker_codes` list happens to include a blocker.

Evidence from code/diff/tests/validation output: `_evaluate_verified_decision_blockers` only checks for `ledger_key_management_policy`, a state-action contract, missing replay payloads, negative weights without `short_capability_package`, and then copies explicit `blocker_codes` from the decision payload at `src/tradingx/promotion.py:731-774`. The `paper_shadow_placeholder` ledger payload has `"blocker_codes":[]` and `"max_state":"paper_shadow"` at `tests/fixtures/promotion/paper_shadow_placeholder/ledger/records.jsonl:1`. Its CAS artifacts are only a retained replay input, `ledger_key_management_policy`, approval, and `state_action_contract` at `tests/fixtures/promotion/paper_shadow_placeholder/cas/*`; there is no capability manifest, promotion evidence, utility, mandate, benchmark, allocation, tax/account, jurisdiction/account-use, or instrument-package artifact. The same minimal artifact set is used by `tests/fixtures/promotion/valid`. Running `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tradingx promotion-check --strategy-id trend-following-v1 --artifact-root tests/fixtures/promotion/paper_shadow_placeholder` returned `max_state: "paper_shadow"` with `blocker_codes: []`. The focused Wave 1 suite still passed: `65 passed in 3.99s`.

Why it matters: This preserves the original mutable/ledger-payload suppression failure in a signed form. A ledger record can omit blockers and become `paper_shadow` without the artifacts the roadmap explicitly says must exist before `paper_shadow` eligibility. That defeats artifact-derived blocker recomputation and overstates the evidence actually present.

Required fix: Promotion evaluation must require and semantically validate the required first-slice evidence classes before allowing `paper_shadow`: capability manifest, promotion evidence, placeholder mandate/benchmark/wealth-thesis/utility/allocation/tax/account/jurisdiction/instrument-package artifacts, retained replay inputs, key policy, approval, and state-action contract. Missing artifacts must deterministically emit the relevant blocker codes, independent of the decision payload's `blocker_codes` field.

Required test or validation to prove the fix: Add negative fixtures where the ledger payload omits `utility_definition_missing`, `instrument_package_missing`, and mandate-related blockers while the corresponding artifacts are absent; `promotion-check` must still return `research_only` or lower with recomputed blockers. Add a positive `paper_shadow` fixture containing signed placeholder mandate, benchmark, wealth-thesis, utility, allocation, tax/account, jurisdiction/account-use, and instrument-package artifacts and prove the decision is reproduced from those artifacts alone.

# Finding W1-R3-002

Severity: blocker

Affected file or component: `config/strategy/promotion/trend-following-v1`, `src/tradingx/authority.py`, runtime promotion providers using `config/strategy/promotion`

Roadmap requirement involved: invariant 18 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2106-2108`; signature/trust-root task at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2222-2227`; enforcement and acceptance criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:611-643`.

Exact issue: Fixture signatures are accepted from the default non-test promotion config root. The default `config/strategy/promotion/trend-following-v1/trust_root.json` sets `"fixture_root": true`, and the approval CAS payload uses a `fixture:` signature. `verify_approval_signature` rejects fixture signatures only when `trust_root.fixture_root` is false; it does not enforce that fixture roots are confined to `tests/fixtures` or another explicit test-only root.

Evidence from code/diff/tests/validation output: `verify_approval_signature` accepts `fixture:` signatures whenever `trust_root.fixture_root` is true at `src/tradingx/authority.py:717-724`. The default config trust root sets `"fixture_root": true` at `config/strategy/promotion/trend-following-v1/trust_root.json:2`, and its approval artifact uses `signature_ref:"fixture:operator-key:promotion_decision:..."` at `config/strategy/promotion/trend-following-v1/cas/e2/e27bfeb0ae307e537664a5cf8c80ce04ee256b553bb732082b1e62e0a9a64731.json:1`. Runtime builders wire `build_artifact_promotion_decision_provider(Path("config/strategy/promotion"))` into activation paths, so this is not isolated to `tests/fixtures`. Running the default CLI command returned a ledger-derived decision from that fixture-signed config bundle instead of rejecting the signature: `max_state: "research_only"`, blockers `["utility_definition_missing", "instrument_package_missing"]`.

Why it matters: The roadmap's invariant is path-sensitive: placeholder or fixture signatures must never be authority outside test roots. Allowing any checked-in config bundle to self-declare `fixture_root: true` makes test HMAC signatures authority-bearing and creates a direct path for fixture-signed records to satisfy runtime/CLI authority checks if their blocker set is loosened.

Required fix: Separate fixture/test trust roots from runtime/default promotion roots. `fixture_root: true` must be rejected unless the caller explicitly opts into a test fixture context rooted under `tests/fixtures` or an equivalent non-runtime test harness. Default `config/strategy/promotion` artifacts must use non-fixture signatures or be classified as non-authority diagnostic samples.

Required test or validation to prove the fix: Add tests proving `promotion-check --strategy-id trend-following-v1` and `build_artifact_promotion_decision_provider(Path("config/strategy/promotion"))` reject `fixture:` signatures outside `tests/fixtures` with `authority_artifact_invalid`. Keep a separate positive fixture test proving fixture signatures are accepted only when the root is explicitly test-scoped.

# Finding W1-R3-003

Severity: high

Affected file or component: blocker registry and coverage validation in `src/tradingx/promotion.py`, `tests/unit/test_blocker_registry.py`, default CLI/config blocker outputs

Roadmap requirement involved: blocker registry requirements at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:1995-2028`; formal invariant 17 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2103-2105`; Wave 1 design task 1 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2195-2200`; exit criterion at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2302-2304`.

Exact issue: The coverage matrix still treats emitted Wave 1 blockers as covered when every enforcement field is `not_runtime_applicable`. This leaves W1-R2-001 unresolved for actual emitted blockers such as `utility_definition_missing`, `instrument_package_missing`, and `state_action_contract_missing`.

Evidence from code/diff/tests/validation output: `_record` defaults `fixture`, `evaluator`, `red_test`, `cli_output`, `web_report_field`, and `runtime_enforcement` to `not_runtime_applicable` at `src/tradingx/promotion.py:105-134`; only seven codes are patched with real fixture/test/evaluator references at `src/tradingx/promotion.py:239-270`. The default `trend-following-v1` config emits `utility_definition_missing` and `instrument_package_missing` in `config/strategy/promotion/trend-following-v1/ledger/records.jsonl:1`, but their registry rows have `owning_wave='legacy_inventory'` and every coverage endpoint set to `not_runtime_applicable`. `state_action_contract_missing` is emitted by `_evaluate_verified_decision_blockers` at `src/tradingx/promotion.py:744-745` and tested at `tests/unit/test_promotion.py:90-96`, but its registry row is also all `not_runtime_applicable`. Running `validate_blocker_registry_coverage()` printed `coverage accepted`, and the focused test `test_coverage_matrix_has_schema_to_runtime_trace_for_each_blocker` passes because it checks truthiness, so the literal `not_runtime_applicable` string satisfies the assertion.

Why it matters: A blocker can appear in CLI/config/runtime output without a real evaluator, red test, fixture, CLI/report mapping, or runtime enforcement mapping. The registry therefore remains a partially synthetic inventory, not the generated schema-to-runtime coverage matrix required before promotion decisions can be trusted.

Required fix: For every emitted blocker code, require real coverage references unless runtime non-applicability is narrowly justified for the runtime field only. `not_runtime_applicable` must not satisfy evaluator, red-test, fixture, schema/artifact source, or CLI/report coverage for emitted blockers. Add real mappings for `utility_definition_missing`, `instrument_package_missing`, `state_action_contract_missing`, and every blocker emitted by fixtures, config bundles, CLI output, web/report payloads, and runtime refusal messages.

Required test or validation to prove the fix: Add registry validation tests that fail when an emitted blocker has `not_runtime_applicable` for evaluator, red test, fixture, or CLI/report output. Add a fixture using `utility_definition_missing` and `instrument_package_missing` and prove coverage validation fails until those blockers have real evaluator, fixture, red-test, CLI/report, and enforcement mappings.

# Finding W1-R3-004

Severity: high

Affected file or component: `schemas/quant/state_action_contract.schema.json`, `src/tradingx/promotion.py`, `src/tradingx/activation.py`, `src/tradingx/execution.py`

Roadmap requirement involved: state-action contract definition at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:552-554`; enforcement rule at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:615`; invariant 5 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2079-2080`; Wave 1 design task 9 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2235-2236`.

Exact issue: The state-action contract is schema-valid with no required runtime semantics beyond an opaque `contracts` object, and runtime enforcement validates only `order_permission`. Required fields named by the roadmap, including data/broker access, capital ceiling, short permissions, required runtime controls, route constraints, and disallowed actions, are neither modeled nor enforced.

Evidence from code/diff/tests/validation output: `schemas/quant/state_action_contract.schema.json:6-10` requires only `schema_version`, `kind`, and `contracts`; `contracts` has no required properties or nested schema. `validate_state_action_contracts` checks only `contract.get("order_permission", "none")` against a small allowed set at `src/tradingx/promotion.py:891-909`. Activation falls back to `DEFAULT_STATE_ACTION_CONTRACTS` when no contract is injected at `src/tradingx/activation.py:291-305`, and order-route guards do the same at `src/tradingx/execution.py:100-135`. The canonical checked-in state-action contract artifact contains only `order_permission` entries at `tests/fixtures/promotion/paper_shadow_placeholder/cas/c5/c5f1da3e7a33c424dc5faecb38252fa3c647ac7d721ec45562fe32942eeeb705.json:1`. The positive test `test_state_action_contracts_load_from_validated_artifact` loads a contract with only `paper_shadow.order_permission` and no data access, broker access, capital ceiling, short permission, controls, constraints, or disallowed actions at `tests/unit/test_promotion.py:146-165`.

Why it matters: Wave 1 claims the canonical state-action contract gates activation, runtime planning, and order-route selection, but the contract cannot express most of the boundary it is supposed to enforce. Runtime code can therefore permit behavior without checking capital ceilings, broker/data access, short permissions, required controls, or disallowed actions against the canonical artifact.

Required fix: Expand the state-action contract schema and validator to require the roadmap fields for each promotion state. Runtime activation, planner, and order-route guards must consume the validated canonical contract derived from the promotion artifact bundle, not an unrelated default, and must reject actions outside data/broker/order/capital/short/control/route/disallowed-action constraints.

Required test or validation to prove the fix: Add schema and integration tests where contracts missing capital ceiling, broker/data access, short permissions, route constraints, required controls, or disallowed actions fail closed. Add runtime tests proving an otherwise sufficient promotion decision is refused when the canonical contract disallows the requested activation or order route, even if the hard-coded defaults would allow it.

# Finding W1-R3-005

Severity: medium

Affected file or component: `AuthorityLedger.read_verified_records` in `src/tradingx/authority.py`, approval verification tests in `tests/unit/test_authority.py`

Roadmap requirement involved: approval-record fields at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:575-585`; invariant 8 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2085-2086`; signature/trust-root task at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2222-2227`.

Exact issue: The ledger's verified-read path accepts approval records without `signed_at_utc`, even though the approval schema and roadmap require a signed timestamp. This leaves the ledger verification API weaker than the promotion-path schema validation.

Evidence from code/diff/tests/validation output: `AuthorityLedger._verify_approval_payload` manually checks `schema_version`, `kind`, `payload_hash`, `scope`, `risk_accepted`, `operator_identity_ref`, `role_registry_ref`, `authority_boundary_ref`, and `expires_at_utc` at `src/tradingx/authority.py:419-465`, but it does not call `validate_quant_artifact(... approval_record ...)` and does not require `signed_at_utc`. The positive verified-ledger test builds an approval payload without `signed_at_utc` at `tests/unit/test_authority.py:394-410`, then `read_verified_records` accepts it at `tests/unit/test_authority.py:420-427`. The focused Wave 1 suite still passed: `65 passed in 3.99s`.

Why it matters: Approval timestamp semantics are part of the authority boundary. A verified ledger read can currently treat an approval as valid even when it could not pass the checked-in approval schema, so callers using the ledger API directly can accept authority records that the promotion path would reject.

Required fix: Make `AuthorityLedger.read_verified_records` validate approval payloads with `schemas/quant/approval_record.schema.json` before manual semantic checks. Enforce `signed_at_utc` presence, canonical UTC format, signed-at within trust-root/key validity, signed-at not after expiry, and signed-at not in the future relative to verification time unless explicitly modeled.

Required test or validation to prove the fix: Change the positive verified-ledger approval fixture to include `signed_at_utc`. Add negative verified-ledger tests for missing `signed_at_utc`, non-UTC signed timestamp, signed-at after expiry, signed-at outside key validity, and signed-at in the future; each must fail before a ledger record is treated as verified.
