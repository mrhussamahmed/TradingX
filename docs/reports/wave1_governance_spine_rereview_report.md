# Finding W1-R2-001

Severity: blocker

Affected file or component: blocker registry and coverage matrix in `src/tradingx/promotion.py`, `schemas/quant/blocker_registry.schema.json`, `tests/unit/test_blocker_registry.py`

Roadmap requirement involved: blocker registry requirements and generated matrix at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:1995-2028`; invariant 17 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2103-2105`; Wave 1 design task 1 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2195-2200`; exit criterion at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2302-2304`.

Exact issue: The blocker coverage matrix is still synthetic, not generated from actual schema/evaluator/test/fixture/CLI/web/runtime/report outputs. This leaves W1-R1-005 only partially fixed: rows can claim evaluator, red-test, CLI, and runtime coverage even when those objects do not exist.

Evidence from code/diff/tests/validation output: `_record` fabricates `schema_field`, `evaluator`, `red_test`, `cli_output`, and `runtime_enforcement` from the blocker string at `src/tradingx/promotion.py:86-100`. Only seven codes get real fixture paths at `src/tradingx/promotion.py:206-220`; the rest use `fixture="not_runtime_applicable"` by default at `src/tradingx/promotion.py:83-85`. `validate_blocker_registry_coverage` checks only non-empty fields and fixture existence when the fixture is not `not_runtime_applicable` at `src/tradingx/promotion.py:235-258`; it does not verify that evaluator functions, red tests, CLI output fields, web/report fields, or runtime refusal points exist. `_discover_blocker_codes` scans only `src`, `tests`, `schemas`, and `docs/reports`, omitting the roadmap and config artifacts, and only detects `Blocker("...")` and literal `blocker_codes` arrays at `src/tradingx/promotion.py:279-310`. `schemas/quant/blocker_registry.schema.json:20-30` still does not require `schema_field` or `cli_output` even though the roadmap requires both. `tests/unit/test_blocker_registry.py:43-57` asserts truthiness only. `rg` finds no real `evaluate_capacity_extrapolation_risk` or `test_capacity_extrapolation_risk`, despite the registry claiming those names.

Why it matters: The governance spine can present unimplemented blocker coverage as complete. A missing runtime refusal, missing CLI field, or missing web/report mapping would not fail CI, directly violating the authority-data rule for blocker codes.

Required fix: Replace the fabricated rows with canonical registry data and a real generated coverage check. The check must scan roadmap/docs, schemas, fixtures, tests, CLI expected output, web/report payloads, and runtime refusal paths; it must verify referenced evaluator functions, red tests, fixtures, CLI/report fields, and runtime mappings exist or are explicitly and narrowly marked `not_runtime_applicable`.

Required test or validation to prove the fix: Add failing tests for a registry row with a missing evaluator, missing red test, missing CLI field, missing web/report field, and missing runtime refusal point. Add a fixture where a blocker appears in the roadmap or web/report payloads but not the registry, and prove coverage validation fails.

# Finding W1-R2-002

Severity: blocker

Affected file or component: quant schemas, promotion fixtures, `src/tradingx/promotion.py`, `src/tradingx/authority.py`

Roadmap requirement involved: Milestone 1 core rule at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:508-520`; schema list at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:540-550`; implementation doctrine at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:1978-1987`; schema validation task at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2228-2234`; golden fixture task at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2246-2248`; acceptance criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:641-645`.

Exact issue: Authority-bearing schemas exist, but they are not enforced on the authority path and several checked-in authority fixtures do not conform to the checked-in schemas. This leaves W1-R1-001, W1-R1-006, and W1-R1-009 only partially fixed: the evaluator resolves CAS refs and signatures, but it still accepts unversioned or schema-incompatible authority payloads.

