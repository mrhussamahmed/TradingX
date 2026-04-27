# Finding W1-R1-001
Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, `src/tradingx/__main__.py`, `tests/fixtures/promotion/*`

Roadmap requirement involved: Milestone 1 core rule and enforcement at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:508-520`; acceptance criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:641-643`; Wave 1 design tasks 5, 6, 12, and 14 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2215-2248`; exit criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2298-2299`.

Exact issue: `promotion-check` and `evaluate_promotion_manifest` derive authority from a mutable fixture `manifest.json`, not from append-only ledger records plus retained content-addressed artifacts and signed approvals. The evaluator copies `max_state`, `artifact_refs`, `ledger_sequence`, and `ledger_hash` from the manifest and never opens an authority ledger, dereferences the content-addressed artifact refs, validates the manifest schema, verifies approval signatures, or verifies key/WORM policy artifacts.

Evidence from code/diff/tests/validation output: `evaluate_promotion_manifest` reads only `root / "manifest.json"` at `src/tradingx/promotion.py:281-289`, computes blockers from booleans and explicit `blocker_codes` at `src/tradingx/promotion.py:296-313`, and accepts the manifest-provided state at `src/tradingx/promotion.py:314-319`. It then copies `artifact_refs`, `ledger_sequence`, and `ledger_hash` directly from the same mutable payload at `src/tradingx/promotion.py:325-335`. Repository search shows `AuthorityLedger`, `validate_quant_artifact`, and `verify_approval_signature` are not used by production promotion code; they are only defined in `src/tradingx/authority.py` and exercised by tests. The `paper_shadow_placeholder` fixture contains fake refs and hashes at `tests/fixtures/promotion/paper_shadow_placeholder/manifest.json:11-13`, and the fixture directory contains only `manifest.json` and `input.json`, not the referenced CAS payload. Running `.venv/bin/tradingx promotion-check --strategy-id trend-following-v1 --artifact-root tests/fixtures/promotion/paper_shadow_placeholder` returned `max_state: "paper_shadow"` with no blockers despite those fake refs. The Wave 1 targeted suite still passed: `33 passed in 7.04s`.

Why it matters: This violates the trust-spine source-of-truth rule. A hand-authored or tampered manifest can claim a promotion state and ledger hash without proving the referenced evidence exists, is replayable, is signed, or is ledger-derived. That creates a direct mutable-file authority path.

Required fix: Rework promotion evaluation so the manifest is only an input pointer or fixture inventory, not authority. The decision must be derived by loading and validating content-addressed artifacts, reading/verifying the append-only ledger chain, checking replay refs exist, validating approval records, verifying signatures against an explicit trust root, enforcing key/WORM policy, and then computing blockers from those verified artifacts.

Required test or validation to prove the fix: Add golden tests where a manifest with fake `artifact_refs`, fake `ledger_hash`, missing CAS payloads, missing approval payloads, and missing replay payloads cannot produce `paper_shadow` or higher. Add a positive artifact-only fixture whose `promotion-check` output is reproduced from the ledger and CAS payloads with no trust in mutable config or fixture fields.

# Finding W1-R1-002
Severity: blocker

Affected file or component: `src/tradingx/promotion.py`, `src/tradingx/activation.py`

