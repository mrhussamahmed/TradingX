# Wave 1 Round 1 Fix Report - Governance Spine First Slice

Review report fixed:

- `docs/reports/wave1_governance_spine_review_report.md`

Findings fixed:

- `W1-R1-001`: `promotion-check` no longer trusts mutable manifest state, fake refs, or manifest ledger claims. Manifests locate an authority bundle only. `evaluate_promotion_manifest` now derives decisions from append-only ledger records, retained content-addressed artifacts, retained replay refs, approval refs, signature verification, and explicit trust roots. Promotion fixtures were regenerated as ledger/CAS/trust-root bundles.
- `W1-R1-002`: `load_promotion_decision` no longer reads mutable projection files as authority. Projection drift now fails closed when a projection exists without `source_decision_hash`, when the projection state exceeds the ledger-derived cap, or when the source decision hash mismatches.
- `W1-R1-003`: runtime activation paths in CLI runtime plan/start, service builders, web runtime components, and automation now pass a default artifact-backed promotion decision provider, `paper_trading` required state, and projection root. `LocalActivationGateway` refuses by default when V5 promotion authority is not configured; legacy behavior requires `legacy_non_authority_mode=True`.
- `W1-R1-004`: `AlpacaPaperExecutionGateway` order submission now denies by default unless a V5 guard authorizes the route or the gateway is explicitly labeled `legacy_paper_non_authority`. Existing legacy production constructors were labeled explicitly.
- `W1-R1-005`: blocker registry records now include owning wave, real fixture mappings for Wave 1 blocker fixtures, fixture existence checks, and source scanning for discovered blocker codes. Coverage rows expose `owning_wave`.
- `W1-R1-006`: `AuthorityLedger` now exposes verified read behavior that resolves artifact refs, replay refs, approval payload refs, and verifies approval signatures against trust roots. Promotion evaluation uses the same retained evidence concepts and fails closed on missing/malformed approval or artifact evidence.
- `W1-R1-007`: canonical serialization now normalizes `Decimal` objects and UTC-equivalent timestamp strings. The decimal-string schema format rejects noncanonical textual decimals.
- `W1-R1-008`: web/report surfaces now label legacy gate/read-model/recommendation/Gate 3 surfaces with `legacy_non_authority`; Gate 3 action messages and reporting actions no longer present legacy gate artifacts as V5 promotion approval.
- `W1-R1-009`: added first-slice quant schemas for strategy capability manifests, promotion evidence, promotion decisions, ledger records, content-addressed artifacts, approval records, operator identities, ledger key policy, and state-action contracts. Added `config/strategy/capabilities/` and `config/strategy/promotion/` placeholders.

Files changed for fixes:

- `src/tradingx/authority.py`
- `src/tradingx/promotion.py`
- `src/tradingx/activation.py`
- `src/tradingx/__main__.py`
- `src/tradingx/service.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/automation.py`
- `src/tradingx/execution.py`
- `src/tradingx/controller.py`
- `src/tradingx/supervisor.py`
- `src/tradingx/web/readmodels.py`
- `src/tradingx/reporting.py`
- `src/tradingx/gate3.py`
- `schemas/quant/*.schema.json`
- `config/strategy/capabilities/.gitkeep`
- `config/strategy/promotion/.gitkeep`
- `tests/fixtures/promotion/`
- Wave 1 authority, promotion, blocker registry, execution, activation, service, CLI, web, reporting, Gate 3, and fallback tests.

Tests added or updated:

- Added tests proving mutable manifest claims with fake refs cannot grant authority.
- Added tests proving projection files without source decision hashes are drift.
- Added tests proving `load_promotion_decision` ignores projection-file authority claims.
- Added tests proving all unguarded order-submission methods deny by default.
- Added tests proving explicit legacy paper routes can submit but are not V5 authority.
- Added tests proving guarded routes with sufficient promotion state can submit.
- Added tests proving default activation without V5 authority refuses and explicit legacy activation is labeled.
- Added tests proving runtime-plan/runtime-start/service/web constructors wire promotion enforcement.
- Added tests proving blocker registry fixture mappings and source scanning work.
- Added tests proving schema samples validate for required Wave 1 quant artifact schemas.
- Added tests proving verified ledger reads resolve artifact, replay, and approval refs and reject placeholder signatures.
- Added tests proving web/report/Gate 3 surfaces expose legacy non-authority status.

Validation commands run:

- `uv run pytest tests/unit/test_authority.py tests/unit/test_blocker_registry.py tests/unit/test_promotion.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/unit/test_portfolio_live_construction.py tests/integration/test_promotion_activation.py tests/unit/test_main.py::test_promotion_check_reports_blockers_from_fixture_artifacts tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_web_readmodels.py::test_local_web_read_model_builds_dashboard_from_artifacts_and_docs`
- `uv run pytest tests/unit/test_authority.py tests/unit/test_blocker_registry.py tests/unit/test_promotion.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/integration/test_promotion_activation.py tests/unit/test_main.py tests/unit/test_service.py tests/unit/test_web_runtime.py tests/unit/test_web_readmodels.py tests/unit/test_gate3.py tests/unit/test_reporting.py tests/integration/test_fallback_drill.py tests/unit/test_drift_artifact_regeneration.py`
- `uv run ruff check .`
- `uv run mypy src/tradingx`
- `uv run pytest tests/unit tests/integration`

Validation results:

- Focused Wave 1 suite: 56 passed.
- Affected regression group: 152 passed.
- Ruff: all checks passed.
- Mypy: success, no issues in 110 source files.
- Full unit and integration suite: 922 passed, 98 skipped, 2 warnings in 302.38 seconds.

Unresolved risks:

- The verified authority bundle is still local filesystem based for Wave 1. Later waves must deepen production custody, external WORM controls, and live-probe token semantics.
- Fixture trust roots intentionally use deterministic fixture signatures; production roots reject fixture signatures when `fixture_root` is false.