Evidence from code/diff/tests/validation output: `_evaluate_authority_bundle` reads the manifest, trust root, ledger, artifact payloads, replay refs, and approval refs at `src/tradingx/promotion.py:403-433` without calling `validate_quant_artifact` for the manifest, trust root, ledger record, promotion decision, content-addressed artifact, approval record, strategy capability manifest, promotion evidence, or state-action contract. `_evaluate_verified_decision_blockers` only checks for a CAS payload with `kind="ledger_key_management_policy"` and a truthy `worm_controls`, replay existence, negative weights, and explicit `blocker_codes` at `src/tradingx/promotion.py:535-568`. `schemas/quant/promotion_manifest.schema.json:6-12` requires `ledger_key_management_policy`, `replay_inputs`, and `target_weights`, but the current fixture manifests contain only pointer fields such as `artifact_store_root`, `ledger_root`, and `trust_root_path` at `tests/fixtures/promotion/paper_shadow_placeholder/manifest.json:1-8`. Running the checked-in validator against `paper_shadow_placeholder`, `valid`, and `key_policy_missing` manifests failed with `SchemaValidationError: missing required field ledger_key_management_policy`. The trust-root schema requires `schema_version` at `schemas/quant/trust_root.schema.json:6-13`, but fixture trust roots omit it at `tests/fixtures/promotion/paper_shadow_placeholder/trust_root.json:1-15` and are accepted because they are not schema-validated. The ledger-record schema requires `previous_hash` as a string at `schemas/quant/promotion_decision_ledger_record.schema.json:6-16`, while the first ledger records use `"previous_hash": null` at `tests/fixtures/promotion/paper_shadow_placeholder/ledger/records.jsonl:1`. The focused Wave 1 suite still passed: `57 passed in 6.73s`.

Why it matters: Closed-world schema validation is the barrier between retained authority artifacts and hand-shaped JSON. If fixtures and schemas disagree, later migrations and replay validation cannot prove what was actually authorized. Unversioned or malformed trust roots and policy artifacts can still carry authority.

Required fix: Align schemas with the actual authority-bundle shape or update fixtures to the intended schemas, then validate every authority-bearing payload before it can affect a promotion decision. The positive `paper_shadow` fixture must include schema-valid promotion evidence, strategy capability, approval, trust-root, key policy, replay, ledger, and state-action artifacts.

Required test or validation to prove the fix: Add a fixture-wide validation test that loads every `tests/fixtures/promotion/**` manifest, trust root, ledger record, CAS payload, approval record, and replay artifact through the relevant schema. Add mutation tests proving unknown fields, missing `schema_version`, invalid enum/state, incompatible initial ledger hash semantics, and malformed approval/trust-root payloads fail closed in `promotion-check`.

# Finding W1-R2-003

Severity: blocker

Affected file or component: state-action contract enforcement in `src/tradingx/promotion.py`, `src/tradingx/activation.py`, `src/tradingx/execution.py`, runtime activation builders