Roadmap requirement involved: Projection files are generated readability projections only at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:510` and `docs/roadmap/tradingx_quant_hardening_execution_plan.md:588-604`; local projection edits cannot increase authority at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:640-642`; formal invariants 1 and 12 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2075-2094`.

Exact issue: `load_promotion_decision` treats the mutable projection file itself as a promotion decision. It reads `promotion_state`, `max_state`, blockers, artifact refs, ledger sequence, and ledger hash from `config/strategy/promotion/<strategy_id>.json` without verifying the ledger or the projection's source decision. `check_projection_drift` only checks `source_decision_hash` when the field exists, so a projection with no source hash is not drift by default.

Evidence from code/diff/tests/validation output: `load_promotion_decision` reads the projection file at `src/tradingx/promotion.py:339-351` and returns `max_state` from `payload.get("max_state", payload["promotion_state"])` at `src/tradingx/promotion.py:363-365`. `check_projection_drift` returns non-drift when no file exists at `src/tradingx/promotion.py:385-386` and accepts a missing `source_decision_hash` because the mismatch check is gated on `if source_hash` at `src/tradingx/promotion.py:400-407`. The only test for `load_promotion_decision` covers a missing file returning disabled at `tests/unit/test_promotion.py:122-130`; there is no test proving a hand-edited projection without a source hash cannot increase authority.

Why it matters: If any caller wires `load_promotion_decision` as the decision provider, a local config edit can set `max_state` or `promotion_state` to a higher state and make activation see that projection as authority. That is the exact projection-drift failure mode the roadmap says Wave 1 must eliminate.

Required fix: Remove projection-derived authority from `load_promotion_decision`, or make it return only a non-authoritative projection object. Promotion decisions used by activation must come from ledger/CAS replay. Projection drift must fail closed when the projection is missing required ledger/source decision refs, has no `source_decision_hash`, or disagrees with the ledger-derived decision.

Required test or validation to prove the fix: Add an integration test where `config/strategy/promotion/trend-following-v1.json` is hand-edited to `production` with no `source_decision_hash`; activation must refuse with `authority_artifact_invalid` or a projection-drift blocker. Add another test proving a projection whose hash matches a ledger-derived decision is accepted only when the ledger-derived cap permits the requested runtime state.

# Finding W1-R1-003
Severity: blocker

Affected file or component: runtime activation wiring in `src/tradingx/__main__.py`, `src/tradingx/service.py`, `src/tradingx/web/runtime.py`, `src/tradingx/automation.py`, and `src/tradingx/activation.py`

Roadmap requirement involved: Activation gateway refusal at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:608-615`; acceptance criteria at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:648`; Wave 1 design task 13 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2243-2245`.

Exact issue: Promotion enforcement is opt-in and is not wired into the default runtime activation paths. `_enforce_promotion_authority` returns immediately when no `promotion_decision_provider` or `required_promotion_state` is configured, and the main runtime/service/web builders instantiate `LocalActivationGateway` without either argument.

Evidence from code/diff/tests/validation output: The early return is at `src/tradingx/activation.py:252-257`. Default CLI runtime planning and runtime start create `LocalActivationGateway` without promotion enforcement at `src/tradingx/__main__.py:477-480` and `src/tradingx/__main__.py:555-558`. Default service construction does the same at `src/tradingx/service.py:751-755` and `src/tradingx/service.py:814-817`. The local web runtime builder does the same at `src/tradingx/web/runtime.py:977-980`, and automation does the same at `src/tradingx/automation.py:896-900`. The integration test explicitly asserts legacy default activation still succeeds without a V5 policy at `tests/integration/test_promotion_activation.py:65-75`.

Why it matters: Wave 1's activation refusal exists only in tests and manually configured call sites. The production runtime paths can still create or load legacy activations without consulting a V5 promotion decision, so the first governance slice does not actually enforce the activation boundary it claims to add.

Required fix: Wire a default promotion decision provider into runtime activation paths, derived from the ledger/CAS authority source. If legacy paper operation must continue, require an explicit legacy/non-authority activation mode and prevent it from satisfying any V5 state-action contract or order-capable authority requirement.

Required test or validation to prove the fix: Add tests around `runtime-plan`, `runtime-start`, `build_default_trading_service`, `build_runtime_host_trading_service`, and `build_default_local_web_components` showing that absent V5 authority refuses the requested runtime state with exact blocker codes. Add a separate explicit legacy-paper compatibility test that verifies the path is labeled non-authority and cannot become order-route authority.

# Finding W1-R1-004
Severity: high

Affected file or component: `src/tradingx/execution.py`, order-capable execution gateway construction sites

Roadmap requirement involved: Deny-by-default order-route guard at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2237-2240`; formal invariant 19 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2109-2111`; red test at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2290-2292`.

Exact issue: Directly constructed `AlpacaPaperExecutionGateway` instances can still submit orders because the guard runs only when `authority_guard` is configured. The test proves `assert_v5_order_authority()` raises on an unguarded gateway, but the actual submit methods do not call that method and do not deny unguarded routes by default.

Evidence from code/diff/tests/validation output: `AlpacaPaperExecutionGateway.__init__` defaults `authority_guard` to `None` at `src/tradingx/execution.py:128-137`. `submit_market_order`, `submit_marketable_limit_order`, `submit_oco_exit_order`, and `close_position` call `_assert_order_route_authority_if_configured` at `src/tradingx/execution.py:158`, `src/tradingx/execution.py:203`, `src/tradingx/execution.py:231`, and `src/tradingx/execution.py:259`; that helper only checks when a guard exists at `src/tradingx/execution.py:347-349`. The Wave 1 test for direct construction only checks the separate property/method at `tests/unit/test_execution_authority.py:50-55`; it never asserts that unguarded `submit_market_order` is denied. Existing production constructors still instantiate `AlpacaPaperExecutionGateway` without an authority guard, for example `src/tradingx/controller.py:1690` and `src/tradingx/controller.py:1721`.

Why it matters: The order-route boundary is the last place to prevent accidental or bypassed order submission. A guard that is optional and not enforced by default does not satisfy the deny-by-default requirement.

Required fix: Make order-capable submission methods deny by default unless the route has either a verified V5 authority guard or an explicit legacy-paper mode that is named and labeled as non-authority. V5-required routes must require strategy id, state-action contract, and a sufficient ledger-derived decision before submitting.

Required test or validation to prove the fix: Add tests proving direct unguarded calls to `submit_market_order`, `submit_marketable_limit_order`, `submit_oco_exit_order`, and `close_position` raise `OrderRouteAuthorityError`. Add positive tests for an explicitly labeled legacy-paper route and for a guarded V5 route with a sufficient promotion decision.

# Finding W1-R1-005
Severity: high

Affected file or component: blocker registry and coverage matrix in `src/tradingx/promotion.py`, `schemas/quant/blocker_registry.schema.json`, `tests/unit/test_blocker_registry.py`

Roadmap requirement involved: Blocker registry requirements at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:1995-2028`; generated coverage matrix at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2013-2018`; Wave 1 design task 1 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2195-2200`; formal invariant 17 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2103-2105`.

Exact issue: The coverage matrix is not actually generated from code, docs, fixtures, tests, CLI output, web output, and runtime enforcement points. `_record` fabricates evaluator names, fixture paths, test names, CLI output paths, and runtime enforcement strings from each blocker code, and the tests only assert those fields are non-empty. Required fields such as owning wave are missing from the dataclass/schema, and the referenced fixtures/evaluators/runtime enforcement points do not have to exist.

Evidence from code/diff/tests/validation output: `BlockerRegistryRecord` lacks an `owning_wave` field at `src/tradingx/promotion.py:46-58`. `_record` synthesizes `schema_field`, `evaluator`, `red_test`, `fixture`, `cli_output`, and `runtime_enforcement` strings at `src/tradingx/promotion.py:77-82`. The schema requires only a subset of the roadmap fields at `schemas/quant/blocker_registry.schema.json:20-30` and omits `owning_wave`, `schema_field`, and `cli_output`. The coverage test only checks truthiness at `tests/unit/test_blocker_registry.py:41-54`. The actual fixture tree contains directories such as `valid/`, `legacy/`, and `unsupported_short_side/`, not the generated paths like `tests/fixtures/promotion/capacity_extrapolation_risk.json`.

Why it matters: A non-empty string matrix can pass CI while blockers have no real evaluator, no real fixture, no real red test, and no real runtime/report enforcement. That defeats the roadmap's purpose of making blocker codes authority data rather than ad hoc strings.

Required fix: Store the canonical registry as validated data with every roadmap-required field, including owning wave. Generate coverage by scanning blocker emissions in docs, schemas, fixtures, tests, CLI expected output, web/report payloads, and runtime refusal output. Validate that referenced evaluators, fixtures, tests, CLI/report fields, and runtime enforcement points actually exist, or explicitly mark `not_runtime_applicable`.

Required test or validation to prove the fix: Add a coverage test that fails when a blocker appears in any scanned source but is absent from the registry, when a registry row references a missing fixture/evaluator/test, or when required fields such as owning wave, schema/artifact source, CLI/report field, and runtime enforcement mapping are missing.

# Finding W1-R1-006
Severity: high

Affected file or component: `src/tradingx/authority.py`, ledger and approval verification

Roadmap requirement involved: Ledger verification requirements at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2215-2221`; signature/trust-root requirements at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2222-2227`; formal invariants 2, 3, 8, and 18 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2075-2108`.