Roadmap requirement involved: state-action contract definition at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:552-554`; enforcement rule at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:615`; invariant 5 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2079-2080`; Wave 1 design task 9 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2235-2236`; red test at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2270-2271`.

Exact issue: State-action contracts are implemented only as a standalone loader/validator and are not enforced before activation, runtime planning, or order-route selection.

Evidence from code/diff/tests/validation output: Repository search shows `load_state_action_contracts` and `validate_state_action_contracts` are only defined in `src/tradingx/promotion.py:612-635` and `src/tradingx/promotion.py:673-691` and are only called by `tests/unit/test_promotion.py:163-195`. `LocalActivationGateway.__init__` accepts promotion-decision and projection inputs but no state-action contract input at `src/tradingx/activation.py:44-64`. `_enforce_promotion_authority` checks only provider presence, projection drift, and `decision.max_state` versus the required state at `src/tradingx/activation.py:254-280`. `OrderRouteAuthorityGuard.assert_authorized` checks only strategy id and promotion state at `src/tradingx/execution.py:106-116`; the gateway then trusts that guard at `src/tradingx/execution.py:349-357`.

Why it matters: A ledger-derived promotion state can be sufficient for activation or an order route even when the canonical state-action contract is absent, too permissive, or mismatched. That violates the roadmap’s explicit ordering that state-action contracts gate activation, runtime planning, and order routes.

Required fix: Make a validated state-action contract an authority input to promotion decisions and runtime guards. Activation, runtime planning, and order-route selection must check the requested action against the contract and emit `state_action_contract_missing` or a more specific blocker before use.

Required test or validation to prove the fix: Add integration tests where a ledger-derived `paper_trading` decision is otherwise sufficient but the state-action contract is missing, malformed, or grants paper orders in `paper_shadow`; activation and every order-capable route must refuse with `state_action_contract_missing`. Add a positive test where a schema-valid contract permits the requested action and the route proceeds only when the promotion state is also sufficient.

# Finding W1-R2-004

Severity: high

Affected file or component: approval schema and signature verification in `schemas/quant/approval_record.schema.json`, `src/tradingx/authority.py`, `src/tradingx/promotion.py`

Roadmap requirement involved: approval-record fields at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:575-585`; key-management and approval rule at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:586`; invariants 8 and 18 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2085-2108`; Wave 1 signature task at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2222-2227`.

Exact issue: Approval verification does not bind the signer scope to the requested authority action and does not enforce approval expiry or most roadmap-required approval fields.

Evidence from code/diff/tests/validation output: `schemas/quant/approval_record.schema.json:6-13` requires only `schema_version`, `kind`, `payload_hash`, `scope`, and `signature_ref`; it does not require operator identity, role registry version, authority boundary ref, approval scope structure, risk accepted, expiry, canonical payload hash metadata, or signature timestamp semantics listed in the roadmap. Promotion verification passes `required_scope=str(approval_payload.get("scope", ""))` to the signature verifier at `src/tradingx/promotion.py:519-524`; ledger verified reads do the same at `src/tradingx/authority.py:433-441`. `verify_approval_signature` only checks that the provided `required_scope` equals the scope embedded in the signature and is in the key’s trust-root scopes at `src/tradingx/authority.py:707-708`. It checks trust-root validity bounds at `src/tradingx/authority.py:709-715`, but there is no approval-record expiry field or expiry check. Tests exercise low-level scope mismatch by passing a different `required_scope` directly at `tests/unit/test_authority.py:495-502`, but no full promotion-evaluation test proves an approval with the wrong action scope or expired approval record is rejected.

Why it matters: The approval record’s own `scope` value becomes self-authorizing. A key trusted for some non-promotion scope could approve a promotion decision if the approval and signature both use that non-promotion scope. Separately, approval records do not expire, so stale reviewer intent can continue to authorize decisions.

Required fix: Make approval records schema-complete and action-bound. Promotion evaluation must require the approval scope to cover the actual action being authorized, such as `promotion_decision` for promotion records and the appropriate route contract for runtime actions, independent of the approval payload’s self-declared scope. Enforce approval expiry, identity, role registry, authority boundary, risk acceptance, revocation, and rotation rules.

Required test or validation to prove the fix: Add full `evaluate_promotion_manifest` fixtures for wrong-scope approval, expired approval, missing expiry, missing operator identity, missing authority boundary, revoked key, rotated key, and wrong trust root. Each must fail closed before producing `paper_shadow` or higher.

# Finding W1-R2-005

Severity: high

Affected file or component: `promotion-check` CLI in `src/tradingx/__main__.py`, default promotion artifact/config layout

Roadmap requirement involved: CLI contract at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:629-635`; acceptance criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:639-641`; red test at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2286-2287`; exit criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2298-2299`.

Exact issue: The default CLI acceptance path is not implemented, and the CLI can report a promotable decision for the wrong requested strategy.

Evidence from code/diff/tests/validation output: Running `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tradingx promotion-check --strategy-id trend-following-v1` returned `strategy_id: "unknown"`, `max_state: "disabled"`, and `blocker_codes: ["authority_artifact_invalid"]`, not the required reproducible `research_only` decision with exact mandate/utility blockers. The only checked-in files under `config/strategy/capabilities` and `config/strategy/promotion` are `.gitkeep` placeholders. In the CLI handler, `evaluate_promotion_manifest(Path(args.artifact_root))` is called without tying the artifact root to the requested strategy at `src/tradingx/__main__.py:377-379`; if the evaluated payload strategy differs from `args.strategy_id`, the code only adds `requested_strategy_id` at `src/tradingx/__main__.py:380-384` and still returns success at `src/tradingx/__main__.py:385-389`. Running `promotion-check --strategy-id mean-reversion-v1 --artifact-root tests/fixtures/promotion/paper_shadow_placeholder` returned exit code 0 with `strategy_id: "trend-following-v1"` and `max_state: "paper_shadow"`.

Why it matters: Operators and CI can ask for one strategy and receive a successful promotion report for another. The primary roadmap acceptance command also does not produce the required blocked research-only decision, so Wave 1 cannot prove the real default strategy path from artifacts alone.

Required fix: Make `promotion-check` fail closed on strategy-id mismatch and return a non-authoritative blocked result for the requested strategy. Add or wire the default artifact bundle needed for `promotion-check --strategy-id trend-following-v1` to produce the roadmap-required exact blockers without `--artifact-root`.

Required test or validation to prove the fix: Add CLI tests for the default command, wrong-strategy artifact root, missing artifact root, and per-strategy artifact root. The wrong-strategy case must exit nonzero or return `authority_artifact_invalid` for the requested strategy; it must not surface another strategy’s `paper_shadow` decision as successful output.

# Finding W1-R2-006

Severity: medium

Affected file or component: activation and order-route refusal messages in `src/tradingx/activation.py`, `src/tradingx/execution.py`

Roadmap requirement involved: activation refusal acceptance criterion at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:648`; invariant 14 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2097-2098`; Wave 1 activation task at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2243-2245`.

Exact issue: Runtime refusal messages do not expose the exact blocker codes or artifact refs when a promotion decision is below the required state.

Evidence from code/diff/tests/validation output: `LocalActivationGateway._enforce_promotion_authority` raises only `"promotion capped at <state>; requested <state>"` when state is insufficient at `src/tradingx/activation.py:276-280`; it discards `decision.blocker_codes` and `decision.artifact_refs`. `OrderRouteAuthorityGuard.assert_authorized` similarly raises only route label, strategy id, cap, and required state at `src/tradingx/execution.py:111-116`. `tests/integration/test_promotion_activation.py:30-31` asserts only the capped-state text, not exact blocker codes or artifact refs.

Why it matters: Activation refusal is supposed to be an operator-facing enforcement surface. Without blocker codes and non-secret artifact refs, the refusal is not reproducible or actionable and does not satisfy the CLI/runtime observability invariant.

Required fix: Include blocker codes and safe artifact refs in activation and order-route refusal payloads/messages. The message must avoid leaking signing material, but it should identify the blocker list and retained evidence refs used to make the refusal.

Required test or validation to prove the fix: Add activation and order-route tests where the provider returns blockers and artifact refs; assert the refusal includes all blocker codes and safe refs. Add a regression case proving secrets or signature material are not included.

# Finding W1-R2-007

Severity: medium

Affected file or component: web/read-model and Gate 3 legacy non-authority labeling in `src/tradingx/web/readmodels.py`, `src/tradingx/gate3.py`, `tests/unit/test_web_readmodels.py`

Roadmap requirement involved: one-way authority surface rule at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2064-2068`; invariant 16 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2101-2102`; Wave 1 design task 15 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2249-2252`; red test at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2293-2294`.

Exact issue: Legacy gate statuses and recommendations can still be consumed as raw promotion-like values without an adjacent authority classification, and the Gate 3 readiness report still tells operators to decide whether to advance without labeling that action as non-authority.

Evidence from code/diff/tests/validation output: `LocalWebReadModel.build_dashboard_snapshot` returns raw `gate_statuses` and `recommendations` at `src/tradingx/web/readmodels.py:197-208`, while the `legacy_non_authority` labels are placed separately inside `document_summary` at `src/tradingx/web/readmodels.py:209-217`. The test asserts `snapshot.gate_statuses["1"] == "pass"` and `snapshot.recommendations["promote_candidate"] == 1` alongside the separate document labels at `tests/unit/test_web_readmodels.py:204-215`. `src/tradingx/gate3.py:139-144` still returns `"Review the Gate 3 package and decide whether to advance."` for passing Gate 3 readiness reports; that field is used in reports at `src/tradingx/gate3.py:805` and `src/tradingx/gate3.py:983`.

Why it matters: UI/API consumers can read `pass`, `promote_candidate`, or `decide whether to advance` without carrying the separate non-authority label. That preserves a path for legacy validation and gate artifacts to imply promotion authority outside the V5 ledger decision.

Required fix: Attach `legacy_non_authority` or `exploratory` classification directly to each gate status, recommendation, and Gate 3 operator-action field, or rename the legacy fields so they cannot be interpreted as V5 promotion authority. Keep the separate document summary label, but do not rely on it as the only classification.

Required test or validation to prove the fix: Add contract tests for dashboard/read-model payloads and Gate 3 readiness reports proving every legacy gate status, recommendation, and advance/promotion-like message carries an adjacent non-authority classification and no raw `promote_candidate` value is exposed without that classification.