Exact issue: `AuthorityLedger` verifies that artifact, approval, and replay refs are non-empty, but it does not verify that referenced CAS payloads exist, that replay payloads are retained, that approval records exist, or that approval signatures are scoped/current/trusted. `verify_approval_signature` is isolated test helper behavior and is not integrated into ledger append/read or promotion evaluation.

Evidence from code/diff/tests/validation output: Ledger append checks only non-empty refs at `src/tradingx/authority.py:353-358`. Ledger read checks only non-empty loaded lists at `src/tradingx/authority.py:447-459`. There is no `FileContentAddressedStore` or trust-root dependency in `AuthorityLedger.__init__` at `src/tradingx/authority.py:276-280`. Repository search shows `verify_approval_signature` is not called outside `tests/unit/test_authority.py`. The CLI accepted `tests/fixtures/promotion/valid/manifest.json` as `paper_shadow` even though its `artifact_refs` and `ledger_hash` are placeholder hash strings and no corresponding CAS payload is present.

Why it matters: A ledger record with ceremonial refs can be treated as structurally valid even when the evidence, replay input, or approval payload is missing or unsigned. This is a core authority failure: hashes and refs are insufficient unless the retained payloads and signatures are verified.

Required fix: Give ledger verification access to the artifact store and trust roots, require content-addressed refs to resolve to retained payloads, validate approval record schemas, verify approval signatures and scope/expiry/revocation, verify replay refs, and make missing payloads fail closed.

Required test or validation to prove the fix: Add tests where ledger read/append fails on a missing artifact payload, missing replay payload, malformed approval ref, expired approval, revoked key, wrong-scope signature, wrong trust root, and fixture signature outside fixture roots. Add an integration test proving promotion evaluation cannot use a ledger record until those checks pass.

# Finding W1-R1-007
Severity: high

Affected file or component: canonical serialization and schema format validation in `src/tradingx/authority.py`, tests in `tests/unit/test_authority.py`

Roadmap requirement involved: Canonical JSON serialization requirement at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2206-2208`; formal invariant 13 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2095-2096`.

Exact issue: Decimal and timestamp normalization are incomplete for authority-bearing JSON artifacts. `Decimal("1.2300")` is serialized as `"1.2300"` rather than a normalized decimal representation, and timestamp strings are not normalized at all. JSON artifact producers using `"1.23"` versus `"1.2300"` or `"2026-04-26T12:00:00Z"` versus `"2026-04-26T12:00:00+00:00"` will produce different hashes even when they represent the same value.

Evidence from code/diff/tests/validation output: `_normalize_for_json` serializes `Decimal` with `str(value)` at `src/tradingx/authority.py:41-45` and only normalizes `datetime` objects, not schema-typed timestamp strings. The canonical JSON dumper does not receive schema context at `src/tradingx/authority.py:58-64`. The test explicitly asserts the non-normalized decimal output `"amount":"1.2300"` at `tests/unit/test_authority.py:23-47`. The `decimal-string` validator accepts any `Decimal(value)` parse and does not enforce or produce a canonical decimal string at `src/tradingx/authority.py:235-245`.

Why it matters: Content addressing and replay depend on stable canonical hashes across producers and platforms. Formatting-equivalent decimals or UTC timestamps can fork artifact hashes, break replay, and create false material changes.

Required fix: Introduce schema-aware canonicalization for decimal-string and utc-datetime fields, or require and validate a single canonical textual representation before hashing. Normalize `Decimal` values and decimal strings consistently, and normalize UTC timestamps to one representation such as `Z`.

Required test or validation to prove the fix: Add tests proving `Decimal("1.2300")`, `Decimal("1.23")`, and JSON decimal strings representing the same value either hash identically or reject noncanonical forms. Add tests proving UTC-equivalent timestamp strings hash identically or reject noncanonical forms.

# Finding W1-R1-008
Severity: high

Affected file or component: web and report surfaces in `src/tradingx/web/readmodels.py`, `src/tradingx/web/app.py`, `src/tradingx/web/runtime.py`, `src/tradingx/reporting.py`

Roadmap requirement involved: Web non-authority labeling at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2249-2252`; red test at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2293-2294`; formal invariant 16 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2101-2102`.

Exact issue: The implementation adds `v5_authority_status: legacy_non_authority` only under `document_summary`, while gate statuses, validation recommendations, gate report actions, Gate 3 promotion packages, and decision/reporting text can still present pass/promote/advance language without an adjacent V5 non-authority label.

Evidence from code/diff/tests/validation output: `LocalWebReadModel.build_dashboard_snapshot` preserves legacy `gate_statuses` and `recommendations` at `src/tradingx/web/readmodels.py:196-207` and adds the non-authority label only to `document_summary` at `src/tradingx/web/readmodels.py:208-214`. The test asserts `gate_statuses["1"] == "pass"` and `recommendations["promote_candidate"] == 1` alongside only the document label at `tests/unit/test_web_readmodels.py:200-209`. `/api/actions/gate-report` returns the action result from `generate_gate_report` without adding a V5 authority label at `src/tradingx/web/app.py:1193-1207`; the action result says `Generated Gate {gate} report` at `src/tradingx/web/runtime.py:548-554`. `build_gate_decision_brief` still says a passing gate should be reviewed to decide whether to advance beyond the gate at `src/tradingx/reporting.py:30-35`.

Why it matters: Operator/web surfaces remain able to imply promotion or advancement from legacy gate artifacts. The label is too narrow to satisfy the roadmap requirement that existing gate, validation, and promotion-like read models show legacy or exploratory status without implying V5 approval.

Required fix: Add authority status/classification to every gate, validation, recommendation, decision brief, promotion package, and gate-report action response. Rename or wrap legacy recommendations so `promote_candidate` cannot be interpreted as V5 authority without a ledger-derived promotion decision.

Required test or validation to prove the fix: Add contract tests for dashboard, evidence list endpoints, `/api/actions/gate-report`, decision report, and Gate 3 package endpoints proving legacy outputs include `legacy_non_authority` or `exploratory` classification and do not present old gate artifacts as V5 promotion approval.

# Finding W1-R1-009
Severity: high

Affected file or component: `schemas/quant/`, `config/strategy/`, state-action/capability artifact model

Roadmap requirement involved: Milestone 1 schema list at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:540-556`; Wave 1 write scope at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2167-2170`; Wave 1 design tasks 2, 7, and 9 at `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2201-2236`.

Exact issue: Most required authority-bearing schemas and artifacts are absent. The repository has only `blocker_registry.schema.json`, `promotion_manifest.schema.json`, and `trust_root.schema.json`; it lacks the roadmap-listed schemas for strategy capability manifests, promotion evidence, promotion decisions, promotion decision ledger records, content-addressed artifacts, approval records, operator identities, ledger key-management policy, and state-action contracts. There are also no `config/strategy/capabilities/` or `config/strategy/promotion/` artifacts in the current tree.

Evidence from code/diff/tests/validation output: `schemas/quant/` contains only three files in the current worktree. `config/strategy` contains only the `weights/` directory and no capability or promotion directories. `validate_state_action_contracts` accepts an in-memory mapping at `src/tradingx/promotion.py:410-429`; there is no schema-backed loader or fixture for a canonical `state_action_contract` artifact. The targeted Wave 1 tests passed despite these missing schemas and artifacts.

Why it matters: Without these schemas and fixture artifacts, Wave 1 cannot validate strategy capabilities, evidence classification, promotion decision payloads, ledger records, approval identity/scope, key/WORM policy, or canonical state-action contracts. That leaves major roadmap requirements unimplemented and allows tests to pass against ad hoc in-memory structures.

Required fix: Add the missing quant schemas and canonical fixture artifacts, wire them into `validate_quant_artifact` or a real JSON Schema validator, and load state-action and capability contracts from validated artifacts rather than arbitrary mappings.

Required test or validation to prove the fix: Add schema tests for each required artifact type covering required fields, unknown fields, enums, refs, schema-version drift, and unsupported keywords. Add integration fixtures proving promotion evaluation fails closed when any required capability, approval, key policy, promotion decision, ledger record, or state-action contract artifact is missing or malformed.
